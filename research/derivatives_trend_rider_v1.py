#!/usr/bin/env python3
"""Derivatives Trend Rider v1 — frozen strategy; data-layer repair only.
Actual Binance USD-M derivatives positioning selects rare trend states; price only times entry.
No Wave Rider C3/T-day reuse. Missing derivatives history => no signal.
10m execution is deterministically resampled from native Binance 5m klines.
"""
from __future__ import annotations
import argparse, io, math, zipfile, urllib.request
from pathlib import Path
import numpy as np
import pandas as pd

ROOT='https://data.binance.vision/data/futures/um'
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

def days(year):
    end=pd.Timestamp(f'{year}-08-14',tz='UTC') if year==2026 else pd.Timestamp(f'{year}-12-31',tz='UTC')
    return pd.date_range(pd.Timestamp(f'{year}-01-01',tz='UTC'),end,freq='D')

def load_kl(sym,interval,year):
    # Binance does not publish native 10m archives. For 10m, fetch native 5m and
    # aggregate fixed UTC-aligned pairs: open=first, high=max, low=min, close=last, quote volume=sum.
    source_interval='5m' if interval=='10m' else interval
    arr=[]
    for ym in months(year):
        d=read_zip(f'{ROOT}/monthly/klines/{sym}/{source_interval}/{sym}-{source_interval}-{ym}.zip')
        if d is None:continue
        d=d.iloc[:,:12]; d.columns=['ot','o','h','l','c','v','ct','qv','n','tbv','tbq','x']
        for c in ['ot','o','h','l','c','qv']:d[c]=pd.to_numeric(d[c],errors='coerce')
        arr.append(d[['ot','o','h','l','c','qv']])
    if year==2026:
        for day in range(1,15):
            ds=f'2026-08-{day:02d}'; d=read_zip(f'{ROOT}/daily/klines/{sym}/{source_interval}/{sym}-{source_interval}-{ds}.zip')
            if d is None:continue
            d=d.iloc[:,:12]; d.columns=['ot','o','h','l','c','v','ct','qv','n','tbv','tbq','x']
            for c in ['ot','o','h','l','c','qv']:d[c]=pd.to_numeric(d[c],errors='coerce')
            arr.append(d[['ot','o','h','l','c','qv']])
    if not arr:return None
    x=pd.concat(arr).drop_duplicates('ot').sort_values('ot'); x['dt']=pd.to_datetime(x.ot,unit='ms',utc=True,errors='coerce'); x=x.dropna(subset=['dt']).set_index('dt')
    if interval=='10m':
        x=(x[['o','h','l','c','qv']].resample('10min',origin='epoch',label='left',closed='left')
           .agg({'o':'first','h':'max','l':'min','c':'last','qv':'sum'}).dropna(subset=['o','h','l','c']))
    return x

def norm(s):return str(s).lower().replace('_','').replace('-','').replace(' ','')
def findcol(df,alternatives):
    if df is None:return None
    cols={norm(c):c for c in df.columns}
    for keys in alternatives:
        for nc,c in cols.items():
            if all(k in nc for k in keys):return c
    return None

def parse_time(v):
    n=pd.to_numeric(v,errors='coerce')
    if n.notna().mean()>.8:
        med=n.dropna().abs().median()
        unit='us' if med>1e14 else ('ms' if med>1e11 else 's')
        return pd.to_datetime(n,unit=unit,utc=True,errors='coerce')
    return pd.to_datetime(v,utc=True,errors='coerce')

def load_oi_metrics(sym,year):
    arr=[]; hit=0
    for d in days(year):
        ds=d.strftime('%Y-%m-%d'); x=read_zip(f'{ROOT}/daily/metrics/{sym}/{sym}-metrics-{ds}.zip')
        if x is not None and len(x):arr.append(x);hit+=1
    return (pd.concat(arr,ignore_index=True) if arr else None),hit

def load_funding(sym,year):
    arr=[]
    for ym in months(year):
        x=read_zip(f'{ROOT}/monthly/fundingRate/{sym}/{sym}-fundingRate-{ym}.zip')
        if x is not None and len(x):arr.append(x)
    return pd.concat(arr,ignore_index=True) if arr else None

def derivatives_hourly(sym,year,k1):
    met,metric_days=load_oi_metrics(sym,year); fun=load_funding(sym,year)
    diag={'metric_days':metric_days,'metric_rows':0 if met is None else len(met),'funding_rows':0 if fun is None else len(fun)}
    if met is None or fun is None:return None,diag
    tc=findcol(met,[['createtime'],['timestamp'],['time']])
    oi=findcol(met,[['sumopeninterestvalue'],['sumopeninterest'],['openinterest']])
    ft=findcol(fun,[['fundingtime'],['calctime'],['timestamp'],['time']])
    fr=findcol(fun,[['lastfundingrate'],['fundingrate']])
    diag.update({'metric_time_col':tc or '', 'oi_col':oi or '', 'fund_time_col':ft or '', 'fund_col':fr or ''})
    if not all([tc,oi,ft,fr]):return None,diag
    m=met[[tc,oi]].copy(); m['dt']=parse_time(m[tc]); m[oi]=pd.to_numeric(m[oi],errors='coerce'); m=m.dropna(subset=['dt',oi]).set_index('dt').sort_index()[[oi]].resample('1h').last().ffill(limit=2)
    f=fun[[ft,fr]].copy(); f['dt']=parse_time(f[ft]); f[fr]=pd.to_numeric(f[fr],errors='coerce'); f=f.dropna(subset=['dt',fr]).set_index('dt').sort_index()[[fr]].resample('1h').last().ffill(limit=8)
    x=k1[['c','qv']].copy(); x['ret4']=x.c.pct_change(4); x['ret24']=x.c.pct_change(24); x['rvol']=x.qv/x.qv.rolling(24).median(); x=x.join(m).join(f)
    x['oi4']=x[oi].pct_change(4); x['oi24']=x[oi].pct_change(24); x['fund']=x[fr]; x['dfund']=x[fr]-x[fr].shift(8)
    x['participation']=np.sign(x.ret4)*(x.ret4.abs().rank(pct=True)+x.oi4.clip(lower=0).rank(pct=True)+x.rvol.rank(pct=True))
    x['squeeze']=np.sign(x.ret4)*(x.ret4.abs().rank(pct=True)+(-np.sign(x.ret4)*x.fund).rank(pct=True)+x.oi4.abs().rank(pct=True))
    x['divergence']=np.sign(x.ret24)*(x.ret24.abs().rank(pct=True)+(-np.sign(x.ret24)*x.oi24).rank(pct=True)+x.dfund.abs().rank(pct=True))
    diag['usable_hour_rows']=int(x[['oi4','fund']].dropna().shape[0])
    return x[['ret4','ret24','rvol','oi4','oi24','fund','dfund','participation','squeeze','divergence']].replace([np.inf,-np.inf],np.nan),diag

