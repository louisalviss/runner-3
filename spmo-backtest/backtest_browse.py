#!/usr/bin/env python3
import sys, re, time, json, difflib
import urllib.parse, urllib.request
from pathlib import Path
import pandas as pd
import numpy as np
import yfinance as yf
from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).resolve().parent))
import backtest_archive as b

SEC_UA='Louis research contact@example.com'
_series_cache={}

class UResp:
    def __init__(self, content, status=200):
        self.content=content; self.status_code=status
        self.text=content.decode('utf-8','replace')
    def raise_for_status(self):
        if self.status_code>=400: raise RuntimeError(f'HTTP {self.status_code}')
    def close(self): pass

def urllib_get(url, *, stream=False, headers=None, tries=6, timeout=60):
    h={'User-Agent':SEC_UA}
    if headers: h.update(headers)
    last=None
    for i in range(tries):
        try:
            req=urllib.request.Request(url,headers=h)
            with urllib.request.urlopen(req,timeout=timeout) as resp:
                data=resp.read(); status=resp.status
            return UResp(data,status)
        except Exception as e:
            last=e; print('URLLIB GETERR',repr(e),url)
            time.sleep(0.8*(i+1))
    raise last

def complete_url_folder(fn):
    acc=Path(fn).stem; folder=acc.replace('-','')
    return f'https://www.sec.gov/Archives/edgar/data/{b.CIK}/{folder}/{acc}.txt'

def parse_atom_entries(content, form):
    soup=BeautifulSoup(content,'xml'); out=[]
    for e in soup.find_all('entry'):
        fd=e.find('filing-date'); ft=e.find('filing-type'); acc=e.find('accession-number')
        if not fd or not acc: continue
        out.append({'cik':b.CIK,'company':'Invesco Exchange-Traded Fund Trust II',
                    'form':ft.get_text(strip=True) if ft else form,
                    'filed':pd.Timestamp(fd.get_text(strip=True)),
                    'filename':f'edgar/data/{b.CIK}/{acc.get_text(strip=True)}.txt'})
    return out

def series_rows(form):
    if form in _series_cache: return _series_cache[form]
    params={'action':'getcompany','CIK':b.SERIES,'type':form,'owner':'exclude','count':'100','output':'atom'}
    url='https://www.sec.gov/cgi-bin/browse-edgar?'+urllib.parse.urlencode(params)
    rows=parse_atom_entries(urllib_get(url,timeout=45).content,form)
    df=pd.DataFrame(rows)
    if len(df): df=df.drop_duplicates(['form','filed','filename']).sort_values('filed')
    print('SERIES',form,'inventory',len(df))
    _series_cache[form]=df
    return df

def master_rows_from_series(year,q):
    qstart=pd.Timestamp(year=year,month=3*(q-1)+1,day=1)
    # Legacy SPMO shareholder reports shifted filing cadence in 2019 (Apr-30 report filed in May,
    # while earlier years were filed in July). Include the preceding 100 days; the legacy parser
    # still requires the portfolio report date itself to be after the rebalance and <=120d later.
    start=qstart-pd.Timedelta(days=100)
    end=qstart+pd.offsets.QuarterEnd(startingMonth=3)
    parts=[]
    for form in ('NPORT-P','N-CSR','N-CSRS','N-Q'):
        df=series_rows(form)
        if len(df): parts.append(df[(df.filed>=start)&(df.filed<=end)])
    if not parts: return []
    df=pd.concat(parts,ignore_index=True).drop_duplicates(['form','filed','filename']).sort_values(['filed','form'])
    print('SERIES WINDOW',year,q,start.date(),end.date(),'candidates',len(df),'forms',df.groupby('form').size().to_dict() if len(df) else {})
    return df.to_dict('records')

