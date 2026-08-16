#!/usr/bin/env python3
import argparse,re,time
from pathlib import Path
import requests,pandas as pd,yfinance as yf
from bs4 import BeautifulSoup,NavigableString

H={'User-Agent':'SPMO independent research contact@example.com','Accept-Encoding':'gzip, deflate'}
ALIASES=[
 ('Microsoft','MSFT'),('Amazon.com','AMZN'),('Facebook','META'),('Meta Platforms','META'),('General Electric','GE'),('AT&T','T'),('Verizon','VZ'),('McDonald','MCD'),('Home Depot','HD'),('Philip Morris','PM'),('Visa','V'),('Altria','MO'),('Starbucks','SBUX'),('NIKE','NKE'),('Accenture','ACN'),('Lockheed Martin','LMT'),('Progressive','PGR'),('Apple','AAPL'),('Mastercard','MA'),('Adobe','ADBE'),('Activision Blizzard','ATVI'),('Broadcom','AVGO'),('NVIDIA','NVDA'),('Netflix','NFLX'),('PayPal','PYPL'),('Comcast','CMCSA'),('Charter Communications','CHTR'),('Intuit','INTU'),('QUALCOMM','QCOM'),('Texas Instruments','TXN'),('Applied Materials','AMAT'),('Lam Research','LRCX'),('Micron Technology','MU'),('Cisco Systems','CSCO'),('Oracle','ORCL'),('Salesforce','CRM'),('Costco','COST'),('Walmart','WMT'),('Wal-Mart','WMT'),('Target','TGT'),('PepsiCo','PEP'),('Coca-Cola','KO'),('Procter & Gamble','PG'),('UnitedHealth','UNH'),('Eli Lilly','LLY'),('Johnson & Johnson','JNJ'),('Merck','MRK'),('AbbVie','ABBV'),('Pfizer','PFE'),('JPMorgan','JPM'),('Bank of America','BAC'),('Goldman Sachs','GS'),('Morgan Stanley','MS'),('Wells Fargo','WFC'),('Berkshire Hathaway','BRK-B'),('BlackRock','BLK'),('CME Group','CME'),('Intercontinental Exchange','ICE'),('S&P Global','SPGI'),('Equinix','EQIX'),('American Tower','AMT'),('NextEra','NEE'),('American Water Works','AWK'),('Exxon Mobil','XOM'),('Chevron','CVX'),('ConocoPhillips','COP'),('3M','MMM'),('Union Pacific','UNP'),('Raytheon','RTX'),('Northrop Grumman','NOC'),('Cintas','CTAS'),('Equifax','EFX'),('Roper Technologies','ROP'),('Snap-on','SNA'),('Republic Services','RSG'),('Dollar General','DG'),('Dollar Tree','DLTR'),('AutoZone','AZO'),('O’Reilly','ORLY'),("O'Reilly",'ORLY'),('Ross Stores','ROST'),('Darden Restaurants','DRI'),('Carnival','CCL'),('D.R. Horton','DHI'),('Hasbro','HAS'),('Expedia','EXPE'),('Interpublic','IPG'),('L Brands','BBWI'),('Mondelez','MDLZ'),('Kraft Heinz','KHC'),('Kroger','KR'),('Kimberly-Clark','KMB'),('General Mills','GIS'),('Hormel Foods','HRL'),('Kellogg','K'),('Estée Lauder','EL'),('Estee Lauder','EL'),('Constellation Brands','STZ'),('Boston Scientific','BSX'),('Cigna','CI'),('Edwards Lifesciences','EW'),('Stryker','SYK'),('Public Storage','PSA'),('American International Group','AIG'),('Nasdaq','NDAQ'),('Reynolds American','RAI'),('Time Warner Cable','TWC'),('Alphabet','GOOG')]

def fetch(url):
    for i in range(4):
        try:
            r=requests.get(url,headers=H,timeout=180)
            print('FETCH',r.status_code,len(r.content),url,flush=True)
            if r.status_code==200 and len(r.content)>10000:return r.text
        except Exception as e: print('FETCH_ERR',repr(e),flush=True)
        time.sleep(2+i*2)
    raise RuntimeError('fetch failed')

def flatten(html):
    soup=BeautifulSoup(html,'lxml')
    for tr in list(soup.find_all('tr')):
        cells=[' '.join(c.stripped_strings) for c in tr.find_all(['td','th'],recursive=False)]
        if cells: tr.replace_with(NavigableString('\n'+'\t'.join(cells)+'\n'))
    return soup.get_text('\n').replace('\xa0',' ')

