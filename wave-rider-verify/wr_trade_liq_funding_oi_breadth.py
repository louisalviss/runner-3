import csv,io,json,math,statistics,zipfile,time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor,as_completed
from datetime import datetime,timezone
from pathlib import Path
import requests

A24=Path('/tmp/a24'); A25=Path('/tmp/a25'); OUT=Path('/tmp/final7'); OUT.mkdir(parents=True,exist_ok=True)

def load_jsonl(p):
    out=[]
    with open(p) as f:
        for line in f:
            if line.strip(): out.append(json.loads(line))
    return out
seen=set(); T=[]
for a in load_jsonl(A24/'all_trades.jsonl')+load_jsonl(A25/'trades.jsonl'):
    k=(a['symbol'],a['signal_time'],a['entry'],a['stop'])
    if k not in seen: seen.add(k); T.append(a)
T.sort(key=lambda a:(a['signal_time'],a['symbol']))

def dt(a): return datetime.fromtimestamp(a['signal_time']/1000,tz=timezone.utc)
def year(a): return dt(a).year
def net(a,bps=6): return a['R']-(a['entry']/abs(a['entry']-a['stop']))*bps/10000
def sd(x): return statistics.stdev(x) if len(x)>=2 else 0

def getzip(url,tries=3):
    for i in range(tries):
        try:
            r=requests.get(url,timeout=25,headers={'User-Agent':'runner3-wr-liq-fund-oi/1.0'})
            if r.status_code==404:return None
            r.raise_for_status(); return r.content
        except Exception:
            if i==tries-1:return None
            time.sleep(.4*(i+1))

def unzip_rows(data):
    if not data:return []
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as z: txt=z.read(z.namelist()[0]).decode(errors='ignore')
        return list(csv.reader(io.StringIO(txt)))
    except Exception:return []

def daily_rows(data):
    rows=unzip_rows(data); out=[]
    for r in rows:
        if r and r[0].isdigit() and len(r)>7:
            out.append({'t':int(r[0]),'c':float(r[4]),'qv':float(r[7])})
    return out

def funding_rows(data):
    rows=unzip_rows(data); out=[]
    if not rows:return out
    header=[x.lower() for x in rows[0]]
    has_header=any('fund' in x or 'time' in x for x in header)
    start=1 if has_header else 0
    ti=next((i for i,x in enumerate(header) if 'time' in x),0) if has_header else 0
    fi=next((i for i,x in enumerate(header) if 'fund' in x and 'rate' in x),None) if has_header else None
    for r in rows[start:]:
        try:
            if fi is None:
                # Common Data Vision fundingRate layout ends with last_funding_rate.
                cand=[i for i,x in enumerate(r) if i!=ti]
                vals=[]
                for i in cand:
                    try:
                        v=float(r[i]);
                        if abs(v)<0.1: vals.append((i,v))
                    except: pass
                if not vals: continue
                i,v=vals[-1]
            else: v=float(r[fi])
            ts=int(float(r[ti]))
            if ts<10**12: ts*=1000
            out.append({'t':ts,'fund':v})
        except: pass
    return out

def metric_rows(data):
    rows=unzip_rows(data); out=[]
    if not rows:return out
    h=[x.lower() for x in rows[0]]
    if not any('open_interest' in x for x in h): return out
    ti=next((i for i,x in enumerate(h) if 'create_time' in x or x=='time' or 'timestamp' in x),0)
    oi=next((i for i,x in enumerate(h) if x=='sum_open_interest'),None)
    if oi is None: oi=next((i for i,x in enumerate(h) if 'open_interest' in x and 'value' not in x),None)
    if oi is None:return out
    for r in rows[1:]:
        try:
            s=r[ti]
            if s.isdigit(): ts=int(s); ts=ts*1000 if ts<10**12 else ts
            else: ts=int(datetime.fromisoformat(s.replace('Z','+00:00')).timestamp()*1000)
            out.append({'t':ts,'oi':float(r[oi])})
        except: pass
    return out

