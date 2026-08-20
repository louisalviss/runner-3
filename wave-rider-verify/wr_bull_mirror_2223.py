import csv, glob, io, json, math, statistics, time, zipfile
from bisect import bisect_right
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone, date
from pathlib import Path
from zoneinfo import ZoneInfo
import requests

SRC=Path('/tmp/all'); OUT=Path('/tmp/final'); OUT.mkdir(parents=True,exist_ok=True)
ET=ZoneInfo('America/New_York')
BASKET=['ETHUSDT','SOLUSDT','XRPUSDT','BNBUSDT','DOGEUSDT','ADAUSDT','LINKUSDT','AVAXUSDT','DOTUSDT','LTCUSDT','BCHUSDT','TRXUSDT','SUIUSDT','AAVEUSDT','UNIUSDT','NEARUSDT','ETCUSDT','FILUSDT','ICPUSDT','APTUSDT']
COSTS=(4,6,8,10,12,15,20)
EVENTS={
 2022:{
  'NFP':['2022-01-07','2022-02-04','2022-03-04','2022-04-01','2022-05-06','2022-06-03','2022-07-08','2022-08-05','2022-09-02','2022-10-07','2022-11-04','2022-12-02'],
  'CPI':['2022-01-12','2022-02-10','2022-03-10','2022-04-12','2022-05-11','2022-06-10','2022-07-13','2022-08-10','2022-09-13','2022-10-13','2022-11-10','2022-12-13'],
  'FOMC':['2022-01-26','2022-03-16','2022-05-04','2022-06-15','2022-07-27','2022-09-21','2022-11-02','2022-12-14'],
 },
 2023:{
  'NFP':['2023-01-06','2023-02-03','2023-03-10','2023-04-07','2023-05-05','2023-06-02','2023-07-07','2023-08-04','2023-09-01','2023-10-06','2023-11-03','2023-12-08'],
  'CPI':['2023-01-12','2023-02-14','2023-03-14','2023-04-12','2023-05-10','2023-06-13','2023-07-12','2023-08-10','2023-09-13','2023-10-12','2023-11-14','2023-12-12'],
  'FOMC':['2023-02-01','2023-03-22','2023-05-03','2023-06-14','2023-07-26','2023-09-20','2023-11-01','2023-12-13'],
 }
}
EVENT_DATES={y:sorted({date.fromisoformat(x) for xs in d.values() for x in xs}) for y,d in EVENTS.items()}
ALL_EVENT_DATES=sorted({x for xs in EVENT_DATES.values() for x in xs})
T_ON={-2,-1,0,2,3}

def load_trades():
    out=[]
    for p in glob.glob(str(SRC/'trades-*.jsonl')):
        for line in open(p):
            if line.strip():out.append(json.loads(line))
    out.sort(key=lambda a:(a['signal_time'],a['symbol']))
    return out
ALL=load_trades()
def dt(a):return datetime.fromtimestamp(a['signal_time']/1000,tz=timezone.utc)
def net(a,bps=6):return a['R']-(a['entry']/abs(a['entry']-a['stop']))*bps/10000
def sd(x):return statistics.stdev(x) if len(x)>=2 else 0.0
def t_on(a):
    d=dt(a).astimezone(ET).date()
    return any((d-e).days in T_ON for e in ALL_EVENT_DATES)
T=[a for a in ALL if dt(a).year in (2022,2023) and t_on(a)]

def getzip(url,tries=3):
    for i in range(tries):
        try:
            r=requests.get(url,timeout=30,headers={'User-Agent':'runner3-wr-bull-mirror-2223/1.0'})
            if r.status_code==404:return None
            r.raise_for_status();return r.content
        except Exception:
            if i==tries-1:return None
            time.sleep(.4*(i+1))

def rows_zip(data):
    if not data:return []
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as z:txt=z.read(z.namelist()[0]).decode(errors='ignore')
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
        yield y,m;m+=1
        if m==13:y+=1;m=1
months=list(month_range(2021,10,2023,12))
daily={s:[] for s in ['BTCUSDT']+BASKET}
def fetch_daily(job):
    s,y,m=job;fn=f'{s}-1d-{y:04d}-{m:02d}.zip';u=f'https://data.binance.vision/data/futures/um/monthly/klines/{s}/1d/{fn}'
    return s,daily_rows(getzip(u))
with ThreadPoolExecutor(max_workers=24) as ex:
    fs=[ex.submit(fetch_daily,(s,y,m)) for s in daily for y,m in months]
    for q in as_completed(fs):
        s,r=q.result();daily[s]+=r
