import csv, io, json, math, statistics, time, zipfile
from bisect import bisect_right
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
import requests
import sys

# Reuse the frozen 10m/common-universe/session/T definitions from the successful matrix.
sys.path.insert(0,'wave-rider-verify')
import wr_tf_session_t_matrix as m

OUT=Path('/tmp/final'); OUT.mkdir(parents=True,exist_ok=True)
COSTS=(4,6,8,10,12,15,20)

T=[a for a in m.T if m.session(a)=='ZONE_C' and m.t_on(a)]
T.sort(key=lambda a:(a['signal_time'],a['symbol']))

def dt(a): return datetime.fromtimestamp(a['signal_time']/1000,tz=timezone.utc)
def net(a,bps=6): return a['R']-(a['entry']/abs(a['entry']-a['stop']))*bps/10000
def sd(x): return statistics.stdev(x) if len(x)>=2 else 0.0

def market_feats(ts):
    b=m.hist('BTCUSDT',ts)
    if len(b)<61:return None
    c=[x[1] for x in b]
    lr=[math.log(c[i]/c[i-1]) for i in range(1,len(c))]
    btc='BTC_UP' if c[-1]/c[-31]-1>0 else 'BTC_DOWN'
    vol='VOL_HIGH' if sd(lr[-20:])>sd(lr[-60:]) else 'VOL_LOW'
    ups=[]
    for s in m.BASKET:
        h=m.hist(s,ts)
        if len(h)>=21: ups.append(h[-1][1]/h[-21][1]-1>0)
    if len(ups)<10:return None
    breadth='BREADTH_UP' if sum(ups)/len(ups)>0.5 else 'BREADTH_DOWN'
    return {'btc':btc,'vol':vol,'breadth':breadth}

X=[]
for a in T:
    f=market_feats(a['signal_time'])
    if f:
        z=dict(a); z['_mkt']=f; X.append(z)

# Funding3 for every exact Zone-C T-ON trade, independent of bear/bull state.
def month_prev(y,mn): return (y-1,12) if mn==1 else (y,mn-1)
def rows_zip(data):
    if not data:return []
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as z: txt=z.read(z.namelist()[0]).decode(errors='ignore')
        return list(csv.reader(io.StringIO(txt)))
    except Exception:return []
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

def getzip(url,tries=3):
    for i in range(tries):
        try:
            r=requests.get(url,timeout=25,headers={'User-Agent':'runner3-wr-bull-mirror-exact/1.0'})
            if r.status_code==404:return None
            r.raise_for_status();return r.content
        except Exception:
            if i==tries-1:return None
            time.sleep(.4*(i+1))

need=defaultdict(set)
for a in X:
    d=dt(a); need[a['symbol']].add((d.year,d.month)); need[a['symbol']].add(month_prev(d.year,d.month))
fund={s:[] for s in need}
def fetch_f(job):
    s,y,mn=job; fn=f'{s}-fundingRate-{y:04d}-{mn:02d}.zip'; u=f'https://data.binance.vision/data/futures/um/monthly/fundingRate/{s}/{fn}'
    return s,funding_rows(getzip(u))
with ThreadPoolExecutor(max_workers=24) as ex:
    fs=[ex.submit(fetch_f,(s,y,mn)) for s,ms in need.items() for y,mn in ms]
    for q in as_completed(fs):
        s,r=q.result();fund[s]+=r
for s in fund:fund[s]=sorted(dict(fund[s]).items())
ft={s:[x[0] for x in arr] for s,arr in fund.items()}
F=[]
for a in X:
    arr=fund.get(a['symbol'],[]); times=ft.get(a['symbol'],[]); i=bisect_right(times,a['signal_time']-1)
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
    return {
      'costs':{str(b):met(xs,b) for b in COSTS},
      'years':{str(y):{str(b):met([a for a in xs if dt(a).year==y],b) for b in (6,8,10,12)} for y in (2025,2026)},
      'months':month_stats(xs),
      'side':{s:met([a for a in xs if str(a.get('side','')).upper()==s],6) for s in ('LONG','SHORT')}
    }

bull=[a for a in F if a['_mkt']['btc']=='BTC_UP']
states={}
for vol in ('VOL_HIGH','VOL_LOW'):
  for br in ('BREADTH_UP','BREADTH_DOWN'):
    for fu in ('FUND_POS','FUND_NONPOS'):
      key='|'.join(('BTC_UP',vol,br,fu))
      xs=[a for a in bull if a['_mkt']['vol']==vol and a['_mkt']['breadth']==br and a['_fund']==fu]
      states[key]=desc(xs)

PRIMARY='BTC_UP|VOL_LOW|BREADTH_UP|FUND_POS'
rank=[]
for k,v in states.items():
    c=v['costs']['6'];rank.append({'regime':k,'n':c['n'],'net6':c['net'],'avg6':c['avg'],'dd6':c['max_dd'],'positive_months':v['months']['positive'],'active_months':v['months']['active']})
rank.sort(key=lambda x:(float('-inf') if x['avg6'] is None else x['avg6']),reverse=True)

bear=[a for a in F if a['_mkt']['btc']=='BTC_DOWN' and a['_mkt']['vol']=='VOL_HIGH' and a['_mkt']['breadth']=='BREADTH_DOWN' and a['_fund']=='FUND_NONPOS']
report={
 'status':'WR_BULL_MIRROR_EXACT_COMPLETE',
 'scope':{'tf':'10m','zone_c_vn':'23:00-00:59','t_on':[-2,-1,0,2,3],'base_zonec_t_on_trades':len(T),'market_covered':len(X),'funding3_covered':len(F),'first':dt(T[0]).isoformat(),'last':dt(T[-1]).isoformat()},
 'primary_predeclared_mirror':{'rule':PRIMARY,'result':states[PRIMARY]},
 'bull_all':desc(bull),
 'bull_8_states':states,
 'ranking_diagnostic_only':rank,
 'same_scope_bear_c3_reference':desc(bear),
 'definitions':{'btc':'prior-closed daily 30d return >0 = UP; <0 is bear rule','vol':'BTC prior-closed daily RV20 > RV60 = HIGH; <= = LOW','breadth':'fixed 20-asset prior-closed 20d positive-return share >50%=UP else DOWN','funding3':'mean last 3 funding observations strictly before trade; >0=POS else NONPOS','primary_mirror':'exact sign/complement mirror of frozen C3 market gate; WR entry direction is NOT flipped'},
 'warning':'Retrospective diagnostic. Primary symmetric mirror was predeclared. The other seven bull cells are map diagnostics only and may not be promoted directly from this run.'
}
json.dump(report,open(OUT/'bull_mirror_exact.json','w'),indent=2)
print(json.dumps({'status':report['status'],'primary':report['primary_predeclared_mirror'],'bull_rank':rank,'bear_ref_net6':report['same_scope_bear_c3_reference']['costs']['6']},indent=2))
