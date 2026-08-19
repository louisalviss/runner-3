import csv,io,json,math,statistics,zipfile
from collections import defaultdict
from datetime import datetime,timezone
from pathlib import Path
import requests

A24=Path('/tmp/a24'); A25=Path('/tmp/a25'); OUT=Path('/tmp/final2'); OUT.mkdir(parents=True,exist_ok=True)

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

s=requests.Session(); s.headers['User-Agent']='runner3-wr-trade-regime/1.0'
def getzip(url):
    r=s.get(url,timeout=60)
    if r.status_code==404:return None
    r.raise_for_status(); return r.content

def read_daily(data):
    if not data:return []
    out=[]
    with zipfile.ZipFile(io.BytesIO(data)) as z: text=z.read(z.namelist()[0]).decode()
    for row in csv.reader(io.StringIO(text)):
        if row and row[0].isdigit():
            out.append({'t':int(row[0]),'o':float(row[1]),'h':float(row[2]),'l':float(row[3]),'c':float(row[4]),'v':float(row[5])})
    return out

bars=[]
for y in range(2023,2027):
    for m in range(1,13):
        if (y,m)<(2023,4) or (y,m)>(2026,8):continue
        fn=f'BTCUSDT-1d-{y:04d}-{m:02d}.zip'
        u=f'https://data.binance.vision/data/futures/um/monthly/klines/BTCUSDT/1d/{fn}'
        try: bars.extend(read_daily(getzip(u)))
        except Exception as e: print('FETCH_ERR',fn,repr(e),flush=True)
bars=sorted({b['t']:b for b in bars}.values(),key=lambda b:b['t'])

def sd(xs): return statistics.stdev(xs) if len(xs)>=2 else None

def features(ts):
    # Only candles fully closed before signal time.
    h=[b for b in bars if b['t']+86400000<=ts]
    if len(h)<70:return None
    c=[b['c'] for b in h]
    ret30=c[-1]/c[-31]-1
    lr=[math.log(c[i]/c[i-1]) for i in range(1,len(c))]
    v20=(sd(lr[-20:]) or 0)*math.sqrt(365); v60=(sd(lr[-60:]) or 0)*math.sqrt(365)
    trs=[]
    for i in range(1,len(h)):
        prev=h[i-1]['c']; b=h[i]
        trs.append(max(b['h']-b['l'],abs(b['h']-prev),abs(b['l']-prev))/prev)
    atr14=sum(trs[-14:])/14; atr60=sum(trs[-60:])/60
    vol7=sum(b['v'] for b in h[-7:])/7; vol30=sum(b['v'] for b in h[-30:])/30
    return {
      'trend':'UP' if ret30>0 else 'DOWN',
      'rv':'HIGH' if v20>v60 else 'LOW',
      'atr':'HIGH' if atr14>atr60 else 'LOW',
      'liq':'HIGH' if vol7>vol30 else 'LOW',
      'ret30':ret30,'rv_ratio':v20/v60 if v60 else None,'atr_ratio':atr14/atr60 if atr60 else None,'vol_ratio':vol7/vol30 if vol30 else None,
    }

for i,a in enumerate(T):
    f=features(a['signal_time'])
    if f:a['_reg']=f

T=[a for a in T if '_reg' in a and 2024<=year(a)<=2026]

models={
 'TREND_X_RV': lambda a: f"{a['_reg']['trend']}_{a['_reg']['rv']}",
 'TREND_X_ATR':lambda a: f"{a['_reg']['trend']}_{a['_reg']['atr']}",
 'TREND_X_LIQ':lambda a: f"{a['_reg']['trend']}_{a['_reg']['liq']}",
}

report_models={}
for model,fn in models.items():
    cells=defaultdict(list); cells_side=defaultdict(list)
    for a in T:
        c=fn(a); cells[c].append(a); cells_side[c+'_'+a['side']].append(a)
    def summarize(groups,min_n):
        out={}; survivors=[]
        for c,xs in sorted(groups.items()):
            byy={str(y):stat([a for a in xs if year(a)==y]) for y in (2024,2025,2026)}
            out[c]={'total':stat(xs),'by_year':byy}
            if byy['2024']['n']>=min_n and byy['2025']['n']>=min_n and byy['2024']['net_r_6bps']>0 and byy['2025']['net_r_6bps']>0:
                survivors.append(c)
        selected=[a for a in T if (fn(a) in survivors if groups is cells else fn(a)+'_'+a['side'] in survivors)]
        return out,survivors,{str(y):stat([a for a in selected if year(a)==y]) for y in (2024,2025,2026)},stat(selected)
    a,b,c,d=summarize(cells,200)
    e,f,g,h=summarize(cells_side,100)
    report_models[model]={
      'regime_cells':a,'survivors_2024_2025':b,'survivor_aggregate_by_year':c,'survivor_total':d,
      'regime_side_cells':e,'side_survivors_2024_2025':f,'side_survivor_aggregate_by_year':g,'side_survivor_total':h,
    }

# Fixed stop-width diagnostic layered only after regime results; no survivor selection based on it.
stop_bands={'LT_0.4':lambda a:a['stop_pct']<0.4,'0.4_TO_0.8':lambda a:0.4<=a['stop_pct']<0.8,'GE_0.8':lambda a:a['stop_pct']>=0.8}
stop_diag={}
for k,fn in stop_bands.items():
    xs=[a for a in T if fn(a)]
    stop_diag[k]={'by_year':{str(y):stat([a for a in xs if year(a)==y]) for y in (2024,2025,2026)},'total':stat(xs)}

report={
 'status':'WR_PER_TRADE_REGIME_DIAGNOSTIC_COMPLETE',
 'scope':'Exact Zone C 10m trades 2024-01 through 2026-08; BTC daily features use only fully closed candles before each trade.',
 'warning':'Retrospective diagnostic, not pristine OOS. Survivor definition is predeclared: regime n>=200/year or regime+side n>=100/year, net6>0 independently in both 2024 and 2025; 2026 shown only as diagnostic.',
 'models':report_models,
 'stop_width_diagnostic':stop_diag,
 'baseline_by_year':{str(y):stat([a for a in T if year(a)==y]) for y in (2024,2025,2026)},
}
json.dump(report,open(OUT/'trade_regime_report.json','w'),indent=2)
print(json.dumps(report,indent=2))