def atr(df,n=14):
    pc=df.c.shift(); tr=pd.concat([(df.h-df.l),(df.h-pc).abs(),(df.l-pc).abs()],axis=1).max(axis=1); return tr.rolling(n).mean()

def run(year,tf):
    der={}; kt={}; diagnostics=[]
    for s in SYMS:
        a=load_kl(s,'1h',year); b=load_kl(s,tf,year)
        if a is None or b is None:
            diagnostics.append({'symbol':s,'tf':tf,'price_ok':False});continue
        d,diag=derivatives_hourly(s,year,a); diag.update({'symbol':s,'tf':tf,'price_ok':True,'derivatives_ok':d is not None}); diagnostics.append(diag)
        if d is None or diag.get('usable_hour_rows',0)<24:continue
        der[s]=d; kt[s]=b
    if len(der)<6:return pd.DataFrame(),diagnostics
    common=sorted(set().union(*[set(x.index) for x in der.values()])); states={s:{} for s in der}
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
            vals=sorted([(s,float(r[fam])) for s,r in rows if pd.notna(r[fam])],key=lambda z:z[1]); n=max(1,int(math.ceil(len(vals)*.10))); lo={s for s,_ in vals[:n]}; hi={s for s,_ in vals[-n:]}
            for s,r in rows:
                side=None
                if s in hi and breadth>=.55 and r.ret4>0:side='LONG'
                if s in lo and breadth<=.45 and r.ret4<0:side='SHORT'
                if side:states[s][(t,fam)]=(side,float(r[fam]))
    trades=[]
    for s,df in kt.items():
        z=df.copy(); z['atr']=atr(z); z['hi12']=z.h.shift(1).rolling(12).max(); z['lo12']=z.l.shift(1).rolling(12).min()
        for i in range(21,len(z)-1):
            t=z.index[i]; ht=t.floor('1h')-pd.Timedelta(hours=1)
            for fam in ['participation','squeeze','divergence']:
                st=states[s].get((ht,fam))
                if not st:continue
                side,score=st; row=z.iloc[i]
                if side=='LONG' and not (row.c>row.hi12):continue
                if side=='SHORT' and not (row.c<row.lo12):continue
                entry=float(row.c); stop=float(entry-1.5*row.atr if side=='LONG' else entry+1.5*row.atr); risk=abs(entry-stop); sp=risk/entry
                if not (.002<=sp<=.025):continue
                for tp in TP_GRID:
                    target=entry+(tp*risk if side=='LONG' else -tp*risk); gross=None
                    for j in range(i+1,min(i+49,len(z))):
                        q=z.iloc[j]
                        if side=='LONG':
                            if q.l<=stop:gross=-1;break
                            if q.h>=target:gross=tp;break
                        else:
                            if q.h>=stop:gross=-1;break
                            if q.l<=target:gross=tp;break
                    if gross is None:
                        ex=float(z.iloc[min(i+48,len(z)-1)].c); gross=((ex-entry)/risk)*(1 if side=='LONG' else -1)
                    rec={'year':year,'tf':tf,'family':fam,'tp':tp,'symbol':s,'time':t.isoformat(),'side':side,'grossR':gross,'stop_pct':sp,'score':score}
                    for c in COSTS:rec[f'net{c}']=gross-(entry/risk)*c/10000
                    trades.append(rec)
    return pd.DataFrame(trades),diagnostics

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--year',type=int,required=True); ap.add_argument('--out',required=True); a=ap.parse_args(); out=Path(a.out);out.mkdir(parents=True,exist_ok=True)
    # 5m already completed and failed comprehensively in run 32376461430. This repair run tests only the previously missing 10m branch.
    all=[];diags=[]
    for tf in ['10m']:
        d,g=run(a.year,tf);diags+=g
        if len(d):all.append(d)
    x=pd.concat(all,ignore_index=True) if all else pd.DataFrame(); x.to_csv(out/'trades.csv',index=False); pd.DataFrame(diags).to_csv(out/'coverage.csv',index=False)
    eligible=len(set(pd.DataFrame(diags).query("derivatives_ok == True").symbol)) if diags and 'derivatives_ok' in pd.DataFrame(diags).columns else 0
    print('year',a.year,'rows',len(x),'eligible_symbols',eligible,'timeframes',sorted(x.tf.unique()) if len(x) else [])
    if eligible<6:raise SystemExit(f'DATA_QUALITY_FAIL eligible_symbols={eligible}')
    if len(x)==0 or set(x.tf.astype(str))!={'10m'}:raise SystemExit('DATA_QUALITY_FAIL missing_10m_trades')
if __name__=='__main__':main()
