#!/usr/bin/env python3
from __future__ import annotations
import csv, io, json, math, os, random, sys, time, zipfile
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo
import requests

ROOT=Path('/tmp/wr-tvol-fixed')
HARNESS=ROOT/'harness'
sys.path.insert(0,str(HARNESS/'base'))
sys.path.insert(0,str(HARNESS))
import wr_tv_parity as base
from close_confirm import Position, assert_canonical_parity
base.TF='5'; base.TF_MS=300000
ref=base.load_ref()

VOL=json.load(open(ROOT/'volume_all_candidates.json'))['candidates']
TINFO=json.load(open(ROOT/'volume_candidates.json'))
ALLOWED_T=set(TINFO['allowed_T_dates'])
T_LABELS=TINFO['T_labels']
SYMBOLS=sorted(VOL)
REPORT_START=datetime(2025,1,1,tzinfo=timezone.utc)
REPORT_END=datetime(2026,8,15,tzinfo=timezone.utc)
HISTORY_START=datetime(2024,12,1,tzinfo=timezone.utc)
LOAD_END=datetime(2026,9,1,tzinfo=timezone.utc)  # settlement only after REPORT_END
VN=ZoneInfo('Asia/Ho_Chi_Minh')
NY=ZoneInfo('America/New_York')
BINANCE='https://data.binance.vision'
OUT=ROOT/'batch'; OUT.mkdir(parents=True,exist_ok=True)
SHARD=int(os.getenv('SHARD','0')); SHARDS=int(os.getenv('SHARDS','32'))

@dataclass
class K:
    ot:int; ct:int; o:float; h:float; l:float; c:float; v:float; qv:float

def sess():
    s=requests.Session(); s.headers['User-Agent']='runner3-wr-tvol-fixed-exit/1.0'; return s

def months():
    d=date(2024,12,1); end=date(2026,8,1)
    while d<=end:
        yield d.year,d.month
        d=(d.replace(day=28)+timedelta(days=4)).replace(day=1)

def get_zip(http,url):
    last=None
    for k in range(4):
        try:
            r=http.get(url,timeout=60)
            if r.status_code==404:return None
            r.raise_for_status(); return r.content
        except Exception as e:
            last=e
            if k==3: raise
            time.sleep(.5*(k+1))
    raise last

def read_zip(data):
    if not data:return []
    out=[]
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        text=z.read(z.namelist()[0]).decode()
    for row in csv.reader(io.StringIO(text)):
        if not row or not row[0].isdigit():continue
        out.append(K(int(row[0]),int(row[6]),float(row[1]),float(row[2]),float(row[3]),float(row[4]),float(row[5]),float(row[7])))
    return out

def load_symbol(http,sym):
    bars=[]
    for y,m in months():
        fn=f'{sym}-5m-{y:04d}-{m:02d}.zip'
        url=f'{BINANCE}/data/futures/um/monthly/klines/{sym}/5m/{fn}'
        bars.extend(read_zip(get_zip(http,url)))
    lo=int(HISTORY_START.timestamp()*1000); hi=int(LOAD_END.timestamp()*1000)
    ded={b.ot:b for b in bars if lo<=b.ot<hi}
    return [ded[k] for k in sorted(ded)]

def infer_tick(bars):
    vals=[]
    for b in bars[:3000]: vals.extend([b.o,b.h,b.l,b.c])
    return float(ref.infer_tick(vals)) if vals else None

def info(tick):
    return {'timezone':'Etc/UTC','exchange_timezone':'Etc/UTC','session':'0000-0000:1234567','subsessions':[{'id':'regular','session':'0000-0000:1234567'}],'_tick':tick}

def eligible_volume_t(firstq):
    def f(ms):
        vdt=datetime.fromtimestamp(ms/1000,tz=timezone.utc).astimezone(VN)
        if vdt.date().isoformat() not in ALLOWED_T:return False
        sd=(vdt-timedelta(hours=6)).date().isoformat()
        q=firstq.get(sd)
        return q is not None and ms>=int(q)
    return f

