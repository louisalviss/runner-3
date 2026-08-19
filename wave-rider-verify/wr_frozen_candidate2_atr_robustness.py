import csv,io,json,math,random,statistics,zipfile,time
from collections import defaultdict
from datetime import datetime,timezone
from pathlib import Path
import requests

A24=Path('/tmp/a24'); A25=Path('/tmp/a25'); OUT=Path('/tmp/final5'); OUT.mkdir(parents=True,exist_ok=True)

def load_jsonl(p):
    out=[]
    with open(p) as f:
        for line in f:
            if line.strip(): out.append(json.loads(line))
    return out

seen=set(); T=[]
for a in load_jsonl(A24/'all_trades.jsonl')+load_jsonl(A25/'trades.jsonl'):
    k=(a['symbol'],a['signal_time'],a['entry'],a['stop'])
    if k not in seen:
        seen.add(k); T.append(a)
T.sort(key=lambda a:(a['signal_time'],a['symbol']))

def net(a,bps): return a['R']-(a['entry']/abs(a['entry']-a['stop']))*bps/10000
def dt(a): return datetime.fromtimestamp(a['signal_time']/1000,tz=timezone.utc)
def year(a): return dt(a).year
def month(a): return dt(a).strftime('%Y-%m')
def stat(xs):
    z={'n':len(xs),'gross_r':sum(a['R'] for a in xs)}
    for b in (4,6,8,10,12,15,20): z[f'net_r_{b}bps']=sum(net(a,b) for a in xs)
    z['avg_net6_r']=z['net_r_6bps']/z['n'] if z['n'] else None
    return z

def sd(xs): return statistics.stdev(xs) if len(xs)>=2 else None

def pct(xs,p):
    z=sorted(xs); i=(len(z)-1)*p; lo=int(math.floor(i)); hi=int(math.ceil(i))
    return z[lo] if lo==hi else z[lo]*(hi-i)+z[hi]*(i-lo)

S=requests.Session(); S.headers['User-Agent']='runner3-wr-candidate2-atr/1.0'
def fetch_zip(url,tries=3):
    for i in range(tries):
        try:
            r=S.get(url,timeout=30)
            if r.status_code==404:return None
            r.raise_for_status(); return r.content
        except Exception:
            if i==tries-1:return None
            time.sleep(0.5*(i+1))

def read_daily(data):
    if not data:return []
    out=[]
    with zipfile.ZipFile(io.BytesIO(data)) as z: text=z.read(z.namelist()[0]).decode()
    for row in csv.reader(io.StringIO(text)):
        if row and row[0].isdigit():
            out.append({'t':int(row[0]),'h':float(row[2]),'l':float(row[3]),'c':float(row[4])})
    return out

# Frozen parent gate: BTC 30d return < 0 and BTC RV20 > RV60, fully closed daily candles only.
btc=[]
for y in range(2023,2027):
    for m in range(1,13):
        if (y,m)<(2023,4) or (y,m)>(2026,8): continue
        fn=f'BTCUSDT-1d-{y:04d}-{m:02d}.zip'
        u=f'https://data.binance.vision/data/futures/um/monthly/klines/BTCUSDT/1d/{fn}'
        d=fetch_zip(u)
        if d: btc.extend(read_daily(d))
btc=sorted({b['t']:b for b in btc}.values(),key=lambda b:b['t'])

def btc_gate(ts):
    h=[b for b in btc if b['t']+86400000<=ts]
    if len(h)<70:return False
    c=[b['c'] for b in h]; lr=[math.log(c[i]/c[i-1]) for i in range(1,len(c))]
    return (c[-1]/c[-31]-1)<0 and (sd(lr[-20:]) or 0)>(sd(lr[-60:]) or 0)

P=[a for a in T if 2024<=year(a)<=2026 and btc_gate(a['signal_time'])]
expected_parent={2024:317,2025:1050,2026:645}
actual_parent={y:sum(year(a)==y for a in P) for y in expected_parent}
if actual_parent!=expected_parent:
    raise RuntimeError(f'PARENT_PARITY_FAIL expected={expected_parent} actual={actual_parent}')

# Need only altcoin ATR. Same policy as discovery run: current + prior 3 calendar months, closed bars only.
need=defaultdict(set)
for a in P:
    d=dt(a); y,m=d.year,d.month
    for k in range(4):
        yy,mm=y,m-k
        while mm<=0: yy-=1; mm+=12
        need[a['symbol']].add((yy,mm))
cache={}
for idx,(sym,months) in enumerate(sorted(need.items())):
    bars=[]
    for y,m in sorted(months):
        fn=f'{sym}-1d-{y:04d}-{m:02d}.zip'
        u=f'https://data.binance.vision/data/futures/um/monthly/klines/{sym}/1d/{fn}'
        d=fetch_zip(u)
        if d: bars.extend(read_daily(d))
    cache[sym]=sorted({b['t']:b for b in bars}.values(),key=lambda b:b['t'])
    if idx%50==0: print('SYMBOLS',idx,'/',len(need),flush=True)

def atr_high(a):
    h=[b for b in cache.get(a['symbol'],[]) if b['t']+86400000<=a['signal_time']]
    if len(h)<70:return None
    tr=[]
    for i in range(1,len(h)):
        prev=h[i-1]['c']; b=h[i]
        tr.append(max(b['h']-b['l'],abs(b['h']-prev),abs(b['l']-prev))/prev)
    atr14=sum(tr[-14:])/14; atr60=sum(tr[-60:])/60
    return atr14>atr60

PF=[]; C=[]
for a in P:
    x=atr_high(a)
    if x is not None:
        PF.append(a)
        if x: C.append(a)

