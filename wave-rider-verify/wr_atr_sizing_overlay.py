import csv,io,json,math,statistics,zipfile,time
from collections import defaultdict
from datetime import datetime,timezone
from pathlib import Path
import requests

A24=Path('/tmp/a24'); A25=Path('/tmp/a25'); OUT=Path('/tmp/final6'); OUT.mkdir(parents=True,exist_ok=True)

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

def dt(a): return datetime.fromtimestamp(a['signal_time']/1000,tz=timezone.utc)
def year(a): return dt(a).year
def month(a): return dt(a).strftime('%Y-%m')
def net(a,bps): return a['R']-(a['entry']/abs(a['entry']-a['stop']))*bps/10000
def sd(xs): return statistics.stdev(xs) if len(xs)>=2 else None

S=requests.Session(); S.headers['User-Agent']='runner3-wr-atr-sizing-overlay/1.0'
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
        if row and row[0].isdigit(): out.append({'t':int(row[0]),'h':float(row[2]),'l':float(row[3]),'c':float(row[4])})
    return out

# Frozen parent regime: BTC 30d return < 0 AND BTC RV20 > RV60, closed daily candles only.
btc=[]
for y in range(2023,2027):
  for m in range(1,13):
    if (y,m)<(2023,4) or (y,m)>(2026,8): continue
    fn=f'BTCUSDT-1d-{y:04d}-{m:02d}.zip'
    d=fetch_zip(f'https://data.binance.vision/data/futures/um/monthly/klines/BTCUSDT/1d/{fn}')
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
if actual_parent!=expected_parent: raise RuntimeError(f'PARENT_PARITY_FAIL expected={expected_parent} actual={actual_parent}')

# Recreate the frozen alt ATR state, using only closed candles before trade.
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
        d=fetch_zip(f'https://data.binance.vision/data/futures/um/monthly/klines/{sym}/1d/{fn}')
        if d: bars.extend(read_daily(d))
    cache[sym]=sorted({b['t']:b for b in bars}.values(),key=lambda b:b['t'])
    if idx%50==0: print('SYMBOLS',idx,'/',len(need),flush=True)

def atr_state(a):
    h=[b for b in cache.get(a['symbol'],[]) if b['t']+86400000<=a['signal_time']]
    if len(h)<70:return None
    tr=[]
    for i in range(1,len(h)):
        prev=h[i-1]['c']; b=h[i]
        tr.append(max(b['h']-b['l'],abs(b['h']-prev),abs(b['l']-prev))/prev)
    return 'HIGH' if sum(tr[-14:])/14>sum(tr[-60:])/60 else 'LOW'

PF=[]
for a in P:
    s=atr_state(a)
    if s is not None:
        a['_atr_state']=s; PF.append(a)

if len(PF)!=1804: raise RuntimeError(f'FEATURE_COVERAGE_PARITY_FAIL expected=1804 actual={len(PF)}')
counts={s:sum(a['_atr_state']==s for a in PF) for s in ('HIGH','LOW')}
if counts!={'HIGH':862,'LOW':942}: raise RuntimeError(f'ATR_STATE_PARITY_FAIL {counts}')

# Predeclared policies only. No search/tuning in this run.
POLICIES={
 'BASE_1_1':{'HIGH':1.0,'LOW':1.0},
 'H1_L0.5':{'HIGH':1.0,'LOW':0.5},
 'H1_L0.25':{'HIGH':1.0,'LOW':0.25},
 'H1.25_L0.5':{'HIGH':1.25,'LOW':0.5},
}

def evaluate(rows,weights):
    rows=sorted(rows,key=lambda a:(a['signal_time'],a['symbol']))
    exposure=sum(weights[a['_atr_state']] for a in rows)
    avg_size=exposure/len(rows) if rows else 0
    totals={'n':len(rows),'exposure_units':exposure,'avg_size':avg_size,'weighted_gross_r':sum(weights[a['_atr_state']]*a['R'] for a in rows)}
    for b in (4,6,8,10,12,15,20): totals[f'weighted_net_r_{b}bps']=sum(weights[a['_atr_state']]*net(a,b) for a in rows)
    totals['net6_per_exposure_unit']=totals['weighted_net_r_6bps']/exposure if exposure else None
    eq=0; peak=0; maxdd=0
    for a in rows:
        eq+=weights[a['_atr_state']]*net(a,6); peak=max(peak,eq); maxdd=min(maxdd,eq-peak)
    totals['max_drawdown_net6_r']=maxdd
    totals['net6_to_abs_maxdd']=totals['weighted_net_r_6bps']/abs(maxdd) if maxdd<0 else None
    months=sorted({month(a) for a in rows})
    mp={m:sum(weights[a['_atr_state']]*net(a,6) for a in rows if month(a)==m) for m in months}
    totals['active_months']=len(months); totals['positive_months']=sum(v>0 for v in mp.values()); totals['negative_months']=sum(v<0 for v in mp.values())
    totals['month_profile_net6']=mp
    totals['by_year']={str(y):{f'net{b}':sum(weights[a['_atr_state']]*net(a,b) for a in rows if year(a)==y) for b in (6,8,10,12,15,20)} | {'n':sum(year(a)==y for a in rows),'exposure_units':sum(weights[a['_atr_state']] for a in rows if year(a)==y)} for y in (2024,2025,2026)}
    # Capital-neutral view: scale each policy so mean size across the same trades equals 1.0.
    scale=1/avg_size if avg_size else 1
    totals['normalized_to_avg_size1']={
      'scale_factor':scale,
      'net6':totals['weighted_net_r_6bps']*scale,
      'net8':totals['weighted_net_r_8bps']*scale,
      'net10':totals['weighted_net_r_10bps']*scale,
      'net12':totals['weighted_net_r_12bps']*scale,
      'net15':totals['weighted_net_r_15bps']*scale,
      'net20':totals['weighted_net_r_20bps']*scale,
      'maxdd_net6':maxdd*scale,
      'net6_to_abs_maxdd':totals['net6_to_abs_maxdd'],
    }
    return totals

results={k:evaluate(PF,w) for k,w in POLICIES.items()}
base=results['BASE_1_1']
comparison={}
for k,v in results.items():
    comparison[k]={
      'raw_delta_net6_vs_base':v['weighted_net_r_6bps']-base['weighted_net_r_6bps'],
      'raw_delta_maxdd_vs_base':v['max_drawdown_net6_r']-base['max_drawdown_net6_r'],
      'return_dd_ratio_vs_base':(v['net6_to_abs_maxdd']/base['net6_to_abs_maxdd']) if base['net6_to_abs_maxdd'] else None,
      'normalized_net6_delta_vs_base':v['normalized_to_avg_size1']['net6']-base['weighted_net_r_6bps'],
      'positive_month_delta_vs_base':v['positive_months']-base['positive_months'],
    }

report={
 'status':'WR_ATR_SIZING_OVERLAY_COMPLETE',
 'parent_regime':'Exact Zone C 10m AND BTC 30d return < 0 AND BTC RV20 > RV60.',
 'atr_definition':'ALT normalized ATR14 > ATR60 using only fully closed daily candles before trade.',
 'policy_note':'Four policies were predeclared before this run. This run does not search thresholds. Candidate ATR feature itself was discovered retrospectively, so results are not pristine OOS.',
 'feature_coverage_n':len(PF),'atr_state_counts':counts,
 'policies':POLICIES,'results':results,'comparison':comparison,
}
json.dump(report,open(OUT/'atr_sizing_overlay_report.json','w'),indent=2)
print(json.dumps(report,indent=2))