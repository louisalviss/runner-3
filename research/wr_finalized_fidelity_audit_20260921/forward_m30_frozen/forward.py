#!/usr/bin/env python3
from __future__ import annotations
import csv, io, json, math, os, re, sys, time, zipfile, hashlib
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta, timezone, date
from pathlib import Path
from zoneinfo import ZoneInfo
import requests

BASE=Path('/opt/wr-m30-forward')
DATA=BASE/'data'; CACHE=BASE/'cache'; LOGS=BASE/'logs'
CFG=json.loads((BASE/'config.json').read_text())
sys.path.insert(0,str(BASE))
import reference_verify as ref

VN=ZoneInfo(CFG['timezone_for_T'])
UTC=timezone.utc
TF=int(CFG['timeframe_minutes']); TFMS=TF*60_000
START=datetime.fromisoformat(CFG['forward_start_utc'].replace('Z','+00:00'))
START_MS=int(START.timestamp()*1000)
WARMUP_START=(START-timedelta(days=35)).date()
SYMS=CFG['symbols']
TICKS={k:float(v) for k,v in CFG['tick_size'].items()}
TP_R=2.3
BLS_ICS='https://www.bls.gov/schedule/news_release/bls.ics'
FED_URL='https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm'
DBX_BASE='/stragety/wave-rider-recheck/forward'

@dataclass
class Pos:
    d:int; e:float; s:float; t:float; sig_i:int; sig_t:int; sig_h:float; sig_l:float
    entry_t:int|None=None

def iso(ms:int|None):
    return None if ms is None else datetime.fromtimestamp(ms/1000,tz=UTC).isoformat().replace('+00:00','Z')

def day_iter(a:date,b:date):
    d=a
    while d<=b:
        yield d; d+=timedelta(days=1)

def http_get(url, timeout=35):
    s=requests.Session(); s.headers['User-Agent']='wr-m30-forward/1.0 (+shadow-validation)'
    for k in range(3):
        try:
            r=s.get(url,timeout=timeout)
            return r
        except Exception:
            if k==2: raise
            time.sleep(1+k)

def refresh_calendar():
    now=datetime.now(UTC)
    t0=[]; sources={}
    # BLS ICS: CPI and Employment Situation, release date remains same calendar date in VN.
    r=http_get(BLS_ICS); r.raise_for_status(); txt=r.text
    sources['bls_ics_sha256']=hashlib.sha256(r.content).hexdigest()
    for block in txt.split('BEGIN:VEVENT')[1:]:
        sm=re.search(r'^SUMMARY:(.*)$',block,re.M)
        dm=re.search(r'^DTSTART(?:;[^:]*)?:(\d{8})',block,re.M)
        if not sm or not dm: continue
        summary=sm.group(1).strip()
        if summary not in {'Consumer Price Index','Employment Situation'}: continue
        d=datetime.strptime(dm.group(1),'%Y%m%d').date()
        if d>=WARMUP_START:
            t0.append({'date':d.isoformat(),'type':'CPI' if summary=='Consumer Price Index' else 'NFP','source':'BLS'})
    # FOMC official calendars. Meeting statement is normally 14:00 ET, therefore VN T0 is meeting-end date +1 day.
    r=http_get(FED_URL); r.raise_for_status(); html=r.text
    sources['fed_html_sha256']=hashlib.sha256(r.content).hexdigest()
    stripped=re.sub(r'<script.*?</script>',' ',html,flags=re.S|re.I)
    stripped=re.sub(r'<style.*?</style>',' ',stripped,flags=re.S|re.I)
    stripped=re.sub(r'<[^>]+>','\n',stripped)
    import html as _html
    lines=[re.sub(r'\s+',' ',_html.unescape(z)).strip() for z in stripped.splitlines()]
    lines=[z for z in lines if z]
    months={m:i for i,m in enumerate(['January','February','March','April','May','June','July','August','September','October','November','December'],1)}
    for year in (2026,2027):
        hdr=f'{year} FOMC Meetings'
        try: i=lines.index(hdr)
        except ValueError: continue
        month=None
        for z in lines[i+1:i+80]:
            if z.endswith('FOMC Meetings') and z!=hdr: break
            if z in months: month=months[z]; continue
            m=re.fullmatch(r'(\d{1,2})-(\d{1,2})\*?',z)
            if m and month:
                end_day=int(m.group(2))
                end=date(year,month,end_day)
                vn_t0=end+timedelta(days=1)
                if vn_t0>=WARMUP_START:
                    t0.append({'date':vn_t0.isoformat(),'type':'FOMC','source':'Federal Reserve'})
    # dedupe exact type/date
    uniq={(x['date'],x['type']):x for x in t0}
    out={'generated_utc':now.isoformat(),'t0':sorted(uniq.values(),key=lambda x:(x['date'],x['type'])),'sources':sources,
         'bls_url':BLS_ICS,'fed_url':FED_URL,'fomc_vn_rule':'official meeting end date +1 VN calendar day (14:00 ET statement crosses midnight in VN)'}
    (DATA/'calendar.json').write_text(json.dumps(out,indent=2))
    return out

