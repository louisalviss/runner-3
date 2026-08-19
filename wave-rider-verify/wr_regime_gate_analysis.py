import csv,io,json,math,os,statistics,zipfile
from collections import defaultdict
from datetime import datetime,timezone
from pathlib import Path
import requests

A24=Path('/tmp/a24')
A25=Path('/tmp/a25')
OUT=Path('/tmp/final'); OUT.mkdir(parents=True,exist_ok=True)

def load_jsonl(path):
    out=[]
    with open(path) as f:
        for line in f:
            if line.strip(): out.append(json.loads(line))
    return out

t24=load_jsonl(A24/'all_trades.jsonl')
t25=load_jsonl(A25/'trades.jsonl')
# Deduplicate defensively.
seen=set(); T=[]
for a in t24+t25:
    k=(a['symbol'],a['signal_time'],a['entry'],a['stop'])
    if k not in seen:
        seen.add(k); T.append(a)
T.sort(key=lambda a:(a['signal_time'],a['symbol']))

def net(a,bps): return a['R']-(a['entry']/abs(a['entry']-a['stop']))*bps/10000

def month_key(ts):
    d=datetime.fromtimestamp(ts/1000,tz=timezone.utc)
    return (d.year,d.month)

by_month=defaultdict(list)
for a in T: by_month[month_key(a['signal_time'])].append(a)

# Load BTCUSDT futures daily candles from Binance Vision monthly archives.
s=requests.Session(); s.headers['User-Agent']='runner3-wr-regime-gate/1.0'
def getzip(url):
    r=s.get(url,timeout=60)
    if r.status_code==404:return None
    r.raise_for_status(); return r.content

def read_daily(data):
    if not data:return []
    out=[]
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        text=z.read(z.namelist()[0]).decode()
    for row in csv.reader(io.StringIO(text)):
        if row and row[0].isdigit():
            out.append({'t':int(row[0]),'o':float(row[1]),'h':float(row[2]),'l':float(row[3]),'c':float(row[4])})
    return out

bars=[]
for y in range(2023,2027):
    for m in range(1,13):
        if (y,m)<(2023,5) or (y,m)>(2026,8): continue
        fn=f'BTCUSDT-1d-{y:04d}-{m:02d}.zip'
        url=f'https://data.binance.vision/data/futures/um/monthly/klines/BTCUSDT/1d/{fn}'
        try: bars.extend(read_daily(getzip(url)))
        except Exception as e: print('BTC_FETCH_ERR',fn,repr(e),flush=True)
bars=sorted({b['t']:b for b in bars}.values(),key=lambda x:x['t'])

def mean(xs): return sum(xs)/len(xs) if xs else None

def stdev(xs): return statistics.stdev(xs) if len(xs)>=2 else None

def btc_features(y,m):
    start=int(datetime(y,m,1,tzinfo=timezone.utc).timestamp()*1000)
    hist=[b for b in bars if b['t']<start]
    if len(hist)<100:return {}
    c=[b['c'] for b in hist]
    rets=[math.log(c[i]/c[i-1]) for i in range(1,len(c)) if c[i-1]>0 and c[i]>0]
    last=c[-1]
    ret30=last/c[-31]-1 if len(c)>=31 else None
    ret90=last/c[-91]-1 if len(c)>=91 else None
    sma90=mean(c[-90:])
    vol30=(stdev(rets[-30:]) or 0)*math.sqrt(365)
    vol90=(stdev(rets[-90:]) or 0)*math.sqrt(365)
    hi90=max(c[-90:])
    return {
      'btc_ret30':ret30,'btc_ret90':ret90,'btc_above_sma90':last>sma90,
      'btc_vol30':vol30,'btc_vol90':vol90,'btc_vol_ratio':vol30/vol90 if vol90 else None,
      'btc_dd90':last/hi90-1,
    }

def prev_month(y,m):
    m-=1
    if m==0:y-=1;m=12
    return y,m

def prior_zone_features(y,m):
    k=prev_month(y,m); xs=by_month.get(k,[])
    if not xs:return {}
    sy=defaultdict(list)
    for a in xs: sy[a['symbol']].append(a)
    sym_net=[sum(net(a,6) for a in v) for v in sy.values()]
    return {
      'prev_zone_n':len(xs),
      'prev_zone_net6':sum(net(a,6) for a in xs),
      'prev_zone_avg_net6':mean([net(a,6) for a in xs]),
      'prev_zone_breadth':sum(v>0 for v in sym_net)/len(sym_net) if sym_net else None,
      'prev_zone_median_stop':statistics.median(a['stop_pct'] for a in xs),
      'prev_zone_long_share':sum(a['side']=='LONG' for a in xs)/len(xs),
    }

