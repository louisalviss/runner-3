import csv, io, json, math, statistics, time, zipfile
from bisect import bisect_right
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone, date
from pathlib import Path
from zoneinfo import ZoneInfo
import requests

BASE=Path('/tmp/base'); OUT=Path('/tmp/final'); OUT.mkdir(parents=True,exist_ok=True)
ET=ZoneInfo('America/New_York')
BASKET=['ETHUSDT','SOLUSDT','XRPUSDT','BNBUSDT','DOGEUSDT','ADAUSDT','LINKUSDT','AVAXUSDT','DOTUSDT','LTCUSDT','BCHUSDT','TRXUSDT','SUIUSDT','AAVEUSDT','UNIUSDT','NEARUSDT','ETCUSDT','FILUSDT','ICPUSDT','APTUSDT']
COSTS=(4,6,8,10,12,15,20)
EVENTS={
 'NFP':['2024-01-05','2024-02-02','2024-03-08','2024-04-05','2024-05-03','2024-06-07','2024-07-05','2024-08-02','2024-09-06','2024-10-04','2024-11-01','2024-12-06'],
 'CPI':['2024-01-11','2024-02-13','2024-03-12','2024-04-10','2024-05-15','2024-06-12','2024-07-11','2024-08-14','2024-09-11','2024-10-10','2024-11-13','2024-12-11'],
 'FOMC':['2024-01-31','2024-03-20','2024-05-01','2024-06-12','2024-07-31','2024-09-18','2024-11-07','2024-12-18']
}
EVENT_DATES=sorted({date.fromisoformat(x) for xs in EVENTS.values() for x in xs})
T_ON={-2,-1,0,2,3}

def load_jsonl(p):
    out=[]
    with open(p) as f:
        for line in f:
            if line.strip(): out.append(json.loads(line))
    return out
ALL=load_jsonl(BASE/'all_trades.jsonl')
T=[a for a in ALL if datetime.fromtimestamp(a['signal_time']/1000,tz=timezone.utc).year==2024]
T.sort(key=lambda a:(a['signal_time'],a['symbol']))

def dt(a): return datetime.fromtimestamp(a['signal_time']/1000,tz=timezone.utc)
def net(a,bps=6): return a['R']-(a['entry']/abs(a['entry']-a['stop']))*bps/10000
def sd(x): return statistics.stdev(x) if len(x)>=2 else 0.0
def t_on(a):
    d=dt(a).astimezone(ET).date()
    return any((d-e).days in T_ON for e in EVENT_DATES)
T=[a for a in T if t_on(a)]

def getzip(url,tries=3):
    for i in range(tries):
        try:
            r=requests.get(url,timeout=30,headers={'User-Agent':'runner3-wr-bull-mirror-2024/1.0'})
            if r.status_code==404:return None
            r.raise_for_status(); return r.content
        except Exception:
            if i==tries-1:return None
            time.sleep(.4*(i+1))

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
            if r and r[0].isdigit() and len(r)>4: out.append((int(r[0]),float(r[4])))
        except: pass
    return out

def funding_rows(data):
    rows=rows_zip(data);out=[]
    if not rows:return out
    h=[x.lower() for x in rows[0]];has=any('fund' in x or 'time' in x for x in h);start=1 if has else 0
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
            ts=int(float(r[ti]));ts=ts*1000 if ts<10**12 else ts
            out.append((ts,v))
        except:pass
    return out

def month_range(y0,m0,y1,m1):
    y,m=y0,m0
    while (y,m)<=(y1,m1):
        yield y,m
        m+=1
        if m==13:y+=1;m=1
months=list(month_range(2023,10,2024,12))
daily={s:[] for s in ['BTCUSDT']+BASKET}
def fetch_daily(job):
    s,y,m=job;fn=f'{s}-1d-{y:04d}-{m:02d}.zip';u=f'https://data.binance.vision/data/futures/um/monthly/klines/{s}/1d/{fn}'
    return s,daily_rows(getzip(u))
with ThreadPoolExecutor(max_workers=20) as ex:
    fs=[ex.submit(fetch_daily,(s,y,m)) for s in daily for y,m in months]
    for q in as_completed(fs):
        s,r=q.result();daily[s]+=r
for s in daily: daily[s]=sorted(dict(daily[s]).items())
daily_times={s:[x[0] for x in arr] for s,arr in daily.items()}
def hist(s,ts):
    arr=daily[s];i=bisect_right(daily_times[s],ts-86400000);return arr[:i]

def market_feats(ts):
    b=hist('BTCUSDT',ts)
    if len(b)<61:return None
    c=[x[1] for x in b];lr=[math.log(c[i]/c[i-1]) for i in range(1,len(c))]
    btc='BTC_UP' if c[-1]/c[-31]-1>0 else 'BTC_DOWN'
    vol='VOL_HIGH' if sd(lr[-20:])>sd(lr[-60:]) else 'VOL_LOW'
    ups=[]
    for s in BASKET:
        h=hist(s,ts)
        if len(h)>=21:ups.append(h[-1][1]/h[-21][1]-1>0)
    if len(ups)<10:return None
    br='BREADTH_UP' if sum(ups)/len(ups)>0.5 else 'BREADTH_DOWN'
    return {'btc':btc,'vol':vol,'breadth':br}
X=[]
for a in T:
    f=market_feats(a['signal_time'])
    if f:
        z=dict(a);z['_mkt']=f;X.append(z)