def run_fixed_case(bars, inf, eligible_signal, *, guarded:bool):
    bars=[b for b in bars if b.ot>=int(HISTORY_START.timestamp()*1000)]
    if len(bars)<100:return [],{'error':'too_few_bars'}
    ind,_,_=ref.calc_ind(bars); tick=base.tv_tick(inf,[x.c for x in bars]); sc=base.SessionClock(inf,'start')
    start_ms=int(REPORT_START.timestamp()*1000); end_ms=int(REPORT_END.timestamp()*1000)
    eq=100000.; pending=None; active=None; trades=[]
    counters={'signals':0,'eligible_signals':0,'fills':0,'unfilled_nextbar':0,'open_censored':0}
    exits={k:0 for k in ('TP','SL','AMBIG->SL')}
    # Frozen canonical embedded news list used by the prior run, only for guarded signal admission.
    news=[datetime(2025,11,20,8,30,tzinfo=NY),datetime(2025,12,10,14,0,tzinfo=NY),datetime(2025,12,16,8,30,tzinfo=NY),datetime(2025,12,18,8,30,tzinfo=NY)]
    news=[int(x.timestamp()*1000) for x in news]
    def news_locked(t):
        return guarded and any(e-15*60000 <= t < e+15*60000 for e in news)
    def signal_allowed(b):
        if not guarded:return True
        market,rdc=sc.state(b)
        if not market or rdc is None:return False
        tc=b.ct; ne=rdc-40*60000
        noentry=tc<=rdc and (tc>=ne or tc+base.TF_MS>=ne)
        return not noentry
    def close(i,reason):
        nonlocal active,eq
        p=active; b=bars[i]
        both=b.h>=max(p.s,p.t) and b.l<=min(p.s,p.t)
        if both: reason='AMBIG->SL'
        cr=2.3 if reason=='TP' else -1.0
        eq += cr*p.risk
        if p.report:
            trades.append({'signal':p.sig_t,'exit':b.ct,'side':'L' if p.d==1 else 'S','R':cr,'reason':reason,
                           'e':p.e,'s':p.s,'t':p.t,'trigger':p.trigger,'entry_time':p.entry_t,'variant':'fixed_guarded' if guarded else 'fixed_pure'})
        exits[reason]+=1; active=None
    for i,b in enumerate(bars):
        closed=False
        if active is not None:
            r,_px=ref.next_bracket(active,b,None)
            if r:
                close(i,r); closed=True
        if active is None and pending is not None and not closed:
            if i==pending.sig_i+1:
                fill=(pending.d==1 and round(b.h/tick)>=round(pending.e/tick)) or (pending.d==-1 and round(b.l/tick)<=round(pending.e/tick))
                if fill:
                    active=pending; pending=None; active.entry_t=b.ot; counters['fills']+=1
                    gap=(active.d==1 and round(b.o/tick)>=round(active.e/tick)) or (active.d==-1 and round(b.o/tick)<=round(active.e/tick))
                    r,_px=ref.next_bracket(active,b,None if gap else active.e)
                    if r:
                        close(i,r); closed=True
                else:
                    counters['unfilled_nextbar']+=1
        if pending is not None and active is None and i>=pending.sig_i+1:
            pending=None
        # Never open a new report signal after REPORT_END. We still process bars after it to settle open trades.
        if b.ct>=end_ms:
            continue
        if active is None and pending is None and not closed:
            z=ind[i]
            lr=z['ha'] and b.c>z['ema'] and z['ag'] and z['chop_ok'] and z['res'] is not None
            sr=z['hb'] and b.c<z['ema'] and z['ar'] and z['chop_ok'] and z['sup'] is not None
            allowed=signal_allowed(b)
            safe=not news_locked(b.ct) and not news_locked(b.ct+base.TF_MS)
            nl=allowed and safe and z['sra_ok'] and b.c>b.o and lr and b.c>z['res'] and b.l<=z['res']
            ns=allowed and safe and z['sra_ok'] and b.c<b.o and sr and b.c<z['sup'] and b.h>=z['sup']
            if nl or ns:
                counters['signals']+=1
                if eligible_signal is not None and not bool(eligible_signal(int(b.ct))):
                    continue
                counters['eligible_signals']+=1
                if nl:d=1; trigger=b.h+tick; s=b.l-tick
                else:d=-1; trigger=b.l-tick; s=b.h+tick
                e=trigger; dist=abs(e-s); t=e+2.3*(e-s) if d==1 else e-2.3*(s-e)
                q=math.floor((max(eq,0)*0.01)/dist); risk=dist*q
                if q>0 and risk>0:
                    report=start_ms<=b.ct<end_ms
                    pending=Position(d,e,s,t,risk,q,i,b.ct,b.h,b.l,report,trigger,None,None)
    if active is not None and active.report:
        counters['open_censored']=1
    return trades,{'n':len(trades),'R':sum(x['R'] for x in trades),'exits':exits,'counters':counters,'bars':len(bars)}

