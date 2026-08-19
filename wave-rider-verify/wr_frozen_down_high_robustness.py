import csv,io,json,math,random,statistics,zipfile
from collections import defaultdict
from datetime import datetime,timezone
from pathlib import Path
import requests

A24=Path('/tmp/a24'); A25=Path('/tmp/a25'); OUT=Path('/tmp/final3'); OUT.mkdir(parents=True,exist_ok=True)

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

s=requests.Session(); s.headers['User-Agent']='runner3-wr-frozen-regime/1.0'
def getzip(url):
    r=s.get(url,timeout=60)
    if r.status_code==404:return None
    r.raise_for_status(); return r.content

def read_daily(data):
    if not data:return []
    out=[]
    with zipfile.ZipFile(io.BytesIO(data)) as z: text=z.read(z.namelist()[0]).decode()
    for row in csv.reader(io.StringIO(text)):
        if row and row[0].isdigit(): out.append({'t':int(row[0]),'c':float(row[4])})
    return out

bars=[]
for y in range(2023,2027):
    for m in range(1,13):
        if (y,m)<(2023,4) or (y,m)>(2026,8): continue
        fn=f'BTCUSDT-1d-{y:04d}-{m:02d}.zip'
        u=f'https://data.binance.vision/data/futures/um/monthly/klines/BTCUSDT/1d/{fn}'
        try: bars.extend(read_daily(getzip(u)))
        except Exception as e: print('FETCH_ERR',fn,repr(e),flush=True)
bars=sorted({b['t']:b for b in bars}.values(),key=lambda b:b['t'])

def sd(xs): return statistics.stdev(xs) if len(xs)>=2 else None

def frozen_match(ts):
    h=[b for b in bars if b['t']+86400000<=ts]
    if len(h)<70:return False
    c=[b['c'] for b in h]
    ret30=c[-1]/c[-31]-1
    lr=[math.log(c[i]/c[i-1]) for i in range(1,len(c))]
    v20=(sd(lr[-20:]) or 0)*math.sqrt(365); v60=(sd(lr[-60:]) or 0)*math.sqrt(365)
    return ret30<0 and v20>v60

S=[a for a in T if 2024<=year(a)<=2026 and frozen_match(a['signal_time'])]

# Ordered equity / drawdown at net6.
eq=0; peak=0; maxdd=0; dd_start=None; worst=None
for a in S:
    eq += net(a,6)
    if eq>peak:
        peak=eq; dd_start=dt(a).isoformat()
    dd=eq-peak
    if dd<maxdd:
        maxdd=dd; worst={'time':dt(a).isoformat(),'equity':eq,'peak':peak,'drawdown':dd,'peak_time':dd_start}

# Month profile.
by_month={m:stat([a for a in S if month(a)==m]) for m in sorted({month(a) for a in S})}
pos_months=sum(1 for v in by_month.values() if v['net_r_6bps']>0)
neg_months=sum(1 for v in by_month.values() if v['net_r_6bps']<0)

# Leave-one-month-out.
loo={}
for m in by_month:
    xs=[a for a in S if month(a)!=m]
    loo[m]=stat(xs)['net_r_6bps']

# Bootstrap trade-level and month-block net6 expectancy.
rng=random.Random(20260819)
vals=[net(a,6) for a in S]
def pct(xs,p):
    z=sorted(xs); i=(len(z)-1)*p; lo=int(math.floor(i)); hi=int(math.ceil(i))
    return z[lo] if lo==hi else z[lo]*(hi-i)+z[hi]*(i-lo)
trade_boot=[]
for _ in range(5000): trade_boot.append(sum(rng.choice(vals) for _ in vals)/len(vals))
month_vals={m:[net(a,6) for a in S if month(a)==m] for m in by_month}
months=list(month_vals)
block_boot=[]
for _ in range(5000):
    picks=[rng.choice(months) for __ in months]
    vv=[x for m in picks for x in month_vals[m]]
    block_boot.append(sum(vv)/len(vv) if vv else 0)

