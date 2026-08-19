import csv, io, json, math, statistics, time, zipfile
from bisect import bisect_right
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
import requests

BASE=Path('/tmp/base'); OUT=Path('/tmp/final'); OUT.mkdir(parents=True,exist_ok=True)
BASKET=['ETHUSDT','SOLUSDT','XRPUSDT','BNBUSDT','DOGEUSDT','ADAUSDT','LINKUSDT','AVAXUSDT','DOTUSDT','LTCUSDT','BCHUSDT','TRXUSDT','SUIUSDT','AAVEUSDT','UNIUSDT','NEARUSDT','ETCUSDT','FILUSDT','ICPUSDT','APTUSDT']

# Diagnostic only. The 2x2x2x2 regime dimensions are predeclared:
# BTC 30d UP/DOWN x BTC RV20 HIGH/LOW vs RV60 x breadth UP/DOWN at 50% x funding3 POS/NONPOS.
# No threshold/window changes are allowed after seeing results.

def load_jsonl(p):
    xs=[]
    with open(p) as f:
        for line in f:
            if line.strip(): xs.append(json.loads(line))
    return xs
T=load_jsonl(BASE/'trades.jsonl'); T.sort(key=lambda a:(a['signal_time'],a['symbol']))

def dt(a): return datetime.fromtimestamp(a['signal_time']/1000,tz=timezone.utc)
def net(a,bps=6): return a['R']-(a['entry']/abs(a['entry']-a['stop']))*bps/10000
def sd(x): return statistics.stdev(x) if len(x)>=2 else 0.0

def getzip(url,tries=3):
    for i in range(tries):
        try:
            r=requests.get(url,timeout=25,headers={'User-Agent':'runner3-wr-regime-map/1.0'})
            if r.status_code==404:return None
            r.raise_for_status(); return r.content
        except Exception:
            if i==tries-1:return None
            time.sleep(.35*(i+1))

def rows_zip(data):
    if not data:return []
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            txt=z.read(z.namelist()[0]).decode(errors='ignore')
        return list(csv.reader(io.StringIO(txt)))
    except Exception:return []

def daily_rows(data):
    out=[]
    for r in rows_zip(data):
        try:
            if r and r[0].isdigit() and len(r)>4:out.append((int(r[0]),float(r[4])))
        except:pass
    return out

def funding_rows(data):
    rows=rows_zip(data); out=[]
    if not rows:return out
    h=[x.lower() for x in rows[0]]; has=any('fund' in x or 'time' in x for x in h); start=1 if has else 0
    ti=next((i for i,x in enumerate(h) if 'time' in x),0) if has else 0
    fi=next((i for i,x in enumerate(h) if 'fund' in x and 'rate' in x),None) if has else None
    for r in rows[start:]:
        try:
            if fi is None:
                cand=[]
                for i,x in enumerate(r):
                    if i==ti:continue
                    try:
                        v=float(x)
                        if abs(v)<0.1:cand.append(v)
                    except:pass
                if not cand:continue
                v=cand[-1]
            else:v=float(r[fi])
            ts=int(float(r[ti])); ts=ts*1000 if ts<10**12 else ts
            out.append((ts,v))
        except:pass
    return out

def month_range(y0,m0,y1,m1):
    y,m=y0,m0
    while (y,m)<=(y1,m1):
        yield y,m
        m+=1
        if m==13:y+=1;m=1

def month_prev(y,m):return (y-1,12) if m==1 else (y,m-1)

# Need enough history before first trade for 60d vol and 30d returns.
first=dt(T[0]); last=dt(T[-1]); start_y,start_m=first.year,first.month
# fetch two prior months as buffer
for _ in range(2):start_y,start_m=month_prev(start_y,start_m)
months=list(month_range(start_y,start_m,last.year,last.month))

daily={s:[] for s in ['BTCUSDT']+BASKET}
def fetch_daily(job):
    s,y,m=job; fn=f'{s}-1d-{y:04d}-{m:02d}.zip'; u=f'https://data.binance.vision/data/futures/um/monthly/klines/{s}/1d/{fn}'
    return s,daily_rows(getzip(u))
with ThreadPoolExecutor(max_workers=20) as ex:
    fs=[ex.submit(fetch_daily,(s,y,m)) for s in daily for y,m in months]
    for q in as_completed(fs):
        s,r=q.result(); daily[s]+=r
