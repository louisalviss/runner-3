#!/usr/bin/env python3
import re,time
from pathlib import Path
import requests
import pandas as pd
import yfinance as yf

PERIODS=[
 ('2016-03-18','2016-04-30','2016-09-16','0001193125-16-644489'),
 ('2016-09-16','2016-10-31','2017-03-17','0001193125-17-002614'),
 ('2017-03-17','2017-04-30','2017-09-15','0001193125-17-221822'),
 ('2017-09-15','2017-10-31','2018-03-16','0001193125-18-002695'),
 ('2018-03-16','2018-04-30','2018-09-21','0001193125-18-214392'),
 ('2018-09-21','2018-10-31','2019-03-15','0001193125-19-002456'),
 ('2019-03-15','2019-04-30','2019-09-20','0001193125-19-190405'),
]
PRIMARY_DOCS={
 '0001193125-16-644489':'d176916dncsrs.htm',
 '0001193125-17-002614':'d269293dncsr.htm',
 '0001193125-18-002695':'d473179dncsr.htm',
 '0001193125-19-002456':'d525171dncsr.htm',
 '0001193125-19-190405':'d740133dncsrs.htm',
}
ALIASES=[
 ('Microsoft','MSFT'),('Amazon.com','AMZN'),('Facebook','META'),('Meta Platforms','META'),('General Electric','GE'),('AT&T','T'),('Verizon','VZ'),('McDonald','MCD'),('Home Depot','HD'),('Philip Morris','PM'),('Visa','V'),('Altria','MO'),('Starbucks','SBUX'),('NIKE','NKE'),('Accenture','ACN'),('Lockheed Martin','LMT'),('Progressive','PGR'),('Apple','AAPL'),('Mastercard','MA'),('Adobe','ADBE'),('Activision Blizzard','ATVI'),('Broadcom','AVGO'),('NVIDIA','NVDA'),('Netflix','NFLX'),('PayPal','PYPL'),('Comcast','CMCSA'),('Charter Communications','CHTR'),('Intuit','INTU'),('QUALCOMM','QCOM'),('Texas Instruments','TXN'),('Applied Materials','AMAT'),('Lam Research','LRCX'),('Micron Technology','MU'),('Cisco Systems','CSCO'),('Oracle','ORCL'),('Salesforce','CRM'),('Booking Holdings','BKNG'),('Priceline','BKNG'),('Costco','COST'),('Walmart','WMT'),('Wal-Mart','WMT'),('Target','TGT'),('PepsiCo','PEP'),('Coca-Cola','KO'),('Procter & Gamble','PG'),('UnitedHealth','UNH'),('Eli Lilly','LLY'),('Johnson & Johnson','JNJ'),('Merck','MRK'),('AbbVie','ABBV'),('Pfizer','PFE'),('JPMorgan','JPM'),('Bank of America','BAC'),('Goldman Sachs','GS'),('Morgan Stanley','MS'),('Wells Fargo','WFC'),('Berkshire Hathaway','BRK-B'),('BlackRock','BLK'),('CME Group','CME'),('Intercontinental Exchange','ICE'),('S&P Global','SPGI'),('Equinix','EQIX'),('American Tower','AMT'),('NextEra','NEE'),('American Water Works','AWK'),('Exxon Mobil','XOM'),('Chevron','CVX'),('ConocoPhillips','COP'),('3M','MMM'),('Union Pacific','UNP'),('Raytheon','RTX'),('Northrop Grumman','NOC'),('Cintas','CTAS'),('Equifax','EFX'),('Roper Technologies','ROP'),('Snap-on','SNA'),('Republic Services','RSG'),('Dollar General','DG'),('Dollar Tree','DLTR'),('AutoZone','AZO'),('O’Reilly','ORLY'),("O'Reilly",'ORLY'),('Ross Stores','ROST'),('Darden Restaurants','DRI'),('Carnival','CCL'),('D.R. Horton','DHI'),('Hasbro','HAS'),('Expedia','EXPE'),('Interpublic','IPG'),('L Brands','BBWI'),('Mondelez','MDLZ'),('Kraft Heinz','KHC'),('Kroger','KR'),('Kimberly-Clark','KMB'),('General Mills','GIS'),('Hormel Foods','HRL'),('Kellogg','K'),('Kellanova','K'),('Estée Lauder','EL'),('Estee Lauder','EL'),('Constellation Brands','STZ'),('Boston Scientific','BSX'),('Cigna','CI'),('Edwards Lifesciences','EW'),('Stryker','SYK'),('Public Storage','PSA'),('American International Group','AIG'),('Nasdaq','NDAQ'),('Reynolds American','RAI'),('Time Warner Cable','TWC'),('Alphabet','GOOG'),('Alphabet Inc. Class A','GOOGL'),
]
H={'User-Agent':'Mozilla/5.0 runner-3 SPMO research'}