# Modern N-PORT: retain SEC ticker when present so CUSIP/name heuristics are only fallbacks.
def parse_nport_xml_fixed(xml):
    soup=BeautifulSoup(xml,'xml'); sid=soup.find('seriesId')
    if not sid or sid.get_text(strip=True)!=b.SERIES: return None
    rd=soup.find('repPdDate')
    if not rd: return None
    report=pd.Timestamp(rd.get_text(strip=True)); out=[]
    for n in soup.find_all('invstOrSec'):
        def text(tag):
            z=n.find(tag); return z.get_text(' ',strip=True) if z else None
        name=text('name'); val=text('valUSD'); sh=text('balance'); cusip=text('cusip')
        tk=None; tnode=n.find('ticker')
        if tnode:
            tk=tnode.get('value') or tnode.get_text(strip=True) or None
        if not name or not val: continue
        try: v=float(val.replace(',',''))
        except: continue
        try: s=float(sh.replace(',','')) if sh else np.nan
        except: s=np.nan
        if v>0: out.append({'name':name,'cusip':cusip,'shares':s,'value':v,'sec_ticker':tk})
    if len(out)<50: return None
    return report,pd.DataFrame(out)

def norm_name(s):
    s=str(s).upper().replace('&',' AND ')
    s=re.sub(r'\b(THE|INCORPORATED|INC|CORPORATION|CORP|COMPANY|CO|PLC|LTD|LIMITED|HOLDINGS|HOLDING|CLASS [A-Z]|COMMON STOCK|GROUP)\b',' ',s)
    s=re.sub(r'[^A-Z0-9 ]',' ',s); return re.sub(r'\s+',' ',s).strip()

def name_score(a,c):
    a=norm_name(a); c=norm_name(c)
    if not a or not c: return 0
    ta=set(a.split()); tc=set(c.split())
    jac=len(ta&tc)/max(1,len(ta|tc))
    seq=difflib.SequenceMatcher(None,a,c).ratio()
    return max(jac,seq)

def yahoo_candidates(q):
    try:
        r=b.S.get('https://query1.finance.yahoo.com/v1/finance/search',params={'q':q,'quotesCount':10,'newsCount':0},headers={'User-Agent':'Mozilla/5.0'},timeout=15)
        if r.status_code!=200: return []
        return [z for z in r.json().get('quotes',[]) if z.get('quoteType')=='EQUITY' and z.get('symbol')]
    except Exception: return []

def resolve_symbol(name,cusip=None,sec_ticker=None):
    if sec_ticker and str(sec_ticker).strip() not in ('','nan','None'):
        return str(sec_ticker).strip().replace('.','-')
    overrides={
      'General Electric Co.':'GE','TJX Cos., Inc. (The)':'TJX','Williams Cos., Inc. (The)':'WMB',
      'Interpublic Group of Cos., Inc. (The)':'IPG','Amazon.com, Inc.':'AMZN','Apple, Inc.':'AAPL','Apple Inc.':'AAPL',
      'Microsoft Corp.':'MSFT','Microsoft Corporation':'MSFT','Facebook, Inc., Class A':'META','Facebook, Inc. Class A':'META',
      'Meta Platforms, Inc., Class A':'META','Meta Platforms, Inc.':'META','Alphabet, Inc., Class A':'GOOGL',
      'Alphabet Inc. Class A':'GOOGL','Alphabet, Inc. Class C':'GOOG','Alphabet, Inc., Class C':'GOOG',
      'Google, Inc., Class A':'GOOGL','Google Inc., Class A':'GOOGL','Berkshire Hathaway, Inc., Class B':'BRK-B',
      'Berkshire Hathaway Inc. Class B':'BRK-B','NVIDIA Corp.':'NVDA','NVIDIA Corporation':'NVDA','Broadcom Inc.':'AVGO','Broadcom, Inc.':'AVGO'
    }
    if name in overrides: return overrides[name]
    if cusip and str(cusip) not in ('nan','None',''):
        for z in yahoo_candidates(str(cusip)):
            sym=z.get('symbol','').replace('.','-')
            if sym and z.get('exchange') in ('NMS','NYQ','NGM','NCM','ASE','PCX'): return sym
    best=(0,None)
    for z in yahoo_candidates(name):
        if z.get('exchange') not in ('NMS','NYQ','NGM','NCM','ASE','PCX'): continue
        sc=max(name_score(name,z.get('longname','')),name_score(name,z.get('shortname','')))
        if sc>best[0]: best=(sc,z.get('symbol','').replace('.','-'))
    return best[1] if best[0]>=0.55 else None