def exact_spmo_section(t,snapshot):
    date=pd.Timestamp(snapshot)
    date_forms=[date.strftime('%B %d, %Y').replace(' 0',' '),date.strftime('%B %d, %Y')]
    pat=re.compile(r'PowerShares\s+S&P\s*500(?:\s*®)?\s+Momentum\s+Portfolio\s*\(SPMO\)',re.I)
    cand=[]
    for m in pat.finditer(t):
        pre=t[max(0,m.start()-1000):m.start()]
        post=t[m.start():min(len(t),m.start()+35000)]
        score=0
        if any(x in post[:2500] for x in date_forms): score+=100
        if re.search(r'Schedule of Investments',pre[-1200:]+post[:1000],re.I): score+=100
        if re.search(r'Number of\s*Shares',post[:12000],re.I): score+=100
        if 'Common Stocks' in post[:12000]: score+=80
        if 'Total Investments' in post[:35000]: score+=50
        rows=sum(1 for ln in post[:25000].splitlines() if '\t' in ln and re.match(r'^\s*[\d,]+\t',ln))
        score+=min(rows,120)
        cand.append((score,rows,m.start(),m.group(0),post[:500].replace('\n',' ')))
    if not cand: raise RuntimeError('No exact SPMO title')
    cand.sort(reverse=True)
    print('SECTION_CANDIDATES',cand[:8],flush=True)
    score,rows,start,_,_=cand[0]
    if score<250 or rows<20: raise RuntimeError(f'No credible SPMO schedule candidate score={score} rows={rows}')

    # Some annual reports split the SPMO Schedule of Investments over two pages.
    # If the best explicit SPMO title is the '(continued)' page, recover the prior
    # page from its nearest preceding 'Number of Shares' header. We still terminate
    # at this SPMO schedule's own Net Assets line, so adjacent Trust II funds cannot leak in.
    head=t[start:start+700]
    if re.search(r'\(continued\)',head,re.I):
        lookback=max(0,start-20000)
        prior=t[lookback:start]
        headers=list(re.finditer(r'Number of\s*Shares',prior,re.I))
        if headers:
            recovered=lookback+headers[-1].start()
            prior_rows=sum(1 for ln in t[recovered:start].splitlines() if '\t' in ln and re.match(r'^\s*[\d,]+\t',ln))
            print('CONTINUATION_RECOVERY',start,'->',recovered,'prior_rows',prior_rows,flush=True)
            if prior_rows>=20:
                start=recovered

    m_end=re.search(r'Net Assets\s*[—-]\s*100\.0%[^\n]*',t[start:start+80000],re.I)
    if not m_end: raise RuntimeError('No SPMO Net Assets boundary')
    end=start+m_end.end()
    z=t[start:end]
    print('SECTION_SELECTED',start,end,'chars',len(z),'rows',rows,flush=True)
    return z

def parse_holdings(z):
    out=[]
    for line in z.splitlines():
        parts=[' '.join(x.strip().split()) for x in line.split('\t')]
        parts=[x for x in parts if x not in ('','$','—','-')]
        if len(parts)<3: continue
        nums=[]
        for i,x in enumerate(parts):
            y=x.replace('$','').replace(',','').replace('(','').replace(')','').strip()
            if y.isdigit(): nums.append(i)
        if len(nums)<2: continue
        i0,i1=nums[0],nums[-1]
        if i1<=i0: continue
        try:
            shares=int(re.sub(r'\D','',parts[i0])); value=int(re.sub(r'\D','',parts[i1]))
        except: continue
        names=[x for x in parts[i0+1:i1] if re.search(r'[A-Za-z]',x)]
        if not names or shares<=0 or value<=0: continue
        name=max(names,key=len).strip('*_ ')
        low=name.lower()
        if any(q in low for q in ['common stocks','total investments','net assets','other assets','number of shares','sector breakdown']):continue
        if '%' in name and not re.search(r'Inc|Corp|Co\.|PLC|Ltd|Class|REIT',name,re.I):continue
        out.append((shares,name,value))
    d=pd.DataFrame(out,columns=['shares','name','snapshot_value']).drop_duplicates()
    d=d.sort_values('snapshot_value',ascending=False).reset_index(drop=True)
    print('HOLDINGS_COUNT',len(d),flush=True)
    print('TOP_SNAPSHOT\n'+d.head(45).to_string(index=False),flush=True)
    if len(d)<60: raise RuntimeError(f'Too few SPMO holdings parsed: {len(d)}')
    return d

