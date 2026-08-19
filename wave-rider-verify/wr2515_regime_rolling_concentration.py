import csv, io, json, math, os, statistics, time, zipfile
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from pathlib import Path
import requests

LEDGER=Path(os.environ.get('LEDGER','/tmp/base10/trades.jsonl'))
ROBUST=Path(os.environ.get('ROBUST','/tmp/cohort/robust_both_years.json'))
OUT=Path(os.environ.get('OUT','/tmp/out')); OUT.mkdir(parents=True,exist_ok=True)
VN=timezone(timedelta(hours=7))

rows=[json.loads(x) for x in LEDGER.open() if x.strip()]
robust=set(json.load(ROBUST.open()))
for r in rows:
    d=datetime.fromtimestamp(r['signal_time']/1000,tz=timezone.utc)
    dv=d.astimezone(VN)
    r['year']=d.year; r['month']=f'{d.year:04d}-{d.month:02d}'; r['hour_vn']=dv.hour; r['dow_vn']=dv.weekday()
    r['net4']=r['R']-(r['entry']/abs(r['entry']-r['stop']))*.0004
    r['net6']=r['R']-(r['entry']/abs(r['entry']-r['stop']))*.0006
    r['net8']=r['R']-(r['entry']/abs(r['entry']-r['stop']))*.0008
    r['net10']=r['R']-(r['entry']/abs(r['entry']-r['stop']))*.0010

def stat(rs):
    z={'n':len(rs)}
    for b in (4,6,8,10): z[f'net{b}']=sum(r[f'net{b}'] for r in rs)
    z['gross']=sum(r['R'] for r in rs)
    z['avg_net6']=z['net6']/z['n'] if z['n'] else None
    z['win_rate']=sum(r['R']>0 for r in rs)/z['n'] if z['n'] else None
    return z

def q(vals,p):
    a=sorted(x for x in vals if x is not None and math.isfinite(x))
    if not a:return None
    x=(len(a)-1)*p; lo=int(math.floor(x)); hi=int(math.ceil(x))
    return a[lo] if lo==hi else a[lo]*(hi-x)+a[hi]*(x-lo)

by_sym=defaultdict(list)
for r in rows: by_sym[r['symbol']].append(r)

def concentration_report(rs):
    b=defaultdict(list)
    for r in rs:b[r['symbol']].append(r)
    sym=[{'symbol':s,**stat(v)} for s,v in b.items()]
    sym.sort(key=lambda x:x['net6'],reverse=True)
    total=stat(rs)
    pos=[x for x in sym if x['net6']>0]
    denom=sum(abs(x['net6']) for x in sym) or 1
    hhi=sum((abs(x['net6'])/denom)**2 for x in sym)
    def drop(k):
        bad=set(x['symbol'] for x in sym[:k])
        return stat([r for r in rs if r['symbol'] not in bad])
    def share(k):
        s=sum(x['net6'] for x in sym[:k])
        return s/total['net6'] if total['net6'] else None
    return {'total':total,'symbols':len(sym),'positive_symbols':len(pos),'top5_share_of_total_net6':share(5),'top10_share_of_total_net6':share(10),'abs_pnl_hhi':hhi,
            'drop_top1':drop(1),'drop_top5':drop(5),'drop_top10':drop(10),'top20_symbols':sym[:20]}

conc={'all':concentration_report(rows),'2025':concentration_report([r for r in rows if r['year']==2025]),
      '2026':concentration_report([r for r in rows if r['year']==2026]),
      'robust40_fullsample_diagnostic':concentration_report([r for r in rows if r['symbol'] in robust])}

def month_index(m):
    y,mo=map(int,m.split('-'));return y*12+mo-1
