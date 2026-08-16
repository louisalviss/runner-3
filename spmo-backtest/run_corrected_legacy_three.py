#!/usr/bin/env python3
import re,time
from pathlib import Path
import requests,pandas as pd,yfinance as yf
from bs4 import BeautifulSoup,NavigableString

PERIODS=[
 ('2018-03-16','2018-04-30','2018-09-21','0001193125-18-214392','https://www.sec.gov/Archives/edgar/data/1378872/000119312518214392/d566829dncsrs.htm'),
 ('2018-09-21','2018-11-30','2019-03-15','0001193125-19-020397','https://www.sec.gov/Archives/edgar/data/1378872/000119312519020397/d683996dnq.htm'),
 ('2019-03-15','2019-05-31','2019-09-20','0001752724-19-086759','https://www.sec.gov/Archives/edgar/data/1378872/000175272419086759/ETF_Trust_II.htm'),
]
ALIASES=[('Microsoft','MSFT'),('Apple','AAPL'),('Amazon','AMZN'),('Facebook','META'),('Alphabet','GOOG'),('JPMorgan','JPM'),('Berkshire Hathaway','BRK-B'),('Bank of America','BAC'),('Visa','V'),('Mastercard','MA'),('Johnson & Johnson','JNJ'),('UnitedHealth','UNH'),('Home Depot','HD'),('Comcast','CMCSA'),('Boeing','BA'),('NVIDIA','NVDA'),('Adobe','ADBE'),('Netflix','NFLX'),('PayPal','PYPL'),('Cisco','CSCO'),('Intel','INTC'),('Broadcom','AVGO'),('Accenture','ACN'),('Texas Instruments','TXN'),('3M','MMM'),('Union Pacific','UNP'),('Lockheed Martin','LMT'),('McDonald','MCD'),('NIKE','NKE'),('Costco','COST'),('Walmart','WMT'),('Target','TGT'),('PepsiCo','PEP'),('Coca-Cola','KO'),('Procter','PG'),('Pfizer','PFE'),('Merck','MRK'),('AbbVie','ABBV'),('Eli Lilly','LLY'),('Exxon','XOM'),('Chevron','CVX'),('Conoco','COP'),('Salesforce','CRM'),('Oracle','ORCL'),('QUALCOMM','QCOM'),('Applied Materials','AMAT'),('Micron','MU'),('Booking','BKNG'),('Priceline','BKNG'),('Starbucks','SBUX'),('Morgan Stanley','MS'),('Wells Fargo','WFC'),('Goldman','GS'),('Caterpillar','CAT'),('Deere','DE'),('Raytheon','RTX'),('Honeywell','HON'),('Amgen','AMGN'),('Abbott','ABT'),('Thermo Fisher','TMO'),('Danaher','DHR'),('Intuit','INTU'),('Automatic Data','ADP'),('S&P Global','SPGI'),('CME Group','CME'),('American Express','AXP'),('Citigroup','C'),('PNC Financial','PNC'),('U.S. Bancorp','USB'),('Charles Schwab','SCHW'),('American Tower','AMT'),('CBRE','CBRE'),('SBA Communications','SBAC')]

def fetch(url):
    hdr={'User-Agent':'SPMO independent research contact@example.com','Accept-Encoding':'gzip, deflate'}
    for i in range(4):
        try:
            r=requests.get(url,headers=hdr,timeout=180)
            print('SEC_FETCH',r.status_code,len(r.content),url,flush=True)
            if r.status_code==200 and len(r.content)>10000:return r.text
        except Exception as e: print('SEC_FETCH_ERR',repr(e),flush=True)
        time.sleep(2+2*i)
    raise RuntimeError('SEC fetch failed '+url)

def text_from_html(url):
    soup=BeautifulSoup(fetch(url),'lxml')
    for tr in list(soup.find_all('tr')):
        cells=[' '.join(c.stripped_strings) for c in tr.find_all(['td','th'],recursive=False)]
        if cells: tr.replace_with(NavigableString('\n'+'\t'.join(cells)+'\n'))
    return soup.get_text('\n')