def resolve_all_fixed(frames):
    keys={}
    for f in frames.values():
        for _,r in f.iterrows():
            keys[(r.get('name'),r.get('cusip'),r.get('sec_ticker'))]=None
    print('RESOLVE',len(keys),'unique issuer records')
    for i,k in enumerate(list(keys)):
        keys[k]=resolve_symbol(*k)
        if i%50==0: print('  resolved',i,'/',len(keys))
        time.sleep(.025)
    Path(b.OUT/'ticker_map.json').write_text(json.dumps({f'{k[0]}|{k[1]}|{k[2]}':v for k,v in keys.items()},indent=2,ensure_ascii=False))
    for rb,f in frames.items():
        z=f.copy(); z['ticker']=[keys[(r.get('name'),r.get('cusip'),r.get('sec_ticker'))] for _,r in z.iterrows()]
        frames[rb]=z
    return keys

def rank_frames_fixed(frames,meta):
    tickers=sorted(set(t for f in frames.values() for t in f.ticker.dropna()))
    print('DOWNLOAD PRICE',len(tickers),'tickers')
    raw=yf.download(tickers,start='2016-03-01',end='2026-08-25',auto_adjust=False,actions=True,threads=True,progress=False)
    rc=b.field_df(raw,'Close'); ac=b.field_df(raw,'Adj Close'); ro=b.field_df(raw,'Open')
    if ac.empty:
        adj=yf.download(tickers,start='2016-03-01',end='2026-08-25',auto_adjust=True,threads=True,progress=False)
        ac=b.field_df(adj,'Close'); ao=b.field_df(adj,'Open')
    else:
        ao=ro*(ac/rc)
    md={pd.Timestamp(x['rb']):pd.Timestamp(x['reportDate']) for x in meta}
    ranked={}; allz=[]
    for rb,f in frames.items():
        snap=md[rb]; z=f.copy(); vals=[]
        for _,r in z.iterrows():
            t=r.ticker
            if not t or t not in rc.columns: vals.append(np.nan); continue
            ps=b.before(rc,snap,t); pr=b.before(rc,rb,t)
            # Rewind disclosed portfolio value by the Yahoo price ratio. This is invariant to
            # Yahoo's backward split adjustment, unlike multiplying SEC pre-split share counts.
            val=float(r.value)*(pr/ps) if np.isfinite(ps) and ps>0 and np.isfinite(pr) else np.nan
            vals.append(val)
        z['rb_value']=vals
        z=z[z.rb_value.notna() & (z.rb_value>0)].sort_values('rb_value',ascending=False).reset_index(drop=True)
        z['rank']=np.arange(1,len(z)+1); z['weight']=z.rb_value/z.rb_value.sum(); ranked[rb]=z
        zz=z.copy(); zz.insert(0,'rebalance',str(rb.date())); zz.insert(1,'snapshot',str(snap.date())); allz.append(zz)
        print('RANK',rb.date(),'resolved',len(z),'top1',z.iloc[0].ticker if len(z) else None,z.iloc[0]['name'] if len(z) else None)
    pd.concat(allz,ignore_index=True).to_csv(b.OUT/'ranked_holdings.csv',index=False)
    return ranked,ac,ao

_orig_build=b.build_snapshots
def build_snapshots_strict(rbs):
    frames,meta,errors=_orig_build(rbs)
    if len(frames)!=len(rbs):
        raise RuntimeError(f'Strict gate: only {len(frames)}/{len(rbs)} rebalance snapshots; errors={errors}')
    return frames,meta,errors

b.get=urllib_get
b.complete_url=complete_url_folder
b.master_rows=master_rows_from_series
b.parse_nport_xml=parse_nport_xml_fixed
b.resolve_all=resolve_all_fixed
b.rank_frames=rank_frames_fixed
b.build_snapshots=build_snapshots_strict
b.main()
