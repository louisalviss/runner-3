#!/usr/bin/env python3
import json, math, re, time
from datetime import date, timedelta
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
import requests
import yfinance as yf

OUT=Path('spmo-modern2/output'); OUT.mkdir(parents=True,exist_ok=True)
ROOT='hf://datasets/trader298/sec-nport'
SERIES='S000050154'


def third_friday(y,m):
    d=date(y,m,15)
    while d.weekday()!=4:d+=timedelta(days=1)
    return pd.Timestamp(d)

# 13 fully reconstructable rebalance periods with post-rebalance public N-PORT:
# Sep-2019 ... Sep-2025, exits through Mar-2026.
TARGETS=[]
for y in range(2019,2026):
    rb=third_friday(y,9); rep=pd.Timestamp(y,11,30); TARGETS.append((rb,rep,y+1,1))
for y in range(2020,2026):
    rb=third_friday(y,3); rep=pd.Timestamp(y,5,31); TARGETS.append((rb,rep,y,3))
TARGETS=sorted(TARGETS)
NEXT_RB={rb:third_friday(rb.year+1,3) if rb.month==9 else third_friday(rb.year,9) for rb,_,_,_ in TARGETS}

con=duckdb.connect(); con.execute('INSTALL httpfs'); con.execute('LOAD httpfs')


def get_snapshot(rb,rep,y,q):
    info=f"{ROOT}/FUND_REPORTED_INFO/year={y}/quarter={q}/*.parquet"
    sub=f"{ROOT}/SUBMISSION/year={y}/quarter={q}/*.parquet"
    filings=con.execute(f"""
      SELECT f.ACCESSION_NUMBER,f.SERIES_NAME,f.NET_ASSETS,s.FILING_DATE,s.REPORT_DATE,s.IS_LAST_FILING
      FROM '{info}' f JOIN '{sub}' s USING (ACCESSION_NUMBER)
      WHERE f.SERIES_ID='{SERIES}' AND s.REPORT_DATE=DATE '{rep.date()}'
      ORDER BY (upper(coalesce(s.IS_LAST_FILING,''))='Y'),s.FILING_DATE,f.ACCESSION_NUMBER
    """).fetchdf()
    if filings.empty: raise RuntimeError(f'No filing for {rep.date()} partition {y}Q{q}')
    f=filings.iloc[-1]; acc=f.ACCESSION_NUMBER
    hp=f"{ROOT}/FUND_REPORTED_HOLDING/year={y}/quarter={q}/*.parquet"
    ip=f"{ROOT}/IDENTIFIERS/year={y}/quarter={q}/*.parquet"
    h=con.execute(f"""
      WITH ids AS (
        SELECT HOLDING_ID,max(IDENTIFIER_TICKER) FILTER (WHERE IDENTIFIER_TICKER IS NOT NULL) AS ticker,
               max(IDENTIFIER_ISIN) FILTER (WHERE IDENTIFIER_ISIN IS NOT NULL) AS isin
        FROM '{ip}' GROUP BY HOLDING_ID
      )
      SELECT h.HOLDING_ID,h.ISSUER_NAME AS name,h.ISSUER_TITLE,h.ISSUER_CUSIP,
             cast(h.BALANCE as DOUBLE) AS shares,h.UNIT,
             cast(h.CURRENCY_VALUE as DOUBLE) AS value,cast(h.PERCENTAGE as DOUBLE) AS reported_pct,
             h.ASSET_CAT,h.PAYOFF_PROFILE,ids.ticker,ids.isin
      FROM '{hp}' h LEFT JOIN ids USING (HOLDING_ID)
      WHERE h.ACCESSION_NUMBER='{acc}' AND h.ASSET_CAT='EC'
        AND (h.PAYOFF_PROFILE IS NULL OR upper(h.PAYOFF_PROFILE)='LONG')
      ORDER BY h.CURRENCY_VALUE DESC NULLS LAST
    """).fetchdf()
    h=h[h.value.notna() & (h.value>0)].copy()
    h['rb']=rb; h['report_date']=rep; h['accession']=acc
    return f,h


