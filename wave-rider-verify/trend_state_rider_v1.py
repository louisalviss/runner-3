#!/usr/bin/env python3
import csv, io, json, math, os, statistics, time, zipfile
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
import requests

YEAR=int(os.getenv('YEAR','2025'))
OUT=Path(os.getenv('OUT_DIR','/tmp/tsr')); OUT.mkdir(parents=True,exist_ok=True)
SYMBOLS=['BTCUSDT','ETHUSDT','SOLUSDT','XRPUSDT','BNBUSDT','DOGEUSDT','ADAUSDT','AVAXUSDT','LINKUSDT','DOTUSDT','BCHUSDT','LTCUSDT','TRXUSDT','AAVEUSDT','NEARUSDT']
TFS=(5,10)
ALPHAS=('PRICE_FLOW','PRICE_OI','PRICE_OI_FUND')
ENTRIES=('BREAK12','PULLBACK20')
TPS=(1.5,2.0,2.5,3.0)
BPS=(4,6,8,10,12)
MAX_POS=3
EPISODE_MS=30*60*1000
MIN_STOP=.002
MAX_STOP=.025
BASE='https://data.binance.vision/data/futures/um'
sess=requests.Session(); sess.headers['User-Agent']='runner3-trend-state-rider-v1/1.0'

class Bar:
    __slots__=('ot','o','h','l','c','ct','qv','tbq')
    def __init__(self,r):
        self.ot=int(r[0]); self.o=float(r[1]); self.h=float(r[2]); self.l=float(r[3]); self.c=float(r[4]); self.ct=int(r[6]); self.qv=float(r[7]); self.tbq=float(r[10])

def getzip(url):
    for k in range(4):
        try:
            r=sess.get(url,timeout=60)
            if r.status_code==404:return None
            r.raise_for_status(); return r.content
        except Exception:
            if k==3: raise
            time.sleep(.6*(k+1))

def csv_rows(data):
    if not data:return []
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        text=z.read(z.namelist()[0]).decode('utf-8-sig')
    return list(csv.reader(io.StringIO(text)))

def month_seq(year):
    seq=[]
    py,pm=(year-1,12)
    seq.append((py,pm))
    last=7 if year==2026 else 12
    seq += [(year,m) for m in range(1,last+1)]
    return seq

def load_5m(sym):
    out=[]
    for y,m in month_seq(YEAR):
        fn=f'{sym}-5m-{y:04d}-{m:02d}.zip'
        url=f'{BASE}/monthly/klines/{sym}/5m/{fn}'
        try:
            for r in csv_rows(getzip(url)):
                if r and r[0].isdigit(): out.append(Bar(r))
        except Exception as e: print('KLINE_ERR',sym,fn,repr(e),flush=True)
    if YEAR==2026:
        for d in range(1,15):
            fn=f'{sym}-5m-2026-08-{d:02d}.zip'; url=f'{BASE}/daily/klines/{sym}/5m/{fn}'
            try:
                for r in csv_rows(getzip(url)):
                    if r and r[0].isdigit(): out.append(Bar(r))
            except Exception as e: print('KLINE_ERR',sym,fn,repr(e),flush=True)
    ded={b.ot:b for b in out}; return [ded[k] for k in sorted(ded)]

def parse_ts(v):
    try:
        x=float(v); return int(x if x>1e12 else x*1000)
    except: pass
    for f in ('%Y-%m-%d %H:%M:%S','%Y-%m-%dT%H:%M:%S','%Y-%m-%d'):
        try:return int(datetime.strptime(v[:19],f).replace(tzinfo=timezone.utc).timestamp()*1000)
        except:pass
    return None

