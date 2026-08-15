#!/usr/bin/env python3
import re,json,time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor,as_completed
import numpy as np
import pandas as pd
import requests
import yfinance as yf

OUT=Path('spmo-2026/output');OUT.mkdir(parents=True,exist_ok=True)
RB=pd.Timestamp('2026-03-20'); REP=pd.Timestamp('2026-05-31'); END=pd.Timestamp('2026-08-14')
SRC='https://www.sec.gov/Archives/edgar/data/1378872/000137887226001362/primary_doc.xml'
text=requests.get('https://r.jina.ai/'+SRC,timeout=120).text
(OUT/'jina.txt').write_text(text)
# Jina renders each investment's numeric fields as one line. Keep only Long equity rows.
pat=re.compile(r'(?m)^([A-Z0-9]{9})\s+([0-9.]+)\s+NS\s+USD\s+([0-9.]+)\s+([0-9.]+)\s+Long\s+EC\s+')
rows=[]
for m in pat.finditer(text):
    rows.append({'cusip':m.group(1),'shares':float(m.group(2)),'value':float(m.group(3)),'reported_pct':float(m.group(4))})
h=pd.DataFrame(rows).drop_duplicates('cusip').reset_index(drop=True)
print('EQUITY_ROWS',len(h),'VALUE',h.value.sum(),'PCT',h.reported_pct.sum(),flush=True)
if len(h)<90:raise RuntimeError('Too few parsed 2026 equities')

FORCE={'02079K305':'GOOGL','02079K107':'GOOG','084670702':'BRK-B','084670108':'BRK-A','67066G104':'NVDA','595112103':'MU'}
US={'NMS','NYQ','NGM','NCM','ASE','PCX'}
def look(c):
    if c in FORCE:return c,FORCE[c]
    s=requests.Session();s.headers.update({'User-Agent':'Mozilla/5.0'})
    try:
        j=s.get('https://query1.finance.yahoo.com/v1/finance/search',params={'q':c,'quotesCount':8,'newsCount':0},timeout=8).json()
        q=[x for x in j.get('quotes',[]) if x.get('quoteType')=='EQUITY' and x.get('exchange') in US]
        return c,(q[0].get('symbol').replace('.','-') if q else None)
    except Exception:return c,None
mp={}
with ThreadPoolExecutor(max_workers=16) as ex:
    fs=[ex.submit(look,c) for c in h.cusip]
    for i,f in enumerate(as_completed(fs),1):
        c,t=f.result();mp[c]=t
h['ticker']=h.cusip.map(mp)
print('TICKER_RESOLVED',h.ticker.notna().sum(),'/',len(h),flush=True)

T=sorted(set(h.ticker.dropna()))
d=yf.download(T,start='2026-03-10',end='2026-08-16',auto_adjust=False,actions=False,progress=False,threads=True)
def field(k):
    if isinstance(d.columns,pd.MultiIndex):return d[k]
    return d[[k]].rename(columns={k:T[0]})
cl=field('Close');adj=field('Adj Close');op=field('Open')
def before(df,x,t):
    if t not in df.columns:return np.nan
    z=df[t].dropna();z=z[z.index<=x];return float(z.iloc[-1]) if len(z) else np.nan

def after(df,x,t):
    if t not in df.columns:return (None,np.nan)
    z=df[t].dropna();z=z[z.index>=x];return (z.index[0],float(z.iloc[0])) if len(z) else (None,np.nan)

# Validate identity: report-period implied price should closely match Yahoo 2026-05-29 close.
valid=[]
for _,r in h.iterrows():
    imp=r.value/r.shares if r.shares else np.nan; px=before(cl,REP,r.ticker) if r.ticker else np.nan
    err=abs(px/imp-1) if np.isfinite(px) and np.isfinite(imp) and imp else np.nan
    valid.append(np.isfinite(err) and err<=.12)
h['valid']=valid
bad=h[~h.valid].sort_values('reported_pct',ascending=False)
print('INVALID',len(bad),'MAX_PCT',bad.reported_pct.max() if len(bad) else 0,'SUM_PCT',bad.reported_pct.sum(),flush=True)
bad.to_csv(OUT/'invalid.csv',index=False)

z=h[h.valid].copy();vals=[]
for _,r in z.iterrows():
    ps=before(cl,REP,r.ticker);pr=before(cl,RB,r.ticker)
    vals.append(r.value*pr/ps if np.isfinite(ps) and np.isfinite(pr) and ps>0 else np.nan)
z['rb_value']=vals;z=z[z.rb_value.notna()].sort_values('rb_value',ascending=False).reset_index(drop=True)
z['rank']=np.arange(1,len(z)+1);z['weight']=z.rb_value/z.rb_value.sum();z.to_csv(OUT/'ranked.csv',index=False)
print('TOP20\n',z.head(20)[['rank','cusip','ticker','weight']].to_string(index=False),flush=True)

# Return of each top-N portfolio to 2026-08-14; both close entry and next-open entry.
out=[]
for n in [1,5,10,15,20]:
  zz=z.head(n)
  for wm in ['equal','spmo_weight']:
    w=np.repeat(1/len(zz),len(zz)) if wm=='equal' else (zz.weight/zz.weight.sum()).to_numpy()
    for mode in ['close','next_open']:
      rs=[];ww=[]
      for (_,r),wi in zip(zz.iterrows(),w):
        t=r.ticker
        if mode=='close': ep=before(adj,RB,t);xp=before(adj,END,t)
        else:
          _,ep=after(op,RB+pd.Timedelta(days=1),t);xp=before(adj,END,t)
          # Use adjusted open factor from same day.
          dd,_=after(op,RB+pd.Timedelta(days=1),t)
          if dd is not None and t in adj.columns and t in cl.columns:
            rawo=float(op.loc[dd,t]);fac=float(adj.loc[dd,t]/cl.loc[dd,t]);ep=rawo*fac
        if np.isfinite(ep) and np.isfinite(xp) and ep>0:rs.append(xp/ep);ww.append(wi)
      ww=np.array(ww);ww=ww/ww.sum();mult=float(np.dot(rs,ww))
      out.append({'n':n,'weight_mode':wm,'mode':mode,'multiple':mult,'return':mult-1})
r=pd.DataFrame(out);r.to_csv(OUT/'period_return.csv',index=False);print('RETURNS\n',r.to_string(index=False),flush=True)
Path(OUT/'summary.json').write_text(json.dumps({'rows':len(h),'resolved':int(h.ticker.notna().sum()),'valid':int(h.valid.sum()),'top1':z.iloc[0].ticker,'returns':r.to_dict('records')},indent=2))