def stat(xs):
    z={'n':len(xs),'gross_r':sum(a['R'] for a in xs)}
    for b in (4,6,8,10,12): z[f'net_r_{b}bps']=sum(net(a,b) for a in xs)
    z['avg_net6_r']=z['net_r_6bps']/z['n'] if z['n'] else None
    return z

months=[]
for y,m in sorted(k for k in by_month if (2024,1)<=k<=(2026,8)):
    f={'month':f'{y}-{m:02d}','year':y,'month_num':m}
    f.update(btc_features(y,m)); f.update(prior_zone_features(y,m))
    f['baseline']=stat(by_month[(y,m)])
    months.append(f)

# Predeclared, simple, month-start-known gates. No threshold fitting beyond zero/1/0.5.
def g_all(f): return True
def g_trend90(f): return f.get('btc_ret90') is not None and f['btc_ret90']>0
def g_above90(f): return bool(f.get('btc_above_sma90'))
def g_vol_expand(f): return f.get('btc_vol_ratio') is not None and f['btc_vol_ratio']>1
def g_prev_pnl(f): return f.get('prev_zone_net6') is not None and f['prev_zone_net6']>0
def g_prev_breadth(f): return f.get('prev_zone_breadth') is not None and f['prev_zone_breadth']>0.5
def g_trend_prev_pnl(f): return g_trend90(f) and g_prev_pnl(f)
def g_trend_prev_breadth(f): return g_trend90(f) and g_prev_breadth(f)
def g_riskoff_avoid(f):
    r=f.get('btc_ret90'); v=f.get('btc_vol_ratio')
    return r is not None and v is not None and not (r<0 and v>1)

gates={
 'ALL':g_all,
 'BTC_RET90_POS':g_trend90,
 'BTC_ABOVE_SMA90':g_above90,
 'BTC_VOL30_GT_VOL90':g_vol_expand,
 'PREV_ZONE_NET6_POS':g_prev_pnl,
 'PREV_ZONE_BREADTH_GT_50':g_prev_breadth,
 'BTC_RET90_POS_AND_PREV_ZONE_NET6_POS':g_trend_prev_pnl,
 'BTC_RET90_POS_AND_PREV_ZONE_BREADTH_GT_50':g_trend_prev_breadth,
 'AVOID_NEG_TREND_HIGH_VOL':g_riskoff_avoid,
}

reports={}
for name,fn in gates.items():
    chosen=[f for f in months if fn(f)]
    chosen_keys={(int(f['month'][:4]),int(f['month'][5:7])) for f in chosen}
    xs=[a for a in T if month_key(a['signal_time']) in chosen_keys and (2024,1)<=month_key(a['signal_time'])<=(2026,8)]
    byy={}
    for y in (2024,2025,2026):
        yy=[a for a in xs if month_key(a['signal_time'])[0]==y]
        byy[str(y)]=stat(yy)
    reports[name]={
      'months_selected':[f['month'] for f in chosen],
      'n_months':len(chosen),
      'total':stat(xs),
      'by_year':byy,
      'positive_selected_months_net6':sum(f['baseline']['net_r_6bps']>0 for f in chosen),
    }

# Retrospective selection using 2024-2025 only: require both years net6 >= 0, then rank by combined net6.
train_rank=[]
for name,r in reports.items():
    a=r['by_year']['2024']['net_r_6bps']; b=r['by_year']['2025']['net_r_6bps']
    if a>=0 and b>=0 and name!='ALL': train_rank.append((a+b,name))
train_rank.sort(reverse=True)
selected_train_gate=train_rank[0][1] if train_rank else None

report={
 'status':'WR_REGIME_GATE_DIAGNOSTIC_COMPLETE',
 'scope':'exact Zone C 10m trades 2024-01 through 2026-08; BTC features known at each month start',
 'warning':'Retrospective diagnostic only. 2026 is not pristine untouched OOS because aggregate 2026 behavior was already observed before this analysis.',
 'features':'BTC trailing 30/90d return, SMA90 state, 30/90d realized vol ratio, 90d drawdown; prior-month Zone C aggregate net6/breadth/activity/stop/long share',
 'months':months,
 'gates':reports,
 'train_2024_2025_gate_candidates_ranked':train_rank,
 'train_selected_gate':selected_train_gate,
 'train_selected_gate_2026_diagnostic':reports[selected_train_gate]['by_year']['2026'] if selected_train_gate else None,
}
json.dump(report,open(OUT/'regime_report.json','w'),indent=2)
print(json.dumps({k:v for k,v in report.items() if k!='months'},indent=2))