def load_series(sym,kind):
    # Binance Vision historical futures auxiliary series. Missing files are not imputed.
    vals=[]
    for y,m in month_seq(YEAR):
        fn=f'{sym}-{kind}-{y:04d}-{m:02d}.zip'; url=f'{BASE}/monthly/{kind}/{sym}/{fn}'
        try: rows=csv_rows(getzip(url))
        except Exception as e: print(kind.upper()+'_ERR',sym,fn,repr(e),flush=True); continue
        if not rows: continue
        header=[x.strip().lower() for x in rows[0]]
        has_header=any(not x.replace('.','',1).isdigit() for x in rows[0])
        data=rows[1:] if has_header else rows
        for r in data:
            try:
                if kind=='metrics':
                    if has_header:
                        d=dict(zip(header,r)); ts=parse_ts(d.get('create_time',''))
                        vv=d.get('sum_open_interest_value') or d.get('sum_open_interest')
                    else:
                        ts=parse_ts(r[0]); vv=r[2] if len(r)>2 else None
                else:
                    if has_header:
                        d=dict(zip(header,r)); ts=parse_ts(d.get('calc_time') or d.get('funding_time') or d.get('time') or '')
                        vv=d.get('last_funding_rate') or d.get('funding_rate')
                    else:
                        ts=parse_ts(r[0]); vv=r[-1]
                if ts is not None and vv is not None: vals.append((ts,float(vv)))
            except: continue
    vals.sort(); return vals

def ema(v,n):
    a=2/(n+1); p=None; out=[]
    for x in v:
        p=x if p is None else a*x+(1-a)*p; out.append(p)
    return out