def norm_ticker(x):
    if x is None or (isinstance(x,float) and np.isnan(x)):return None
    s=str(x).strip().upper()
    if not s:return None
    s=s.replace('/','-')
    # Yahoo class-share convention.
    if re.fullmatch(r'[A-Z]+\.[A-Z]',s):s=s.replace('.','-')
    aliases={
      'FB':'META','ANTM':'ELV','ABC':'COR','VIAC':'PARA','VIACA':'PARAA',
      'DISCA':'WBD','DISCK':'WBD','NLOK':'GEN','RE':'EG','PKI':'RVTY',
      'FISV':'FI','INFO':'SPGI','BLL':'BALL','FBHS':'FBIN','CTVA-W':'CTVA'
    }
    return aliases.get(s,s)

snap_rows=[]; frames={}
for rb,rep,y,q in TARGETS:
    f,h=get_snapshot(rb,rep,y,q); h['ticker_raw']=h.ticker; h['ticker']=h.ticker.map(norm_ticker)
    frames[rb]=h
    snap_rows.append({'rb':rb.date(),'report_date':rep.date(),'accession':f.ACCESSION_NUMBER,
                      'filing_date':pd.Timestamp(f.FILING_DATE).date(),'net_assets':float(f.NET_ASSETS),'equities':len(h)})
    print('SNAP',rb.date(),'->',rep.date(),f.ACCESSION_NUMBER,'equities',len(h),flush=True)
pd.DataFrame(snap_rows).to_csv(OUT/'snapshots.csv',index=False)

# Add name-search fallback candidates only when N-PORT ticker is absent.
sess=requests.Session(); sess.headers.update({'User-Agent':'Mozilla/5.0'})
name_cache={}
for h in frames.values():
    for idx,r in h[h.ticker.isna()].iterrows():
        name=r['name']
        if name in name_cache: h.at[idx,'ticker']=name_cache[name]; continue
        try:
            js=sess.get('https://query1.finance.yahoo.com/v1/finance/search',params={'q':name,'quotesCount':6,'newsCount':0},timeout=15).json()
            qs=[z for z in js.get('quotes',[]) if z.get('quoteType')=='EQUITY' and z.get('exchange') in ('NMS','NYQ','NGM','NCM','ASE','PCX')]
            t=norm_ticker(qs[0].get('symbol')) if qs else None
        except Exception:t=None
        name_cache[name]=t; h.at[idx,'ticker']=t; time.sleep(.03)
Path(OUT/'name_ticker_fallback.json').write_text(json.dumps(name_cache,indent=2))

tickers=sorted(set(t for h in frames.values() for t in h.ticker.dropna()))
print('TICKERS',len(tickers),flush=True)
start=(TARGETS[0][0]-pd.Timedelta(days=10)).strftime('%Y-%m-%d')
end=(NEXT_RB[TARGETS[-1][0]]+pd.Timedelta(days=10)).strftime('%Y-%m-%d')
data=yf.download(tickers,start=start,end=end,auto_adjust=False,actions=True,threads=True,progress=False)


def fld(field):
    if isinstance(data.columns,pd.MultiIndex):
        if field not in data.columns.get_level_values(0):return pd.DataFrame(index=data.index)
        x=data[field]; return x.to_frame() if isinstance(x,pd.Series) else x
    if field in data.columns and len(tickers)==1:return data[[field]].rename(columns={field:tickers[0]})
    return pd.DataFrame(index=data.index)

rawc=fld('Close'); adjc=fld('Adj Close'); op=fld('Open'); splits=fld('Stock Splits')
if adjc.empty:
    ad=yf.download(tickers,start=start,end=end,auto_adjust=True,actions=False,threads=True,progress=False)
    if isinstance(ad.columns,pd.MultiIndex): adjc=ad['Close']; adjo=ad['Open']
    else: adjc=ad[['Close']].rename(columns={'Close':tickers[0]}); adjo=ad[['Open']].rename(columns={'Open':tickers[0]})
else:
    adjo=op*(adjc/rawc)


def before(df,d,t):
    if t not in df.columns:return np.nan
    s=df[t].dropna();s=s[s.index<=d]
    return float(s.iloc[-1]) if len(s) else np.nan

