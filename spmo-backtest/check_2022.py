#!/usr/bin/env python3
from pathlib import Path
import pandas as pd
import yfinance as yf

BASE=Path(__file__).resolve().parent
IN=BASE/'data'/'2022-05-31_top_candidates.csv'
OUT=BASE/'output'; OUT.mkdir(exist_ok=True)
RB=pd.Timestamp('2022-03-18')
SNAP=pd.Timestamp('2022-05-31')
EXIT=pd.Timestamp('2022-09-16')

df=pd.read_csv(IN)
tickers=df.ticker.tolist()
data=yf.download(tickers,start='2022-03-15',end='2022-09-22',auto_adjust=False,actions=True,threads=True,progress=False)

def field(name):
    x=data[name]
    if isinstance(x,pd.Series): x=x.to_frame(tickers[0])
    return x

close=field('Close')
adj=field('Adj Close')
open_=field('Open')

def at(frame, d, t):
    s=frame[t].dropna()
    if d in s.index:return float(s.loc[d])
    s=s[s.index<=d]
    return float(s.iloc[-1])

def after(frame,d,t):
    s=frame[t].dropna(); s=s[s.index>=d]
    return s.index[0],float(s.iloc[0])

rows=[]
for _,r in df.iterrows():
    t=r.ticker
    p_rb=at(close,RB,t); p_snap=at(close,SNAP,t)
    rb_value=float(r.snapshot_value)*p_rb/p_snap
    a_rb=at(adj,RB,t); a_exit=at(adj,EXIT,t)
    close_ret=a_exit/a_rb-1
    en_d,en_open=after(open_,RB+pd.Timedelta(days=1),t)
    ex_d,ex_open=after(open_,EXIT+pd.Timedelta(days=1),t)
    # Adjust raw opens onto adjusted-close scale for splits/dividends.
    en_adj_open=en_open*(at(adj,en_d,t)/at(close,en_d,t))
    ex_adj_open=ex_open*(at(adj,ex_d,t)/at(close,ex_d,t))
    next_open_ret=ex_adj_open/en_adj_open-1
    rows.append({**r.to_dict(),'rb_close':p_rb,'snapshot_close':p_snap,'reconstructed_rb_value':rb_value,
                 'close_to_close_return':close_ret,'next_open_entry':str(en_d.date()),'next_open_exit':str(ex_d.date()),
                 'next_open_return':next_open_ret})

z=pd.DataFrame(rows).sort_values('reconstructed_rb_value',ascending=False).reset_index(drop=True)
z['reconstructed_rank']=z.index+1
z['reconstructed_weight_candidates_only']=z.reconstructed_rb_value/z.reconstructed_rb_value.sum()
z.to_csv(OUT/'check_2022_results.csv',index=False)
print(z[['reconstructed_rank','ticker','snapshot_pct','rb_close','snapshot_close','reconstructed_rb_value','close_to_close_return','next_open_return']].to_string(index=False))
print('\nTOP1',z.iloc[0].ticker)
print('TOP1 close-to-close return',z.iloc[0].close_to_close_return)
print('TOP1 next-open return',z.iloc[0].next_open_return)