def idx_month(i):return f'{i//12:04d}-{i%12+1:02d}'
months=sorted(set(r['month'] for r in rows))
roll=[]
for testm in months:
    ti=month_index(testm)
    trainms={idx_month(ti-k) for k in (3,2,1)}
    tr=[r for r in rows if r['month'] in trainms]
    te=[r for r in rows if r['month']==testm]
    if len(tr)<1000 or len(te)<100:continue
    lo=q([r['stop_pct'] for r in tr],.33); hi=q([r['stop_pct'] for r in tr],.67)
    cands=[]
    def add(name,fn):
        xs=[r for r in tr if fn(r)]
        if len(xs)>=200:
            st=stat(xs);cands.append((st['avg_net6'],st['net6'],name,fn,len(xs)))
    add('ALL',lambda r:True)
    for side in ('LONG','SHORT'):add(f'side={side}',lambda r,side=side:r['side']==side)
    add('stop=LOW',lambda r:r['stop_pct']<lo)
    add('stop=MID',lambda r:lo<=r['stop_pct']<hi)
    add('stop=HIGH',lambda r:r['stop_pct']>=hi)
    for side in ('LONG','SHORT'):
        add(f'{side}&stop=LOW',lambda r,side=side:r['side']==side and r['stop_pct']<lo)
        add(f'{side}&stop=MID',lambda r,side=side:r['side']==side and lo<=r['stop_pct']<hi)
        add(f'{side}&stop=HIGH',lambda r,side=side:r['side']==side and r['stop_pct']>=hi)
    for h in sorted(set(r['hour_vn'] for r in tr)):add(f'hour={h}',lambda r,h=h:r['hour_vn']==h)
    add('weekday',lambda r:r['dow_vn']<5);add('weekend',lambda r:r['dow_vn']>=5)
    cands.sort(reverse=True,key=lambda x:(x[0],x[1]))
    best=cands[0]
    testsel=[r for r in te if best[3](r)]
    roll.append({'test_month':testm,'train_months':sorted(trainms),'selected_rule':best[2],'train':stat([r for r in tr if best[3](r)]),'test':stat(testsel),'control_test':stat(te),'stop_q33':lo,'stop_q67':hi})
roll_summary={'windows':len(roll),'positive_test_windows':sum(x['test']['net6']>0 for x in roll),'negative_test_windows':sum(x['test']['net6']<=0 for x in roll)}
for key in ('n','gross','net4','net6','net8','net10'):roll_summary[key]=sum(x['test'][key] for x in roll)
roll_summary['avg_net6']=roll_summary['net6']/roll_summary['n'] if roll_summary['n'] else None
roll_summary['control_net6']=sum(x['control_test']['net6'] for x in roll)
roll_summary['control_n']=sum(x['control_test']['n'] for x in roll)

sess=requests.Session();sess.headers['User-Agent']='runner3-wr2515-regime/1.0'
months_dl=[(2024,12)]+[(2025,m) for m in range(1,13)]+[(2026,m) for m in range(1,8)]

def getzip(url):
    for k in range(4):
        try:
            rr=sess.get(url,timeout=60)
            if rr.status_code==404:return None
            rr.raise_for_status();return rr.content
        except Exception:
            if k==3:raise
            time.sleep(.5*(k+1))

def parse_zip(data):
    out=[]
    if not data:return out
    with zipfile.ZipFile(io.BytesIO(data)) as z:text=z.read(z.namelist()[0]).decode()
    for row in csv.reader(io.StringIO(text)):
        if row and row[0].isdigit():out.append((int(row[0]),float(row[1]),float(row[2]),float(row[3]),float(row[4]),float(row[5])))
    return out

