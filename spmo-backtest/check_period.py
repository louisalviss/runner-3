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
data=yf.download(tickers,start=(rb-pd.Timedelta(days=5)).strftime('%Y-%m-%d'),end=(ex+pd.Timedelta(days=6)).strftime('%Y-%m-%d'),auto_adjust=False,actions=True,threads=True,progress=False)

def fld(n):
    x=data[n]
    return x.to_frame(tickers[0]) if isinstance(x,pd.Series) else x
close=fld('Close'); adj=fld('Adj Close'); op=fld('Open')
def at(f,d,t):
    s=f[t].dropna(); s=s[s.index<=d]
    return float(s.iloc[-1])
def after(f,d,t):
    s=f[t].dropna(); s=s[s.index>=d]
    return s.index[0],float(s.iloc[0])
rows=[]
for _,r in df.iterrows():
    t=r.ticker; pr=at(close,rb,t); ps=at(close,snap,t)
    rv=float(r.snapshot_value)*pr/ps
    cr=at(adj,ex,t)/at(adj,rb,t)-1
    ed,eo=after(op,rb+pd.Timedelta(days=1),t); xd,xo=after(op,ex+pd.Timedelta(days=1),t)
    eao=eo*(at(adj,ed,t)/at(close,ed,t)); xao=xo*(at(adj,xd,t)/at(close,xd,t))
    rows.append({**r.to_dict(),'rb_close':pr,'snapshot_close':ps,'reconstructed_rb_value':rv,'close_to_close_return':cr,'next_open_return':xao/eao-1})
z=pd.DataFrame(rows).sort_values('reconstructed_rb_value',ascending=False).reset_index(drop=True)
z['reconstructed_rank']=z.index+1
Path(a.output).parent.mkdir(parents=True,exist_ok=True); z.to_csv(a.output,index=False)
print(z[['reconstructed_rank','ticker','snapshot_pct','rb_close','snapshot_close','reconstructed_rb_value','close_to_close_return','next_open_return']].to_string(index=False))
print('\nTOP1',z.iloc[0].ticker)
print('TOP1 close-to-close return',z.iloc[0].close_to_close_return)
print('TOP1 next-open return',z.iloc[0].next_open_return)