def labels_for(vnd:date,cal):
    labs=[]
    for e in cal['t0']:
        d0=date.fromisoformat(e['date']); off=(vnd-d0).days
        mp={-2:'T-2',-1:'T-1',0:'T0',1:'T+1',2:'T+2',3:'T+3'}
        if off in mp: labs.append(mp[off])
    return sorted(set(labs))

def classify(ms:int,cal):
    vd=datetime.fromtimestamp(ms/1000,tz=UTC).astimezone(VN).date()
    if vd.weekday()>=5: return 'OFF_WEEKEND',[]
    labs=labels_for(vd,cal)
    excl=set(CFG['day_rule']['exclude_if_any_label'])
    if excl.intersection(labs): return 'OFF_EVENT_OVERLAP',labs
    if 'T-1' in labs and 'T+1' in labs: return 'T-1+T+1',labs
    if 'T-1' in labs: return 'T-1',labs
    if 'T+1' in labs: return 'T+1',labs
    return 'NORMAL',labs

def admitted(ms:int,cal):
    c,l=classify(ms,cal)
    return c in {'NORMAL','T-1','T+1','T-1+T+1'},c,l

def fetch_daily(sym:str,d:date):
    sd=d.isoformat(); folder=CACHE/sym; folder.mkdir(parents=True,exist_ok=True)
    p=folder/f'{sd}.zip'
    if p.exists() and p.stat().st_size>100: return p
    url=f'https://data.binance.vision/data/futures/um/daily/klines/{sym}/1m/{sym}-1m-{sd}.zip'
    r=http_get(url)
    if r.status_code==404: return None
    r.raise_for_status(); tmp=p.with_suffix('.tmp'); tmp.write_bytes(r.content); tmp.replace(p); return p

def latest_common_day():
    # Only closed UTC days. Probe backwards until every symbol has that day.
    d=datetime.now(UTC).date()-timedelta(days=1)
    for _ in range(8):
        ok=True
        for s in SYMS:
            if fetch_daily(s,d) is None: ok=False
        if ok: return d
        d-=timedelta(days=1)
    raise RuntimeError('no common Binance Vision daily archive in last 8 closed UTC days')

def load_1m(sym:str,end_day:date):
    bars=[]; missing=[]
    for d in day_iter(WARMUP_START,end_day):
        p=fetch_daily(sym,d)
        if p is None:
            missing.append(d.isoformat()); continue
        try:
            with zipfile.ZipFile(p) as z: text=z.read(z.namelist()[0]).decode()
        except Exception:
            p.unlink(missing_ok=True); missing.append(d.isoformat()); continue
        for row in csv.reader(io.StringIO(text)):
            if not row or not row[0].isdigit(): continue
            bars.append(ref.Bar(int(row[0]),int(row[6]),*map(float,row[1:5])))
    ded={x.ot:x for x in bars}; return [ded[k] for k in sorted(ded)],missing

