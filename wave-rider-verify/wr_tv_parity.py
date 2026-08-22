#!/usr/bin/env python3
from __future__ import annotations
import json, math, os, random, re, string, sys, time, types
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone, date
from pathlib import Path
from zoneinfo import ZoneInfo
import websocket

# Manual TradingView oracle supplied from WR 2.5.13 WINDOW REPORT, 5m.
# Window is VN time 2026-07-12 00:00 -> 2026-08-01 00:00 exclusive.
START = datetime(2026,7,11,17,0,tzinfo=timezone.utc)
END   = datetime(2026,7,31,17,0,tzinfo=timezone.utc)
ORACLES = {
    'OANDA:EURUSD':  (15, -5.10),
    'OANDA:USDJPY':  (8,  -4.70),
    'OANDA:XAUUSD':  (10,  0.61),
    'ICMARKETS:US500': (11, -3.21),
    'NASDAQ:AAPL':   (2,  -1.72),
}
TF='5'; TF_MS=300000
TARGET_BARS=25000
REF_URL='https://raw.githubusercontent.com/louisalviss/runner-3/8192984ad6a3e5f99b49020c79b5758ef2ac44a7/wave-rider-verify/reference_verify.py'
OUT=Path('wave-rider-verify/output/tv-parity'); OUT.mkdir(parents=True,exist_ok=True)

@dataclass
class Bar:
    ot:int; ct:int; o:float; h:float; l:float; c:float
@dataclass
class P:
    d:int; e:float; s:float; t:float; risk:float; qty:float; sig_i:int; sig_t:int; sig_h:float; sig_l:float; report:bool


def sid(prefix):
    return prefix+''.join(random.choice(string.ascii_lowercase) for _ in range(12))
def frame(m,p):
    x=json.dumps({'m':m,'p':p},separators=(',',':'))
    return f'~m~{len(x)}~m~{x}'
def unpack(raw):
    out=[]
    for s in re.findall(r'~m~\d+~m~(.*?)(?=~m~\d+~m~|$)',raw,re.S):
        if s.startswith('~h~'): out.append(('hb',s)); continue
        try: out.append(('json',json.loads(s)))
        except Exception: pass
    return out

def tv_fetch(symbol, session='regular', total=TARGET_BARS):
    cs=sid('cs_')
    ws=websocket.create_connection('wss://data.tradingview.com/socket.io/websocket?from=chart',
        origin='https://www.tradingview.com',timeout=15,enable_multithread=True)
    def send(m,p): ws.send(frame(m,p))
    send('set_auth_token',['unauthorized_user_token'])
    send('set_locale',['en','US'])
    send('chart_create_session',[cs,''])
    send('switch_timezone',[cs,'Etc/UTC'])
    cfg='='+json.dumps({'symbol':symbol,'adjustment':'splits','session':session},separators=(',',':'))
    send('resolve_symbol',[cs,'sym_1',cfg])
    send('create_series',[cs,'s1','s1','sym_1',TF,min(5000,total),''])
    rows={}; info=None; completed=0; deadline=time.time()+120
    while time.time()<deadline:
        try: raw=ws.recv()
        except Exception: break
        for kind,msg in unpack(raw):
            if kind=='hb':
                try: ws.send(frame('',[]).replace('{"m":"","p":[]}',msg))
                except Exception: pass
                continue
            m=msg.get('m'); p=msg.get('p',[])
            if m=='symbol_resolved' and p and isinstance(p[-1],dict): info=p[-1]
            if m=='timescale_update' and len(p)>1 and isinstance(p[1],dict):
                ser=p[1].get('s1') or p[1].get('sds_1')
                if isinstance(ser,dict):
                    for item in ser.get('s',[]) or []:
                        v=item.get('v') if isinstance(item,dict) else None
                        if not v or len(v)<5: continue
                        try:
                            ts=int(float(v[0])); rows[ts]=(float(v[1]),float(v[2]),float(v[3]),float(v[4]))
                        except Exception: pass
            if m=='series_completed':
                completed+=1
                if len(rows)<total and completed<8:
                    send('request_more_data',[cs,'s1',min(5000,total-len(rows))])
                else:
                    deadline=0; break
    try: ws.close()
    except Exception: pass
    if not rows: raise RuntimeError(f'{symbol} {session}: no TradingView bars')
    bars=[Bar(ts*1000,ts*1000+TF_MS,*rows[ts]) for ts in sorted(rows)]
    return bars,info or {}