def run_one(sym,bars):
    if len(bars)<1000:return {'symbol':sym,'status':'INSUFFICIENT','bars':len(bars)},[]
    tick=infer_tick(bars)
    if not tick:return {'symbol':sym,'status':'NO_TICK','bars':len(bars)},[]
    wr=[base.Bar(b.ot,b.ct,b.o,b.h,b.l,b.c) for b in bars]; inf=info(tick); elig=eligible_volume_t(VOL.get(sym,{}))
    alltr=[]; sm={'symbol':sym,'status':'OK','bars':len(bars),'tick':tick,'variants':{}}
    orig=ref.calc_ind; cache={}
    def cached(bs):
        key=(len(bs),int(bs[0].ot),int(bs[-1].ot))
        if key not in cache:cache[key]=orig(bs)
        return cache[key]
    ref.calc_ind=cached
    try:
        for name,guarded in [('fixed_guarded',True),('fixed_pure',False)]:
            rows,raw=run_fixed_case(wr,inf,elig,guarded=guarded)
            sm['variants'][name]=raw
            for t in rows:
                d=datetime.fromtimestamp(int(t['signal'])/1000,tz=timezone.utc).astimezone(VN).date().isoformat()
                z={'symbol':sym,'audit_variant':name,'signal_date_vn':d,'t_labels':T_LABELS.get(d,[])}; z.update(t); alltr.append(z)
    finally: ref.calc_ind=orig
    return sm,alltr

def canary(sym='AUCTIONUSDT'):
    http=sess(); bars=load_symbol(http,sym); tick=infer_tick(bars); wr=[base.Bar(b.ot,b.ct,b.o,b.h,b.l,b.c) for b in bars]; inf=info(tick)
    n=assert_canonical_parity(base,ref,wr,inf,HISTORY_START,REPORT_START,REPORT_END,anchor='start',use_session=True)
    sm,tr=run_one(sym,bars)
    print(json.dumps({'canonical_engine_parity_n':n,'fixed':sm['variants'],'trade_rows':len(tr)},indent=2),flush=True)

def shard():
    mine=[s for i,s in enumerate(SYMBOLS) if i%SHARDS==SHARD]; http=sess(); sums=[]; trades=[]
    for i,sym in enumerate(mine,1):
        try:
            bars=load_symbol(http,sym); sm,tr=run_one(sym,bars); sums.append(sm); trades.extend(tr)
            print('DONE',SHARD,i,len(mine),sym,{k:v.get('n') for k,v in sm.get('variants',{}).items()},flush=True)
        except Exception as e:
            sums.append({'symbol':sym,'status':'ERROR','error':repr(e)}); print('ERROR',SHARD,sym,repr(e),flush=True)
    (OUT/f'summary-{SHARD}.json').write_text(json.dumps({'shard':SHARD,'symbols':mine,'results':sums},separators=(',',':')))
    with (OUT/f'trades-{SHARD}.jsonl').open('w') as f:
        for t in trades:f.write(json.dumps(t,separators=(',',':'))+'\n')
    print('SHARD_FINISH',SHARD,'symbols',len(mine),'trades',len(trades),flush=True)

def cost_r(t,bps=6):
    d=abs(float(t['e'])-float(t['s']))
    return 0.0 if d<=0 else float(t['e'])/d*(bps/10000.0)

