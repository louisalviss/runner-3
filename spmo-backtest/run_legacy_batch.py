#!/usr/bin/env python3
import re
from pathlib import Path
import requests
import pandas as pd
import yfinance as yf
from bs4 import BeautifulSoup

PERIODS=[
 ('2016-03-18','2016-04-30','2016-09-16','0001193125-16-644489'),
 ('2016-09-16','2016-10-31','2017-03-17','0001193125-17-002614'),
 ('2017-03-17','2017-04-30','2017-09-15','0001193125-17-221822'),
 ('2017-09-15','2017-10-31','2018-03-16','0001193125-18-002695'),
 ('2018-03-16','2018-04-30','2018-09-21','0001193125-18-214392'),
 ('2018-09-21','2018-10-31','2019-03-15','0001193125-18-321151'),
 ('2019-03-15','2019-04-30','2019-09-20','0001193125-19-138363'),
]

ALIASES=[
 ('Microsoft','MSFT'),('Amazon.com','AMZN'),('Facebook','META'),('Meta Platforms','META'),('General Electric','GE'),('AT&T','T'),('Verizon','VZ'),('McDonald','MCD'),('Home Depot','HD'),('Philip Morris','PM'),('Visa','V'),('Altria','MO'),('Starbucks','SBUX'),('NIKE','NKE'),('Accenture','ACN'),('Lockheed Martin','LMT'),('Progressive','PGR'),('Apple','AAPL'),('Mastercard','MA'),('Adobe','ADBE'),('Activision Blizzard','ATVI'),('Broadcom','AVGO'),('NVIDIA','NVDA'),('Netflix','NFLX'),('PayPal','PYPL'),('Comcast','CMCSA'),('Charter Communications','CHTR'),('Intuit','INTU'),('QUALCOMM','QCOM'),('Texas Instruments','TXN'),('Applied Materials','AMAT'),('Lam Research','LRCX'),('Micron Technology','MU'),('Cisco Systems','CSCO'),('Oracle','ORCL'),('Salesforce','CRM'),('Booking Holdings','BKNG'),('Priceline','BKNG'),('Costco','COST'),('Walmart','WMT'),('Wal-Mart','WMT'),('Target','TGT'),('PepsiCo','PEP'),('Coca-Cola','KO'),('Procter & Gamble','PG'),('UnitedHealth','UNH'),('Eli Lilly','LLY'),('Johnson & Johnson','JNJ'),('Merck','MRK'),('AbbVie','ABBV'),('Pfizer','PFE'),('JPMorgan','JPM'),('Bank of America','BAC'),('Goldman Sachs','GS'),('Morgan Stanley','MS'),('Wells Fargo','WFC'),('Berkshire Hathaway','BRK-B'),('BlackRock','BLK'),('CME Group','CME'),('Intercontinental Exchange','ICE'),('S&P Global','SPGI'),('Equinix','EQIX'),('American Tower','AMT'),('NextEra','NEE'),('American Water Works','AWK'),('Exxon Mobil','XOM'),('Chevron','CVX'),('ConocoPhillips','COP'),('3M','MMM'),('Union Pacific','UNP'),('Raytheon','RTX'),('Northrop Grumman','NOC'),('Cintas','CTAS'),('Equifax','EFX'),('Roper Technologies','ROP'),('Snap-on','SNA'),('Republic Services','RSG'),('Dollar General','DG'),('Dollar Tree','DLTR'),('AutoZone','AZO'),('O’Reilly','ORLY'),("O'Reilly",'ORLY'),('Ross Stores','ROST'),('Darden Restaurants','DRI'),('Carnival','CCL'),('D.R. Horton','DHI'),('Hasbro','HAS'),('Expedia','EXPE'),('Interpublic','IPG'),('L Brands','BBWI'),('Mondelez','MDLZ'),('Kraft Heinz','KHC'),('Kroger','KR'),('Kimberly-Clark','KMB'),('General Mills','GIS'),('Hormel Foods','HRL'),('Kellogg','K'),('Kellanova','K'),('Estée Lauder','EL'),('Estee Lauder','EL'),('Constellation Brands','STZ'),('Boston Scientific','BSX'),('Cigna','CI'),('Edwards Lifesciences','EW'),('Stryker','SYK'),('Public Storage','PSA'),('American International Group','AIG'),('Nasdaq','NDAQ'),
]

