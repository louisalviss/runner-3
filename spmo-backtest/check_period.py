#!/usr/bin/env python3
import argparse
from pathlib import Path
import pandas as pd
import yfinance as yf

p=argparse.ArgumentParser()
p.add_argument('--csv',required=True)
p.add_argument('--rebalance',required=True)
p.add_argument('--snapshot',required=True)
p.add_argument('--exit',required=True)
p.add_argument('--output',required=True)
a=p.parse_args()

rb=pd.Timestamp(a.rebalance); snap=pd.Timestamp(a.snapshot); ex=pd.Timestamp(a.exit)
df=pd.read_csv(a.csv); tickers=df.ticker.tolist()
start=(rb-pd.Timedelta(days=5)).strftime('%Y-%m-%d')
end=(ex+pd.Timedelta(days=6)).strftime('%Y-%m-%d')
data=yf.download(tickers,start=start,end=end,auto_adjust=False,actions=True,threads=False,progress=False)

def fld(n):
    x=data[n]
    return x.to_frame(tickers[0]) if isinstance(x,pd.Series) else x
close=fld('Close'); adj=fld('Adj Close'); op=fld('Open')

def ensure_ticker(t):
    global close,adj,op
    ok=(t in close.columns and not close[t].dropna().empty and t in adj.columns and not adj[t].dropna().empty and t in op.columns and not op[t].dropna().empty)
    if ok:return
    one=yf.download(t,start=start,end=end,auto_adjust=False,actions=True,threads=False,progress=False)
    if one.empty:raise RuntimeError(f'No price data for {t}')
    def onef(n):
        x=one[n]
        if isinstance(x,pd.DataFrame):
            if t in x.columns:return x[t]
            return x.iloc[:,0]
        return x
    close[t]=onef('Close'); adj[t]=onef('Adj Close'); op[t]=onef('Open')

def at(f,d,t):
    s=f[t].dropna(); s=s[s.index<=d]
    if s.empty:raise RuntimeError(f'No {t} price on/before {d.date()}')
    return float(s.iloc[-1])
def after_or_none(f,d,t):
    s=f[t].dropna(); s=s[s.index>=d]
    if s.empty:return None
    return s.index[0],float(s.iloc[0])
rows=[]
for _,r in df.iterrows():
    t=r.ticker; ensure_ticker(t)
    pr=at(close,rb,t); ps=at(close,snap,t)
    rv=float(r.snapshot_value)*pr/ps
    cr=at(adj,ex,t)/at(adj,rb,t)-1
    ent=after_or_none(op,rb+pd.Timedelta(days=1),t)
    ext=after_or_none(op,ex+pd.Timedelta(days=1),t)
    no_ret=float('nan')
    if ent is not None and ext is not None:
        ed,eo=ent; xd,xo=ext
        eao=eo*(at(adj,ed,t)/at(close,ed,t)); xao=xo*(at(adj,xd,t)/at(close,xd,t))
        no_ret=xao/eao-1
    rows.append({**r.to_dict(),'rb_close':pr,'snapshot_close':ps,'reconstructed_rb_value':rv,'close_to_close_return':cr,'next_open_return':no_ret})
z=pd.DataFrame(rows).sort_values('reconstructed_rb_value',ascending=False).reset_index(drop=True)
z['reconstructed_rank']=z.index+1
Path(a.output).parent.mkdir(parents=True,exist_ok=True); z.to_csv(a.output,index=False)
print(z[['reconstructed_rank','ticker','snapshot_pct','rb_close','snapshot_close','reconstructed_rb_value','close_to_close_return','next_open_return']].to_string(index=False))
print('\nTOP1',z.iloc[0].ticker)
print('TOP1 close-to-close return',z.iloc[0].close_to_close_return)
print('TOP1 next-open return',z.iloc[0].next_open_return)
