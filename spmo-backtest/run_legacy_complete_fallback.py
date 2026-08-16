#!/usr/bin/env python3
import re,time
from pathlib import Path
import requests,pandas as pd,yfinance as yf
from bs4 import BeautifulSoup, NavigableString

PERIODS=[
 ('2017-09-15','2017-10-31','2018-03-16','0001193125-18-002695'),
 ('2018-03-16','2018-04-30','2018-09-21','0001193125-18-214392'),
]
ALIASES=[('Microsoft','MSFT'),('Apple','AAPL'),('Amazon','AMZN'),('Facebook','META'),('Alphabet','GOOG'),('JPMorgan','JPM'),('Berkshire Hathaway','BRK-B'),('Bank of America','BAC'),('Visa','V'),('Mastercard','MA'),('Johnson & Johnson','JNJ'),('UnitedHealth','UNH'),('Home Depot','HD'),('Comcast','CMCSA'),('Boeing','BA'),('NVIDIA','NVDA'),('Adobe','ADBE'),('Netflix','NFLX'),('PayPal','PYPL'),('Cisco','CSCO'),('Intel','INTC'),('Broadcom','AVGO'),('Accenture','ACN'),('Texas Instruments','TXN'),('3M','MMM'),('Union Pacific','UNP'),('Lockheed Martin','LMT'),('McDonald','MCD'),('NIKE','NKE'),('Costco','COST'),('Walmart','WMT'),('Target','TGT'),('PepsiCo','PEP'),('Coca-Cola','KO'),('Procter','PG'),('Pfizer','PFE'),('Merck','MRK'),('AbbVie','ABBV'),('Eli Lilly','LLY'),('Exxon','XOM'),('Chevron','CVX'),('Conoco','COP'),('Salesforce','CRM'),('Oracle','ORCL'),('QUALCOMM','QCOM'),('Applied Materials','AMAT'),('Micron','MU'),('Booking','BKNG'),('Priceline','BKNG'),('Starbucks','SBUX'),('Morgan Stanley','MS'),('Wells Fargo','WFC'),('Goldman','GS')]

def get_complete(acc):
    url=f'https://r.jina.ai/https://www.sec.gov/Archives/edgar/data/1378872/{acc.replace("-","")}/{acc}.txt'
    for i in range(4):
        try:
            r=requests.get(url,timeout=300,headers={'User-Agent':'runner-3 SPMO research'})
            print('FETCH_COMPLETE',acc,r.status_code,len(r.text),flush=True)
            if r.status_code==200 and len(r.text)>10000:return r.text
        except Exception as e:print('FETCH_ERR',repr(e),flush=True)
        time.sleep(3+3*i)
    raise RuntimeError('complete fetch failed '+acc)

def doc_text(acc):
    raw=get_complete(acc)
    blocks=re.findall(r'<DOCUMENT>([\s\S]*?)</DOCUMENT>',raw,re.I)
    print('DOC_BLOCKS',len(blocks),flush=True)
    candidates=[]
    for b in blocks:
        typm=re.search(r'<TYPE>\s*([^\r\n<]+)',b,re.I); typ=typm.group(1).strip().upper() if typm else ''
        if typ not in ('N-CSR','N-CSRS','N-Q'):continue
        tm=re.search(r'<TEXT>([\s\S]*?)</TEXT>',b,re.I); html=tm.group(1) if tm else b
        if not re.search(r'(?:PowerShares|Invesco)\s+S&P\s+500.*?Momentum',html,re.I|re.S):continue
        soup=BeautifulSoup(html,'lxml')
        for tr in list(soup.find_all('tr')):
            cells=[' '.join(c.stripped_strings) for c in tr.find_all(['td','th'],recursive=False)]
            if cells: tr.replace_with(NavigableString('\n'+'\t'.join(cells)+'\n'))
        txt=soup.get_text('\n')
        candidates.append((typ,len(txt),txt))
    if not candidates:raise RuntimeError('No SPMO report document in complete submission')
    candidates.sort(key=lambda x:x[1],reverse=True)
    print('CHOSEN_DOC',candidates[0][0],candidates[0][1],flush=True)
    return candidates[0][2]

def segment(t):
    occ=[m.start() for m in re.finditer(r'(?:PowerShares|Invesco)\s+S&P\s+500(?:®)?\s+Momentum\s+(?:Portfolio|ETF)[^\n]{0,120}(?:\(SPMO\))?',t,re.I)]
    print('SPMO_OCC',len(occ),occ[:20],flush=True)
    if not occ:raise RuntimeError('No SPMO occurrence after HTML conversion')
    opts=[]
    for s0 in occ:
        line=t[s0:t.find('\n',s0) if t.find('\n',s0)>=0 else s0+250]
        if 'continued' in line.lower():continue
        s=max(0,s0-2000)
        # stop at next fund schedule/title well after this section
        nxt=[]
        for pat in [r'\n(?:PowerShares|Invesco)\s+[^\n]{2,100}\s+(?:Portfolio|ETF)',r'\nSchedule of Investments']:
            m=re.search(pat,t[s0+5000:],re.I)
            if m:nxt.append(s0+5000+m.start())
        e=min(nxt) if nxt else min(len(t),s0+180000)
        z=t[s:e]
        n=sum(1 for ln in z.splitlines() if '\t' in ln and re.search(r'\d',ln))
        opts.append((n,z))
    opts.sort(key=lambda x:x[0],reverse=True)
    print('SEG_ROWS',[(x[0],len(x[1])) for x in opts[:5]],flush=True)
    return opts[0][1]

