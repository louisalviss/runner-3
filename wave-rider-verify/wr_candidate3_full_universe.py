import csv, io, json, math, random, statistics, time, zipfile
from bisect import bisect_right
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
import requests

BASE=Path('/tmp/base')
OUT=Path('/tmp/final'); OUT.mkdir(parents=True, exist_ok=True)

# Frozen Candidate #3 transferred unchanged from Zone C 10m research:
# BTC 30d return < 0 AND BTC RV20 > RV60 AND broad market <=50% up over 20d
# AND mean(last 3 funding observations before trade) <= 0.
# This is a retrospective cross-session/full-universe TRANSFER TEST. No tuning.
BASKET=['ETHUSDT','SOLUSDT','XRPUSDT','BNBUSDT','DOGEUSDT','ADAUSDT','LINKUSDT','AVAXUSDT','DOTUSDT','LTCUSDT','BCHUSDT','TRXUSDT','SUIUSDT','AAVEUSDT','UNIUSDT','NEARUSDT','ETCUSDT','FILUSDT','ICPUSDT','APTUSDT']


def load_jsonl(p):
    xs=[]
    with open(p) as f:
        for line in f:
            if line.strip(): xs.append(json.loads(line))
    return xs

T=load_jsonl(BASE/'trades.jsonl')
T.sort(key=lambda a:(a['signal_time'],a['symbol']))

def dt(a): return datetime.fromtimestamp(a['signal_time']/1000,tz=timezone.utc)
def year(a): return dt(a).year
def net(a,bps=6): return a['R']-(a['entry']/abs(a['entry']-a['stop']))*bps/10000

def getzip(url,tries=3):
    for i in range(tries):
        try:
            r=requests.get(url,timeout=25,headers={'User-Agent':'runner3-wr-c3-full/1.0'})
            if r.status_code==404: return None
            r.raise_for_status(); return r.content
        except Exception:
            if i==tries-1: return None
            time.sleep(.35*(i+1))

def unzip_rows(data):
    if not data:return []
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            txt=z.read(z.namelist()[0]).decode(errors='ignore')
        return list(csv.reader(io.StringIO(txt)))
    except Exception:return []

def daily_rows(data):
    out=[]
    for r in unzip_rows(data):
        try:
            if r and r[0].isdigit() and len(r)>4: out.append((int(r[0]),float(r[4])))
        except: pass
    return out

def funding_rows(data):
    rows=unzip_rows(data); out=[]
    if not rows:return out
    h=[x.lower() for x in rows[0]]
    has_header=any('fund' in x or 'time' in x for x in h)
    start=1 if has_header else 0
    ti=next((i for i,x in enumerate(h) if 'time' in x),0) if has_header else 0
    fi=next((i for i,x in enumerate(h) if 'fund' in x and 'rate' in x),None) if has_header else None
    for r in rows[start:]:
        try:
            if fi is None:
                vals=[]
                for i,x in enumerate(r):
                    if i==ti: continue
                    try:
                        v=float(x)
                        if abs(v)<0.1: vals.append(v)
                    except: pass
                if not vals: continue
                v=vals[-1]
            else: v=float(r[fi])
            ts=int(float(r[ti])); ts=ts*1000 if ts<10**12 else ts
            out.append((ts,v))
        except: pass
    return out

def month_prev(y,m):
    return (y-1,12) if m==1 else (y,m-1)

# Fetch prior-closed daily bars for BTC and fixed breadth basket.
start=(2024,9); end=(2026,8)
def month_range():
    y,m=start
    while (y,m)<=end:
        yield y,m
        m+=1
        if m==13:y+=1;m=1

symbols_daily=['BTCUSDT']+BASKET
daily={s:[] for s in symbols_daily}
def fetch_daily(job):
    s,y,m=job
    fn=f'{s}-1d-{y:04d}-{m:02d}.zip'
    u=f'https://data.binance.vision/data/futures/um/monthly/klines/{s}/1d/{fn}'
    return s,daily_rows(getzip(u))
