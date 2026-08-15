#!/usr/bin/env python3
import io, json, math, re, time
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import requests
import yfinance as yf
from bs4 import BeautifulSoup

OUT=Path('spmo-backtest/output'); OUT.mkdir(parents=True,exist_ok=True)
UA={'User-Agent':'spmo-independent-backtest louisalviss-research github.com/louisalviss/runner-3'}
CIK='0001378872'; SERIES='S000050154'
NAMES=['Invesco S&P 500 Momentum ETF','PowerShares S&P 500 Momentum Portfolio']
START=pd.Timestamp('2016-03-18'); END=pd.Timestamp('2026-08-14')


def get(url, **kw):
    last=None
    for i in range(6):
        try:
            last=requests.get(url,headers=UA,timeout=45,**kw)
            if last.status_code==200:return last
            print('HTTP',last.status_code,url)
        except Exception as e: print('GET error',e,url)
        time.sleep(1.2*(i+1))
    if last is not None:last.raise_for_status()
    raise RuntimeError('GET failed '+url)


def third_friday(y,m):
    d=date(y,m,15)
    while d.weekday()!=4:d+=timedelta(days=1)
    return pd.Timestamp(d)


def rebalances():
    return [third_friday(y,m) for y in range(2016,2027) for m in (3,9) if START<=third_friday(y,m)<=END]


def efts(q, forms, start, end):
    url='https://efts.sec.gov/LATEST/search-index'
    rows=[]; off=0
    while True:
        p={'q':q,'forms':forms,'startdt':start,'enddt':end,'ciks':CIK,'from':off}
        r=get(url,params=p).json(); hits=r.get('hits',{}).get('hits',[])
        if not hits:break
        for h in hits:
            s=h.get('_source',{}); ad=s.get('adsh') or h.get('_id','').split(':')[0]
            rows.append({'accessionNumber':ad,'form':s.get('form'),'filingDate':s.get('file_date'),
                         'reportDate':s.get('period_ending'),'file':h.get('_id','').split(':',1)[-1]})
        off+=len(hits)
        total=r.get('hits',{}).get('total',{}).get('value',0)
        if off>=total or off>=1000:break
        time.sleep(.2)
    return rows


def filing_inventory():
    rows=[]
    rows += efts(SERIES,'NPORT-P','2019-01-01','2026-08-15')
    rows += efts('"Invesco S&P 500 Momentum ETF"','NPORT-P','2019-01-01','2026-08-15')
    rows += efts('"PowerShares S&P 500 Momentum Portfolio"','N-Q,N-CSR,N-CSRS','2015-01-01','2019-12-31')
    rows += efts('"Invesco S&P 500 Momentum ETF"','N-Q,N-CSR,N-CSRS','2018-01-01','2019-12-31')
    df=pd.DataFrame(rows)
    if df.empty:raise RuntimeError('EFTS returned no filings')
    df=df.dropna(subset=['accessionNumber']).drop_duplicates('accessionNumber')
    df['reportDate']=pd.to_datetime(df['reportDate'],errors='coerce'); df['filingDate']=pd.to_datetime(df['filingDate'],errors='coerce')
    df=df.sort_values(['reportDate','filingDate'])
    df.to_csv(OUT/'efts_filings.csv',index=False)
    print('EFTS filings',len(df)); print(df[['form','reportDate','filingDate','accessionNumber']].to_string(index=False))
    return df


def submission_url(adsh):
    folder=adsh.replace('-','')
    return f'https://www.sec.gov/Archives/edgar/data/{int(CIK)}/{folder}/{adsh}.txt'


def parse_nport(txt):
    if SERIES not in txt and not any(n.lower() in txt.lower() for n in NAMES): return None
    soup=BeautifulSoup(txt,'xml'); out=[]
    for node in soup.find_all('invstOrSec'):
        def g(*tags):
            for t in tags:
                z=node.find(t)
                if z and z.get_text(strip=True):return z.get_text(' ',strip=True)
        name=g('name','nameOfIssuer'); val=g('valUSD','valueUSD','value'); bal=g('balance'); cusip=g('cusip')
        if not name or not val:continue
        try:v=float(str(val).replace(',',''))
        except:continue
        try:sh=float(str(bal).replace(',','')) if bal else np.nan
        except:sh=np.nan
        out.append({'name':name,'cusip':cusip,'shares':sh,'value':v})
    if len(out)<50:return None
    return pd.DataFrame(out)