def parse(z):
    rows=[]
    for line in z.splitlines():
        p=[' '.join(x.replace('\xa0',' ').split()) for x in line.split('\t')]
        p=[x for x in p if x not in ('','$','—','-')]
        if len(p)<3:continue
        # find first numeric shares, last numeric value; name is text between
        def num(x):return re.fullmatch(r'\$?\(?[\d,]+\)?',x.replace(' ','') or '') is not None
        nums=[i for i,x in enumerate(p) if num(x) and re.search(r'\d',x)]
        if len(nums)<2:continue
        i0,i1=nums[0],nums[-1]
        if i1<=i0:continue
        names=[x for x in p[i0+1:i1] if re.search('[A-Za-z]',x)]
        if not names:continue
        name=max(names,key=len).strip('*_ '); low=name.lower()
        if any(q in low for q in ['common stocks','total investments','net assets','money market','other assets']):continue
        try:
            shares=int(re.sub(r'[^\d]','',p[i0])); value=int(re.sub(r'[^\d]','',p[i1]))
        except:continue
        if shares and value:rows.append((shares,name,value))
    d=pd.DataFrame(rows,columns=['shares','name','snapshot_value']).drop_duplicates().sort_values('snapshot_value',ascending=False).reset_index(drop=True)
    print('PARSED_ROWS',len(d),'TOP\n',d.head(25).to_string(index=False),flush=True)
    if len(d)<50:raise RuntimeError('Too few holdings parsed '+str(len(d)))
    return d

def resolve(n):
    if 'Alphabet' in n:
        if 'Class A' in n:return 'GOOGL'
        if 'Class C' in n:return 'GOOG'
    for k,v in ALIASES:
        if k.lower() in n.lower():return v
    try:
        for q in yf.Search(n,max_results=6,news_count=0).quotes:
            if q.get('quoteType')=='EQUITY' and q.get('symbol'):return q['symbol'].replace('.','-')
    except Exception as e:print('SEARCH_FAIL',n,repr(e),flush=True)
    return None

def fld(d,n,tickers):
    x=d[n]; return x.to_frame(tickers[0]) if isinstance(x,pd.Series) else x
def at(f,d,t):
    s=f[t].dropna();s=s[s.index<=d]
    if s.empty:raise RuntimeError(f'No {t} <= {d}')
    return float(s.iloc[-1])
def after(f,d,t):
    s=f[t].dropna();s=s[s.index>=d];return (s.index[0],float(s.iloc[0])) if len(s) else None

outs=[]
for rb_s,snap_s,ex_s,acc in PERIODS:
    print('\n=== PERIOD',rb_s,'===',flush=True)
    h=parse(segment(doc_text(acc))).head(35).copy(); h['ticker']=h.name.map(resolve)
    print('RESOLVED\n',h[['ticker','name','snapshot_value']].to_string(index=False),flush=True)
    h=h.dropna(subset=['ticker']).drop_duplicates('ticker'); tick=h.ticker.tolist()
    rb=pd.Timestamp(rb_s);snap=pd.Timestamp(snap_s);ex=pd.Timestamp(ex_s)
    d=yf.download(tick,start=(rb-pd.Timedelta(days=7)).strftime('%Y-%m-%d'),end=(ex+pd.Timedelta(days=7)).strftime('%Y-%m-%d'),auto_adjust=False,actions=True,threads=False,progress=False)
    close,adj,op=fld(d,'Close',tick),fld(d,'Adj Close',tick),fld(d,'Open',tick); rr=[]
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
    top=z.iloc[0]; margin=top.reconstructed_value/z.iloc[1].reconstructed_value-1
    print('TOP1_RESULT',rb_s,top.ticker,float(top.close_return),float(top.next_open_return),'MARGIN',float(margin),flush=True)
    outs.append({'rebalance_date':rb_s,'snapshot_date':snap_s,'exit_date':ex_s,'top1':top.ticker,'reconstructed_top1_value':top.reconstructed_value,'close_to_close_return':top.close_return,'next_open_return':top.next_open_return,'source_accession':acc,'top1_margin_vs_2':margin})
Path('spmo-backtest/output').mkdir(parents=True,exist_ok=True);pd.DataFrame(outs).to_csv('spmo-backtest/output/legacy_complete_results.csv',index=False)