def agg(src,m=30):
    ms=m*60000; out=[]; key=None; g=[]
    def emit(g):
        if len(g)!=m:return None
        if any(g[j+1].ot-g[j].ot!=60000 for j in range(len(g)-1)):return None
        return ref.Bar(g[0].ot,g[-1].ct,g[0].o,max(x.h for x in g),min(x.l for x in g),g[-1].c)
    for x in src:
        k=x.ot//ms
        if key is None:key=k
        if k!=key:
            y=emit(g)
            if y:out.append(y)
            g=[];key=k
        g.append(x)
    y=emit(g)
    if y:out.append(y)
    return out

def run_symbol(sym,bars,tick,cal):
    ind,_,_=ref.calc_ind(bars)
    pending=None; active=None; trades=[]; diag={'signals':0,'admitted_signals':0,'fills':0,'expired':0,'blocked_day':0,'tp':0,'sl':0,'ema':0,'session':0}
    def close(i,reason,px):
        nonlocal active
        b=bars[i]; p=active
        both=b.h>=max(p.s,p.t) and b.l<=min(p.s,p.t) and reason in ('TP','SL')
        if both: reason='AMBIG->SL'
        rr=TP_R if reason=='TP' else (-1.0 if reason in ('SL','AMBIG->SL') else ((px-p.e)*(1 if p.d==1 else -1)/abs(p.e-p.s)))
        tc,labs=classify(p.sig_t,cal)
        if p.sig_t>=START_MS:
            trades.append({'symbol':sym,'tf':TF,'signal_ms':p.sig_t,'signal_iso':iso(p.sig_t),'entry_ms':p.entry_t,'entry_iso':iso(p.entry_t),'exit_ms':b.ct,'exit_iso':iso(b.ct),
                'side':'LONG' if p.d==1 else 'SHORT','tclass':tc,'tlabels':'+'.join(labs),'entry':p.e,'stop':p.s,'target':p.t,'exit_price':px,'exit_reason':reason,'R':rr,'ambiguous':both})
        active=None
    for i,b in enumerate(bars):
        closed=False
        if active is not None:
            r,px=ref.next_bracket(active,b,None)
            if r:
                diag['tp' if r=='TP' else 'sl']+=1; close(i,r,px); closed=True
        if active is None and pending is not None and not closed:
            if i==pending.sig_i+1:
                fill=(pending.d==1 and b.h>=pending.e) or (pending.d==-1 and b.l<=pending.e)
                if fill:
                    active=pending; pending=None; active.entry_t=b.ot; diag['fills']+=1
                    gap=(active.d==1 and b.o>=active.e) or (active.d==-1 and b.o<=active.e)
                    r,px=ref.next_bracket(active,b,None if gap else active.e)
                    if r:
                        diag['tp' if r=='TP' else 'sl']+=1; close(i,r,px); closed=True
                else: diag['expired']+=1
        allowed_session,sexit=ref.session_flags(b.ct,TFMS)
        if active is not None and not closed:
            z=ind[i]
            le=active.d==1 and b.c<z['ema'] and not z['ha'] and not z['ema_up']
            se=active.d==-1 and b.c>z['ema'] and not z['hb'] and bool(z['ema_up'])
            if sexit: diag['session']+=1; close(i,'SESSION',b.c); closed=True
            elif le or se: diag['ema']+=1; close(i,'EMA',b.c); closed=True
        if pending is not None and active is None and i>=pending.sig_i+1: pending=None
        if b.ct<START_MS: continue
        if active is None and pending is None and not closed:
            z=ind[i]
            lr=z['ha'] and b.c>z['ema'] and z['ag'] and z['chop_ok'] and z['res'] is not None
            sr=z['hb'] and b.c<z['ema'] and z['ar'] and z['chop_ok'] and z['sup'] is not None
            nl=allowed_session and z['sra_ok'] and b.c>b.o and lr and b.c>z['res'] and b.l<=z['res']
            ns=allowed_session and z['sra_ok'] and b.c<b.o and sr and b.c<z['sup'] and b.h>=z['sup']
            if nl or ns:
                diag['signals']+=1
                ok,tc,labs=admitted(b.ct,cal)
                if not ok:
                    diag['blocked_day']+=1; continue
                diag['admitted_signals']+=1
                if nl:
                    d=1; e=round(b.h/tick)*tick+tick; s=round(b.l/tick)*tick-tick; t=e+TP_R*(e-s)
                else:
                    d=-1; e=round(b.l/tick)*tick-tick; s=round(b.h/tick)*tick+tick; t=e-TP_R*(s-e)
                if abs(e-s)>0: pending=Pos(d,e,s,t,i,b.ct,b.h,b.l)
    open_state=None
    if active is not None:
        open_state={'type':'active','signal_iso':iso(active.sig_t),'entry_iso':iso(active.entry_t),'side':'LONG' if active.d==1 else 'SHORT','entry':active.e,'stop':active.s,'target':active.t}
    elif pending is not None:
        open_state={'type':'pending','signal_iso':iso(pending.sig_t),'side':'LONG' if pending.d==1 else 'SHORT','entry':pending.e,'stop':pending.s,'target':pending.t}
    return trades,diag,open_state