def load_ref():
    # Workflow downloads the frozen verifier to /tmp/reference_verify.py.
    path='/tmp/reference_verify.py'; src=Path(path).read_text()
    mod=types.ModuleType('wrref_tv'); mod.__file__=path; sys.modules[mod.__name__]=mod
    exec(compile(src,path,'exec'),mod.__dict__); return mod

def pine_day(d:date):
    # Pine: Sunday=1, Monday=2 ... Saturday=7.
    return ((d.weekday()+1)%7)+1

def parse_hhmm(s): return int(s[:2])*60+int(s[2:])

def regular_session_string(info):
    subs=info.get('subsessions')
    if isinstance(subs,list):
        for z in subs:
            if isinstance(z,dict) and str(z.get('id','')).lower()=='regular' and z.get('session'):
                return z['session']
    return info.get('session') or '0000-0000:1234567'

class SessionClock:
    def __init__(self,info,anchor='start'):
        tzname=info.get('timezone') or info.get('exchange_timezone') or 'Etc/UTC'
        try:self.tz=ZoneInfo(tzname)
        except Exception:self.tz=timezone.utc
        self.raw=regular_session_string(info); self.anchor=anchor; self.parts=[]
        for seg in str(self.raw).split(','):
            if ':' in seg: hh,days=seg.rsplit(':',1)
            else: hh,days=seg,'1234567'
            if '-' not in hh: continue
            a,b=hh.split('-',1); self.parts.append((parse_hhmm(a),parse_hhmm(b),set(int(x) for x in days if x.isdigit())))
    def intervals(self,ms):
        dt=datetime.fromtimestamp(ms/1000,tz=timezone.utc).astimezone(self.tz); d0=dt.date()
        for delta in range(-2,3):
            d=d0+timedelta(days=delta)
            for a,b,days in self.parts:
                if self.anchor=='start':
                    if pine_day(d) not in days: continue
                    st=datetime.combine(d,datetime.min.time(),self.tz)+timedelta(minutes=a)
                    en=datetime.combine(d,datetime.min.time(),self.tz)+timedelta(minutes=b)+(timedelta(days=1) if b<=a else timedelta())
                else:
                    if pine_day(d) not in days: continue
                    en=datetime.combine(d,datetime.min.time(),self.tz)+timedelta(minutes=b)
                    st=datetime.combine(d,datetime.min.time(),self.tz)+timedelta(minutes=a)-(timedelta(days=1) if b<=a else timedelta())
                yield int(st.timestamp()*1000),int(en.timestamp()*1000)
    def state(self,bar):
        # session.ismarket is true for bars whose opening instant belongs to regular session.
        for st,en in self.intervals(bar.ot+1):
            if st <= bar.ot+1 < en: return True,en
        return False,None

def tv_tick(info,vals):
    try:
        mm=float(info.get('minmov',1)); ps=float(info.get('pricescale',1));
        if mm>0 and ps>0:return mm/ps
    except Exception:pass
    # fallback from observed precision
    return 10**(-max(0,max(len(f'{x:.10f}'.rstrip('0').split('.')[-1]) for x in vals[:1000])))

def managed_r(p,px):
    den=abs(p.e-p.s)
    return 0.0 if den<=0 else ((px-p.e)*(1 if p.d==1 else -1)/den)