# Frozen BTC parent gate.
btc=[]
for y in range(2023,2027):
  for m in range(1,13):
    if (y,m)<(2023,4) or (y,m)>(2026,8): continue
    fn=f'BTCUSDT-1d-{y:04d}-{m:02d}.zip'; u=f'https://data.binance.vision/data/futures/um/monthly/klines/BTCUSDT/1d/{fn}'
    btc+=daily_rows(getzip(u))
btc=sorted({b['t']:b for b in btc}.values(),key=lambda x:x['t'])
def btc_gate(ts):
    h=[b for b in btc if b['t']+86400000<=ts]
    if len(h)<70:return False
    c=[b['c'] for b in h]; lr=[math.log(c[i]/c[i-1]) for i in range(1,len(c))]
    return c[-1]/c[-31]-1<0 and sd(lr[-20:])>sd(lr[-60:])
P=[a for a in T if 2024<=year(a)<=2026 and btc_gate(a['signal_time'])]
expected={2024:317,2025:1050,2026:645}; actual={y:sum(year(a)==y for a in P) for y in expected}
if actual!=expected: raise RuntimeError(f'PARENT_PARITY_FAIL {actual}')

# Months needed per symbol, plus prior month for trailing features.
need=defaultdict(set)
for a in P:
    d=dt(a); y,m=d.year,d.month
    for k in range(2):
        yy,mm=y,m-k
        while mm<=0: yy-=1; mm+=12
        need[a['symbol']].add((yy,mm))

cache={s:{'d':[],'f':[],'oi':[]} for s in need}
def fetch_one(args):
    s,y,m=args
    base='https://data.binance.vision/data/futures/um/monthly'
    fn=f'{s}-1d-{y:04d}-{m:02d}.zip'; d=daily_rows(getzip(f'{base}/klines/{s}/1d/{fn}'))
    ff=f'{s}-fundingRate-{y:04d}-{m:02d}.zip'; f=funding_rows(getzip(f'{base}/fundingRate/{s}/{ff}'))
    mf=f'{s}-metrics-{y:04d}-{m:02d}.zip'; oi=metric_rows(getzip(f'{base}/metrics/{s}/{mf}'))
    return s,d,f,oi
jobs=[(s,y,m) for s,ms in need.items() for y,m in ms]
with ThreadPoolExecutor(max_workers=18) as ex:
    fut=[ex.submit(fetch_one,j) for j in jobs]
    for i,q in enumerate(as_completed(fut)):
        s,d,f,oi=q.result(); cache[s]['d']+=d; cache[s]['f']+=f; cache[s]['oi']+=oi
        if i%200==0: print('FILES',i,'/',len(jobs),flush=True)
for s in cache:
    for k in cache[s]: cache[s][k]=sorted({x['t']:x for x in cache[s][k]}.values(),key=lambda x:x['t'])

# 20-asset market breadth proxy, full daily history. Predeclared fixed basket.
basket=['ETHUSDT','SOLUSDT','XRPUSDT','BNBUSDT','DOGEUSDT','ADAUSDT','LINKUSDT','AVAXUSDT','DOTUSDT','LTCUSDT','BCHUSDT','TRXUSDT','SUIUSDT','AAVEUSDT','UNIUSDT','NEARUSDT','ETCUSDT','FILUSDT','ICPUSDT','APTUSDT']
bars20={s:[] for s in basket}
def fetch_basket(args):
    s,y,m=args; fn=f'{s}-1d-{y:04d}-{m:02d}.zip'; u=f'https://data.binance.vision/data/futures/um/monthly/klines/{s}/1d/{fn}'
    return s,daily_rows(getzip(u))
bj=[(s,y,m) for s in basket for y in range(2023,2027) for m in range(1,13) if (y,m)>=(2023,9) and (y,m)<=(2026,8)]
with ThreadPoolExecutor(max_workers=18) as ex:
    for q in as_completed([ex.submit(fetch_basket,j) for j in bj]):
        s,d=q.result(); bars20[s]+=d