expected_candidate={2024:138,2025:409,2026:315}
actual_candidate={y:sum(year(a)==y for a in C) for y in expected_candidate}
if actual_candidate!=expected_candidate:
    raise RuntimeError(f'CANDIDATE_PARITY_FAIL expected={expected_candidate} actual={actual_candidate}')

def robustness(xs,seed):
    xs=sorted(xs,key=lambda a:(a['signal_time'],a['symbol']))
    eq=0; peak=0; maxdd=0; peak_time=None; worst=None
    for a in xs:
        eq+=net(a,6)
        if eq>peak: peak=eq; peak_time=dt(a).isoformat()
        dd=eq-peak
        if dd<maxdd:
            maxdd=dd; worst={'time':dt(a).isoformat(),'equity':eq,'peak':peak,'drawdown':dd,'peak_time':peak_time}
    months=sorted({month(a) for a in xs})
    bm={m:stat([a for a in xs if month(a)==m]) for m in months}
    loo={m:stat([a for a in xs if month(a)!=m])['net_r_6bps'] for m in months}
    rng=random.Random(seed); vals=[net(a,6) for a in xs]
    tb=[sum(rng.choice(vals) for _ in vals)/len(vals) for __ in range(5000)] if vals else []
    mv={m:[net(a,6) for a in xs if month(a)==m] for m in months}
    mb=[]
    if months:
        for _ in range(5000):
            picks=[rng.choice(months) for __ in months]
            vv=[v for m in picks for v in mv[m]]
            mb.append(sum(vv)/len(vv) if vv else 0)
    sym=defaultdict(list)
    for a in xs:sym[a['symbol']].append(a)
    sr=sorted([(stat(v)['net_r_6bps'],k,len(v)) for k,v in sym.items()],reverse=True)
    pos=sum(max(0,v) for v,_,_ in sr)
    conc={
      'top_symbols':[{'symbol':k,'n':n,'net6':v} for v,k,n in sr[:15]],
      'top5_positive_share':sum(max(0,v) for v,_,_ in sr[:5])/pos if pos else None,
      'remove_top1_net6':stat([a for a in xs if sr and a['symbol']!=sr[0][1]])['net_r_6bps'] if sr else None,
      'remove_top5_net6':stat([a for a in xs if a['symbol'] not in {k for _,k,_ in sr[:5]}])['net_r_6bps'] if sr else None,
      'remove_top10_net6':stat([a for a in xs if a['symbol'] not in {k for _,k,_ in sr[:10]}])['net_r_6bps'] if sr else None,
    }
    sides=sorted({a['side'] for a in xs})
    return {
      'total':stat(xs),
      'by_year':{str(y):stat([a for a in xs if year(a)==y]) for y in (2024,2025,2026)},
      'month_profile':bm,
      'positive_months':sum(v['net_r_6bps']>0 for v in bm.values()),
      'negative_months':sum(v['net_r_6bps']<0 for v in bm.values()),
      'active_months':len(bm),
      'max_drawdown_net6_r':maxdd,'max_drawdown_detail':worst,
      'leave_one_month_out_net6':{'min':min(loo.values()) if loo else None,'max':max(loo.values()) if loo else None,'values':loo},
      'bootstrap_trade_mean_net6_95ci':[pct(tb,.025),pct(tb,.975)] if tb else [None,None],
      'bootstrap_month_block_mean_net6_95ci':[pct(mb,.025),pct(mb,.975)] if mb else [None,None],
      'side_contribution':{s:{'total':stat([a for a in xs if a['side']==s]),'by_year':{str(y):stat([a for a in xs if a['side']==s and year(a)==y]) for y in (2024,2025,2026)}} for s in sides},
      'symbol_concentration':conc,
    }

parent_cov=robustness(PF,20260820)
candidate=robustness(C,20260821)

# Direct same-feature-covered comparison. No threshold search.
comparison={
 'feature_covered_parent_n':len(PF),'candidate_n':len(C),'retained_pct':100*len(C)/len(PF) if PF else None,
 'delta_total_net6':candidate['total']['net_r_6bps']-parent_cov['total']['net_r_6bps'],
 'delta_total_net8':candidate['total']['net_r_8bps']-parent_cov['total']['net_r_8bps'],
 'delta_maxdd_net6':candidate['max_drawdown_net6_r']-parent_cov['max_drawdown_net6_r'],
 'delta_positive_months':candidate['positive_months']-parent_cov['positive_months'],
 'by_year_net6_delta':{str(y):candidate['by_year'][str(y)]['net_r_6bps']-parent_cov['by_year'][str(y)]['net_r_6bps'] for y in (2024,2025,2026)},
}

report={
 'status':'WR_FROZEN_CANDIDATE2_ATR_ROBUSTNESS_COMPLETE',
 'frozen_definition':'Exact Zone C 10m AND BTC 30d return < 0 AND BTC RV20 > RV60 AND altcoin normalized ATR14 > normalized ATR60. All regime inputs use fully closed daily candles before trade.',
 'warning':'Candidate #2 was discovered retrospectively from 2024-2026. This is a frozen robustness test, not pristine OOS. No thresholds are tuned here.',
 'parity':{'parent_expected':expected_parent,'parent_actual':actual_parent,'candidate_expected':expected_candidate,'candidate_actual':actual_candidate,'feature_covered_parent_n':len(PF)},
 'candidate':candidate,
 'parent_same_feature_coverage':parent_cov,
 'comparison':comparison,
}
json.dump(report,open(OUT/'frozen_candidate2_atr_robustness.json','w'),indent=2)
print(json.dumps(report,indent=2))