def aggregate(b,mins):
    ms=mins*60000; g=defaultdict(list)
    for x in b:g[(x.ot//ms)*ms].append(x)
    out=[]
    for ot in sorted(g):
        xs=sorted(g[ot],key=lambda z:z.ot)
        if not xs:continue
        r=['0']*11; r[0]=str(ot); r[1]=str(xs[0].o); r[2]=str(max(z.h for z in xs)); r[3]=str(min(z.l for z in xs)); r[4]=str(xs[-1].c); r[6]=str(ot+ms-1); r[7]=str(sum(z.qv for z in xs)); r[10]=str(sum(z.tbq for z in xs))
        out.append(Bar(r))
    return out

def latest_before(series,ts,max_age_ms):
    # simple binary search
    lo,hi=0,len(series)
    while lo<hi:
        mid=(lo+hi)//2
        if series[mid][0]<=ts:lo=mid+1
        else:hi=mid
    if lo==0:return None
    t,v=series[lo-1]
    return v if ts-t<=max_age_ms else None

def zscores(vals):
    good=[x for x in vals if x is not None and math.isfinite(x)]
    if len(good)<5:return [None]*len(vals)
    mu=sum(good)/len(good); sd=(sum((x-mu)**2 for x in good)/len(good))**.5
    if sd<1e-12:return [0.0 if x is not None else None for x in vals]
    return [None if x is None else (x-mu)/sd for x in vals]

def build_alpha(data,oi,fund):
    # Hourly cross-sectional alpha. All features are based on completed 1h bars only.
    h1={s:aggregate(data[s],60) for s in data}
    feats=defaultdict(dict)
    for s,b in h1.items():
        c=[x.c for x in b]; e20=ema(c,20); e50=ema(c,50)
        for i in range(50,len(b)):
            t=b[i].ct
            if datetime.fromtimestamp(t/1000,timezone.utc).year!=YEAR: continue
            m4=c[i]/c[i-4]-1 if i>=4 else None
            m24=c[i]/c[i-24]-1 if i>=24 else None
            q4=sum(x.qv for x in b[i-3:i+1])
            prev=[x.qv for x in b[max(0,i-27):i-3]]
            rv=q4/((sum(prev)/len(prev))*4) if prev and sum(prev)>0 else None
            ov=latest_before(oi.get(s,[]),t,2*3600000)
            ov0=latest_before(oi.get(s,[]),t-4*3600000,2*3600000)
            od=(ov/ov0-1) if ov is not None and ov0 not in (None,0) else None
            fu=latest_before(fund.get(s,[]),t,12*3600000)
            feats[t][s]={'m4':m4,'m24':m24,'rv':math.log(max(rv,1e-9)) if rv else None,'oi4':od,'fund':fu,'trend':1 if e20[i]>e50[i] and e50[i]>e50[i-4] else (-1 if e20[i]<e50[i] and e50[i]<e50[i-4] else 0)}
    states={a:defaultdict(dict) for a in ALPHAS}
    for t,row in sorted(feats.items()):
        syms=[s for s in SYMBOLS if s in row and row[s]['m24'] is not None]
        if len(syms)<8 or 'BTCUSDT' not in row: continue
        btc=row['BTCUSDT']['m24']; breadth=sum(row[s]['m24']>0 for s in syms)/len(syms)
        raw={}
        cols={k:zscores([row[s][k] for s in syms]) for k in ('m4','m24','rv','oi4','fund')}
        for j,s in enumerate(syms):
            rs=row[s]['m24']-btc
            raw.setdefault(s,{})['rs']=rs
        zrs=zscores([raw[s]['rs'] for s in syms])
        for j,s in enumerate(syms):
            base=cols['m4'][j]+cols['m24'][j]+zrs[j]+0.5*cols['rv'][j] if None not in (cols['m4'][j],cols['m24'][j],zrs[j],cols['rv'][j]) else None
            scores={'PRICE_FLOW':base}
            scores['PRICE_OI']=None if base is None or cols['oi4'][j] is None else base+0.75*cols['oi4'][j]
            scores['PRICE_OI_FUND']=None if scores['PRICE_OI'] is None or cols['fund'][j] is None else scores['PRICE_OI'][j] if False else scores['PRICE_OI']+0.25*cols['fund'][j]
            for a,sc in scores.items():
                if sc is not None: states[a][t][s]={'score':sc,'trend':row[s]['trend'],'breadth':breadth}
    # Convert scores to top/bottom 20% rank, with breadth gate.
    ranked={a:defaultdict(dict) for a in ALPHAS}
    for a in ALPHAS:
        for t,row in states[a].items():
            arr=sorted([(v['score'],s,v) for s,v in row.items()])
            n=len(arr); k=max(1,int(math.ceil(n*.20)))
            shorts=arr[:k]; longs=arr[-k:]
            for sc,s,v in shorts:
                if v['trend']==-1 and v['breadth']<=.45: ranked[a][t][s]={'dir':-1,'score':sc,'breadth':v['breadth']}
            for sc,s,v in longs:
                if v['trend']==1 and v['breadth']>=.55: ranked[a][t][s]={'dir':1,'score':sc,'breadth':v['breadth']}
    return ranked

def strength(x,d):
    r=x.h-x.l
    if r<=0:return False
    body=abs(x.c-x.o)/r; clv=(x.c-x.l)/r
    return body>=.35 and (clv>=.65 if d==1 else clv<=.35)

def alpha_at(ranked,alpha,sym,ts):
    hour=((ts//3600000)*3600000)-1
    # completed hour timestamps are xx:59:59.999; find latest state within 65m
    keys=ranked[alpha]
    candidates=[k for k in (hour, hour-1, hour+3599999) if k in keys]
    if candidates:
        k=max(x for x in candidates if x<=ts)
        return keys[k].get(sym)
    # fallback bounded scan of recent exact keys
    recent=[k for k in keys.keys() if 0<=ts-k<=3900000]
    if not recent:return None
    return keys[max(recent)].get(sym)

def candidates_for(sym,b,ranked,alpha,entry,tp):
    c=[x.c for x in b]; e20=ema(c,20); out=[]; active_until=-1
    for i in range(25,len(b)-1):
        x=b[i]
        if datetime.fromtimestamp(x.ct/1000,timezone.utc).year!=YEAR:continue
        if x.ot<=active_until:continue
        st=alpha_at(ranked,alpha,sym,x.ct)
        if not st:continue
        d=st['dir']; sig=False; stop=None
        if entry=='BREAK12':
            hh=max(y.h for y in b[i-12:i]); ll=min(y.l for y in b[i-12:i])
            sig=(d==1 and x.c>hh and strength(x,1)) or (d==-1 and x.c<ll and strength(x,-1))
            stop=min(y.l for y in b[i-2:i+1]) if d==1 else max(y.h for y in b[i-2:i+1])
        else:
            p=b[i-1]
            sig=(d==1 and x.l<=e20[i] and x.c>e20[i] and x.c>p.h and strength(x,1)) or (d==-1 and x.h>=e20[i] and x.c<e20[i] and x.c<p.l and strength(x,-1))
            stop=min(x.l,p.l) if d==1 else max(x.h,p.h)
        if not sig:continue
        ent=x.c; risk=abs(ent-stop); sp=risk/ent
        if not (MIN_STOP<=sp<=MAX_STOP):continue
        target=ent+d*tp*risk; exit_px=None; exit_t=None; reason=None
        for y in b[i+1:]:
            sl=(y.l<=stop if d==1 else y.h>=stop); hit=(y.h>=target if d==1 else y.l<=target)
            if sl and hit:
                exit_px=stop; exit_t=y.ct; reason='SL_samebar'; break
            if sl: exit_px=stop; exit_t=y.ct; reason='SL'; break
            if hit: exit_px=target; exit_t=y.ct; reason='TP'; break
            if y.ot-x.ot>=24*3600000:
                exit_px=y.c; exit_t=y.ct; reason='TIME24H'; break
        if exit_px is None:continue
        R=(exit_px-ent)*d/risk
        rec={'year':YEAR,'symbol':sym,'tf':int((b[1].ot-b[0].ot)/60000),'alpha':alpha,'entry_mode':entry,'tp':tp,'signal_time':x.ct,'exit_time':exit_t,'side':'LONG' if d==1 else 'SHORT','score':st['score'],'breadth':st['breadth'],'entry':ent,'stop':stop,'R':R,'exit_reason':reason}
        for bp in BPS:rec[f'net{bp}']=R-(ent/risk)*bp/10000
        out.append(rec); active_until=exit_t
    return out

def portfolio(trades,bp=6):
    # Max 3 concurrent positions. New signals in the same 30m episode share 1R total risk.
    byep=defaultdict(list)
    for r in trades: byep[r['signal_time']//EPISODE_MS].append(r)
    openx=[]; selected=[]
    for ep in sorted(byep):
        t=ep*EPISODE_MS
        openx=[x for x in openx if x>t]
        slots=MAX_POS-len(openx)
        if slots<=0:continue
        arr=sorted(byep[ep],key=lambda r:abs(r['score']),reverse=True)[:slots]
        if not arr:continue
        w=1/len(arr)
        for r in arr:
            selected.append((r,w)); openx.append(r['exit_time'])
    net=sum(r[f'net{bp}']*w for r,w in selected)
    return {'selected':len(selected),'episodes':len(set(r['signal_time']//EPISODE_MS for r,w in selected)),'portfolio_net':net}

def main():
    data={}; oi={}; fund={}; errors=[]
    for s in SYMBOLS:
        try:
            data[s]=load_5m(s)
            oi[s]=load_series(s,'metrics')
            fund[s]=load_series(s,'fundingRate')
            print('LOAD',s,len(data[s]),len(oi[s]),len(fund[s]),flush=True)
        except Exception as e: errors.append({'symbol':s,'error':repr(e)}); print('LOAD_ERR',s,repr(e),flush=True)
    data={s:b for s,b in data.items() if len(b)>1000}
    ranked=build_alpha(data,oi,fund)
    alltr=[]
    for tf in TFS:
        series={s:(data[s] if tf==5 else aggregate(data[s],10)) for s in data}
        for alpha in ALPHAS:
            for entry in ENTRIES:
                for tp in TPS:
                    for s,b in series.items(): alltr += candidates_for(s,b,ranked,alpha,entry,tp)
    with open(OUT/f'trades-{YEAR}.jsonl','w') as f:
        for r in alltr:f.write(json.dumps(r,separators=(',',':'))+'\n')
    summary=[]
    groups=defaultdict(list)
    for r in alltr:groups[(r['tf'],r['alpha'],r['entry_mode'],r['tp'])].append(r)
    for key,rs in groups.items():
        tf,a,e,tp=key; row={'year':YEAR,'tf':tf,'alpha':a,'entry':e,'tp':tp,'trades':len(rs)}
        for bp in BPS:
            row[f'raw_net{bp}']=sum(r[f'net{bp}'] for r in rs)
            p=portfolio(rs,bp); row[f'port_net{bp}']=p['portfolio_net']; row[f'port_selected{bp}']=p['selected']; row[f'episodes{bp}']=p['episodes']
        summary.append(row)
    json.dump(summary,open(OUT/f'summary-{YEAR}.json','w'),indent=2)
    json.dump(errors,open(OUT/f'errors-{YEAR}.json','w'),indent=2)
    print('DONE',YEAR,'symbols',len(data),'trades',len(alltr),'configs',len(summary),flush=True)

if __name__=='__main__':main()