def segment(t,snap_s):
    # Prefer an occurrence whose local context contains the target report date and a Schedule of Investments.
    occ=[m.start() for m in re.finditer(r'Invesco\s+S&P\s+500(?:®)?\s+Momentum\s+ETF(?:\s*\(SPMO\))?',t,re.I)]
    print('SPMO_OCC',len(occ),flush=True)
    if not occ: raise RuntimeError('No SPMO occurrence')
    target=pd.Timestamp(snap_s)
    date_patterns=[target.strftime('%B %d, %Y').replace(' 0',' '),target.strftime('%B %d, %Y')]
    opts=[]
    for s0 in occ:
        before=t[max(0,s0-3000):s0+1000]
        # avoid board/fee/index references; schedule should have many tabular numeric rows nearby
        e_candidates=[]
        for pat in [r'\nSchedule of Investments',r'\nInvesco\s+[^\n]{2,100}\s+ETF(?:\s*\([^\n]+\))?']:
            m=re.search(pat,t[s0+1500:],re.I)
            if m:e_candidates.append(s0+1500+m.start())
        e=min(e_candidates) if e_candidates else min(len(t),s0+180000)
        z=t[max(0,s0-1500):e]
        n=sum(1 for ln in z.splitlines() if '\t' in ln and re.search(r'\d',ln))
        date_bonus=1000 if any(dp in z.replace('\xa0',' ') for dp in date_patterns) else 0
        sched_bonus=1000 if 'Schedule of Investments' in z else 0
        opts.append((n+date_bonus+sched_bonus,n,len(z),z))
    opts.sort(key=lambda x:x[0],reverse=True)
    print('SEGMENT_OPTIONS',[(x[0],x[1],x[2]) for x in opts[:5]],flush=True)
    return opts[0][3]

def parse(z):
    rows=[]
    for line in z.splitlines():
        p=[' '.join(x.replace('\xa0',' ').split()) for x in line.split('\t')]
        p=[x for x in p if x not in ('','$','—','-')]
        if len(p)<3: continue
        def num(x): return re.fullmatch(r'\$?\(?[\d,]+\)?',x.replace(' ','') or '') is not None
        nums=[i for i,x in enumerate(p) if num(x) and re.search(r'\d',x)]
        if len(nums)<2: continue
        i0,i1=nums[0],nums[-1]
        if i1<=i0: continue
        names=[x for x in p[i0+1:i1] if re.search('[A-Za-z]',x)]
        if not names: continue
        name=max(names,key=len).strip('*_ '); low=name.lower()
        if any(q in low for q in ['common stocks','total investments','net assets','money market','other assets','investments purchased','total common']):continue
        if '%' in name and not re.search(r'Inc|Corp|Co\.|PLC|Ltd|Class|REIT',name,re.I):continue
        try:
            shares=int(re.sub(r'[^\d]','',p[i0])); value=int(re.sub(r'[^\d]','',p[i1]))
        except: continue
        if shares and value: rows.append((shares,name,value))
    d=pd.DataFrame(rows,columns=['shares','name','snapshot_value']).drop_duplicates()
    # Drop obvious section/subtotal artifacts and sort by holding value.
    d=d[~d['name'].str.contains(r'—\s*\d| - \d|Sector|Total|Assets|Liabilities',case=False,regex=True,na=False)]
    d=d.sort_values('snapshot_value',ascending=False).reset_index(drop=True)
    print('PARSED_ROWS',len(d),'TOP\n',d.head(30).to_string(index=False),flush=True)
    if len(d)<50: raise RuntimeError('Too few holdings parsed '+str(len(d)))
    return d

def resolve(n):
    n=re.sub(r'\([a-z](?:\)\([a-z]\))*\)$','',n,flags=re.I).strip()
    if 'Alphabet' in n:
        if 'Class A' in n:return 'GOOGL'
        if 'Class C' in n:return 'GOOG'
    for k,v in ALIASES:
        if k.lower() in n.lower():return v
    try:
        for q in yf.Search(n,max_results=6,news_count=0).quotes:
            if q.get('quoteType')=='EQUITY' and q.get('symbol'):
                return q['symbol'].replace('.','-')
    except Exception as e: print('SEARCH_FAIL',n,repr(e),flush=True)
    return None