def resolve(name):
    n=' '.join(str(name).replace('\xa0',' ').split())
    if 'Alphabet' in n:
        if 'Class A' in n: return 'GOOGL'
        if 'Class C' in n: return 'GOOG'
    for key,ticker in ALIASES:
        if key.lower() in n.lower(): return ticker
    try:
        for q in yf.Search(n,max_results=8,news_count=0).quotes:
            sym=q.get('symbol'); typ=q.get('quoteType')
            if sym and typ=='EQUITY' and not any(sym.endswith(x) for x in ['.TO','.L','.AX','.HK']): return sym.replace('.','-')
    except Exception as e: print('YF_SEARCH_FAIL',n,repr(e))
    return None

def num(s):
    s=str(s).replace(',','').replace('$','').strip(); neg=s.startswith('(') and s.endswith(')'); s=s.strip('()')
    if not re.fullmatch(r'\d+(?:\.\d+)?',s): return None
    v=float(s); return -v if neg else v

def parse_spmo(acc):
    compact=acc.replace('-',''); url=f'https://r.jina.ai/https://www.sec.gov/Archives/edgar/data/1378872/{compact}/{acc}.txt'
    r=requests.get(url,timeout=300,headers={'User-Agent':'runner-3 spmo research'}); print('FETCH',acc,r.status_code,'LEN',len(r.text)); r.raise_for_status()
    docs=re.findall(r'<DOCUMENT>(.*?)</DOCUMENT>',r.text,re.S|re.I); candidates=[]
    for doc in docs:
        if 's&p 500 momentum' not in doc.lower() and 'spmo' not in doc.lower(): continue
        m=re.search(r'<TEXT>(.*)</TEXT>',doc,re.S|re.I); soup=BeautifulSoup(m.group(1) if m else doc,'lxml')
        heads=[]
        for p in soup.find_all('p'):
            tx=' '.join(p.stripped_strings)
            if 'S&P 500 Momentum' in tx and '(SPMO)' in tx and '(continued)' not in tx: heads.append(p)
        for head in heads:
            sib=head; near=[]
            for _ in range(15):
                sib=sib.find_next_sibling()
                if sib is None: break
                near.append(' '.join(sib.stripped_strings))
            if not any('Schedule of Investments' in x for x in near): continue
            rows=[]; node=head
            while True:
                node=node.find_next_sibling()
                if node is None: break
                tx=' '.join(node.stripped_strings)
                # Stop on the next S&P 500 Value fund regardless of PowerShares/Invesco naming.
                if 'S&P 500 Value' in tx and ('(SPVU)' in tx or 'Value Portfolio' in tx or 'Value ETF' in tx) and rows: break
                if node.name!='div': continue
                for tr in node.find_all('tr'):
                    cells=[' '.join(td.stripped_strings) for td in tr.find_all(['td','th'])]
                    if len(cells)<8: continue
                    sh=num(cells[1]); val=num(cells[7]); nm=cells[4].strip()
                    if sh is None or val is None or not nm: continue
                    if any(z in nm for z in ['Total Investments','Net Assets','Other assets','Common Stocks and Other Equity Interests']): continue
                    rows.append({'shares':sh,'name':nm,'snapshot_value':val})
            if len(rows)>=40: candidates.append(pd.DataFrame(rows).drop_duplicates(subset=['name','shares','snapshot_value']))
    if not candidates: raise RuntimeError(f'{acc}: no SPMO schedule parsed')
    df=max(candidates,key=len).sort_values('snapshot_value',ascending=False).reset_index(drop=True); print('PARSED',acc,len(df),'TOP\n',df.head(20).to_string(index=False)); return df

