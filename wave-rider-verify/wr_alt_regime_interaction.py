import csv,io,json,math,statistics,zipfile,time
from collections import defaultdict
from datetime import datetime,timezone
from pathlib import Path
import requests

A24=Path('/tmp/a24'); A25=Path('/tmp/a25'); OUT=Path('/tmp/final4'); OUT.mkdir(parents=True,exist_ok=True)

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
def year(a): return datetime.fromtimestamp(a['signal_time']/1000,tz=timezone.utc).year
def stat(xs):
    z={'n':len(xs),'gross_r':sum(a['R'] for a in xs)}
    for b in (4,6,8,10,12): z[f'net_r_{b}bps']=sum(net(a,b) for a in xs)
    z['avg_net6_r']=z['net_r_6bps']/z['n'] if z['n'] else None
    return z

def sd(xs): return statistics.stdev(xs) if len(xs)>=2 else None

S=requests.Session(); S.headers['User-Agent']='runner3-wr-alt-regime/1.0'

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
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        text=z.read(z.namelist()[0]).decode()
    for row in csv.reader(io.StringIO(text)):
        if row and row[0].isdigit():
            # Binance kline: open time, O,H,L,C,base vol,close time,quote vol,...
            qv=float(row[7]) if len(row)>7 else float(row[5])*float(row[4])
            out.append({'t':int(row[0]),'o':float(row[1]),'h':float(row[2]),'l':float(row[3]),'c':float(row[4]),'qv':qv})
    return out

# First recreate frozen BTC gate using fully closed daily bars.
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
    ret30=c[-1]/c[-31]-1; v20=(sd(lr[-20:]) or 0); v60=(sd(lr[-60:]) or 0)
    return ret30<0 and v20>v60

F=[a for a in T if 2024<=year(a)<=2026 and btc_gate(a['signal_time'])]

# Download only daily months needed for symbols that actually appear in frozen regime.
need=defaultdict(set)
for a in F:
    dt=datetime.fromtimestamp(a['signal_time']/1000,tz=timezone.utc)
    # Need current month plus prior 3 calendar months for >=70 closed days.
    y,m=dt.year,dt.month
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

def alt_features(a):
    h=[b for b in cache.get(a['symbol'],[]) if b['t']+86400000<=a['signal_time']]
    if len(h)<70:return None
    c=[b['c'] for b in h]; lr=[math.log(c[i]/c[i-1]) for i in range(1,len(c))]
    rv20=(sd(lr[-20:]) or 0); rv60=(sd(lr[-60:]) or 0)
    trs=[]
    for i in range(1,len(h)):
        prev=h[i-1]['c']; b=h[i]
        trs.append(max(b['h']-b['l'],abs(b['h']-prev),abs(b['l']-prev))/prev)
    atr14=sum(trs[-14:])/14; atr60=sum(trs[-60:])/60
    qv7=sum(b['qv'] for b in h[-7:])/7; qv30=sum(b['qv'] for b in h[-30:])/30
    return {'rv':'HIGH' if rv20>rv60 else 'LOW','atr':'HIGH' if atr14>atr60 else 'LOW','liq':'HIGH' if qv7>qv30 else 'LOW',
            'rv_ratio':rv20/rv60 if rv60 else None,'atr_ratio':atr14/atr60 if atr60 else None,'liq_ratio':qv7/qv30 if qv30 else None}

FF=[]
for a in F:
    f=alt_features(a)
    if f:
        a['_alt']=f; FF.append(a)

models={
 'ALT_RV':lambda a:a['_alt']['rv'],
 'ALT_ATR':lambda a:a['_alt']['atr'],
 'ALT_LIQ':lambda a:a['_alt']['liq'],
 'ALT_RV_X_LIQ':lambda a:a['_alt']['rv']+'_'+a['_alt']['liq'],
 'ALT_ATR_X_LIQ':lambda a:a['_alt']['atr']+'_'+a['_alt']['liq'],
}

def summarize(fn):
    groups=defaultdict(list)
    for a in FF: groups[fn(a)].append(a)
    out={}
    for k,xs in sorted(groups.items()):
        out[k]={'total':stat(xs),'by_year':{str(y):stat([a for a in xs if year(a)==y]) for y in (2024,2025,2026)}}
    return out

# Interaction with previously diagnostic stop bands only; do not select a deployment rule here.
stopbands={'LT_0.4':lambda a:a['stop_pct']<0.4,'0.4_TO_0.8':lambda a:0.4<=a['stop_pct']<0.8,'GE_0.8':lambda a:a['stop_pct']>=0.8}
stop_inter={}
for model,fn in models.items():
    z={}
    for mk in sorted(set(fn(a) for a in FF)):
        for sk,sf in stopbands.items():
            xs=[a for a in FF if fn(a)==mk and sf(a)]
            z[mk+'__'+sk]={'total':stat(xs),'by_year':{str(y):stat([a for a in xs if year(a)==y]) for y in (2024,2025,2026)}}
    stop_inter[model]=z

report={
 'status':'WR_ALT_REGIME_INTERACTION_COMPLETE',
 'frozen_parent_regime':'BTC 30d return < 0 AND BTC RV20 > RV60; exact Zone C 10m.',
 'feature_policy':'Altcoin daily features use only fully closed candles before each trade. RV=20d stdev vs 60d; ATR=14d normalized true range vs 60d; LIQ=7d avg quote volume vs 30d.',
 'warning':'Retrospective diagnostic only. No altcoin sub-gate is promoted from this run.',
 'coverage':{'frozen_trades':len(F),'with_alt_features':len(FF),'coverage_pct':100*len(FF)/len(F) if F else 0,'symbols_requested':len(need)},
 'parent_by_year':{str(y):stat([a for a in F if year(a)==y]) for y in (2024,2025,2026)},
 'feature_models':{k:summarize(fn) for k,fn in models.items()},
 'stop_interactions':stop_inter,
}
json.dump(report,open(OUT/'alt_regime_interaction_report.json','w'),indent=2)
print(json.dumps(report,indent=2))
