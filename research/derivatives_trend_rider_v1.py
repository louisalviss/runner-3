#!/usr/bin/env python3
"""Derivatives Trend Rider v1 — frozen pre-result design.
Actual Binance USD-M derivatives positioning selects rare trend states; price only times entry.
No Wave Rider C3/T-day reuse. Missing derivatives history => no signal.
"""
from __future__ import annotations
import argparse, io, math, zipfile, urllib.request
from pathlib import Path
import numpy as np
import pandas as pd

BASE='https://data.binance.vision/data/futures/um/monthly'
SYMS=['BTCUSDT','ETHUSDT','BNBUSDT','SOLUSDT','XRPUSDT','DOGEUSDT','ADAUSDT','LINKUSDT','AVAXUSDT','DOTUSDT','LTCUSDT','BCHUSDT','TRXUSDT','UNIUSDT','ATOMUSDT','NEARUSDT','APTUSDT','SUIUSDT']
TP_GRID=[1.5,2.0,2.5,3.0]; COSTS=[4,6,8,10,12]

def dl(url):
    try:
        with urllib.request.urlopen(url,timeout=30) as r:return r.read()
    except Exception:return None

def read_zip(url):
    b=dl(url)
    if not b:return None
    try:
        z=zipfile.ZipFile(io.BytesIO(b)); return pd.read_csv(z.open(z.namelist()[0]))
    except Exception:return None

def months(year):
    end=8 if year==2026 else 12
    return [f'{year}-{m:02d}' for m in range(1,end+1)]

def load_kl(sym,interval,year):
    arr=[]
    for ym in months(year):
        d=read_zip(f'{BASE}/klines/{sym}/{interval}/{sym}-{interval}-{ym}.zip')
        if d is None:continue
        d=d.iloc[:,:12]; d.columns=['ot','o','h','l','c','v','ct','qv','n','tbv','tbq','x']
        for c in ['ot','o','h','l','c','qv']:d[c]=pd.to_numeric(d[c],errors='coerce')
        arr.append(d[['ot','o','h','l','c','qv']])
    if not arr:return None
    x=pd.concat(arr).drop_duplicates('ot').sort_values('ot'); x['dt']=pd.to_datetime(x.ot,unit='ms',utc=True); return x.set_index('dt')

def load_metric(sym,kind,year):
    # Binance Vision historical metrics. Schema is inspected by column names, never positional guesses.
    arr=[]
    for ym in months(year):
        urls=[]
        if kind=='metrics': urls=[f'{BASE}/metrics/{sym}/{sym}-metrics-{ym}.zip']
        elif kind=='funding': urls=[f'{BASE}/fundingRate/{sym}/{sym}-fundingRate-{ym}.zip']
        for u in urls:
            d=read_zip(u)
            if d is not None:arr.append(d)
    return pd.concat(arr,ignore_index=True) if arr else None

def findcol(df,keys):
    if df is None:return None
    for c in df.columns:
        s=str(c).lower().replace('_','').replace('-','')
        if all(k in s for k in keys):return c
    return None

def derivatives_hourly(sym,year,k1):
    met=load_metric(sym,'metrics',year); fun=load_metric(sym,'funding',year)
    if met is None or fun is None:return None
    tc=findcol(met,['time']); oi=findcol(met,['sum','openinterest']) or findcol(met,['openinterest'])
    ft=findcol(fun,['fundingtime']) or findcol(fun,['time']); fr=findcol(fun,['fundingrate'])
    if not all([tc,oi,ft,fr]):return None
    m=met[[tc,oi]].copy(); m[tc]=pd.to_numeric(m[tc],errors='coerce'); m[oi]=pd.to_numeric(m[oi],errors='coerce'); m['dt']=pd.to_datetime(m[tc],unit='ms',utc=True,errors='coerce'); m=m.dropna().set_index('dt').sort_index()[[oi]].resample('1h').last().ffill(limit=2)
    f=fun[[ft,fr]].copy(); f[ft]=pd.to_numeric(f[ft],errors='coerce'); f[fr]=pd.to_numeric(f[fr],errors='coerce'); f['dt']=pd.to_datetime(f[ft],unit='ms',utc=True,errors='coerce'); f=f.dropna().set_index('dt').sort_index()[[fr]].resample('1h').last().ffill(limit=8)
    x=k1[['c','qv']].copy(); x['ret4']=x.c.pct_change(4); x['ret24']=x.c.pct_change(24); x['rvol']=x.qv/x.qv.rolling(24).median(); x=x.join(m).join(f)
    x['oi4']=x[oi].pct_change(4); x['oi24']=x[oi].pct_change(24); x['fund']=x[fr]; x['dfund']=x[fr]-x[fr].shift(8)
    # Positioning archetypes: trend participation, squeeze release, and divergence. Signed scores only.
    x['participation']=np.sign(x.ret4)*(x.ret4.abs().rank(pct=True)+x.oi4.clip(lower=0).rank(pct=True)+x.rvol.rank(pct=True))
    x['squeeze']=np.sign(x.ret4)*(x.ret4.abs().rank(pct=True)+(-np.sign(x.ret4)*x.fund).rank(pct=True)+x.oi4.abs().rank(pct=True))
    x['divergence']=np.sign(x.ret24)*(x.ret24.abs().rank(pct=True)+(-np.sign(x.ret24)*x.oi24).rank(pct=True)+x.dfund.abs().rank(pct=True))
    return x[['ret4','ret24','rvol','oi4','oi24','fund','dfund','participation','squeeze','divergence']].replace([np.inf,-np.inf],np.nan)