def num(x):
    s=str(x).replace('$','').replace(',','').replace('(','-').replace(')','').strip()
    s=re.sub(r'[^0-9eE+\-.]','',s)
    try:return float(s)
    except:return np.nan


def parse_legacy(txt):
    low=txt.lower(); poss=[]
    for n in NAMES:
        p=0
        while True:
            i=low.find(n.lower(),p)
            if i<0:break
            poss.append(i); p=i+20
    if not poss:return None
    # Portfolio tables are typically near a name occurrence followed by Common Stocks/Schedule of Investments.
    best=None
    for i in poss:
        seg=txt[i:min(len(txt),i+1200000)]
        score=(seg[:20000].lower().count('common stock')*2 + seg[:20000].lower().count('schedule of investments'))
        if best is None or score>best[0]:best=(score,seg)
    seg=best[1]
    # Stop at next fund heading / page section if possible, but keep enough data for ~100 holdings.
    try:tabs=pd.read_html(io.StringIO(seg))
    except Exception:return None
    rows=[]
    for t in tabs:
        if t.empty:continue
        for _,r in t.iterrows():
            vals=[str(v).strip() for v in r.tolist() if str(v).strip().lower() not in ('nan','none','')]
            if len(vals)<3:continue
            nums=[num(v) for v in vals]; ix=[(j,x) for j,x in enumerate(nums) if pd.notna(x)]
            if len(ix)<2:continue
            text=' '.join(vals); tl=text.lower()
            if any(k in tl for k in ['total common','total investments','net assets','schedule of investments','sector breakdown','number of shares']):continue
            jv,v=ix[-1]; js,sh=ix[-2]
            names=[vals[j] for j in range(0,jv) if pd.isna(nums[j]) and vals[j] not in ('$','—','-')]
            name=' '.join(names); name=re.sub(r'\s+',' ',name).strip(' *†‡')
            if len(name)<2 or v<=0 or sh<=0:continue
            if '%' in name or re.match(r'^(common stocks?|technology|financial|industrials?|consumer|health|energy|materials?|utilities?|real estate)',name,re.I):continue
            rows.append({'name':name,'cusip':None,'shares':sh,'value':v})
    if not rows:return None
    df=pd.DataFrame(rows)
    # Dedup exact rows; table parsing can duplicate cells across multi-index columns.
    df=df.drop_duplicates(['name','shares','value'])
    # Keep plausible issuer lines; legacy filings can contain many other funds after SPMO, so stop once values turn into unrelated blocks is hard.
    # We later validate by expected constituent count and known top-1 sequence.
    if len(df)<50:return None
    return df


def choose_snapshot(df,rb):
    # Need a disclosed portfolio AFTER the rebalance, close enough that holdings still represent that rebalance.
    c=df[(df.reportDate>=rb)&(df.reportDate<=rb+pd.Timedelta(days=100))].copy()
    if c.empty:return None
    c['lag']=(c.reportDate-rb).dt.days
    # Prefer NPORT, otherwise shareholder reports. Avoid pre-rebalance snapshots.
    c['pref']=c.form.map({'NPORT-P':0,'N-CSR':1,'N-CSRS':1,'N-Q':2}).fillna(9)
    return c.sort_values(['lag','pref','filingDate']).iloc[0]


def resolve_tickers(frames):
    names=sorted(set(x for f in frames.values() for x in f.name.tolist()))
    cache={}; sess=requests.Session(); sess.headers.update({'User-Agent':'Mozilla/5.0'})
    overrides={'Alphabet Inc. Class A':'GOOGL','Alphabet Inc Class A':'GOOGL','Alphabet Inc.':'GOOGL',
               'Alphabet Inc. Class C':'GOOG','Facebook, Inc. Class A':'META','Meta Platforms, Inc.':'META',
               'Berkshire Hathaway Inc. Class B':'BRK-B','Berkshire Hathaway, Inc. Class B':'BRK-B'}
    for k,n in enumerate(names):
        if n in overrides:cache[n]=overrides[n];continue
        q=re.sub(r'\b(Common Stock|Class [A-Z]|Inc\.?|Corp\.?|Corporation|PLC|Ltd\.?)\b',' ',n,flags=re.I)
        q=re.sub(r'\s+',' ',q).strip()
        try:
            d=sess.get('https://query1.finance.yahoo.com/v1/finance/search',params={'q':q,'quotesCount':8,'newsCount':0},timeout=15).json()
            qs=[z for z in d.get('quotes',[]) if z.get('quoteType')=='EQUITY' and z.get('exchange') in ('NMS','NYQ','NGM','NCM','ASE','PCX')]
            if qs:cache[n]=qs[0].get('symbol')
        except Exception:pass
        if k%50==0:print('ticker resolve',k,'/',len(names))
        time.sleep(.04)
    Path(OUT/'ticker_map.json').write_text(json.dumps(cache,indent=2,ensure_ascii=False))
    for rb,f in frames.items():f['ticker']=f.name.map(cache)
    return cache