def get_fields(data,tickers):
    def f(n):
        x=data[n]; return x.to_frame(tickers[0]) if isinstance(x,pd.Series) else x
    return f('Close'),f('Adj Close'),f('Open')
def at(f,d,t):
    s=f[t].dropna(); s=s[s.index<=d]
    if s.empty: raise RuntimeError(f'no {t} price <= {d}')
    return float(s.iloc[-1])
def after(f,d,t):
    s=f[t].dropna(); s=s[s.index>=d]; return (s.index[0],float(s.iloc[0])) if len(s) else None

results=[]
for rb_s,snap_s,exit_s,acc in PERIODS:
    print('\n========== PERIOD',rb_s,'=========='); h=parse_spmo(acc); cand=h.head(25).copy(); cand['ticker']=cand['name'].map(resolve); print('RESOLVED\n',cand[['ticker','name','snapshot_value']].to_string(index=False))
    if cand.head(12).ticker.isna().any():
        print('UNRESOLVED_TOP12\n',cand.head(12)[cand.head(12).ticker.isna()][['name','snapshot_value']].to_string(index=False)); raise RuntimeError(f'{acc}: unresolved top12')
    cand=cand.dropna(subset=['ticker']).drop_duplicates('ticker'); rb=pd.Timestamp(rb_s); snap=pd.Timestamp(snap_s); ex=pd.Timestamp(exit_s); tick=cand.ticker.tolist()
    data=yf.download(tick,start=(rb-pd.Timedelta(days=7)).strftime('%Y-%m-%d'),end=(ex+pd.Timedelta(days=7)).strftime('%Y-%m-%d'),auto_adjust=False,actions=True,threads=False,progress=False); close,adj,op=get_fields(data,tick); ranked=[]
    for _,z in cand.iterrows():
        t=z.ticker
        if t not in close.columns or close[t].dropna().empty: print('NO_PRICE',t,z['name']); continue
        try: rv=z.snapshot_value*at(close,rb,t)/at(close,snap,t); cr=at(adj,ex,t)/at(adj,rb,t)-1
        except Exception as e: print('PRICE_FAIL',t,z['name'],repr(e)); continue
        en=after(op,rb+pd.Timedelta(days=1),t); xo=after(op,ex+pd.Timedelta(days=1),t); nr=float('nan')
        if en and xo:
            ed,eo=en; xd,xv=xo; nr=(xv*at(adj,xd,t)/at(close,xd,t))/(eo*at(adj,ed,t)/at(close,ed,t))-1
        ranked.append({'ticker':t,'name':z['name'],'snapshot_value':z.snapshot_value,'reconstructed_value':rv,'close_return':cr,'next_open_return':nr})
    z=pd.DataFrame(ranked).sort_values('reconstructed_value',ascending=False).reset_index(drop=True)
    if len(z)<8: raise RuntimeError(f'{acc}: too few priced candidates')
    print('RANKED\n',z.head(12).to_string(index=False)); top=z.iloc[0]; margin=top.reconstructed_value/z.iloc[1].reconstructed_value-1; print('TOP1_RESULT',rb_s,top.ticker,float(top.close_return),float(top.next_open_return),'MARGIN',float(margin)); results.append({'rebalance_date':rb_s,'snapshot_date':snap_s,'exit_date':exit_s,'top1':top.ticker,'reconstructed_top1_value':top.reconstructed_value,'close_to_close_return':top.close_return,'next_open_return':top.next_open_return,'source_accession':acc,'top1_margin_vs_2':margin})
Path('spmo-backtest/output').mkdir(parents=True,exist_ok=True); out=pd.DataFrame(results); out.to_csv('spmo-backtest/output/legacy_batch_results.csv',index=False); print('\nLEGACY_BATCH_RESULTS\n',out.to_string(index=False))