def resolve(name):
    n=re.sub(r'\s*\([a-z](?:,[a-z])*\)\s*$','',name,flags=re.I).strip()
    if 'Alphabet' in n:
        if 'Class A' in n:return 'GOOGL'
        if 'Class C' in n:return 'GOOG'
    for k,v in ALIASES:
        if k.lower() in n.lower(): return v
    try:
        for q in yf.Search(n,max_results=6,news_count=0).quotes:
            if q.get('quoteType')=='EQUITY' and q.get('symbol'):return q['symbol'].replace('.','-')
    except Exception as e:print('SEARCH_FAIL',n,repr(e),flush=True)
    return None

def fld(d,n,tickers):
    x=d[n]; return x.to_frame(tickers[0]) if isinstance(x,pd.Series) else x
def at(f,d,t):
    s=f[t].dropna();s=s[s.index<=d]
    if s.empty:raise RuntimeError(f'No {t} price <= {d}')
    return float(s.iloc[-1])
def after(f,d,t):
    s=f[t].dropna();s=s[s.index>=d]
    return (s.index[0],float(s.iloc[0])) if len(s) else None

def main():
    ap=argparse.ArgumentParser()
    for a in ['rb','snapshot','exit','accession','url']:ap.add_argument('--'+a,required=True)
    a=ap.parse_args()
    z=exact_spmo_section(flatten(fetch(a.url)),a.snapshot)
    holdings=parse_holdings(z)
    h=holdings.head(50).copy();h['ticker']=h['name'].map(resolve)
    print('RESOLVED_TOP50\n'+h[['ticker','name','snapshot_value']].to_string(index=False),flush=True)
    h=h.dropna(subset=['ticker']).drop_duplicates('ticker')
    tick=h.ticker.tolist()
    if len(tick)<25:raise RuntimeError(f'Too few resolved candidates {len(tick)}')
    rb=pd.Timestamp(a.rb);snap=pd.Timestamp(a.snapshot);ex=pd.Timestamp(a.exit)
    d=yf.download(tick,start=(rb-pd.Timedelta(days=7)).strftime('%Y-%m-%d'),end=(ex+pd.Timedelta(days=7)).strftime('%Y-%m-%d'),auto_adjust=False,actions=True,threads=False,progress=False)
    close,adj,op=fld(d,'Close',tick),fld(d,'Adj Close',tick),fld(d,'Open',tick)
    rr=[]
    for _,r in h.iterrows():
        t=r.ticker
        if t not in close.columns or close[t].dropna().empty:continue
        try:
            rv=r.snapshot_value*at(close,rb,t)/at(close,snap,t)
            cr=at(adj,ex,t)/at(adj,rb,t)-1
        except Exception as e:print('PRICE_FAIL',t,repr(e),flush=True);continue
        en=after(op,rb+pd.Timedelta(days=1),t);xo=after(op,ex+pd.Timedelta(days=1),t);nr=float('nan')
        if en and xo:
            ed,eo=en;xd,xv=xo
            nr=(xv*at(adj,xd,t)/at(close,xd,t))/(eo*at(adj,ed,t)/at(close,ed,t))-1
        rr.append((t,r['name'],int(r.snapshot_value),rv,cr,nr))
    ranked=pd.DataFrame(rr,columns=['ticker','name','snapshot_value','reconstructed_value','close_return','next_open_return']).sort_values('reconstructed_value',ascending=False)
    print('RANKED\n'+ranked.head(20).to_string(index=False),flush=True)
    if len(ranked)<2:raise RuntimeError('Too few priced candidates')
    top=ranked.iloc[0];margin=float(top.reconstructed_value/ranked.iloc[1].reconstructed_value-1)
    result=pd.DataFrame([{'rebalance_date':a.rb,'snapshot_date':a.snapshot,'exit_date':a.exit,'top1':top.ticker,'reconstructed_top1_value':float(top.reconstructed_value),'close_to_close_return':float(top.close_return),'next_open_return':float(top.next_open_return),'candidate_scope':'exact SPMO schedule direct SEC; top50 snapshot holdings','source_accession':a.accession,'top1_margin_vs_2':margin,'parsed_holdings':len(holdings)}])
    out=Path('spmo-backtest/output');out.mkdir(parents=True,exist_ok=True)
    fn=out/f"legacy_exact_{a.rb}.csv";result.to_csv(fn,index=False)
    print('EXACT_RESULT\n'+result.to_string(index=False),flush=True)
if __name__=='__main__':main()