def fdf(data,field):
    if not isinstance(data.columns,pd.MultiIndex):return data[[field]].rename(columns={field:data.attrs.get('ticker','')})
    if field not in data.columns.get_level_values(0):return pd.DataFrame(index=data.index)
    x=data[field]; return x.to_frame() if isinstance(x,pd.Series) else x


def px_before(df,d,t):
    if t not in df.columns:return np.nan
    s=df[t].dropna(); s=s[s.index<=d]
    return float(s.iloc[-1]) if len(s) else np.nan


def px_after(df,d,t):
    if t not in df.columns:return (None,np.nan)
    s=df[t].dropna(); s=s[s.index>=d]
    return (s.index[0],float(s.iloc[0])) if len(s) else (None,np.nan)


def rank_at_rebalance(f,rb,snap,rawclose,splits):
    z=f.copy(); vals=[]
    for _,r in z.iterrows():
        t=r.ticker
        if not t or t not in rawclose.columns:vals.append(np.nan);continue
        # Snapshot value rewound by raw-price ratio. Correct explicit splits between rb and snapshot.
        ps=px_before(rawclose,snap,t); pr=px_before(rawclose,rb,t)
        if not np.isfinite(ps) or not np.isfinite(pr) or ps<=0:vals.append(np.nan);continue
        sf=1.0
        if t in splits.columns:
            ss=splits[t].fillna(0); ss=ss[(ss.index>rb)&(ss.index<=snap)&(ss!=0)]
            for a in ss:sf*=float(a)
        vals.append(float(r.value)*(pr/ps)/sf)
    z['rb_value']=vals; z=z[z.rb_value.notna() & (z.rb_value>0)]
    z=z.sort_values('rb_value',ascending=False).reset_index(drop=True); z['rank']=np.arange(1,len(z)+1); z['weight']=z.rb_value/z.rb_value.sum()
    return z


def curve(tops,rb,ex,adjc,adjo,mode,weight_mode):
    tops=tops[tops.ticker.notna()].copy()
    if tops.empty:return None
    if weight_mode=='equal':w=np.repeat(1/len(tops),len(tops))
    else:w=(tops.weight/tops.weight.sum()).to_numpy()
    ser=[]; wg=[]
    for (_,r),wi in zip(tops.iterrows(),w):
        t=r.ticker
        if t not in adjc.columns:continue
        if mode=='close':
            ep=px_before(adjc,rb,t); start=rb; end=ex; terminal_open=False
        else:
            d,ep=px_after(adjo,rb+pd.Timedelta(days=1),t); start=d; end=ex; terminal_open=True
        if start is None or not np.isfinite(ep) or ep<=0:continue
        idx=adjc.index[(adjc.index>=start)&(adjc.index<=end)]
        s=adjc[t].reindex(idx).ffill()/ep
        if terminal_open:
            dx,p=px_after(adjo,ex+pd.Timedelta(days=1),t)
            if dx is not None and np.isfinite(p):
                s=s[s.index<dx]; s.loc[dx]=p/ep
        ser.append(s.rename(t));wg.append(wi)
    if not ser:return None
    mat=pd.concat(ser,axis=1).ffill(); wg=np.array(wg);wg=wg/wg.sum()
    return mat.mul(wg,axis=1).sum(axis=1)


def stitch(cs):
    out=None;lvl=1.0
    for c in cs:
        c=c.dropna();
        if len(c)<2:continue
        x=c/c.iloc[0]*lvl
        if out is not None and x.index[0] in out.index:x=x.iloc[1:]
        out=x if out is None else pd.concat([out,x]);lvl=float(out.iloc[-1])
    return out


def metrics(eq):
    r=eq.pct_change().dropna(); yrs=(eq.index[-1]-eq.index[0]).days/365.2425
    dd=eq/eq.cummax()-1
    return {'start':str(eq.index[0].date()),'end':str(eq.index[-1].date()),'multiple':float(eq.iloc[-1]/eq.iloc[0]),
            'cagr':float((eq.iloc[-1]/eq.iloc[0])**(1/yrs)-1),'vol':float(r.std()*np.sqrt(252)),
            'sharpe_rf0':float(r.mean()/r.std()*np.sqrt(252)),'max_dd':float(dd.min())}