with ThreadPoolExecutor(max_workers=20) as ex:
    fs=[ex.submit(fetch_daily,(s,y,m)) for s in symbols_daily for y,m in month_range()]
    for q in as_completed(fs):
        s,rows=q.result(); daily[s]+=rows
for s in daily:
    daily[s]=sorted(dict(daily[s]).items())

# Efficient market state per UTC trade day; all inputs are closed before the trade.
def sd(x): return statistics.stdev(x) if len(x)>=2 else 0.0
market_cache={}
def closed_history(s,ts):
    arr=daily[s]; times=[x[0] for x in arr]
    i=bisect_right(times,ts-86400000)
    return arr[:i]

def market_state(ts):
    day=ts//86400000
    if day in market_cache:return market_cache[day]
    b=closed_history('BTCUSDT',ts)
    if len(b)<61:
        market_cache[day]=(False,None); return market_cache[day]
    c=[x[1] for x in b]
    lr=[math.log(c[i]/c[i-1]) for i in range(1,len(c))]
    btc_down=(c[-1]/c[-31]-1)<0
    high_vol=sd(lr[-20:])>sd(lr[-60:])
    vals=[]
    for s in BASKET:
        h=closed_history(s,ts)
        if len(h)>=21: vals.append(h[-1][1]/h[-21][1]-1>0)
    breadth=(sum(vals)/len(vals)) if len(vals)>=10 else None
    broad_down=(breadth is not None and breadth<=0.5)
    market_cache[day]=(btc_down and high_vol and broad_down,breadth)
    return market_cache[day]

M=[]
for i,a in enumerate(T):
    ok,br=market_state(a['signal_time'])
    if ok:
        b=dict(a); b['_breadth']=br; M.append(b)
print('BASE',len(T),'MARKET_PASS',len(M),'SYMS',len(set(a['symbol'] for a in T)),flush=True)

# Fetch funding only for symbol-months actually needed after market gate.
need=defaultdict(set)
for a in M:
    d=dt(a); need[a['symbol']].add((d.year,d.month)); need[a['symbol']].add(month_prev(d.year,d.month))
fund={s:[] for s in need}
def fetch_fund(job):
    s,y,m=job
    fn=f'{s}-fundingRate-{y:04d}-{m:02d}.zip'
    u=f'https://data.binance.vision/data/futures/um/monthly/fundingRate/{s}/{fn}'
    return s,funding_rows(getzip(u))
jobs=[(s,y,m) for s,ms in need.items() for y,m in ms]
with ThreadPoolExecutor(max_workers=24) as ex:
    fs=[ex.submit(fetch_fund,j) for j in jobs]
    for i,q in enumerate(as_completed(fs)):
        s,rows=q.result(); fund[s]+=rows
        if i%500==0: print('FUND_FILES',i,'/',len(jobs),flush=True)
for s in fund:
    fund[s]=sorted(dict(fund[s]).items())

C=[]; funding_covered=0
for a in M:
    arr=fund.get(a['symbol'],[])
    times=[x[0] for x in arr]
    i=bisect_right(times,a['signal_time']-1)
    h=arr[:i]
    if len(h)>=3:
        funding_covered+=1
        f3=sum(x[1] for x in h[-3:])/3
        if f3<=0:
            b=dict(a); b['_fund3']=f3; C.append(b)

# Metrics.
def maxdd(xs,bps):
    eq=peak=mdd=0.0
    for a in sorted(xs,key=lambda z:(z['signal_time'],z['symbol'])):
        eq+=net(a,bps); peak=max(peak,eq); mdd=min(mdd,eq-peak)
    return mdd

def metrics(xs,bps):
    vals=[net(a,bps) for a in xs]
    return {'n':len(xs),'net':sum(vals),'avg':statistics.mean(vals) if vals else None,'max_dd':maxdd(xs,bps)}

def by_month(xs,bps=6):
    z=defaultdict(float)
    for a in xs:z[dt(a).strftime('%Y-%m')]+=net(a,bps)
    return dict(sorted(z.items()))