def metrics(xs,bps):
    vals=[float(t['R'])-(cost_r(t,bps) if bps else 0.0) for t in xs]
    gp=sum(max(x,0) for x in vals); gl=sum(max(-x,0) for x in vals); eq=peak=0.; dd=0.
    for x in vals:eq+=x; peak=max(peak,eq); dd=min(dd,eq-peak)
    return {'n':len(vals),'R':sum(vals),'mean_R':sum(vals)/len(vals) if vals else None,'PF':gp/gl if gl else None,
            'win_rate':100*sum(x>0 for x in vals)/len(vals) if vals else None,'max_DD_R':dd}

def bootstrap(xs,bps,reps=2000,seed=20260921):
    by=defaultdict(list)
    for t in xs:by[t['signal_date_vn']].append(float(t['R'])-(cost_r(t,bps) if bps else 0.0))
    days=sorted(by)
    if not days:return {'days':0,'reps':0,'mean_ci95':[None,None]}
    rng=random.Random(seed); ms=[]
    for _ in range(reps):
        vals=[]
        for _j in range(len(days)):
            d=days[rng.randrange(len(days))]; vals.extend(by[d])
        if vals:ms.append(sum(vals)/len(vals))
    ms.sort(); return {'days':len(days),'reps':len(ms),'mean_ci95':[ms[int(.025*(len(ms)-1))],ms[int(.975*(len(ms)-1))]]}

def merge():
    trades=[]; errors=[]; summaries=[]
    for p in sorted(OUT.glob('summary-*.json')):
        x=json.load(open(p)); summaries.extend(x['results'])
        errors.extend([r for r in x['results'] if r.get('status')=='ERROR'])
    for p in sorted(OUT.glob('trades-*.jsonl')):
        for ln in open(p):
            if ln.strip():trades.append(json.loads(ln))
    report={'status':'COMPLETE' if not errors and len(list(OUT.glob('summary-*.json')))==SHARDS else 'PARTIAL','shards_seen':len(list(OUT.glob('summary-*.json'))),'errors':errors,
            'source':{'engine':'WR corrected Pine-compatible structural signal','market':'Binance USDT futures 5m','signal_period':'2025-01-01..2026-08-14','settlement_bars_through':'2026-08-31','volume_rule':'24h quote volume >=100M AND prior-completed-day avg10D dollar-volume proxy >200M','T_rule':'VN T-2,T-1,T0,T+2,T+3; T+1/white/weekend excluded','entry':'next-bar stop-entry','exit':'fixed +2.3R / -1R only','same_bar':'conservative SL','no_sweep':True},'variants':{}}
    for idx,name in enumerate(('fixed_guarded','fixed_pure')):
        xs=[t for t in trades if t['audit_variant']==name]
        gross=metrics(xs,0); net6=metrics(xs,6)
        yr={str(y):{'gross':metrics([t for t in xs if datetime.fromtimestamp(int(t['signal'])/1000,tz=timezone.utc).year==y],0),'net6':metrics([t for t in xs if datetime.fromtimestamp(int(t['signal'])/1000,tz=timezone.utc).year==y],6)} for y in (2025,2026)}
        bs0=bootstrap(xs,0,seed=20260921+idx); bs6=bootstrap(xs,6,seed=20260931+idx)
        open_censored=sum(int(r.get('variants',{}).get(name,{}).get('counters',{}).get('open_censored',0)) for r in summaries)
        exits=defaultdict(int)
        for r in summaries:
            for k,v in r.get('variants',{}).get(name,{}).get('exits',{}).items():exits[k]+=int(v)
        labels=defaultdict(int)
        for t in xs:
            for z in t.get('t_labels',[]):labels[z]+=1
        report['variants'][name]={'gross':gross,'net6':net6,'by_year':yr,'bootstrap_gross':bs0,'bootstrap_net6':bs6,'open_censored':open_censored,'exit_counts':dict(exits),'T_label_trade_counts':dict(labels)}
    (ROOT/'final_report.json').write_text(json.dumps(report,indent=2)); print(json.dumps(report,indent=2),flush=True)
    if report['status']!='COMPLETE':raise SystemExit(3)
if __name__=='__main__':
    mode=sys.argv[1] if len(sys.argv)>1 else 'shard'
    if mode=='canary':canary(sys.argv[2] if len(sys.argv)>2 else 'AUCTIONUSDT')
    elif mode=='merge':merge()
    else:shard()