def main():
    rbs=rebalances(); print('REBALANCES',len(rbs),[str(x.date()) for x in rbs])
    inv=filing_inventory(); frames={}; snaps=[]; errors=[]
    for rb in rbs:
        row=choose_snapshot(inv,rb)
        if row is None:errors.append({'rb':str(rb.date()),'error':'no post-rebalance filing <=100d'});continue
        u=submission_url(row.accessionNumber)
        try:
            txt=get(u).text
            f=parse_nport(txt) if row.form=='NPORT-P' else parse_legacy(txt)
            if f is None:raise RuntimeError('parse failed/too few holdings')
            frames[rb]=f;snaps.append({'rb':str(rb.date()),'reportDate':str(row.reportDate.date()),'form':row.form,'accession':row.accessionNumber,'holdings':len(f),'url':u})
            print('SNAP',rb.date(),row.form,row.reportDate.date(),'holdings',len(f))
        except Exception as e:errors.append({'rb':str(rb.date()),'accession':row.accessionNumber,'error':repr(e)})
    pd.DataFrame(snaps).to_csv(OUT/'snapshots.csv',index=False);Path(OUT/'errors.json').write_text(json.dumps(errors,indent=2))
    print('USABLE',len(frames),'ERRORS',len(errors));print(json.dumps(errors,indent=2))
    if len(frames)<10:raise RuntimeError('too few usable snapshots')
    resolve_tickers(frames)
    tickers=sorted(set(t for f in frames.values() for t in f.ticker.dropna()))
    print('PRICE TICKERS',len(tickers))
    d=yf.download(tickers,start='2016-03-01',end='2026-08-25',auto_adjust=False,actions=True,threads=True,progress=False)
    rc=fdf(d,'Close'); ac=fdf(d,'Adj Close'); op=fdf(d,'Open'); sp=fdf(d,'Stock Splits')
    if ac.empty:
        a=yf.download(tickers,start='2016-03-01',end='2026-08-25',auto_adjust=True,actions=False,threads=True,progress=False);ac=fdf(a,'Close');ao=fdf(a,'Open')
    else:ao=op*(ac/rc)
    ranked={}; detail=[]
    smap={pd.Timestamp(x['rb']):pd.Timestamp(x['reportDate']) for x in snaps}
    for rb,f in frames.items():
        z=rank_at_rebalance(f,rb,smap[rb],rc,sp);ranked[rb]=z
        zz=z.copy();zz.insert(0,'rebalance',str(rb.date()));detail.append(zz)
    pd.concat(detail,ignore_index=True).to_csv(OUT/'ranked_holdings.csv',index=False)
    # Known-top1 sanity table is a gating diagnostic, not a forced assumption.
    tops=pd.DataFrame([{'rb':str(rb.date()),'top1':z.iloc[0].ticker if len(z) else None,'issuer':z.iloc[0]['name'] if len(z) else None} for rb,z in ranked.items()])
    tops.to_csv(OUT/'top1_sequence.csv',index=False);print('TOP1\n',tops.to_string(index=False))
    rows=[]; allperiod=[]
    for n in (1,5,10,15,20):
      for mode in ('close','next_open'):
       for wm in ('equal','spmo_weight'):
        cs=[]; prs=[]
        for i,rb in enumerate(rbs):
            if rb not in ranked:continue
            ex=rbs[i+1] if i+1<len(rbs) else END
            c=curve(ranked[rb].head(n),rb,ex,ac,ao,mode,wm)
            if c is None:continue
            cs.append(c);prs.append({'n':n,'mode':mode,'weight_mode':wm,'rb':str(rb.date()),'exit':str(ex.date()),'multiple':float(c.iloc[-1]/c.iloc[0]),'tickers':','.join(ranked[rb].head(n).ticker.dropna().tolist())})
        eq=stitch(cs)
        if eq is None or len(eq)<100:continue
        m=metrics(eq);m.update({'n':n,'mode':mode,'weight_mode':wm,'periods':len(cs)});rows.append(m);allperiod+=prs
    pd.DataFrame(rows).to_csv(OUT/'results.csv',index=False);pd.DataFrame(allperiod).to_csv(OUT/'periods.csv',index=False)
    Path(OUT/'summary.json').write_text(json.dumps({'snapshots':snaps,'errors':errors,'results':rows},indent=2))
    print('RESULTS\n',pd.DataFrame(rows).to_string(index=False))

if __name__=='__main__':main()