def load10(sym):
    raw=[]
    for y,m in months_dl:
        fn=f'{sym}-5m-{y:04d}-{m:02d}.zip';u=f'https://data.binance.vision/data/futures/um/monthly/klines/{sym}/5m/{fn}'
        try:raw.extend(parse_zip(getzip(u)))
        except Exception as e:print('FETCH_ERR',sym,fn,repr(e),flush=True)
    for d in range(1,16):
        fn=f'{sym}-5m-2026-08-{d:02d}.zip';u=f'https://data.binance.vision/data/futures/um/daily/klines/{sym}/5m/{fn}'
        try:raw.extend(parse_zip(getzip(u)))
        except Exception as e:print('FETCH_ERR',sym,fn,repr(e),flush=True)
    ded={x[0]:x for x in raw}; raw=[ded[k] for k in sorted(ded)]
    g=defaultdict(list)
    for x in raw:g[(x[0]//600000)*600000].append(x)
    bars=[]
    for ot in sorted(g):
        xs=sorted(g[ot]);bars.append((ot,ot+599999,xs[0][1],max(x[2] for x in xs),min(x[3] for x in xs),xs[-1][4],sum(x[5] for x in xs)))
    return bars

def prep(bars):
    n=len(bars);trs=[None]*n;atr=[None]*n;ps=[0.0]
    for i,b in enumerate(bars):
        prev=bars[i-1][5] if i else b[5]
        trs[i]=max(b[3]-b[4],abs(b[3]-prev),abs(b[4]-prev));ps.append(ps[-1]+b[5])
        if i>=13:atr[i]=sum(trs[i-13:i+1])/14
    return atr,ps,{b[1]:i for i,b in enumerate(bars)}

def sma(prefix,i,n):
    if i+1<n:return None
    return (prefix[i+1]-prefix[i+1-n])/n

def feat_at(bars,prepobj,ct,first_ct):
    atr,ps,ix=prepobj;i=ix.get(ct)
    if i is None or i<200 or atr[i] is None:return None
    a=atr[i];prev=[x for x in atr[max(13,i-50):i] if x is not None];meda=statistics.median(prev) if prev else None
    medv=statistics.median([bars[j][6] for j in range(max(0,i-50),i)]) if i else None
    s50=sma(ps,i,50);s200=sma(ps,i,200);close=bars[i][5]
    return {'atr_pct':100*a/close if close else None,'atr_ratio50':a/meda if meda else None,'vol_ratio50':bars[i][6]/medv if medv else None,
            'trend50_pct':100*(close/s50-1) if s50 else None,'trend200_pct':100*(close/s200-1) if s200 else None,'listing_age_days':(ct-first_ct)/86400000}

robtr=[r for r in rows if r['symbol'] in robust]
market_bars=load10('BTCUSDT');market_p=prep(market_bars);market_first=market_bars[0][1] if market_bars else 0
byrob=defaultdict(list)
for r in robtr:byrob[r['symbol']].append(r)
enriched=[];miss=0
for k,(sym,rs) in enumerate(sorted(byrob.items()),1):
    print('REGIME_SYMBOL',k,len(byrob),sym,flush=True)
    bars=load10(sym)
    if not bars:continue
    pp=prep(bars);first=bars[0][1]
    for r in rs:
        f=feat_at(bars,pp,r['signal_time'],first);mf=feat_at(market_bars,market_p,r['signal_time'],market_first) if market_bars else None
        if not f:miss+=1;continue
        z=dict(r);z.update(f)
        if mf:z['btc_trend200_pct']=mf['trend200_pct'];z['btc_atr_pct']=mf['atr_pct']
        enriched.append(z)

num_features=['stop_pct','atr_pct','atr_ratio50','vol_ratio50','trend50_pct','trend200_pct','listing_age_days','btc_trend200_pct','btc_atr_pct']
train=[r for r in enriched if r['year']==2025];test=[r for r in enriched if r['year']==2026]
regime={'warning':'robust40 cohort was selected using both 2025 and 2026 positivity; 2026 results here are diagnostic, NOT clean OOS','robust_symbols':len(robust),'enriched_trades':len(enriched),'missing_features':miss,'features':{},'best_2025_single_buckets':[]}
for f in num_features:
    vals=[r.get(f) for r in train if r.get(f) is not None and math.isfinite(r.get(f))]
    if len(vals)<100:continue
    a=q(vals,.33);b=q(vals,.67)
    def bucket(r):
        v=r.get(f)
        if v is None:return None
        return 'LOW' if v<a else ('MID' if v<b else 'HIGH')
    info={'q33_2025':a,'q67_2025':b,'2025':{},'2026':{}}
    for lab in ('LOW','MID','HIGH'):
        info['2025'][lab]=stat([r for r in train if bucket(r)==lab]);info['2026'][lab]=stat([r for r in test if bucket(r)==lab])
    regime['features'][f]=info
    eligible=[(info['2025'][lab]['avg_net6'],lab) for lab in ('LOW','MID','HIGH') if info['2025'][lab]['n']>=200]
    if eligible:
        _,lab=max(eligible);regime['best_2025_single_buckets'].append({'feature':f,'bucket':lab,'train':info['2025'][lab],'test_2026_diagnostic':info['2026'][lab]})
regime['best_2025_single_buckets'].sort(key=lambda x:x['train']['avg_net6'],reverse=True)

report={'status':'WR2515_REGIME_ROLLING_CONCENTRATION_COMPLETE','source_run_10m':32227901385,'source_phase3_run':32237685368,
        'concentration':conc,'rolling_3m_1m_oos':{'summary':roll_summary,'windows':roll},'robust40_dynamic_regime_diagnostic':regime}
(OUT/'report.json').write_text(json.dumps(report,indent=2));(OUT/'rolling_oos.json').write_text(json.dumps({'summary':roll_summary,'windows':roll},indent=2));(OUT/'concentration.json').write_text(json.dumps(conc,indent=2));(OUT/'regime40.json').write_text(json.dumps(regime,indent=2))
with (OUT/'enriched_robust40.jsonl').open('w') as f:
    for r in enriched:f.write(json.dumps(r,separators=(',',':'))+'\n')
print(json.dumps({'status':report['status'],'rolling':roll_summary,'concentration_all':conc['all'],'regime_top5':regime['best_2025_single_buckets'][:5]},indent=2))