def run_case(ref,bars,info,history_start,anchor='start',use_session=True):
    bars=[b for b in bars if b.ot>=int(history_start.timestamp()*1000)]
    if len(bars)<100:return [],{'error':'too_few_bars'}
    ind,_,_=ref.calc_ind(bars); tick=tv_tick(info,[x.c for x in bars]); sc=SessionClock(info,anchor)
    start_ms=int(START.timestamp()*1000); end_ms=int(END.timestamp()*1000)
    eq=100000.; pending=None; active=None; trades=[]; exit_counts={k:0 for k in ('TP','SL','EMA','SESSION','AMBIG->SL')}
    # embedded news is late-2025 only; none intersects this 2026 oracle window, but pre-window state may.
    ny=ZoneInfo('America/New_York')
    news=[datetime(2025,11,20,8,30,tzinfo=ny),datetime(2025,12,10,14,0,tzinfo=ny),datetime(2025,12,16,8,30,tzinfo=ny),datetime(2025,12,18,8,30,tzinfo=ny)]
    news=[int(x.timestamp()*1000) for x in news]
    def news_locked(t): return any(e-15*60000 <= t < e+15*60000 for e in news)
    def news_exit(tc): return any((tc<e-15*60000 and tc+TF_MS>=e-15*60000) or (tc>=e-15*60000 and tc<e) for e in news)
    def sess_flags(b):
        if not use_session:return True,False
        market,rdc=sc.state(b)
        if not market or rdc is None:return False,False
        tc=b.ct; ne=rdc-40*60000; ex=rdc-15*60000
        noentry=tc<=rdc and (tc>=ne or tc+TF_MS>=ne)
        lastbar=tc>=rdc or tc+TF_MS>rdc
        sexit=(tc<ex and tc+TF_MS>=ex) or (tc>=ex and tc<=rdc) or lastbar
        return not noentry,sexit
    def close(i,reason,px):
        nonlocal active,eq
        p=active; b=bars[i]
        both=(reason in ('TP','SL') and b.h>=max(p.s,p.t) and b.l<=min(p.s,p.t))
        if both:reason='AMBIG->SL'
        cr=2.3 if reason=='TP' else (-1.0 if reason in ('SL','AMBIG->SL') else managed_r(p,px))
        eq += cr*p.risk
        if p.report: trades.append({'signal':p.sig_t,'exit':b.ct,'side':'L' if p.d==1 else 'S','R':cr,'reason':reason,'e':p.e,'s':p.s,'t':p.t})
        exit_counts[reason]=exit_counts.get(reason,0)+1; active=None
    for i,b in enumerate(bars):
        closed=False
        if active is not None:
            r,px=ref.next_bracket(active,b,None)
            if r:close(i,r,px);closed=True
        if active is None and pending is not None and i==pending.sig_i+1 and not closed:
            fill=(pending.d==1 and round(b.h/tick)>=round(pending.e/tick)) or (pending.d==-1 and round(b.l/tick)<=round(pending.e/tick))
            if fill:
                active=pending;pending=None
                gap=(active.d==1 and round(b.o/tick)>=round(active.e/tick)) or (active.d==-1 and round(b.o/tick)<=round(active.e/tick))
                r,px=ref.next_bracket(active,b,None if gap else active.e)
                if r:close(i,r,px);closed=True
        allowed,sexit=sess_flags(b)
        if active is not None and not closed:
            z=ind[i]; le=active.d==1 and b.c<z['ema'] and not z['ha'] and not z['ema_up']; se=active.d==-1 and b.c>z['ema'] and not z['hb'] and bool(z['ema_up'])
            if sexit:close(i,'SESSION',b.c);closed=True
            elif news_exit(b.ct):close(i,'NEWS',b.c);closed=True
            elif le or se:close(i,'EMA',b.c);closed=True
        if pending is not None and i>=pending.sig_i+1 and active is None: pending=None
        if active is None and pending is None and not closed:
            z=ind[i]; lr=z['ha'] and b.c>z['ema'] and z['ag'] and z['chop_ok'] and z['res'] is not None; sr=z['hb'] and b.c<z['ema'] and z['ar'] and z['chop_ok'] and z['sup'] is not None
            safe=not news_locked(b.ct) and not news_locked(b.ct+TF_MS)
            nl=allowed and safe and z['sra_ok'] and b.c>b.o and lr and b.c>z['res'] and b.l<=z['res']
            ns=allowed and safe and z['sra_ok'] and b.c<b.o and sr and b.c<z['sup'] and b.h>=z['sup']
            if nl or ns:
                if nl:d=1;e=b.h+tick;s=b.l-tick;t=e+2.3*(e-s)
                else:d=-1;e=b.l-tick;s=b.h+tick;t=e-2.3*(s-e)
                dist=abs(e-s); q=math.floor((max(eq,0)*0.01)/dist); risk=dist*q
                if q>0 and risk>0: pending=P(d,e,s,t,risk,q,i,b.ct,b.h,b.l,start_ms<=b.ct<end_ms)
    return trades,{'n':len(trades),'R':sum(x['R'] for x in trades),'tick':tick,'session':sc.raw,'timezone':str(sc.tz),'exits':exit_counts,'bars':len(bars)}

