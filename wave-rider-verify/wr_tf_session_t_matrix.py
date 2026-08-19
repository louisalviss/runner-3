import csv, io, json, math, os, statistics, time, zipfile
from bisect import bisect_right
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo
import requests

BASE=Path(os.environ['BASE_DIR'])
UNIVERSE_FILE=Path(os.environ['UNIVERSE_FILE'])
TF=int(os.environ['TF_MIN'])
OUT=Path(os.environ.get('OUT_DIR','/tmp/out')); OUT.mkdir(parents=True,exist_ok=True)
BASKET=['ETHUSDT','SOLUSDT','XRPUSDT','BNBUSDT','DOGEUSDT','ADAUSDT','LINKUSDT','AVAXUSDT','DOTUSDT','LTCUSDT','BCHUSDT','TRXUSDT','SUIUSDT','AAVEUSDT','UNIUSDT','NEARUSDT','ETCUSDT','FILUSDT','ICPUSDT','APTUSDT']
VN=ZoneInfo('Asia/Ho_Chi_Minh'); ET=ZoneInfo('America/New_York')

# Canonical event-day rule: T0 is the official CPI/NFP/FOMC decision calendar date in ET.
# T-2,T-1,T0,T+2,T+3 are ON; T+1 and all other dates are OFF.
# Actual release dates are frozen from official BLS/Federal Reserve calendars, including 2025 shutdown revisions.
EVENTS={
 '2025-01-10','2025-01-15','2025-01-29','2025-02-07','2025-02-12','2025-03-07','2025-03-12','2025-03-19',
 '2025-04-04','2025-04-10','2025-05-02','2025-05-07','2025-05-13','2025-06-06','2025-06-11','2025-06-18',
 '2025-07-03','2025-07-15','2025-07-30','2025-08-01','2025-08-12','2025-09-05','2025-09-11','2025-09-17',
 '2025-10-24','2025-10-29','2025-11-20','2025-12-10','2025-12-16','2025-12-18',
 '2026-01-09','2026-01-13','2026-01-28','2026-02-11','2026-02-13','2026-03-06','2026-03-11','2026-03-18',
 '2026-04-03','2026-04-10','2026-04-29','2026-05-08','2026-05-12','2026-06-05','2026-06-10','2026-06-17',
 '2026-07-02','2026-07-14','2026-07-29','2026-08-07','2026-08-12'
}
from datetime import date, timedelta
EVENT_DATES=sorted(date.fromisoformat(x) for x in EVENTS)
TON_OFFSETS={-2,-1,0,2,3}

def load_jsonl(p):
    out=[]
    with open(p) as f:
        for line in f:
            if line.strip(): out.append(json.loads(line))
    return out

U=set(json.load(open(UNIVERSE_FILE)))
T=[a for a in load_jsonl(BASE/'trades.jsonl') if a['symbol'] in U]
T.sort(key=lambda a:(a['signal_time'],a['symbol']))

def utc_dt(a): return datetime.fromtimestamp(a['signal_time']/1000,tz=timezone.utc)
def net(a,bps=6): return a['R']-(a['entry']/abs(a['entry']-a['stop']))*bps/10000
def sd(x): return statistics.stdev(x) if len(x)>=2 else 0.0

def session(a):
    d=utc_dt(a).astimezone(VN); m=d.hour*60+d.minute
    if 120<=m<480:return 'ZONE_A'
    if 960<=m<1080:return 'ZONE_B'
    if m>=1380 or m<60:return 'ZONE_C'
    return 'OTHER'

def event_offsets(a):
    d=utc_dt(a).astimezone(ET).date()
    return sorted({(d-e).days for e in EVENT_DATES if -3 <= (d-e).days <= 3})

def t_on(a): return any(x in TON_OFFSETS for x in event_offsets(a))

def getzip(url,tries=3):
    for i in range(tries):
        try:
            r=requests.get(url,timeout=25,headers={'User-Agent':'runner3-wr-tf-session-t/1.0'})
            if r.status_code==404:return None
            r.raise_for_status(); return r.content
        except Exception:
            if i==tries-1:return None
            time.sleep(.35*(i+1))

def rows_zip(data):
    if not data:return []
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as z: txt=z.read(z.namelist()[0]).decode(errors='ignore')
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

def month_prev(y,m):return (y-1,12) if m==1 else (y,m-1)
def month_range(y0,m0,y1,m1):
    y,m=y0,m0
    while (y,m)<=(y1,m1):
        yield y,m
        m+=1
        if m==13:y+=1;m=1

