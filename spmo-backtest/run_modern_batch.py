#!/usr/bin/env python3
import re, requests, xml.etree.ElementTree as ET
import pandas as pd
import yfinance as yf

SERIES='S000050154'
PERIODS=[
 ('2020-03-20','2020-05-31','2020-09-18','0001752724-20-148736'),
 ('2020-09-18','2020-11-30','2021-03-19','0001752724-21-016818'),
 ('2021-03-19','2021-05-31','2021-09-17','0001752724-21-161170'),
 ('2021-09-17','2021-11-30','2022-03-18','0001752724-22-018016'),
]
CUSIP={
 '02079K305':'GOOGL','02079K107':'GOOG','084670702':'BRK-B','67066G104':'NVDA','30231G102':'XOM','91324P102':'UNH','166764100':'CVX','742718109':'PG','060505104':'BAC','717081103':'PFE','191216100':'KO','20825C104':'COP','00287Y109':'ABBV','713448108':'PEP','22160K105':'COST','949746101':'WFC','G1151C101':'ACN',
 '594918104':'MSFT','037833100':'AAPL','023135106':'AMZN','30303M102':'META','30303M102':'META','88160R101':'TSLA','46625H100':'JPM','580135101':'MCD','437076102':'HD','548661107':'LOW','478160104':'JNJ','58933Y105':'MRK','532457108':'LLY','11135F101':'AVGO','64110L106':'NFLX','68389X105':'ORCL','931142103':'WMT','00724F101':'ADBE','007903107':'AMD','79466L302':'CRM','17275R102':'CSCO','20030N101':'CMCSA','254687106':'DIS','92343V104':'VZ','872590104':'TMUS','00766T100':'ATVI','78462F103':'SPGI','461202103':'INTU','747525103':'QCOM','57636Q104':'MA','92826C839':'V','09247X101':'BLK','88579Y101':'MMM','126650100':'CVS','718172109':'PM','74340W103':'PLD','030420103':'AWK','65339F101':'NEE'
}
NAME_MAP=[
 ('Microsoft','MSFT'),('Apple','AAPL'),('Amazon','AMZN'),('Meta Platforms','META'),('Facebook','META'),('NVIDIA','NVDA'),('Berkshire Hathaway','BRK-B'),('Exxon Mobil','XOM'),('UnitedHealth','UNH'),('Chevron','CVX'),('Procter & Gamble','PG'),('Bank of America','BAC'),('Pfizer','PFE'),('Coca-Cola','KO'),('ConocoPhillips','COP'),('AbbVie','ABBV'),('PepsiCo','PEP'),('Costco','COST'),('Wells Fargo','WFC'),('Accenture','ACN'),('Tesla','TSLA'),('JPMorgan','JPM'),('Mastercard','MA'),('Visa','V'),('Adobe','ADBE'),('Advanced Micro Devices','AMD'),('Salesforce','CRM'),('Netflix','NFLX'),('Oracle','ORCL'),('Walmart','WMT'),('Home Depot','HD'),("Lowe",'LOW'),('Johnson & Johnson','JNJ'),('Merck','MRK'),('Eli Lilly','LLY'),('Broadcom','AVGO'),('Comcast','CMCSA'),('Walt Disney','DIS'),('Verizon','VZ'),('T-Mobile','TMUS'),('Activision','ATVI'),('S&P Global','SPGI'),('Intuit','INTU'),('QUALCOMM','QCOM'),('BlackRock','BLK'),('CVS Health','CVS'),('Philip Morris','PM'),('Prologis','PLD'),('American Water Works','AWK'),('NextEra','NEE'),('Linde','LIN'),('Newmont','NEM'),('Target','TGT'),('Charter Communications','CHTR'),('Electronic Arts','EA'),('Take-Two','TTWO'),('Equinix','EQIX'),('American Tower','AMT'),('Crown Castle','CCI'),('Digital Realty','DLR')
]

def local(tag): return tag.split('}',1)[-1]
def txt(el,n):
 for x in el.iter():
  if local(x.tag)==n and x.text: return x.text.strip()
 return None

def fetch_holdings(acc):
 compact=acc.replace('-','')
 url=f'https://r.jina.ai/https://www.sec.gov/Archives/edgar/data/1378872/{compact}/{acc}.txt'
 r=requests.get(url,timeout=180,headers={'User-Agent':'runner-3 spmo research'}); r.raise_for_status()
 if SERIES not in r.text: raise RuntimeError(f'{acc}: SPMO marker absent')
 xmls=re.findall(r'<XML>(.*?)</XML>',r.text,re.S|re.I)
 rows=[]
 for s in xmls:
  if SERIES not in s or 'invstOrSec' not in s: continue
  root=ET.fromstring(s.strip())
  for el in root.iter():
   if local(el.tag)!='invstOrSec': continue
   v=txt(el,'valUSD'); p=txt(el,'pctVal')
   if not v: continue
   rows.append({'name':txt(el,'name'),'cusip':txt(el,'cusip'),'snapshot_value':float(v),'snapshot_pct':float(p) if p else float('nan')})
 if not rows: raise RuntimeError(f'{acc}: no holdings')
 return pd.DataFrame(rows)