def atr(df,n=14):
    pc=df.c.shift(); tr=pd.concat([(df.h-df.l),(df.h-pc).abs(),(df.l-pc).abs()],axis=1).max(axis=1); return tr.rolling(n).mean()

def run(year,tf):
    k1={}; der={}; kt={}
    for s in SYMS:
        a=load_kl(s,'1h',year); b=load_kl(s,tf,year)
        if a is None or b is None:continue
        d=derivatives_hourly(s,year,a)
        if d is None:continue
        k1[s]=a; der[s]=d; kt[s]=b
    if len(der)<6:return pd.DataFrame(),{'eligible_symbols':len(der)}
    # Cross-sectional ranking at completed hourly timestamps; extreme 10% only.
    common=sorted(set().union(*[set(x.index) for x in der.values()]))
    states={s:{} for s in der}
    for t in common:
        rows=[]
        for s,d in der.items():
            if t not in d.index:continue
            r=d.loc[t]
            if r[['ret4','ret24','rvol','oi4','fund']].isna().any():continue
            rows.append((s,r))
        if len(rows)<6:continue
        breadth=np.mean([r.ret24>0 for _,r in rows])
        for fam in ['participation','squeeze','divergence']:
            vals=sorted([(s,float(r[fam])) for s,r in rows if pd.notna(r[fam])],key=lambda z:z[1])
            n=max(1,int(math.ceil(len(vals)*.10))); lo={s for s,_ in vals[:n]}; hi={s for s,_ in vals[-n:]}
            for s,r in rows:
                side=None
                if s in hi and breadth>=.55 and r.ret4>0:side='LONG'
                if s in lo and breadth<=.45 and r.ret4<0:side='SHORT'
                if side:states[s][(t,fam)]=(side,float(r[fam]))
    trades=[]
    for s,df in kt.items():
        z=df.copy(); z['ema20']=z.c.ewm(span=20,adjust=False).mean(); z['atr']=atr(z); z['hi12']=z.h.shift(1).rolling(12).max(); z['lo12']=z.l.shift(1).rolling(12).min()
        for i in range(21,len(z)-1):
            t=z.index[i]; ht=t.floor('1h')-pd.Timedelta(hours=1) # only completed alpha hour
            for fam in ['participation','squeeze','divergence']:
                st=states[s].get((ht,fam));
                if not st:continue
                side,score=st; row=z.iloc[i]
                if side=='LONG' and not (row.c>row.hi12):continue
                if side=='SHORT' and not (row.c<row.lo12):continue
                entry=float(row.c); stop=float(entry-1.5*row.atr if side=='LONG' else entry+1.5*row.atr); risk=abs(entry-stop); sp=risk/entry
                if not (.002<=sp<=.025):continue
                for tp in TP_GRID:
                    target=entry+(tp*risk if side=='LONG' else -tp*risk); ex=None; gross=None
                    for j in range(i+1,min(i+49,len(z))):
                        q=z.iloc[j]
                        if side=='LONG':
                            if q.l<=stop:ex=stop;gross=-1;break
                            if q.h>=target:ex=target;gross=tp;break
                        else:
                            if q.h>=stop:ex=stop;gross=-1;break
                            if q.l<=target:ex=target;gross=tp;break
                    if ex is None:
                        ex=float(z.iloc[min(i+48,len(z)-1)].c); gross=((ex-entry)/risk)*(1 if side=='LONG' else -1)
                    rec={'year':year,'tf':tf,'family':fam,'tp':tp,'symbol':s,'time':t.isoformat(),'side':side,'grossR':gross,'stop_pct':sp,'score':score}
                    for c in COSTS:rec[f'net{c}']=gross-(entry/risk)*c/10000
                    trades.append(rec)
    return pd.DataFrame(trades),{'eligible_symbols':len(der)}

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--year',type=int,required=True); ap.add_argument('--out',required=True); a=ap.parse_args(); out=Path(a.out);out.mkdir(parents=True,exist_ok=True)
    all=[];meta=[]
    for tf in ['5m','10m']:
        d,m=run(a.year,tf); meta.append({'tf':tf,**m});
        if len(d):all.append(d)
    x=pd.concat(all,ignore_index=True) if all else pd.DataFrame(); x.to_csv(out/'trades.csv',index=False); pd.DataFrame(meta).to_csv(out/'coverage.csv',index=False)
    print('year',a.year,'rows',len(x),'coverage',meta)
if __name__=='__main__':main()