def after(df,d,t):
    if t not in df.columns:return (None,np.nan)
    s=df[t].dropna();s=s[s.index>=d]
    return (s.index[0],float(s.iloc[0])) if len(s) else (None,np.nan)

# Validate ticker identity against N-PORT implied per-share price at report date.
validation=[]
for rb,h in frames.items():
    for idx,r in h.iterrows():
        t=r.ticker; implied=np.nan
        if str(r.UNIT).upper()=='NS' and pd.notna(r.shares) and r.shares>0: implied=r.value/r.shares
        px=before(rawc,r.report_date,t) if t else np.nan
        ratio=px/implied if np.isfinite(px) and np.isfinite(implied) and implied>0 else np.nan
        ok=bool(np.isfinite(px) and (not np.isfinite(implied) or 0.75<=ratio<=1.35))
        h.at[idx,'ticker_valid']=ok
        h.at[idx,'snapshot_px_ratio']=ratio
        validation.append({'rb':rb.date(),'report_date':r.report_date.date(),'name':r['name'],'ticker':t,
                           'reported_pct':r.reported_pct,'implied_px':implied,'yahoo_px':px,'ratio':ratio,'valid':ok})
val=pd.DataFrame(validation);val.to_csv(OUT/'ticker_validation.csv',index=False)
miss=val[~val.valid].sort_values(['rb','reported_pct'],ascending=[True,False])
miss.to_csv(OUT/'ticker_invalid.csv',index=False)
print('INVALID_TICKER_ROWS',len(miss),'max_reported_pct',miss.reported_pct.max() if len(miss) else 0,flush=True)

# Rewind each disclosed post-rebalance snapshot to rebalance close.
ranked={}; detail=[]
for rb,h in frames.items():
    z=h[h.ticker_valid.fillna(False)].copy(); vals=[]
    for _,r in z.iterrows():
        t=r.ticker; ps=before(rawc,r.report_date,t); pr=before(rawc,rb,t)
        if not np.isfinite(ps) or not np.isfinite(pr) or ps<=0: vals.append(np.nan); continue
        sf=1.0
        if t in splits.columns:
            ss=splits[t].fillna(0); ss=ss[(ss.index>rb)&(ss.index<=r.report_date)&(ss!=0)]
            for a in ss:sf*=float(a)
        vals.append(r.value*(pr/ps)/sf)
    z['rb_value']=vals; z=z[z.rb_value.notna() & (z.rb_value>0)].sort_values('rb_value',ascending=False).reset_index(drop=True)
    z['rank']=np.arange(1,len(z)+1); z['weight']=z.rb_value/z.rb_value.sum()
    ranked[rb]=z
    zz=z.copy();zz.insert(0,'rebalance',rb.date());detail.append(zz)
    print('TOP5',rb.date(),[(x.ticker,round(x.weight*100,2)) for _,x in z.head(5).iterrows()],flush=True)
pd.concat(detail,ignore_index=True).to_csv(OUT/'ranked_holdings.csv',index=False)

top1=[]
for rb,z in ranked.items():
    r=z.iloc[0] if len(z) else None
    top1.append({'rb':rb.date(),'exit':NEXT_RB[rb].date(),'top1':None if r is None else r.ticker,
                 'issuer':None if r is None else r['name'],'weight':None if r is None else r.weight})
top1=pd.DataFrame(top1);top1.to_csv(OUT/'top1_sequence.csv',index=False)
print('\nTOP1 SEQUENCE\n',top1.to_string(index=False),flush=True)