def resolve(row):
 c=str(row.cusip or '').strip()
 if c in CUSIP:return CUSIP[c]
 n=str(row['name'] or '')
 for k,v in NAME_MAP:
  if k.lower() in n.lower(): return v
 try:
  s=yf.Search(n,max_results=6,news_count=0).quotes
  for q in s:
   sym=q.get('symbol'); qt=q.get('quoteType','')
   if sym and qt in ('EQUITY','ETF') and not sym.endswith(('.TO','.L','.AX')):
    return sym.replace('.','-')
 except Exception as e: print('SEARCH_FAIL',n,e)
 return None

def price_series(tickers,start,end):
 d=yf.download(tickers,start=start,end=end,auto_adjust=False,actions=True,threads=False,progress=False)
 def fld(n):
  x=d[n]; return x.to_frame(tickers[0]) if isinstance(x,pd.Series) else x
 return fld('Close'),fld('Adj Close'),fld('Open')
def at(f,d,t):
 s=f[t].dropna(); s=s[s.index<=d]
 if s.empty: raise RuntimeError(f'no {t} <= {d}')
 return float(s.iloc[-1])
def after(f,d,t):
 s=f[t].dropna(); s=s[s.index>=d]
 if s.empty:return None
 return s.index[0],float(s.iloc[0])

out=[]
for rb_s,snap_s,ex_s,acc in PERIODS:
 print('\n===',rb_s,snap_s,ex_s,acc,'===')
 h=fetch_holdings(acc).sort_values('snapshot_value',ascending=False)
 cand=h[h.snapshot_pct>=1.5].copy()
 cand['ticker']=cand.apply(resolve,axis=1)
 print(cand[['ticker','name','cusip','snapshot_value','snapshot_pct']].to_string(index=False))
 if cand.head(12).ticker.isna().any():
  print('UNRESOLVED_TOP',cand.head(12)[cand.head(12).ticker.isna()][['name','cusip']].to_dict('records'))
  raise RuntimeError('unresolved top candidate')
 cand=cand.dropna(subset=['ticker']).drop_duplicates('ticker')
 tick=cand.ticker.tolist(); rb=pd.Timestamp(rb_s); snap=pd.Timestamp(snap_s); ex=pd.Timestamp(ex_s)
 close,adj,op=price_series(tick,(rb-pd.Timedelta(days=5)).strftime('%Y-%m-%d'),(ex+pd.Timedelta(days=6)).strftime('%Y-%m-%d'))
 rows=[]
 for _,r in cand.iterrows():
  t=r.ticker
  if t not in close.columns or close[t].dropna().empty: continue
  rv=r.snapshot_value*at(close,rb,t)/at(close,snap,t)
  cr=at(adj,ex,t)/at(adj,rb,t)-1
  en=after(op,rb+pd.Timedelta(days=1),t); xo=after(op,ex+pd.Timedelta(days=1),t); nr=float('nan')
  if en and xo:
   ed,eo=en; xd,xx=xo; eao=eo*at(adj,ed,t)/at(close,ed,t); xao=xx*at(adj,xd,t)/at(close,xd,t); nr=xao/eao-1
  rows.append((t,rv,cr,nr,r['name'],r.snapshot_pct))
 z=pd.DataFrame(rows,columns=['ticker','reconstructed_value','close_return','next_open_return','name','snapshot_pct']).sort_values('reconstructed_value',ascending=False)
 print('RANKED\n',z.head(10).to_string(index=False))
 top=z.iloc[0]
 print('TOP1_RESULT',rb_s,top.ticker,float(top.close_return),float(top.next_open_return),acc)
 out.append({'rebalance_date':rb_s,'snapshot_date':snap_s,'exit_date':ex_s,'top1':top.ticker,'reconstructed_top1_value':top.reconstructed_value,'close_to_close_return':top.close_return,'next_open_return':top.next_open_return,'source_accession':acc})
pd.DataFrame(out).to_csv('spmo-backtest/output/modern_batch_results.csv',index=False)
print('\nBATCH_RESULTS\n',pd.DataFrame(out).to_string(index=False))