def metrics(rows):
    def m(costfn=None):
        vals=[]; cost=0.0
        for r in rows:
            g=float(r['R']); c=0.0 if costfn is None else costfn(r); vals.append(g-c); cost+=c
        gp=sum(max(x,0) for x in vals); gl=sum(max(-x,0) for x in vals)
        return {'n':len(rows),'gross_R':sum(float(r['R']) for r in rows),'cost_R':cost,'net_R':sum(vals),'net_E':sum(vals)/len(vals) if vals else None,'PF':gp/gl if gl else None}
    def eqbps(r,bps): return float(r['entry'])/abs(float(r['entry'])-float(r['stop']))*bps/10000
    def sched(r,a,b,c):
        xb=b if r['exit_reason']=='TP' else c
        return (float(r['entry'])*a+float(r['exit_price'])*xb)/abs(float(r['entry'])-float(r['stop']))/10000
    gross=m(); slope=sum(float(r['entry'])/abs(float(r['entry'])-float(r['stop']))/10000 for r in rows)
    return {'gross':gross,'break_even_equivalent_bps': gross['gross_R']/slope if slope and gross['gross_R']>0 else None,
            'bps6':m(lambda r:eqbps(r,6.0)),'fee_5_2_5':m(lambda r:sched(r,5,2,5)),'fee_4p5_1p8_4p5':m(lambda r:sched(r,4.5,1.8,4.5)),'fee_2_2_2':m(lambda r:sched(r,2,2,2))}

def write_csv(rows,path):
    fields=['symbol','tf','signal_ms','signal_iso','entry_ms','entry_iso','exit_ms','exit_iso','side','tclass','tlabels','entry','stop','target','exit_price','exit_reason','R','ambiguous']
    with path.open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields); w.writeheader(); w.writerows(sorted(rows,key=lambda r:(r['signal_ms'],r['symbol'])))

def sync_dropbox(files):
    try:
        sys.path.insert(0,'/opt/url-dropbox-bridge')
        from vps_dropbox import DropboxService
        svc=DropboxService(); svc.ensure_folder(DBX_BASE)
        for p in files:
            svc.overwrite_bytes_verified(f'{DBX_BASE}/{p.name}',p.read_bytes())
        return {'ok':True,'files':[p.name for p in files]}
    except Exception as e:
        return {'ok':False,'error':repr(e)}