def fld(d,n,tickers):
    x=d[n]; return x.to_frame(tickers[0]) if isinstance(x,pd.Series) else x
def at(f,d,t):
    s=f[t].dropna(); s=s[s.index<=d]
    if s.empty: raise RuntimeError(f'No {t} <= {d}')
    return float(s.iloc[-1])
def after(f,d,t):
    s=f[t].dropna();s=s[s.index>=d];return (s.index[0],float(s.iloc[0])) if len(s) else None

outs=[]
for rb_s,snap_s,ex_s,acc,url in PERIODS:
    print('\n=== PERIOD',rb_s,'snapshot',snap_s,'===',flush=True)
    holdings=parse(segment(text_from_html(url),snap_s))
    # The original legacy method used top-30 snapshot holdings. Use top-40 and record the margin.
    h=holdings.head(40).copy();h['ticker']=h['name'].map(resolve)
    print('RESOLVED\n',h[['ticker','name','snapshot_value']].to_string(index=False),flush=True)
    h=h.dropna(subset=['ticker']).drop_duplicates('ticker');tick=h.ticker.tolist()
    if len(tick)<20: raise RuntimeError('Too few resolved candidate tickers')
    rb=pd.Timestamp(rb_s);snap=pd.Timestamp(snap_s);ex=pd.Timestamp(ex_s)
    d=yf.download(tick,start=(rb-pd.Timedelta(days=7)).strftime('%Y-%m-%d'),end=(ex+pd.Timedelta(days=7)).strftime('%Y-%m-%d'),auto_adjust=False,actions=True,threads=False,progress=False)
    close,adj,op=fld(d,'Close',tick),fld(d,'Adj Close',tick),fld(d,'Open',tick);rr=[]
    for _,r in h.iterrows():
        t=r.ticker
        if t not in close.columns or close[t].dropna().empty:continue
        try:rv=r.snapshot_value*at(close,rb,t)/at(close,snap,t);cr=at(adj,ex,t)/at(adj,rb,t)-1
        except Exception as e:print('PRICE_FAIL',t,e,flush=True);continue
        en=after(op,rb+pd.Timedelta(days=1),t);xo=after(op,ex+pd.Timedelta(days=1),t);nr=float('nan')
        if en and xo:
            ed,eo=en;xd,xv=xo;nr=(xv*at(adj,xd,t)/at(close,xd,t))/(eo*at(adj,ed,t)/at(close,ed,t))-1
        rr.append((t,r['name'],r.snapshot_value,rv,cr,nr))
    z=pd.DataFrame(rr,columns=['ticker','name','snapshot_value','reconstructed_value','close_return','next_open_return']).sort_values('reconstructed_value',ascending=False)
    print('RANKED\n',z.head(15).to_string(index=False),flush=True)
    if len(z)<2: raise RuntimeError('No ranked candidates')
    top=z.iloc[0];margin=top.reconstructed_value/z.iloc[1].reconstructed_value-1
    print('TOP1_RESULT',rb_s,top.ticker,float(top.close_return),float(top.next_open_return),'MARGIN',float(margin),flush=True)
    outs.append({'rebalance_date':rb_s,'snapshot_date':snap_s,'exit_date':ex_s,'top1':top.ticker,'reconstructed_top1_value':top.reconstructed_value,'close_to_close_return':top.close_return,'next_open_return':top.next_open_return,'candidate_scope':'top40_snapshot_holdings','source_accession':acc,'top1_margin_vs_2':margin})
Path('spmo-backtest/output').mkdir(parents=True,exist_ok=True)
pd.DataFrame(outs).to_csv('spmo-backtest/output/corrected_legacy_three.csv',index=False)
print('\nCORRECTED_RESULTS\n',pd.DataFrame(outs).to_string(index=False),flush=True)
