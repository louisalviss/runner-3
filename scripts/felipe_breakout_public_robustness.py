#!/usr/bin/env python3
import json, statistics
import numpy as np, pandas as pd

URL='https://raw.githubusercontent.com/plotly/datasets/master/all_stocks_5yr.csv'

def ema(a,n):return pd.Series(a).ewm(span=n,adjust=False).mean().to_numpy()
def atr(g,n):
 h=g.high.to_numpy(float);l=g.low.to_numpy(float);c=g.close.to_numpy(float);pc=np.r_[c[0],c[:-1]]
 tr=np.maximum(h-l,np.maximum(abs(h-pc),abs(l-pc)))
 return pd.Series(tr).ewm(alpha=1/n,adjust=False).mean().to_numpy()
def summ(x):
 if not x:return {'trades':0}
 gp=sum(v for v in x if v>0);gl=-sum(v for v in x if v<0)
 return {'trades':len(x),'win_rate_pct':100*sum(v>0 for v in x)/len(x),'avg_return_pct':100*statistics.fmean(x),'median_return_pct':100*statistics.median(x),'profit_factor':gp/gl if gl else None}

def main():
 df=pd.read_csv(URL,parse_dates=['date']);df.columns=[x.lower() for x in df.columns]
 modes={'gap_aware':[],'ideal_stop_fill':[],'five_day_no_stop':[]}; signals=0
 for sym,g in df.groupby('name'):
  g=g.dropna(subset=['open','high','low','close']).sort_values('date').reset_index(drop=True)
  if len(g)<120:continue
  o=g.open.to_numpy(float);h=g.high.to_numpy(float);l=g.low.to_numpy(float);c=g.close.to_numpy(float)
  e8,e20,e50=ema(c,8),ema(c,20),ema(c,50);a5,a20=atr(g,5),atr(g,20);last=-999
  for i in range(80,len(g)-5):
   if i-last<5:continue
   if not(e8[i]>e20[i]>e50[i] and e8[i]>e8[i-3] and e20[i]>e20[i-5] and e50[i]>e50[i-10]):continue
   if not(c[i]>max(h[i-7:i]) and c[i]>o[i]):continue
   if not(abs(c[i]-o[i])>abs(c[i-1]-o[i-1]) and (c[i]-l[i])/max(1e-12,h[i]-l[i])>=.786):continue
   risk=c[i]-l[i]
   if risk<=0 or risk>2.5*a20[i]:continue
   if not np.all(c[i-7:i]>=e20[i-7:i]):continue
   if not(min(l[i-4:i])>min(l[i-7:i-3]) and a5[i-1]<=.95*a20[i-1]):continue
   launch=None
   for j in range(max(55,i-30),i-6):
    if c[j]>e50[j]+.5*a5[j] and c[j-1]<=e50[j-1]+.5*a5[j-1]:launch=j
   if launch is None:continue
   base=e50[launch]+.5*a5[launch]
   if base<=0 or max(h[launch:i])/base-1<.05:continue
   signals+=1;entry=c[i];stop=l[i];gap_exit=c[i+5];ideal_exit=c[i+5]
   for k in range(i+1,i+6):
    if l[k]<=stop:
     ideal_exit=stop
     gap_exit=o[k] if o[k]<=stop else stop
     break
   modes['gap_aware'].append(gap_exit/entry-1);modes['ideal_stop_fill'].append(ideal_exit/entry-1);modes['five_day_no_stop'].append(c[i+5]/entry-1);last=i
 print(json.dumps({'signals':signals,'results':{k:summ(v) for k,v in modes.items()}},ensure_ascii=False))
if __name__=='__main__':main()