# Side contribution.
by_side={side:{'total':stat([a for a in S if a['side']==side]),'by_year':{str(y):stat([a for a in S if a['side']==side and year(a)==y]) for y in (2024,2025,2026)}} for side in sorted({a['side'] for a in S})}

# Stop interaction, fixed predeclared bands.
bands={'LT_0.4':lambda a:a['stop_pct']<0.4,'0.4_TO_0.8':lambda a:0.4<=a['stop_pct']<0.8,'GE_0.8':lambda a:a['stop_pct']>=0.8}
stop_interaction={k:{'total':stat([a for a in S if fn(a)]),'by_year':{str(y):stat([a for a in S if fn(a) and year(a)==y]) for y in (2024,2025,2026)}} for k,fn in bands.items()}

# Symbol concentration.
sym=defaultdict(list)
for a in S:sym[a['symbol']].append(a)
sym_rows=[]
for k,xs in sym.items():
    st=stat(xs); sym_rows.append((st['net_r_6bps'],k,st['n']))
sym_rows.sort(reverse=True)
base6=stat(S)['net_r_6bps']
concentration={
 'top_symbols':[{'symbol':k,'n':n,'net6':v} for v,k,n in sym_rows[:15]],
 'top5_positive_share':sum(max(0,v) for v,_,_ in sym_rows[:5])/sum(max(0,v) for v,_,_ in sym_rows) if sum(max(0,v) for v,_,_ in sym_rows) else None,
 'remove_top1_net6':stat([a for a in S if a['symbol']!=sym_rows[0][1]])['net_r_6bps'] if sym_rows else None,
 'remove_top5_net6':stat([a for a in S if a['symbol'] not in {k for _,k,_ in sym_rows[:5]}])['net_r_6bps'] if sym_rows else None,
 'remove_top10_net6':stat([a for a in S if a['symbol'] not in {k for _,k,_ in sym_rows[:10]}])['net_r_6bps'] if sym_rows else None,
}

# Event split only if a usable field exists; otherwise explicit unavailable.
event_keys=[k for k in ('event','event_type','macro_event','is_event','event_day') if any(k in a for a in S)]
event_split={'status':'UNAVAILABLE_IN_TRADE_ARTIFACT','detected_keys':event_keys}
if event_keys:
    k=event_keys[0]
    groups=defaultdict(list)
    for a in S: groups[str(a.get(k))].append(a)
    event_split={'status':'AVAILABLE','field':k,'groups':{g:stat(xs) for g,xs in groups.items()}}

report={
 'status':'WR_FROZEN_DOWN_HIGH_ROBUSTNESS_COMPLETE',
 'frozen_definition':'BTC 30d return < 0 AND BTC 20d realized volatility > 60d realized volatility, using only fully closed BTC daily candles before each trade. Exact Zone C 10m trades only.',
 'warning':'Retrospective robustness test. Definition is frozen from prior diagnostic; 2026 is not pristine OOS.',
 'total':stat(S),
 'by_year':{str(y):stat([a for a in S if year(a)==y]) for y in (2024,2025,2026)},
 'month_profile':by_month,
 'positive_months':pos_months,'negative_months':neg_months,
 'max_drawdown_net6_r':maxdd,'max_drawdown_detail':worst,
 'leave_one_month_out_net6':{'min':min(loo.values()) if loo else None,'max':max(loo.values()) if loo else None,'values':loo},
 'bootstrap_trade_mean_net6_95ci':[pct(trade_boot,.025),pct(trade_boot,.975)],
 'bootstrap_month_block_mean_net6_95ci':[pct(block_boot,.025),pct(block_boot,.975)],
 'side_contribution':by_side,
 'stop_width_interaction':stop_interaction,
 'symbol_concentration':concentration,
 'event_split':event_split,
}
json.dump(report,open(OUT/'frozen_down_high_robustness.json','w'),indent=2)
print(json.dumps(report,indent=2))