def jina(u,timeout=240):
    ju='https://r.jina.ai/'+u
    for i in range(3):
        try:
            r=requests.get(ju,headers=H,timeout=timeout)
            print('FETCH',r.status_code,len(r.text),ju,flush=True)
            if r.status_code==200 and len(r.text)>200:return r.text
        except Exception as e:print('FETCH_ERR',repr(e),flush=True)
        time.sleep(2+2*i)
    raise RuntimeError('Jina fetch failed '+u)

def primary_for(acc):
    folder=acc.replace('-','')
    if acc in PRIMARY_DOCS:
        return f'https://www.sec.gov/Archives/edgar/data/1378872/{folder}/{PRIMARY_DOCS[acc]}'
    complete=f'https://www.sec.gov/Archives/edgar/data/1378872/{folder}/{acc}.txt'
    t=jina(complete)
    for b in re.findall(r'<DOCUMENT>([\s\S]*?)</DOCUMENT>',t,re.I):
        tm=re.search(r'<TYPE>\s*([^\r\n<]+)',b,re.I); fm=re.search(r'<FILENAME>\s*([^\r\n<]+)',b,re.I)
        typ=tm.group(1).strip().upper() if tm else ''
        if fm and typ in ('N-CSRS','N-CSR'):
            doc=fm.group(1).strip(); print('PRIMARY_RESOLVED',acc,typ,doc,flush=True)
            return f'https://www.sec.gov/Archives/edgar/data/1378872/{folder}/{doc}'
    raise RuntimeError('No primary N-CSRS/N-CSR for '+acc)

def clean_name(name):
    name=name.strip().strip('*_ ')
    return re.sub(r'\s*\([a-z](?:,[a-z])*\)\s*$','',name,flags=re.I).strip()

def stock_line_count(z):
    n=0
    for line in z.splitlines():
        x=line.replace('\xa0',' ').strip().strip('*')
        if re.match(r'^[\d,]+\s+.+(?:\$)?[\d][\d,]*$',x):n+=1
        elif '\t' in line and re.match(r'^\s*\t?[\d,]+\t',line.replace('\xa0',' ')):n+=1
    return n

def segment(t):
    occ=[m.start() for m in re.finditer(r'(?:PowerShares|Invesco) S&P 500(?:®)? Momentum (?:Portfolio|ETF)[^\n]{0,80}\(SPMO\)',t,re.I)]
    if not occ:raise RuntimeError('No SPMO occurrence')
    c=[]
    for s0 in occ:
        line=t[s0:t.find('\n',s0) if t.find('\n',s0)>=0 else s0+300]
        if 'continued' in line.lower():continue
        prev=t.rfind('Schedule of Investments',max(0,s0-1500),s0); s=prev if prev>=0 else s0
        m=re.search(r'(?:\*\*)?Schedule of Investments(?:\([^\n]*\))?',t[s0+1500:],re.I)
        e=s0+1500+m.start() if m else min(len(t),s0+140000)
        z=t[s:e]; n=stock_line_count(z)
        score=n+200*('Total Investments' in z)+100*('Net Assets' in z)+50*('Common Stocks' in z)
        c.append((score,n,z))
    if not c:raise RuntimeError('No schedule candidate')
    c.sort(reverse=True,key=lambda x:x[0]); score,n,z=c[0]; print('SEGMENT score',score,'lines',n,flush=True)
    if n<70:raise RuntimeError('Too few stock lines '+str(n))
    return z

def parse(z):
    rows=[]
    for line in z.splitlines():
        p=[x.strip() for x in line.replace('\xa0',' ').split('\t')]; p=[x for x in p if x not in ('','$')]
        if len(p)>=3 and re.fullmatch(r'[\d,]+',p[0]) and re.fullmatch(r'[\d,]+',p[-1]) and re.search(r'\d',p[-1]):
            names=[x for x in p[1:-1] if re.search('[A-Za-z]',x)]
            if names:
                name=clean_name(max(names,key=len)); low=name.lower()
                if not any(x in low for x in ['common stocks','total investments','net assets','money market fund','other assets less']):
                    rows.append((int(p[0].replace(',','')),name,int(p[-1].replace(',','')))); continue
        x=line.replace('\xa0',' ').strip().strip('*')
        m=re.match(r'^([\d][\d,]*)\s+(.+?)(?:\$)?([\d][\d,]*)$',x)
        if not m:continue
        shares=int(m.group(1).replace(',','')); name=clean_name(m.group(2)); val=int(m.group(3).replace(',','')); low=name.lower()
        if re.search('[A-Za-z]',name) and not any(q in low for q in ['common stocks','total investments','net assets','money market fund','other assets less']):rows.append((shares,name,val))
    d=pd.DataFrame(rows,columns=['shares','name','snapshot_value']).drop_duplicates().sort_values('snapshot_value',ascending=False).reset_index(drop=True)
    if len(d)<70:raise RuntimeError('Parsed too few holdings '+str(len(d)))
    print('PARSED',len(d),'TOP\n',d.head(20).to_string(index=False),flush=True); return d

