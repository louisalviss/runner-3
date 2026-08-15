#!/usr/bin/env python3
import argparse,re,requests,xml.etree.ElementTree as ET
from pathlib import Path
import pandas as pd
import yfinance as yf
p=argparse.ArgumentParser(); p.add_argument('--accession',required=True); p.add_argument('--rebalance',required=True); p.add_argument('--snapshot',required=True); p.add_argument('--exit',required=True); p.add_argument('--output',required=True); a=p.parse_args()
MAP={'594918104':'MSFT','037833100':'AAPL','023135106':'AMZN','02079K305':'GOOGL','02079K107':'GOOG','084670702':'BRK-B','67066G104':'NVDA','30303M102':'META','88160R101':'TSLA','92826C839':'V','57636Q104':'MA','742718109':'PG','437076102':'HD','65339F101':'NEE','00724F101':'ADBE','191216100':'KO','713448108':'PEP','22160K105':'COST','64110L106':'NFLX','007903107':'AMD','747525103':'QCOM','461202103':'INTU','68389X105':'ORCL','11135F101':'AVGO','46625H100':'JPM','30231G102':'XOM','532457108':'LLY','58933Y105':'MRK','91324P102':'UNH','166764100':'CVX'}
NAMES=[('Microsoft','MSFT'),('Apple','AAPL'),('Amazon','AMZN'),('Alphabet','GOOGL'),('Berkshire','BRK-B'),('NVIDIA','NVDA'),('Facebook','META'),('Meta Platforms','META'),('Visa','V'),('Mastercard','MA'),('Procter','PG'),('Home Depot','HD'),('NextEra','NEE'),('Adobe','ADBE'),('Coca-Cola','KO'),('PepsiCo','PEP'),('Costco','COST'),('Netflix','NFLX'),('QUALCOMM','QCOM'),('Intuit','INTU'),('Oracle','ORCL'),('Broadcom','AVGO'),('JPMorgan','JPM'),('Exxon','XOM'),('Eli Lilly','LLY'),('Merck','MRK'),('UnitedHealth','UNH'),('Chevron','CVX'),('PayPal','PYPL'),('Thermo Fisher','TMO'),('Danaher','DHR'),('Abbott','ABT'),('Target','TGT'),('Starbucks','SBUX'),('Applied Materials','AMAT'),('Goldman Sachs','GS'),('Morgan Stanley','MS'),('Charles Schwab','SCHW'),('Deere','DE'),('NIKE','NKE'),('Moderna','MRNA')]
def loc(t):return t.split('}',1)[-1]
def tx(e,n):
 for x in e.iter():
  if loc(x.tag)==n and x.text:return x.text.strip()
 return None
compact=a.accession.replace('-',''); url=f'https://r.jina.ai/https://www.sec.gov/Archives/edgar/data/1378872/{compact}/{a.accession}.txt'; r=requests.get(url,timeout=180); r.raise_for_status(); text=r.text
rows=[]
for s in re.findall(r'<XML>(.*?)</XML>',text,re.S|re.I):
 if 'S000050154' not in s or 'invstOrSec' not in s:continue
 root=ET.fromstring(s.strip())
 for e in root.iter():
  if loc(e.tag)!='invstOrSec':continue
  v=tx(e,'valUSD'); pc=tx(e,'pctVal'); c=tx(e,'cusip'); n=tx(e,'name')
  if v: rows.append({'name':n,'cusip':c,'snapshot_value':float(v),'snapshot_pct':float(pc) if pc else float('nan')})
if not rows:raise RuntimeError('no holdings')
df=pd.DataFrame(rows).sort_values('snapshot_value',ascending=False); cand=df[df.snapshot_pct>=1.0].copy()
def resolve(z):
 c=str(z.cusip); n=str(z['name'])
 if c in MAP:return MAP[c]
 for k,v in NAMES:
  if k.lower() in n.lower():return v
 try:
  for q in yf.Search(n,max_results=5,news_count=0).quotes:
   if q.get('quoteType')=='EQUITY' and q.get('symbol'):return q['symbol'].replace('.','-')
 except:pass
 return None
cand['ticker']=cand.apply(resolve,axis=1); print('CANDIDATES\n',cand[['ticker','name','cusip','snapshot_value','snapshot_pct']].head(30).to_string(index=False));
if cand.head(12).ticker.isna().any():raise RuntimeError('unresolved top candidate')
cand=cand.dropna(subset=['ticker']).drop_duplicates('ticker'); tick=cand.ticker.tolist(); rb=pd.Timestamp(a.rebalance); sn=pd.Timestamp(a.snapshot); ex=pd.Timestamp(a.exit)
d=yf.download(tick,start=(rb-pd.Timedelta(days=5)).strftime('%Y-%m-%d'),end=(ex+pd.Timedelta(days=6)).strftime('%Y-%m-%d'),auto_adjust=False,actions=True,threads=False,progress=False)
def f(n):
 x=d[n];return x.to_frame(tick[0]) if isinstance(x,pd.Series) else x
cl=f('Close');ad=f('Adj Close');op=f('Open')
def at(x,dt,t):
 s=x[t].dropna();s=s[s.index<=dt];return float(s.iloc[-1])
def aft(x,dt,t):
 s=x[t].dropna();s=s[s.index>=dt];return (s.index[0],float(s.iloc[0])) if len(s) else None
rr=[]
for _,z in cand.iterrows():
 t=z.ticker
 if t not in cl.columns or cl[t].dropna().empty:continue
 rv=z.snapshot_value*at(cl,rb,t)/at(cl,sn,t); cr=at(ad,ex,t)/at(ad,rb,t)-1; en=aft(op,rb+pd.Timedelta(days=1),t); xo=aft(op,ex+pd.Timedelta(days=1),t); nr=float('nan')
 if en and xo:
  ed,eo=en;xd,xv=xo; nr=(xv*at(ad,xd,t)/at(cl,xd,t))/(eo*at(ad,ed,t)/at(cl,ed,t))-1
 rr.append({'ticker':t,'reconstructed_value':rv,'close_return':cr,'next_open_return':nr,'name':z['name'],'snapshot_pct':z.snapshot_pct})
z=pd.DataFrame(rr).sort_values('reconstructed_value',ascending=False); print('RANKED\n',z.head(15).to_string(index=False)); top=z.iloc[0]; print('TOP1_RESULT',top.ticker,float(top.close_return),float(top.next_open_return),float(top.reconstructed_value))
Path(a.output).parent.mkdir(parents=True,exist_ok=True); z.to_csv(a.output,index=False)