def main():
    DATA.mkdir(parents=True,exist_ok=True); CACHE.mkdir(parents=True,exist_ok=True)
    cal=refresh_calendar(); common=latest_common_day()
    allrows=[]; sym_status={}
    for sym in SYMS:
        one,missing=load_1m(sym,common); bars=agg(one,TF)
        tr,diag,open_state=run_symbol(sym,bars,TICKS[sym],cal); allrows.extend(tr)
        sym_status[sym]={'bars_30m':len(bars),'closed_trades':len(tr),'diagnostics':diag,'open_state':open_state,'missing_days':missing[-10:]}
    ledger=DATA/'trades.csv'; write_csv(allrows,ledger)
    met=metrics(allrows); gate=CFG['promotion_gate']; reg=met['fee_5_2_5']
    gate_eval={'trade_count':len(allrows),'minimum_closed_trades_met':len(allrows)>=int(gate['minimum_closed_trades']),
               'net_expectancy_met': reg['net_E'] is not None and reg['net_E']>=float(gate['net_expectancy_R_min']),
               'net_pf_met': reg['PF'] is not None and reg['PF']>=float(gate['net_profit_factor_min']),
               'break_even_bps_met': met['break_even_equivalent_bps'] is not None and met['break_even_equivalent_bps']>=float(gate['break_even_equivalent_bps_min'])}
    gate_eval['promotion_ready']=all(gate_eval[k] for k in ['minimum_closed_trades_met','net_expectancy_met','net_pf_met','break_even_bps_met'])
    status={'updated_utc':datetime.now(UTC).isoformat(),'mode':CFG['mode'],'forward_start_utc':CFG['forward_start_utc'],'data_through_utc_day':common.isoformat(),
            'symbols':SYMS,'tf_minutes':TF,'calendar_t0_count':len(cal['t0']),'symbol_status':sym_status,'metrics':met,'gate':gate_eval,
            'note':'Forward shadow only. Never auto-promote; >=50 trade gate triggers review, not production.'}
    sp=DATA/'status.json'; sp.write_text(json.dumps(status,indent=2))
    rp=DATA/'STATUS.md'; rp.write_text(f"""# Wave Rider M30 frozen forward\n\n- Updated UTC: {status['updated_utc']}\n- Data through UTC day: {common.isoformat()}\n- Start UTC: {CFG['forward_start_utc']}\n- Symbols: SOL / ETH / XRP\n- TF: M30\n- Day filter: weekday NORMAL + T-1 + T+1; exclude any T0/T-2/T+2/T+3 overlap; weekends OFF\n- Mode: SHADOW ONLY / NO EXCHANGE ORDERS\n\n## Progress\n- Closed trades: {len(allrows)} / {gate['minimum_closed_trades']}\n- Gross R: {met['gross']['gross_R']:.4f}\n- Gross E: {met['gross']['net_E'] if met['gross']['net_E'] is not None else 'n/a'}\n- Break-even equivalent bps: {met['break_even_equivalent_bps'] if met['break_even_equivalent_bps'] is not None else 'n/a'}\n- 6bps net R: {met['bps6']['net_R']:.4f}\n- 5/2/5 net R: {reg['net_R']:.4f}\n- 5/2/5 net E: {reg['net_E'] if reg['net_E'] is not None else 'n/a'}\n- 5/2/5 PF: {reg['PF'] if reg['PF'] is not None else 'n/a'}\n- Promotion gate ready: {gate_eval['promotion_ready']}\n\nNo tuning is permitted on this forward lane.\n""")
    cp=BASE/'config.json'; files=[sp,rp,ledger,DATA/'calendar.json',cp]
    sync=sync_dropbox(files); status['dropbox_sync']=sync; sp.write_text(json.dumps(status,indent=2))
    if sync.get('ok'):
        # push final status including sync outcome
        try:
            sys.path.insert(0,'/opt/url-dropbox-bridge'); from vps_dropbox import DropboxService
            DropboxService().overwrite_bytes_verified(f'{DBX_BASE}/status.json',sp.read_bytes())
        except Exception: pass
    print(json.dumps({'closed_trades':len(allrows),'data_through':common.isoformat(),'metrics':met,'gate':gate_eval,'dropbox_sync':sync},indent=2))

if __name__=='__main__': main()