for s in daily:daily[s]=sorted(dict(daily[s]).items())
daily_times={s:[x[0] for x in arr] for s,arr in daily.items()}

def hist(s,ts):
    arr=daily[s]; i=bisect_right(daily_times[s],ts-86400000); return arr[:i]

market_cache={}
def market_feats(ts):
    day=ts//86400000
    if day in market_cache:return market_cache[day]
    b=hist('BTCUSDT',ts)
    if len(b)<61:
        market_cache[day]=None; return None
    c=[x[1] for x in b]; lr=[math.log(c[i]/c[i-1]) for i in range(1,len(c))]
    btc='BTC_UP' if c[-1]/c[-31]-1>0 else 'BTC_DOWN'
    vol='VOL_HIGH' if sd(lr[-20:])>sd(lr[-60:]) else 'VOL_LOW'
    ups=[]
    for s in BASKET:
        h=hist(s,ts)
        if len(h)>=21:ups.append(h[-1][1]/h[-21][1]-1>0)
    breadth=sum(ups)/len(ups) if len(ups)>=10 else None
    broad=None if breadth is None else ('BREADTH_UP' if breadth>0.5 else 'BREADTH_DOWN')
    market_cache[day]={'btc':btc,'vol':vol,'breadth':broad,'breadth_value':breadth}
    return market_cache[day]

M=[]
for a in T:
    x=market_feats(a['signal_time'])
    if x and x['breadth']:
        b=dict(a); b['_mkt']=x; M.append(b)
print('BASE',len(T),'MARKET_COVERED',len(M),'SYMS',len(set(a['symbol'] for a in T)),flush=True)

# Funding3 for every market-covered symbol/month.
need=defaultdict(set)
for a in M:
    d=dt(a); need[a['symbol']].add((d.year,d.month)); need[a['symbol']].add(month_prev(d.year,d.month))
fund={s:[] for s in need}
def fetch_f(job):
    s,y,m=job; fn=f'{s}-fundingRate-{y:04d}-{m:02d}.zip'; u=f'https://data.binance.vision/data/futures/um/monthly/fundingRate/{s}/{fn}'
    return s,funding_rows(getzip(u))
jobs=[(s,y,m) for s,ms in need.items() for y,m in ms]
with ThreadPoolExecutor(max_workers=24) as ex:
    fs=[ex.submit(fetch_f,j) for j in jobs]
    for i,q in enumerate(as_completed(fs)):
        s,r=q.result(); fund[s]+=r
        if i%500==0:print('FUND_FILES',i,'/',len(jobs),flush=True)
for s in fund:fund[s]=sorted(dict(fund[s]).items())
fund_times={s:[x[0] for x in arr] for s,arr in fund.items()}

F=[]
for a in M:
    arr=fund.get(a['symbol'],[]); times=fund_times.get(a['symbol'],[]); i=bisect_right(times,a['signal_time']-1)
    if i>=3:
        f3=sum(x[1] for x in arr[i-3:i])/3
        b=dict(a); b['_fund3']=f3; b['_fund']='FUND_POS' if f3>0 else 'FUND_NONPOS'; F.append(b)
print('FUND3_COVERED',len(F),'PCT',100*len(F)/len(M) if M else 0,flush=True)

def maxdd(xs,bps=6):
    eq=peak=mdd=0.0
    for a in sorted(xs,key=lambda z:(z['signal_time'],z['symbol'])):
        eq+=net(a,bps); peak=max(peak,eq); mdd=min(mdd,eq-peak)
    return mdd

def m(xs,bps=6):
    vals=[net(a,bps) for a in xs]
    return {'n':len(xs),'net':sum(vals),'avg':statistics.mean(vals) if vals else None,'max_dd':maxdd(xs,bps)}

def month_stats(xs):
    z=defaultdict(float)
    for a in xs:z[dt(a).strftime('%Y-%m')]+=net(a,6)
    return {'active':len(z),'positive':sum(v>0 for v in z.values()),'negative':sum(v<0 for v in z.values()),'worst':min(z.values()) if z else None,'best':max(z.values()) if z else None}

def year_stats(xs):
    years=sorted(set(dt(a).year for a in xs))
    return {str(y):{str(b):m([a for a in xs if dt(a).year==y],b) for b in (6,8,10,12)} for y in years}