def curve(z,rb,ex,n,mode,wm):
    z=z.head(n).copy()
    if z.empty:return None
    w=np.repeat(1/len(z),len(z)) if wm=='equal' else (z.weight/z.weight.sum()).to_numpy()
    ss=[]; ww=[]
    for (_,r),wi in zip(z.iterrows(),w):
        t=r.ticker
        if mode=='close':
            ep=before(adjc,rb,t); st=rb; dx=None
        else:
            st,ep=after(adjo,rb+pd.Timedelta(days=1),t); dx,_=after(adjo,ex+pd.Timedelta(days=1),t)
        if st is None or not np.isfinite(ep) or ep<=0:continue
        if mode=='close':
            idx=adjc.index[(adjc.index>=st)&(adjc.index<=ex)]
            s=adjc[t].reindex(idx).ffill()/ep
        else:
            if dx is None:continue
            idx=adjc.index[(adjc.index>=st)&(adjc.index<dx)]
            s=adjc[t].reindex(idx).ffill()/ep
            xp=after(adjo,ex+pd.Timedelta(days=1),t)[1]
            if np.isfinite(xp):s.loc[dx]=xp/ep
        if len(s):ss.append(s.rename(t));ww.append(wi)
    if not ss:return None
    mat=pd.concat(ss,axis=1).ffill();ww=np.array(ww);ww=ww/ww.sum()
    return mat.mul(ww,axis=1).sum(axis=1)

def stitch(cs):
    out=None;lvl=1.0
    for c in cs:
        c=c.dropna()
        if len(c)<2:continue
        x=c/c.iloc[0]*lvl
        if out is not None and x.index[0] in out.index:x=x.iloc[1:]
        out=x if out is None else pd.concat([out,x]);lvl=float(out.iloc[-1])
    return out

def met(eq):
    ret=eq.pct_change().dropna();yrs=(eq.index[-1]-eq.index[0]).days/365.2425;dd=eq/eq.cummax()-1
    return {'start':eq.index[0].date(),'end':eq.index[-1].date(),'multiple':eq.iloc[-1]/eq.iloc[0],
            'cagr':(eq.iloc[-1]/eq.iloc[0])**(1/yrs)-1,'vol':ret.std()*np.sqrt(252),
            'sharpe_rf0':ret.mean()/ret.std()*np.sqrt(252),'max_dd':dd.min()}

rows=[];periods=[]
for n in (1,5,10,15,20):
  for mode in ('close','next_open'):
    for wm in ('equal','spmo_weight'):
      cs=[]
      for rb,_,_,_ in TARGETS:
        ex=NEXT_RB[rb];c=curve(ranked[rb],rb,ex,n,mode,wm)
        if c is None:continue
        cs.append(c); periods.append({'n':n,'mode':mode,'weight_mode':wm,'rb':rb.date(),'exit':ex.date(),
                                      'multiple':c.iloc[-1]/c.iloc[0],'tickers':','.join(ranked[rb].head(n).ticker.tolist())})
      eq=stitch(cs)
      if eq is None:continue
      m=met(eq);m.update({'n':n,'mode':mode,'weight_mode':wm,'periods':len(cs)});rows.append(m)
res=pd.DataFrame(rows);per=pd.DataFrame(periods)
res.to_csv(OUT/'results.csv',index=False);per.to_csv(OUT/'periods.csv',index=False)
print('\nRESULTS\n',res.to_string(index=False),flush=True)

# Diagnostics explicitly requested: worst six-month period and best/worst-period sensitivity.
diag=[]
for _,r in res.iterrows():
    sel=per[(per['n']==r.n)&(per['mode']==r['mode'])&(per.weight_mode==r.weight_mode)].copy()
    if sel.empty:continue
    worst=sel.loc[sel.multiple.idxmin()];best=sel.loc[sel.multiple.idxmax()]
    mult_all=float(sel.multiple.prod()); years=(pd.Timestamp(sel.exit.max())-pd.Timestamp(sel.rb.min())).days/365.2425
    for drop,label in [(best,'drop_best'),(worst,'drop_worst')]:
        m2=mult_all/float(drop.multiple); y2=max(years-0.5,0.5); c2=m2**(1/y2)-1
        diag.append({'n':r.n,'mode':r['mode'],'weight_mode':r.weight_mode,'test':label,
                     'dropped_rb':drop.rb,'dropped_multiple':drop.multiple,'approx_cagr':c2,
                     'worst_rb':worst.rb,'worst_multiple':worst.multiple})
pd.DataFrame(diag).to_csv(OUT/'sensitivity.csv',index=False)

Path(OUT/'summary.json').write_text(json.dumps({'snapshots':snap_rows,'top1':top1.to_dict('records'),
                                                'results':json.loads(res.to_json(orient='records',date_format='iso'))},indent=2,default=str))