def month_prev(y,m):return (y-1,12) if m==1 else (y,m-1)
need=defaultdict(set)
for a in X:
    d=dt(a);need[a['symbol']].add((d.year,d.month));need[a['symbol']].add(month_prev(d.year,d.month))
fund={s:[] for s in need}
def fetch_f(job):
    s,y,m=job;fn=f'{s}-fundingRate-{y:04d}-{m:02d}.zip';u=f'https://data.binance.vision/data/futures/um/monthly/fundingRate/{s}/{fn}'
    return s,funding_rows(getzip(u))
with ThreadPoolExecutor(max_workers=24) as ex:
    fs=[ex.submit(fetch_f,(s,y,m)) for s,ms in need.items() for y,m in ms]
    for q in as_completed(fs):
        s,r=q.result();fund[s]+=r
for s in fund:fund[s]=sorted(dict(fund[s]).items())
ft={s:[x[0] for x in arr] for s,arr in fund.items()}
F=[]
for a in X:
    arr=fund.get(a['symbol'],[]);times=ft.get(a['symbol'],[]);i=bisect_right(times,a['signal_time']-1)
    if i>=3:
        f3=sum(x[1] for x in arr[i-3:i])/3
        z=dict(a);z['_fund3']=f3;z['_fund']='FUND_POS' if f3>0 else 'FUND_NONPOS';F.append(z)

def maxdd(xs,bps=6):
    eq=peak=mdd=0.0
    for a in sorted(xs,key=lambda z:(z['signal_time'],z['symbol'])):
        eq+=net(a,bps);peak=max(peak,eq);mdd=min(mdd,eq-peak)
    return mdd

def met(xs,bps=6):
    vals=[net(a,bps) for a in xs]
    return {'n':len(xs),'net':sum(vals),'avg':statistics.mean(vals) if vals else None,'max_dd':maxdd(xs,bps),'symbols':len(set(a['symbol'] for a in xs))}

def month_stats(xs):
    z=defaultdict(float)
    for a in xs:z[dt(a).strftime('%Y-%m')]+=net(a,6)
    return {'active':len(z),'positive':sum(v>0 for v in z.values()),'negative':sum(v<0 for v in z.values()),'values':dict(sorted(z.items()))}

def desc(xs):
    return {'costs':{str(b):met(xs,b) for b in COSTS},'months':month_stats(xs),'side':{s:met([a for a in xs if str(a.get('side','')).upper()==s],6) for s in ('LONG','SHORT')}}
bull=[a for a in F if a['_mkt']['btc']=='BTC_UP']
states={}
for vol in ('VOL_HIGH','VOL_LOW'):
  for br in ('BREADTH_UP','BREADTH_DOWN'):
    for fu in ('FUND_POS','FUND_NONPOS'):
      key='|'.join(('BTC_UP',vol,br,fu))
      states[key]=desc([a for a in bull if a['_mkt']['vol']==vol and a['_mkt']['breadth']==br and a['_fund']==fu])
PRIMARY='BTC_UP|VOL_LOW|BREADTH_UP|FUND_POS'
rank=[]
for k,v in states.items():
    c=v['costs']['6'];rank.append({'regime':k,'n':c['n'],'net6':c['net'],'avg6':c['avg'],'dd6':c['max_dd'],'positive_months':v['months']['positive'],'active_months':v['months']['active']})
rank.sort(key=lambda x:(float('-inf') if x['avg6'] is None else x['avg6']),reverse=True)
bear=[a for a in F if a['_mkt']['btc']=='BTC_DOWN' and a['_mkt']['vol']=='VOL_HIGH' and a['_mkt']['breadth']=='BREADTH_DOWN' and a['_fund']=='FUND_NONPOS']
report={'status':'WR_BULL_MIRROR_2024_COMPLETE','source':{'run_id':32253319968,'artifact':'wr2024-frozen-rolling-oos-final','exact_zonec_2024_trades':1977,'symbols_completed':274},'scope':{'year':2024,'tf':'10m','zone_c_vn':'23:00-00:59','t_on':[-2,-1,0,2,3],'zonec_t_on_trades':len(T),'market_covered':len(X),'funding3_covered':len(F)},'primary_predeclared_mirror':{'rule':PRIMARY,'result':states[PRIMARY]},'bull_all':desc(bull),'bull_8_states':states,'ranking_diagnostic_only':rank,'same_scope_bear_c3_reference':desc(bear),'definitions':{'btc':'prior-closed daily 30d return >0 = UP','vol':'BTC prior-closed daily RV20 > RV60 = HIGH; <= LOW','breadth':'fixed 20-asset positive prior-closed 20d return share >50%=UP else DOWN','funding3':'mean last 3 funding observations before trade; >0=POS else NONPOS','events':'2024 official BLS CPI/Employment Situation release dates plus FOMC statement dates; ET calendar date','primary_mirror':'BTC_UP + VOL_LOW + BREADTH_UP + FUND_POS; original WR direction preserved'},'warning':'2024 is an older retrospective extension using a frozen exact Zone C trade artifact. It is useful temporal evidence but not pristine OOS for a rule proposed in 2026. Other bull cells remain diagnostics only.'}
json.dump(report,open(OUT/'bull_mirror_2024.json','w'),indent=2)
print(json.dumps({'status':report['status'],'scope':report['scope'],'primary':report['primary_predeclared_mirror'],'bull_rank':rank,'bear_ref':report['same_scope_bear_c3_reference']['costs']['6']},indent=2))