def parse_spmo(acc):
    u=primary_for(acc); print('PRIMARY',u,flush=True); return parse(segment(jina(u)))

def resolve(name):
    n=' '.join(str(name).replace('\xa0',' ').split())
    if 'Alphabet' in n:
        if 'Class A' in n:return 'GOOGL'
        if 'Class C' in n:return 'GOOG'
    for key,ticker in ALIASES:
        if key.lower() in n.lower():return ticker
    try:
        for q in yf.Search(n,max_results=8,news_count=0).quotes:
            sym=q.get('symbol'); typ=q.get('quoteType')
            if sym and typ=='EQUITY' and not any(sym.endswith(x) for x in ['.TO','.L','.AX','.HK']):return sym.replace('.','-')
    except Exception as e:print('YF_SEARCH_FAIL',n,repr(e),flush=True)
    return None

def field(data,n,tickers):
    x=data[n]; return x.to_frame(tickers[0]) if isinstance(x,pd.Series) else x
def at(f,d,t):
    s=f[t].dropna(); s=s[s.index<=d]
    if s.empty:raise RuntimeError(f'No {t} price <= {d}')
    return float(s.iloc[-1])
def after(f,d,t):
    s=f[t].dropna(); s=s[s.index>=d]; return (s.index[0],float(s.iloc[0])) if len(s) else None

results=[]
for rb_s,snap_s,exit_s,acc in PERIODS:
    h=parse_spmo(acc); cand=h.head(30).copy(); cand['ticker']=cand['name'].map(resolve)
    print('RESOLVED\n',cand[['ticker','name','snapshot_value']].to_string(index=False),flush=True)
    cand=cand.dropna(subset=['ticker']).drop_duplicates('ticker')
    rb=pd.Timestamp(rb_s); snap=pd.Timestamp(snap_s); ex=pd.Timestamp(exit_s); tick=cand.ticker.tolist()
    data=yf.download(tick,start=(rb-pd.Timedelta(days=7)).strftime('%Y-%m-%d'),end=(ex+pd.Timedelta(days=7)).strftime('%Y-%m-%d'),auto_adjust=False,actions=True,threads=False,progress=False)
    close=field(data,'Close',tick); adj=field(data,'Adj Close',tick); op=field(data,'Open',tick); ranked=[]
    for _,r in cand.iterrows():
        t=r.ticker
        if t not in close.columns or close[t].dropna().empty:print('NO_PRICE',t,r['name'],flush=True);continue
        try:
            rv=float(r.snapshot_value)*at(close,rb,t)/at(close,snap,t); cr=at(adj,ex,t)/at(adj,rb,t)-1
        except Exception as e:print('PRICE_FAIL',t,r['name'],repr(e),flush=True);continue
        en=after(op,rb+pd.Timedelta(days=1),t); xo=after(op,ex+pd.Timedelta(days=1),t); nr=float('nan')
        if en and xo:
            ed,eo=en; xd,xv=xo; nr=(xv*at(adj,xd,t)/at(close,xd,t))/(eo*at(adj,ed,t)/at(close,ed,t))-1
        ranked.append({'ticker':t,'name':r['name'],'snapshot_value':r.snapshot_value,'reconstructed_value':rv,'close_return':cr,'next_open_return':nr})
    z=pd.DataFrame(ranked).sort_values('reconstructed_value',ascending=False).reset_index(drop=True)
    if len(z)<8:raise RuntimeError('Too few priced candidates '+str(len(z)))
    print('RANKED\n',z.head(15).to_string(index=False),flush=True); top=z.iloc[0]; margin=float(top.reconstructed_value/z.iloc[1].reconstructed_value-1)
    print('TOP1_RESULT',rb_s,top.ticker,float(top.close_return),float(top.next_open_return),'MARGIN',margin,flush=True)
    results.append({'rebalance_date':rb_s,'snapshot_date':snap_s,'exit_date':exit_s,'top1':top.ticker,'reconstructed_top1_value':top.reconstructed_value,'close_to_close_return':top.close_return,'next_open_return':top.next_open_return,'source_accession':acc,'top1_margin_vs_2':margin})
Path('spmo-backtest/output').mkdir(parents=True,exist_ok=True); out=pd.DataFrame(results); out.to_csv('spmo-backtest/output/legacy_batch_results.csv',index=False); print('\nLEGACY_BATCH_RESULTS\n',out.to_string(index=False),flush=True)