for s in bars20: bars20[s]=sorted({x['t']:x for x in bars20[s]}.values(),key=lambda x:x['t'])

def features(a):
    ts=a['signal_time']; z=cache.get(a['symbol'],{})
    d=[x for x in z.get('d',[]) if x['t']+86400000<=ts]
    f=[x for x in z.get('f',[]) if x['t']<ts]
    oi=[x for x in z.get('oi',[]) if x['t']<ts]
    out={}
    if len(d)>=30:
        q7=sum(x['qv'] for x in d[-7:])/7; q30=sum(x['qv'] for x in d[-30:])/30
        out['liq']='HIGH' if q7>q30 else 'LOW'
    if f:
        out['fund']='POS' if f[-1]['fund']>0 else ('NEG' if f[-1]['fund']<0 else 'ZERO')
        if len(f)>=3: out['fund3']='POS' if sum(x['fund'] for x in f[-3:])/3>0 else 'NONPOS'
    if len(oi)>=2:
        last=oi[-1]; old=min(oi,key=lambda x:abs(x['t']-(last['t']-86400000)))
        if old['oi']>0 and old['t']<last['t']: out['oi1d']='UP' if last['oi']/old['oi']-1>0 else 'DOWN'
    vals=[]
    for s,b in bars20.items():
        h=[x for x in b if x['t']+86400000<=ts]
        if len(h)>=21: vals.append(h[-1]['c']/h[-21]['c']-1>0)
    if len(vals)>=10:
        br=sum(vals)/len(vals); out['breadth']='BROAD_UP' if br>0.5 else 'BROAD_DOWN'; out['breadth_value']=br; out['breadth_n']=len(vals)
    return out

F=[]
for a in P:
    x=features(a); b=dict(a); b['_x']=x; F.append(b)

def stat(xs):
    return {'n':len(xs),'net6':sum(net(a,6) for a in xs),'net8':sum(net(a,8) for a in xs),'net10':sum(net(a,10) for a in xs),'net12':sum(net(a,12) for a in xs),'avg_net6':sum(net(a,6) for a in xs)/len(xs) if xs else None}
def model(key):
    groups=defaultdict(list)
    for a in F:
        v=a['_x'].get(key)
        if v is not None: groups[v].append(a)
    return {str(k):{'total':stat(v),'by_year':{str(y):stat([a for a in v if year(a)==y]) for y in (2024,2025,2026)}} for k,v in sorted(groups.items())}
def cross(k1,k2):
    groups=defaultdict(list)
    for a in F:
        x=a['_x'];
        if k1 in x and k2 in x: groups[f'{x[k1]}__{x[k2]}'].append(a)
    return {k:{'total':stat(v),'by_year':{str(y):stat([a for a in v if year(a)==y]) for y in (2024,2025,2026)}} for k,v in sorted(groups.items())}
coverage={k:sum(k in a['_x'] for a in F) for k in ['liq','fund','fund3','oi1d','breadth']}
report={
 'status':'WR_TRADE_LIQ_FUNDING_OI_BREADTH_COMPLETE',
 'warning':'Retrospective diagnostic only. No subgroup from this run is promoted. All features use observations strictly before trade; breadth uses a fixed 20-asset futures basket and prior closed daily bars.',
 'parent':{'n':len(P),'by_year':actual,'net6':sum(net(a,6) for a in P)},
 'coverage':coverage,
 'single_models':{k:model(k) for k in ['liq','fund','fund3','oi1d','breadth']},
 'predeclared_interactions':{
   'LIQ_X_OI':cross('liq','oi1d'),
   'LIQ_X_FUND3':cross('liq','fund3'),
   'BREADTH_X_OI':cross('breadth','oi1d'),
   'BREADTH_X_FUND3':cross('breadth','fund3'),
   'BREADTH_X_LIQ':cross('breadth','liq')
 }
}
json.dump(report,open(OUT/'trade_liq_funding_oi_breadth.json','w'),indent=2)
print(json.dumps(report,indent=2))