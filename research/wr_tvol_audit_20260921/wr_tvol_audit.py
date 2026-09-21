#!/usr/bin/env python3
from __future__ import annotations
import csv, io, json, math, os, random, sys, time, zipfile
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo
import requests

ROOT=Path('/tmp/wr-tvol-audit')
HARNESS=ROOT/'harness'
sys.path.insert(0,str(HARNESS/'base'))
sys.path.insert(0,str(HARNESS))
import wr_tv_parity as base
from close_confirm import run_case, assert_canonical_parity
base.TF='5'; base.TF_MS=300000
ref=base.load_ref()

VOL=json.load(open(ROOT/'volume_all_candidates.json'))['candidates']
FULL=json.load(open(ROOT/'fullstage_firstq.json'))['firstq']
TINFO=json.load(open(ROOT/'volume_candidates.json'))
ALLOWED_T=set(TINFO['allowed_T_dates'])
T_LABELS=TINFO['T_labels']
SYMBOLS=sorted(VOL)

REPORT_START=datetime(2025,1,1,tzinfo=timezone.utc)
REPORT_END=datetime(2026,8,15,tzinfo=timezone.utc)
HISTORY_START=datetime(2024,12,1,tzinfo=timezone.utc)
LOAD_END=datetime(2026,8,19,tzinfo=timezone.utc)
VN=ZoneInfo('Asia/Ho_Chi_Minh')
BINANCE='https://data.binance.vision'
OUT=ROOT/'batch'; OUT.mkdir(parents=True,exist_ok=True)
SHARD=int(os.getenv('SHARD','0')); SHARDS=int(os.getenv('SHARDS','8'))

@dataclass
class K:
    ot:int; ct:int; o:float; h:float; l:float; c:float; v:float; qv:float

def sess():
    s=requests.Session(); s.headers['User-Agent']='runner3-wr-tvol-audit/1.0'; return s

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

def eligible(firstq, require_t):
    def f(ms):
        vdt=datetime.fromtimestamp(ms/1000,tz=timezone.utc).astimezone(VN)
        if require_t and vdt.date().isoformat() not in ALLOWED_T:return False
        sd=(vdt-timedelta(hours=6)).date().isoformat()
        q=firstq.get(sd)
        return q is not None and ms>=int(q)
    return f

def sig(rows):
    return [(int(x['signal']),int(x['exit']),x['side'],round(float(x['R']),10),x['reason'],round(float(x['e']),10),round(float(x['s']),10),round(float(x['t']),10)) for x in rows]

def run_one(sym,bars):
    if len(bars)<1000: return {'symbol':sym,'status':'INSUFFICIENT','bars':len(bars)},[]
    tick=infer_tick(bars)
    if not tick:return {'symbol':sym,'status':'NO_TICK','bars':len(bars)},[]
    wr=[base.Bar(b.ot,b.ct,b.o,b.h,b.l,b.c) for b in bars]
    inf=info(tick)
    specs=[
        ('fullstage_t', FULL.get(sym,{}), True),
        ('volume_all', VOL.get(sym,{}), False),
        ('volume_t', VOL.get(sym,{}), True),
    ]
    alltr=[]; sm={'symbol':sym,'status':'OK','bars':len(bars),'tick':tick,'variants':{}}
    # All variants use identical bars/indicators. Cache calc_ind per symbol only;
    # execution state is still rebuilt independently by run_case for each variant.
    orig_calc_ind=ref.calc_ind
    ind_cache={}
    def cached_calc_ind(bs):
        key=(len(bs), int(bs[0].ot) if bs else 0, int(bs[-1].ot) if bs else 0)
        if key not in ind_cache:
            ind_cache[key]=orig_calc_ind(bs)
        return ind_cache[key]
    ref.calc_ind=cached_calc_ind
    try:
        for name,fq,reqt in specs:
            rows,raw=run_case(base,ref,wr,inf,HISTORY_START,REPORT_START,REPORT_END,variant='canonical',anchor='start',use_session=True,eligible_signal=eligible(fq,reqt))
            sm['variants'][name]={'n':len(rows),'gross_R':sum(float(t['R']) for t in rows),'counters':raw.get('counters',{}),'exits':raw.get('exits',{})}
            for t in rows:
                d=datetime.fromtimestamp(int(t['signal'])/1000,tz=timezone.utc).astimezone(VN).date().isoformat()
                z={'symbol':sym,'audit_variant':name,'signal_date_vn':d,'t_labels':T_LABELS.get(d,[])}
                z.update(t); alltr.append(z)
    finally:
        ref.calc_ind=orig_calc_ind
    return sm,alltr