def describe(xs):
    return {'costs':{str(b):m(xs,b) for b in (4,6,8,10,12,15,20)},'years':year_stats(xs),'months':month_stats(xs),'long':m([a for a in xs if str(a.get('side','')).upper()=='LONG'],6),'short':m([a for a in xs if str(a.get('side','')).upper()=='SHORT'],6),'symbols':len(set(a['symbol'] for a in xs))}

regimes={}
for btc in ('BTC_UP','BTC_DOWN'):
  for vol in ('VOL_HIGH','VOL_LOW'):
    for br in ('BREADTH_UP','BREADTH_DOWN'):
      for fu in ('FUND_POS','FUND_NONPOS'):
        key='|'.join((btc,vol,br,fu)); xs=[a for a in F if a['_mkt']['btc']==btc and a['_mkt']['vol']==vol and a['_mkt']['breadth']==br and a['_fund']==fu]
        regimes[key]=describe(xs)

# Predeclared aggregate diagnostics to understand each dimension without inventing new thresholds.
aggregates={}
for field,vals in [('btc',('BTC_UP','BTC_DOWN')),('vol',('VOL_HIGH','VOL_LOW')),('breadth',('BREADTH_UP','BREADTH_DOWN'))]:
    for v in vals:aggregates[v]=describe([a for a in F if a['_mkt'][field]==v])
for v in ('FUND_POS','FUND_NONPOS'):aggregates[v]=describe([a for a in F if a['_fund']==v])
# bull-focused predeclared slices
bull_slices={
 'BTC_UP':describe([a for a in F if a['_mkt']['btc']=='BTC_UP']),
 'BTC_UP|BREADTH_UP':describe([a for a in F if a['_mkt']['btc']=='BTC_UP' and a['_mkt']['breadth']=='BREADTH_UP']),
 'BTC_UP|BREADTH_DOWN':describe([a for a in F if a['_mkt']['btc']=='BTC_UP' and a['_mkt']['breadth']=='BREADTH_DOWN']),
 'BTC_UP|VOL_HIGH':describe([a for a in F if a['_mkt']['btc']=='BTC_UP' and a['_mkt']['vol']=='VOL_HIGH']),
 'BTC_UP|VOL_LOW':describe([a for a in F if a['_mkt']['btc']=='BTC_UP' and a['_mkt']['vol']=='VOL_LOW']),
 'BTC_UP|FUND_POS':describe([a for a in F if a['_mkt']['btc']=='BTC_UP' and a['_fund']=='FUND_POS']),
 'BTC_UP|FUND_NONPOS':describe([a for a in F if a['_mkt']['btc']=='BTC_UP' and a['_fund']=='FUND_NONPOS'])
}
ranking=[]
for k,v in regimes.items():
    c=v['costs']['6']; ranking.append({'regime':k,'n':c['n'],'net6':c['net'],'avg6':c['avg'],'dd6':c['max_dd'],'positive_months':v['months']['positive'],'active_months':v['months']['active']})
ranking.sort(key=lambda x:(-999 if x['avg6'] is None else x['avg6']),reverse=True)

report={'status':'WR_FULL_REGIME_MAP_COMPLETE','warning':'Retrospective diagnostic only. 16 regimes and thresholds were predeclared. Do not promote/tune a bull rule from this run without a separately frozen robustness test.','source':{'run_id':32158961561,'artifact':'wr2515-5m-tv-tick-final','base_trades':len(T),'base_symbols':len(set(a['symbol'] for a in T)),'first':dt(T[0]).isoformat(),'last':dt(T[-1]).isoformat()},'coverage':{'market':len(M),'funding3':len(F),'funding3_pct_of_market':100*len(F)/len(M) if M else 0},'definitions':{'btc':'30d return >0 = UP else DOWN','vol':'RV20 > RV60 = HIGH else LOW','breadth':'fixed 20-coin basket share with 20d return >0; >50%=UP else DOWN','funding':'mean last 3 observations before trade; >0=POS else NONPOS'},'regimes':regimes,'ranking_by_avg_net6':ranking,'aggregates':aggregates,'bull_slices':bull_slices}
json.dump(report,open(OUT/'full_regime_map.json','w'),indent=2)
print(json.dumps(report,indent=2))