def session(a):
    d=dt(a); mins=((d.hour+7)%24)*60+d.minute
    if 120<=mins<480:return 'ZONE_A_02_08_VN'
    if 960<=mins<1080:return 'ZONE_B_16_18_VN'
    if mins>=1380 or mins<60:return 'ZONE_C_23_01_VN'
    return 'OTHER'

def concentration(xs):
    z=defaultdict(float)
    for a in xs:z[a['symbol']]+=net(a,6)
    r=sorted(z.items(),key=lambda kv:kv[1],reverse=True)
    out={}
    for k in (1,5,10,20):
        drop={x[0] for x in r[:k]}; out[f'drop_top_{k}']=sum(net(a,6) for a in xs if a['symbol'] not in drop)
    return out

def bootstrap_trade(xs,n=5000,seed=251503):
    vals=[net(a,6) for a in xs]
    if not vals:return [None,None]
    r=random.Random(seed); ds=[]
    for _ in range(n): ds.append(sum(r.choice(vals) for _ in vals)/len(vals))
    ds.sort(); return [ds[int(.025*n)],ds[int(.975*n)-1]]

def bootstrap_month(xs,n=5000,seed=251504):
    vals=list(by_month(xs).values())
    if not vals:return [None,None]
    r=random.Random(seed); ds=[]
    for _ in range(n): ds.append(sum(r.choice(vals) for _ in vals)/len(vals))
    ds.sort(); return [ds[int(.025*n)],ds[int(.975*n)-1]]

def summary(xs):
    bm=by_month(xs); total6=sum(net(a,6) for a in xs)
    loo={m:total6-v for m,v in bm.items()}
    bys={}
    for y in (2025,2026):
        yy=[a for a in xs if year(a)==y]
        bys[str(y)]={str(b):metrics(yy,b) for b in (4,6,8,10,12,15,20)}
    sess={}
    for s in ('ZONE_A_02_08_VN','ZONE_B_16_18_VN','ZONE_C_23_01_VN','OTHER'):
        ss=[a for a in xs if session(a)==s]; sess[s]=metrics(ss,6)
    return {
      'unique_symbols':len(set(a['symbol'] for a in xs)),
      'costs':{str(b):metrics(xs,b) for b in (4,6,8,10,12,15,20)},
      'by_year':bys,
      'months':bm,'positive_months':sum(v>0 for v in bm.values()),'active_months':len(bm),
      'leave_one_month_out':{'min':min(loo.values()) if loo else None,'all_positive':all(v>0 for v in loo.values()) if loo else False},
      'bootstrap_trade95':bootstrap_trade(xs),'bootstrap_month95':bootstrap_month(xs),
      'side':{side:metrics([a for a in xs if str(a.get('side','')).upper()==side],6) for side in ('LONG','SHORT')},
      'sessions':sess,'concentration':concentration(xs)
    }

report={
 'status':'WR_CANDIDATE3_FULL_UNIVERSE_TRANSFER_COMPLETE',
 'warning':'Retrospective transfer test. Candidate #3 was discovered on Zone C 10m; this run applies it unchanged to the full WR 5m base trade universe across all sessions. It is not untouched OOS and must not be used to retune thresholds.',
 'source':{'run_id':32158961561,'artifact':'wr2515-5m-tv-tick-final','base_trades':len(T),'base_unique_symbols':len(set(a['symbol'] for a in T)),'first_trade_utc':dt(T[0]).isoformat() if T else None,'last_trade_utc':dt(T[-1]).isoformat() if T else None},
 'coverage':{'market_pass_trades':len(M),'funding3_covered_market_pass':funding_covered,'funding3_coverage_pct':100*funding_covered/len(M) if M else 0},
 'frozen_rule':'BTC30 return<0 + BTC RV20>RV60 + fixed20 breadth<=0.5 + mean(last3 funding)<=0',
 'base_all':summary(T),
 'market_gate_only':summary(M),
 'candidate3':summary(C)
}
json.dump(report,open(OUT/'candidate3_full_universe_transfer.json','w'),indent=2)
print(json.dumps(report,indent=2))