def main():
    ref=load_ref(); results={}; datasets={}
    specs=[('OANDA:EURUSD','regular'),('OANDA:USDJPY','regular'),('OANDA:XAUUSD','regular'),('ICMARKETS:US500','regular'),('NASDAQ:AAPL','regular'),('NASDAQ:AAPL','extended')]
    for sym,sess in specs:
        print('FETCH',sym,sess,flush=True); bars,info=tv_fetch(sym,sess); datasets[(sym,sess)]=(bars,info)
        print('META',sym,sess,json.dumps({k:info.get(k) for k in ('name','exchange','listed_exchange','timezone','session','subsessions','minmov','pricescale','pointvalue','mincontract')},default=str),flush=True)
    warmups=[7,14,30,60,120]
    for sym,expected in ORACLES.items():
        sessions=['regular','extended'] if sym=='NASDAQ:AAPL' else ['regular']
        results[sym]={'expected':{'n':expected[0],'R':expected[1]},'runs':[]}
        for sess in sessions:
            bars,info=datasets[(sym,sess)]
            for days in warmups:
                hs=START-timedelta(days=days)
                for anchor in ('start','end'):
                    tr,met=run_case(ref,bars,info,hs,anchor,True); met.update({'tv_series_session':sess,'warmup_days':days,'session_day_anchor':anchor,'delta_n':met.get('n',0)-expected[0],'delta_R':met.get('R',0)-expected[1]})
                    results[sym]['runs'].append(met)
            tr0,m0=run_case(ref,bars,info,START-timedelta(days=60),'start',False); m0.update({'tv_series_session':sess,'warmup_days':60,'session_day_anchor':'NO_SESSION','delta_n':m0.get('n',0)-expected[0],'delta_R':m0.get('R',0)-expected[1]});results[sym]['runs'].append(m0)
        exact=[r for r in results[sym]['runs'] if r.get('delta_n')==0 and abs(r.get('delta_R',999))<0.015]
        results[sym]['exact_matches']=exact
        print('RESULT',sym,'expected',expected,'best',sorted(results[sym]['runs'],key=lambda r:(abs(r.get('delta_n',99)),abs(r.get('delta_R',999))))[:3],flush=True)
    (OUT/'parity.json').write_text(json.dumps(results,indent=2,default=str))
    summary=[]
    for s,v in results.items():
        best=sorted(v['runs'],key=lambda r:(abs(r.get('delta_n',99)),abs(r.get('delta_R',999))))[0]
        summary.append({'symbol':s,'expected':v['expected'],'exact_match_count':len(v['exact_matches']),'best':best})
    (OUT/'summary.json').write_text(json.dumps(summary,indent=2,default=str))
    print(json.dumps(summary,indent=2,default=str))
if __name__=='__main__': main()