for s in daily:daily[s]=sorted(dict(daily[s]).items())
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
    return {'btc':btc,'vol':vol,'breadth':br,'breadth_n':len(ups)}
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
def states_for(xs):
    bull=[a for a in xs if a['_mkt']['btc']=='BTC_UP'];states={}
    for vol in ('VOL_HIGH','VOL_LOW'):
      for br in ('BREADTH_UP','BREADTH_DOWN'):
        for fu in ('FUND_POS','FUND_NONPOS'):
          key='|'.join(('BTC_UP',vol,br,fu))
          states[key]=desc([a for a in bull if a['_mkt']['vol']==vol and a['_mkt']['breadth']==br and a['_fund']==fu])
    return bull,states
PRIMARY='BTC_UP|VOL_LOW|BREADTH_UP|FUND_POS'
years={}
for y in (2022,2023):
    fy=[a for a in F if dt(a).year==y];bull,states=states_for(fy)
    rank=[]
    for k,v in states.items():
        c=v['costs']['6'];rank.append({'regime':k,'n':c['n'],'net6':c['net'],'avg6':c['avg'],'dd6':c['max_dd'],'positive_months':v['months']['positive'],'active_months':v['months']['active']})
    rank.sort(key=lambda x:(float('-inf') if x['avg6'] is None else x['avg6']),reverse=True)
    bear=[a for a in fy if a['_mkt']['btc']=='BTC_DOWN' and a['_mkt']['vol']=='VOL_HIGH' and a['_mkt']['breadth']=='BREADTH_DOWN' and a['_fund']=='FUND_NONPOS']
    ty=[a for a in T if dt(a).year==y];xy=[a for a in X if dt(a).year==y]
    breadth_ns=[a['_mkt']['breadth_n'] for a in xy]
    years[str(y)]={'coverage':{'zonec_t_on_trades':len(ty),'market_covered':len(xy),'funding3_covered':len(fy),'breadth_valid_assets_min':min(breadth_ns) if breadth_ns else None,'breadth_valid_assets_median':statistics.median(breadth_ns) if breadth_ns else None},'primary_predeclared_mirror':{'rule':PRIMARY,'result':states[PRIMARY]},'bull_all':desc(bull),'bull_8_states':states,'ranking_diagnostic_only':rank,'same_scope_bear_c3_reference':desc(bear)}

bull_all,combined_states=states_for(F)
report={'status':'WR_BULL_MIRROR_2022_2023_COMPLETE','source':{'engine_source_commit':'8ae05d04764d28cd0705277951973376b04a7f53','reference_source_commit':'8192984ad6a3e5f99b49020c79b5758ef2ac44a7','universe':'same frozen current-TV crypto universe, 654 symbols','raw_trades_total_including_2021q4_seed':len(ALL)},'scope':{'years':[2022,2023],'tf':'10m','zone_c_vn':'23:00-00:59','t_on':[-2,-1,0,2,3]},'years':years,'combined_2022_2023':{'primary_predeclared_mirror':{'rule':PRIMARY,'result':combined_states[PRIMARY]},'bull_all':desc(bull_all),'bull_8_states':combined_states},'definitions':{'btc':'prior-closed daily 30d return >0 = UP','vol':'BTC prior-closed daily RV20 > RV60 = HIGH; <= LOW','breadth':'fixed 20-asset prior-closed 20d positive-return share >50%=UP else DOWN; require >=10 valid assets','funding3':'mean last 3 funding observations strictly before trade; >0=POS else NONPOS','events':'official BLS CPI + Employment Situation release dates and Federal Reserve FOMC statement dates, ET calendar date','primary_mirror':'BTC_UP + VOL_LOW + BREADTH_UP + FUND_POS; original WR direction preserved'},'warning':'Retrospective temporal extension. The primary symmetric mirror remains fixed before this run; the other seven bull cells are diagnostic only and must not be promoted directly from this run.'}
json.dump(report,open(OUT/'bull_mirror_2022_2023.json','w'),indent=2)
print(json.dumps({'status':report['status'],'source':report['source'],'years':{y:{'coverage':v['coverage'],'primary_net6':v['primary_predeclared_mirror']['result']['costs']['6']} for y,v in years.items()},'combined_primary_net6':report['combined_2022_2023']['primary_predeclared_mirror']['result']['costs']['6']},indent=2))