def canary(sym='AUCTIONUSDT'):
    http=sess(); bars=load_symbol(http,sym); tick=infer_tick(bars); wr=[base.Bar(b.ot,b.ct,b.o,b.h,b.l,b.c) for b in bars]; inf=info(tick)
    parity_n=assert_canonical_parity(base,ref,wr,inf,HISTORY_START,REPORT_START,REPORT_END,anchor='start',use_session=True)
    got,_=run_case(base,ref,wr,inf,HISTORY_START,REPORT_START,REPORT_END,variant='canonical',anchor='start',use_session=True,eligible_signal=eligible(FULL[sym],False))
    exp=[]
    for ln in open(ROOT/'source'/'trades.jsonl'):
        t=json.loads(ln)
        if t.get('variant')=='canonical' and t.get('symbol')==sym: exp.append(t)
    ok=sig(got)==sig(exp)
    out={'symbol':sym,'engine_all_eligible_parity_n':parity_n,'parent_expected_n':len(exp),'parent_reproduced_n':len(got),'parent_trade_signature_exact':ok}
    print(json.dumps(out,indent=2),flush=True)
    if not ok:
        print('EXPECTED',sig(exp)[:10],flush=True); print('GOT',sig(got)[:10],flush=True); raise SystemExit(2)

def shard():
    mine=[s for i,s in enumerate(SYMBOLS) if i%SHARDS==SHARD]
    http=sess(); sums=[]; trades=[]
    for i,sym in enumerate(mine,1):
        try:
            bars=load_symbol(http,sym)
            sm,tr=run_one(sym,bars); sums.append(sm); trades.extend(tr)
            print('DONE',SHARD,i,len(mine),sym, {k:v['n'] for k,v in sm.get('variants',{}).items()},flush=True)
        except Exception as e:
            sums.append({'symbol':sym,'status':'ERROR','error':repr(e)})
            print('ERROR',SHARD,sym,repr(e),flush=True)
    (OUT/f'summary-{SHARD}.json').write_text(json.dumps({'shard':SHARD,'symbols':mine,'results':sums},separators=(',',':')))
    with (OUT/f'trades-{SHARD}.jsonl').open('w') as f:
        for t in trades:f.write(json.dumps(t,separators=(',',':'))+'\n')
    print('SHARD_FINISH',SHARD,'symbols',len(mine),'trades',len(trades),flush=True)

def cost_r(t,bps=6):
    d=abs(float(t['e'])-float(t['s']))
    return 0.0 if d<=0 else float(t['e'])/d*(bps/10000.0)

def net(t):return float(t['R'])-cost_r(t,6)

def metrics(xs):
    vals=[net(t) for t in xs]; gp=sum(max(x,0) for x in vals); gl=sum(max(-x,0) for x in vals)
    eq=peak=0.0; dd=0.0
    for x in vals:eq+=x;peak=max(peak,eq);dd=min(dd,eq-peak)
    return {'n':len(vals),'R':sum(vals),'mean_R':sum(vals)/len(vals) if vals else None,'PF':gp/gl if gl else None,'win_rate':100*sum(x>0 for x in vals)/len(vals) if vals else None,'max_DD_R':dd}