first=utc_dt(T[0]); last=utc_dt(T[-1]); sy,sm=first.year,first.month
for _ in range(2):sy,sm=month_prev(sy,sm)
months=list(month_range(sy,sm,last.year,last.month))

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
def market_pass(ts):
    day=ts//86400000
    if day in market_cache:return market_cache[day]
    b=hist('BTCUSDT',ts)
    if len(b)<61:market_cache[day]=False; return False
    c=[x[1] for x in b]; lr=[math.log(c[i]/c[i-1]) for i in range(1,len(c))]
    btc_down=(c[-1]/c[-31]-1)<0; vol_high=sd(lr[-20:])>sd(lr[-60:])
    ups=[]
    for s in BASKET:
        h=hist(s,ts)
        if len(h)>=21:ups.append(h[-1][1]/h[-21][1]-1>0)
    broad_down=len(ups)>=10 and (sum(ups)/len(ups))<=0.5
    market_cache[day]=btc_down and vol_high and broad_down
    return market_cache[day]

M=[]
for a in T:
    if market_pass(a['signal_time']):M.append(a)
need=defaultdict(set)
for a in M:
    d=utc_dt(a); need[a['symbol']].add((d.year,d.month)); need[a['symbol']].add(month_prev(d.year,d.month))
fund={s:[] for s in need}
def fetch_f(job):
    s,y,m=job; fn=f'{s}-fundingRate-{y:04d}-{m:02d}.zip'; u=f'https://data.binance.vision/data/futures/um/monthly/fundingRate/{s}/{fn}'
    return s,funding_rows(getzip(u))
jobs=[(s,y,m) for s,ms in need.items() for y,m in ms]
with ThreadPoolExecutor(max_workers=24) as ex:
    fs=[ex.submit(fetch_f,j) for j in jobs]
    for q in as_completed(fs):
        s,r=q.result(); fund[s]+=r
for s in fund:fund[s]=sorted(dict(fund[s]).items())
ft={s:[x[0] for x in arr] for s,arr in fund.items()}
C=[]
for a in M:
    arr=fund.get(a['symbol'],[]); times=ft.get(a['symbol'],[]); i=bisect_right(times,a['signal_time']-1)
    if i>=3 and sum(x[1] for x in arr[i-3:i])/3<=0:C.append(a)

Ckeys={(a['symbol'],a['signal_time'],a['entry'],a['stop']) for a in C}
def is_c3(a):return (a['symbol'],a['signal_time'],a['entry'],a['stop']) in Ckeys

def maxdd(xs,bps):
    eq=peak=mdd=0.0
    for a in sorted(xs,key=lambda z:(z['signal_time'],z['symbol'])):
        eq+=net(a,bps); peak=max(peak,eq); mdd=min(mdd,eq-peak)
    return mdd

def metrics(xs):
    out={'n':len(xs),'symbols':len(set(a['symbol'] for a in xs))}
    for b in (4,6,8,10,12):
        vals=[net(a,b) for a in xs]
        out[f'net{b}']=sum(vals); out[f'avg{b}']=statistics.mean(vals) if vals else None; out[f'dd{b}']=maxdd(xs,b)
    return out

def years(xs):
    return {str(y):metrics([a for a in xs if utc_dt(a).year==y]) for y in (2025,2026)}

def summarize(xs):
    z=metrics(xs); z['by_year']=years(xs); return z

matrix={}
for sess in ('ZONE_A','ZONE_B','ZONE_C','OTHER','ALL'):
    base=[a for a in T if sess=='ALL' or session(a)==sess]
    for tg in ('ALL_DAYS','T_ON'):
        b=[a for a in base if tg=='ALL_DAYS' or t_on(a)]
        c=[a for a in b if is_c3(a)]
        matrix[f'{sess}|{tg}']={'baseline':summarize(b),'candidate3':summarize(c)}

offset_counts=defaultdict(int)
for a in T:
    for x in event_offsets(a): offset_counts[str(x)]+=1
report={
 'status':'WR_TF_SESSION_T_MATRIX_COMPLETE','tf':TF,
 'scope':{'trades':len(T),'symbols':len(U),'first':utc_dt(T[0]).isoformat(),'last':utc_dt(T[-1]).isoformat()},
 'definitions':{'sessions_vn':{'ZONE_A':'02:00-07:59','ZONE_B':'16:00-17:59','ZONE_C':'23:00-00:59','OTHER':'all remaining'},'t0':'official event calendar date in America/New_York; FOMC stays on ET decision date even if VN is next calendar day','t_on_offsets':[-2,-1,0,2,3],'events':'CPI + Employment Situation/NFP + FOMC decision dates','candidate3':'BTC30<0 + BTC RV20>RV60 + fixed20 breadth<=50% + mean(last3 funding)<=0'},
 'coverage':{'market_gate':len(M),'candidate3':len(C),'candidate3_pct':100*len(C)/len(T) if T else 0,'event_offset_trade_hits':dict(offset_counts)},
 'matrix':matrix,
 'warning':'Retrospective ablation/transfer matrix. Do not tune session, timeframe, T offsets, or Candidate3 from this same run.'
}
json.dump(report,open(OUT/f'tf{TF}_session_t_matrix.json','w'),indent=2)
print(json.dumps(report,indent=2))