def bootstrap(xs,reps=2000,seed=20260921):
    by=defaultdict(list)
    for t in xs:by[t['signal_date_vn']].append(net(t))
    days=sorted(by)
    if not days:return {'days':0,'reps':0,'mean_ci95':[None,None]}
    rng=random.Random(seed); ms=[]
    for _ in range(reps):
        vals=[]
        for _j in range(len(days)):
            d=days[rng.randrange(len(days))]; vals.extend(by[d])
        if vals:ms.append(sum(vals)/len(vals))
    ms.sort(); lo=ms[int(.025*(len(ms)-1))]; hi=ms[int(.975*(len(ms)-1))]
    return {'days':len(days),'reps':len(ms),'mean_ci95':[lo,hi]}

def breadth(xs):
    by=defaultdict(list)
    for t in xs:by[t['symbol']].append(t)
    elig={s:a for s,a in by.items() if len(a)>=5}; pos=sum(metrics(a)['R']>0 for a in elig.values())
    return {'eligible_symbols_ge5':len(elig),'positive_symbols':pos,'positive_fraction':pos/len(elig) if elig else None}

def merge():
    trades=[]; errors=[]; seen_summaries=0
    for p in sorted(OUT.glob('summary-*.json')):
        x=json.load(open(p)); seen_summaries+=1
        for r in x['results']:
            if r.get('status')=='ERROR':errors.append(r)
    for p in sorted(OUT.glob('trades-*.jsonl')):
        for ln in open(p):
            if ln.strip():trades.append(json.loads(ln))
    report={'status':'COMPLETE' if not errors and seen_summaries==SHARDS else 'PARTIAL','shards_seen':seen_summaries,'errors':errors,'source':{'engine':'Wave Rider v2.5.13 corrected Pine-compatible verifier','period':'2025-01-01..2026-08-14 signals; history from 2024-12-01','market':'Binance USDT futures archive 5m','cost_model_bps':6,'volume_rule':'24h quote volume >=100M USD AND prior-completed-day avg 10D dollar-volume proxy >200M USD','T_rule':'VN local T-2,T-1,T0,T+2,T+3 around actual CPI/NFP/FOMC releases; T+1/white/weekend excluded','no_sweep':True},'variants':{}}
    for idx,name in enumerate(('fullstage_t','volume_all','volume_t')):
        xs=[t for t in trades if t['audit_variant']==name]
        m=metrics(xs); yr={str(y):metrics([t for t in xs if datetime.fromtimestamp(int(t['signal'])/1000,tz=timezone.utc).year==y]) for y in (2025,2026)}
        bs=bootstrap(xs,seed=20260921+idx); br=breadth(xs)
        labels=defaultdict(int)
        for t in xs:
            for z in t.get('t_labels',[]):labels[z]+=1
        strong=bool(m['n']>=80 and m['R']>0 and (m['mean_R'] or 0)>0 and (m['PF'] or 0)>1.05 and yr['2025']['R']>0 and yr['2026']['R']>0 and bs['mean_ci95'][0] is not None and bs['mean_ci95'][0]>0 and br['positive_fraction'] is not None and br['positive_fraction']>=0.5)
        report['variants'][name]={'metrics':m,'by_year':yr,'bootstrap':bs,'symbol_breadth':br,'T_label_trade_counts':dict(labels),'strong_pass':strong}
    a=report['variants']['volume_all']['metrics']; b=report['variants']['volume_t']['metrics']; f=report['variants']['fullstage_t']['metrics']
    report['comparisons']={
      'volume_t_minus_volume_all_mean_R': (b['mean_R']-a['mean_R']) if a['mean_R'] is not None and b['mean_R'] is not None else None,
      'volume_t_minus_fullstage_t_mean_R': (b['mean_R']-f['mean_R']) if f['mean_R'] is not None and b['mean_R'] is not None else None,
    }
    (ROOT/'final_report.json').write_text(json.dumps(report,indent=2))
    print(json.dumps(report,indent=2),flush=True)
    if report['status']!='COMPLETE': raise SystemExit(3)

if __name__=='__main__':
    mode=sys.argv[1] if len(sys.argv)>1 else 'shard'
    if mode=='canary':canary(sys.argv[2] if len(sys.argv)>2 else 'AUCTIONUSDT')
    elif mode=='merge':merge()
    else:shard()
