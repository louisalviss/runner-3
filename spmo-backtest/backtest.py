#!/usr/bin/env python3
import io, json, math, os, re, sys, time
from datetime import date, datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import requests
import yfinance as yf
from bs4 import BeautifulSoup
from dateutil.relativedelta import relativedelta

OUT = Path('spmo-backtest/output')
OUT.mkdir(parents=True, exist_ok=True)
UA = {'User-Agent': 'SPMO independent research louisalviss github runner contact@example.com'}
CIK = '0001378872'
SERIES = 'S000050154'
FUND_NAMES = ['Invesco S&P 500 Momentum ETF', 'PowerShares S&P 500 Momentum Portfolio']
START = pd.Timestamp('2016-03-18')
END = pd.Timestamp('2026-08-14')


def req(url, **kwargs):
    for i in range(5):
        r = requests.get(url, headers=UA, timeout=60, **kwargs)
        if r.status_code == 200:
            return r
        if r.status_code in (403, 429):
            time.sleep(1.5 * (i + 1)); continue
        r.raise_for_status()
    r.raise_for_status()


def third_friday(year, month):
    d = date(year, month, 15)
    while d.weekday() != 4:
        d += timedelta(days=1)
    return pd.Timestamp(d)


def rebalance_dates():
    ds=[]
    for y in range(2016, 2027):
        for m in (3,9):
            d=third_friday(y,m)
            if START <= d <= END:
                ds.append(d)
    return ds


def load_submissions():
    root=req(f'https://data.sec.gov/submissions/CIK{CIK}.json').json()
    blocks=[root['filings']['recent']]
    for f in root['filings'].get('files',[]):
        u='https://data.sec.gov/submissions/'+f['name']
        blocks.append(req(u).json())
        time.sleep(0.11)
    rows=[]
    for b in blocks:
        if isinstance(b, dict) and 'accessionNumber' in b:
            n=len(b['accessionNumber'])
            for i in range(n):
                rows.append({k:(v[i] if isinstance(v,list) and i<len(v) else None) for k,v in b.items()})
    df=pd.DataFrame(rows).drop_duplicates('accessionNumber')
    df['reportDate']=pd.to_datetime(df['reportDate'], errors='coerce')
    df['filingDate']=pd.to_datetime(df['filingDate'], errors='coerce')
    return df


def filing_url(row):
    acc=row['accessionNumber'].replace('-','')
    doc=row['primaryDocument']
    return f'https://www.sec.gov/Archives/edgar/data/{int(CIK)}/{acc}/{doc}'


def parse_nport(row):
    url=filing_url(row)
    txt=req(url).text
    if SERIES not in txt and not any(n.lower() in txt.lower() for n in FUND_NAMES):
        return None
    soup=BeautifulSoup(txt, 'xml')
    holdings=[]
    # Modern N-PORT XML uses invstOrSec nodes.
    for node in soup.find_all(['invstOrSec','invstOrSecs']):
        if node.name == 'invstOrSecs':
            continue
        def gt(tags):
            for t in tags:
                z=node.find(t)
                if z and z.get_text(strip=True): return z.get_text(' ',strip=True)
            return None
        name=gt(['name','nameOfIssuer'])
        val=gt(['valUSD','valueUSD','value'])
        bal=gt(['balance'])
        ticker=gt(['ticker'])
        cusip=gt(['cusip'])
        asset=gt(['assetCat'])
        if name and val:
            try: val=float(str(val).replace(',',''))
            except: continue
            try: bal=float(str(bal).replace(',','')) if bal else np.nan
            except: bal=np.nan
            holdings.append(dict(name=name,ticker=ticker,cusip=cusip,value=val,shares=bal,asset=asset))
    # Fallback: HTML version has rows but XML parser may miss namespaces.
    if len(holdings)<50:
        hs=BeautifulSoup(txt,'html.parser')
        text=hs.get_text(' ',strip=True)
        raise RuntimeError(f'NPORT parse too small ({len(holdings)}) for {url}; text head={text[:300]}')
    return pd.DataFrame(holdings), url


def clean_num(x):
    s=str(x).replace('$','').replace(',','').replace('(','-').replace(')','').strip()
    s=re.sub(r'[^0-9eE+\-.]','',s)
    if not s or s in ('-','.'): return np.nan
    try: return float(s)
    except: return np.nan


def parse_old_filing(row):
    url=filing_url(row)
    html=req(url).text
    low=html.lower()
    starts=[]
    for n in FUND_NAMES:
        p=0
        while True:
            i=low.find(n.lower(),p)
            if i<0: break
            starts.append(i); p=i+10
    if not starts:
        return None
    # Favor occurrences with "schedule of investments" nearby, usually the actual portfolio section.
    scored=[]
    for i in starts:
        near=re.sub('<[^>]+>',' ', low[max(0,i-2500):i+1500])
        score=(3 if 'schedule of investments' in near else 0)+(1 if 'shares' in near else 0)+(1 if 'value' in near else 0)
        scored.append((score,i))
    scored.sort(reverse=True)
    start=scored[0][1]
    # Take a generous segment; stop at the next schedule heading after at least 20k chars when possible.
    next_sched=low.find('schedule of investments', start+20000)
    end=next_sched if next_sched>0 else min(len(html), start+1800000)
    seg=html[start:end]
    try:
        tables=pd.read_html(io.StringIO(seg))
    except Exception as e:
        raise RuntimeError(f'old filing read_html failed {url}: {e}')
    rows=[]
    for t in tables:
        if t.empty: continue
        # Flatten each row. In SEC tables the rightmost numeric columns are usually shares and value.
        for _,r in t.iterrows():
            vals=[str(v).strip() for v in r.tolist() if str(v).strip().lower() not in ('nan','none','')]
            if len(vals)<2: continue
            text=' '.join(vals)
            if any(k in text.lower() for k in ['total investments','net assets','schedule of investments','continued','principal amount']):
                continue
            nums=[clean_num(v) for v in vals]
            numeric=[(j,n) for j,n in enumerate(nums) if pd.notna(n)]
            if len(numeric)<1: continue
            # Name = leading nonnumeric text, Value = last numeric. Shares = previous numeric if present.
            lastj,value=numeric[-1]
            share=np.nan
            if len(numeric)>=2: share=numeric[-2][1]
            name_parts=[]
            for j,v in enumerate(vals[:lastj]):
                if pd.isna(clean_num(v)) and v not in ('$','—','-'):
                    name_parts.append(v)
            name=' '.join(name_parts).strip()
            name=re.sub(r'\s+',' ',name)
            if len(name)<2 or value<=0: continue
            if '%' in name or name.lower().startswith(('common stocks','technology','financial','consumer','industrials','health care','materials','utilities','energy','real estate')):
                continue
            rows.append(dict(name=name,ticker=None,cusip=None,value=value,shares=share,asset='EC'))
    df=pd.DataFrame(rows)
    if df.empty:
        raise RuntimeError(f'No old holdings parsed from {url}')
    # Collapse duplicate issuer rows conservatively.
    df['name']=df['name'].str.replace(r'\s+',' ',regex=True).str.strip()
    df=df.groupby('name',as_index=False).agg({'ticker':'first','cusip':'first','value':'sum','shares':'sum','asset':'first'})
    # Keep plausible common-stock rows by selecting the dominant block: top values; cash/notes are tiny or named explicitly.
    df=df[~df['name'].str.contains('Treasury|Cash|Money Market|Repurchase|Receivable|Payable',case=False,na=False)]
    if len(df)<60:
        raise RuntimeError(f'Old filing parse too small ({len(df)}) {url}; sample={df.head(20).to_dict("records")}')
    return df, url


def choose_snapshot(filings, rb):
    # Old SEC quarterly schedules are much closer to the rebalance (Apr/Oct). NPORT public snapshots are May/Nov.
    target_month = 4 if rb.month==3 else 10
    if rb.year <= 2018:
        c=filings[(filings['form'].isin(['N-CSR','N-Q'])) & (filings['reportDate']>rb) & (filings['reportDate']<=rb+pd.Timedelta(days=80))].copy()
        if c.empty: return None
        c['dist']=(c['reportDate']-rb).dt.days
        return c.sort_values(['dist','filingDate']).iloc[0]
    # Try NPORT first. Use first report snapshot 15-110 days after rebalance.
    c=filings[(filings['form'].str.startswith('NPORT',na=False)) & (filings['reportDate']>rb+pd.Timedelta(days=15)) & (filings['reportDate']<=rb+pd.Timedelta(days=120))].copy()
    if not c.empty:
        c['dist']=(c['reportDate']-rb).dt.days
        return c.sort_values(['dist','filingDate']).iloc[0]
    c=filings[(filings['form'].isin(['N-CSR','N-Q'])) & (filings['reportDate']>rb) & (filings['reportDate']<=rb+pd.Timedelta(days=100))].copy()
    if c.empty:return None
    c['dist']=(c['reportDate']-rb).dt.days
    return c.sort_values(['dist','filingDate']).iloc[0]


def get_ticker_map(names):
    # Yahoo search endpoint resolves historical issuer names better than guessing.
    out={}
    sess=requests.Session(); sess.headers.update({'User-Agent':'Mozilla/5.0'})
    overrides={
        'Alphabet Inc. Class A':'GOOGL','Alphabet Inc Class A':'GOOGL','Alphabet, Inc. Class A':'GOOGL',
        'Alphabet Inc. Class C':'GOOG','Alphabet Inc Class C':'GOOG','Alphabet, Inc. Class C':'GOOG',
        'Facebook, Inc. Class A':'META','Meta Platforms, Inc. Class A':'META',
        'Berkshire Hathaway Inc. Class B':'BRK-B','Berkshire Hathaway, Inc. Class B':'BRK-B',
    }
    for name in names:
        if name in overrides: out[name]=overrides[name]; continue
        q=re.sub(r'\b(Class [A-Z]|Common Stock|Corp\.?|Corporation|Inc\.?|PLC|Ltd\.?)\b',' ',name,flags=re.I)
        q=re.sub(r'\s+',' ',q).strip()
        try:
            data=sess.get('https://query1.finance.yahoo.com/v1/finance/search',params={'q':q,'quotesCount':6,'newsCount':0},timeout=20).json()
            quotes=[z for z in data.get('quotes',[]) if z.get('quoteType')=='EQUITY' and z.get('exchange') in ('NMS','NYQ','NGM','NCM','ASE','PCX')]
            if quotes: out[name]=quotes[0].get('symbol')
        except Exception: pass
        time.sleep(0.03)
    return out


def download_prices(tickers, start, end):
    tickers=sorted(set([t for t in tickers if t]))
    print(f'Downloading prices for {len(tickers)} tickers')
    data=yf.download(tickers,start=(start-pd.Timedelta(days=10)).strftime('%Y-%m-%d'),end=(end+pd.Timedelta(days=10)).strftime('%Y-%m-%d'),auto_adjust=False,actions=True,group_by='column',threads=True,progress=False)
    return data


def field_df(data, field, tickers):
    if isinstance(data.columns,pd.MultiIndex):
        if field not in data.columns.get_level_values(0): return pd.DataFrame(index=data.index)
        x=data[field].copy()
        if isinstance(x,pd.Series): x=x.to_frame(tickers[0])
        return x
    if field in data.columns:
        return data[[field]].rename(columns={field:tickers[0]})
    return pd.DataFrame(index=data.index)


def nearest_on_or_before(df, d, ticker):
    s=df[ticker].dropna() if ticker in df.columns else pd.Series(dtype=float)
    s=s[s.index<=d]
    return float(s.iloc[-1]) if len(s) else np.nan


def nearest_on_or_after(df,d,ticker):
    s=df[ticker].dropna() if ticker in df.columns else pd.Series(dtype=float)
    s=s[s.index>=d]
    return (s.index[0],float(s.iloc[0])) if len(s) else (None,np.nan)


def estimate_rb_values(h, rb, snap, close, splits):
    vals=[]
    for _,r in h.iterrows():
        t=r['ticker_resolved']; v=float(r['value'])
        if not t or t not in close.columns: vals.append(np.nan); continue
        ps=nearest_on_or_before(close,snap,t); pr=nearest_on_or_before(close,rb,t)
        if not (np.isfinite(ps) and np.isfinite(pr) and ps>0): vals.append(np.nan); continue
        sf=1.0
        if t in splits.columns:
            ss=splits[t].fillna(0)
            ss=ss[(ss.index>rb)&(ss.index<=snap)&(ss!=0)]
            for z in ss: sf*=float(z)
        vals.append(v*(pr/ps)/sf)
    h=h.copy(); h['rb_value_est']=vals
    h=h[h['rb_value_est'].notna() & (h['rb_value_est']>0)]
    h=h.sort_values('rb_value_est',ascending=False).reset_index(drop=True)
    h['rank']=np.arange(1,len(h)+1)
    h['rb_weight_est']=h['rb_value_est']/h['rb_value_est'].sum()
    return h


def period_curve(tickers, entry_date, exit_date, adjclose, adjopen, mode):
    tickers=[t for t in tickers if t in adjclose.columns]
    if not tickers:return None
    if mode=='close':
        entry_px={t:nearest_on_or_before(adjclose,entry_date,t) for t in tickers}
        start=entry_date
        exit=exit_date
        idx=adjclose.index[(adjclose.index>=start)&(adjclose.index<=exit)]
    else:
        entry_px={}; entry_actual=[]
        for t in tickers:
            d,p=nearest_on_or_after(adjopen,entry_date+pd.Timedelta(days=1),t); entry_px[t]=p
            if d is not None: entry_actual.append(d)
        if not entry_actual:return None
        start=max(entry_actual)
        # execute next open after rebalance signal at exit_date
        exit_candidates=[]
        for t in tickers:
            d,p=nearest_on_or_after(adjopen,exit_date+pd.Timedelta(days=1),t)
            if d is not None: exit_candidates.append(d)
        exit=max(exit_candidates) if exit_candidates else exit_date
        idx=adjclose.index[(adjclose.index>=start)&(adjclose.index<exit)]
        idx=idx.append(pd.DatetimeIndex([exit])).unique().sort_values()
    series=[]
    good=[]
    for t in tickers:
        ep=entry_px.get(t,np.nan)
        if not np.isfinite(ep) or ep<=0: continue
        s=adjclose[t].reindex(idx).ffill()/ep
        if mode=='next_open' and len(idx):
            # terminal mark at execution open, not close
            d,p=nearest_on_or_after(adjopen,exit_date+pd.Timedelta(days=1),t)
            if d is not None and d in s.index and np.isfinite(p): s.loc[d]=p/ep
        series.append(s.rename(t)); good.append(t)
    if not series:return None
    mat=pd.concat(series,axis=1)
    curve=mat.mean(axis=1,skipna=True)
    return curve, good


def metrics(eq):
    eq=eq.dropna()
    r=eq.pct_change().dropna()
    years=(eq.index[-1]-eq.index[0]).days/365.2425
    cagr=(eq.iloc[-1]/eq.iloc[0])**(1/years)-1
    vol=r.std(ddof=1)*np.sqrt(252)
    sharpe=(r.mean()/r.std(ddof=1))*np.sqrt(252) if r.std(ddof=1)>0 else np.nan
    dd=eq/eq.cummax()-1
    return {'start':str(eq.index[0].date()),'end':str(eq.index[-1].date()),'multiple':eq.iloc[-1]/eq.iloc[0],'cagr':cagr,'vol':vol,'sharpe_rf0':sharpe,'max_dd':dd.min(),'days':len(eq)}


def stitch(curves):
    out=None; level=1.0
    for c in curves:
        c=c.dropna()
        if len(c)<2: continue
        norm=c/c.iloc[0]*level
        if out is not None and norm.index[0] in out.index: norm=norm.iloc[1:]
        out=norm if out is None else pd.concat([out,norm])
        level=float(out.iloc[-1])
    return out


def main():
    rbs=rebalance_dates()
    print('Rebalances', [str(x.date()) for x in rbs], 'count=',len(rbs))
    filings=load_submissions()
    filings.to_csv(OUT/'sec_filings.csv',index=False)
    snapshots=[]; holdings_by_rb={}; errs=[]
    for rb in rbs:
        row=choose_snapshot(filings,rb)
        if row is None:
            errs.append({'rb':str(rb.date()),'error':'no snapshot filing'}); continue
        try:
            if str(row['form']).startswith('NPORT'): parsed=parse_nport(row)
            else: parsed=parse_old_filing(row)
            if parsed is None: raise RuntimeError('filing did not contain target fund')
            h,url=parsed
            h=h[h['value']>0].copy()
            snapshots.append({'rb':str(rb.date()),'reportDate':str(row['reportDate'].date()),'filingDate':str(row['filingDate'].date()),'form':row['form'],'accession':row['accessionNumber'],'url':url,'holdings':len(h)})
            holdings_by_rb[rb]=h
            print(rb.date(),row['form'],row['reportDate'].date(),'holdings',len(h))
        except Exception as e:
            errs.append({'rb':str(rb.date()),'accession':row['accessionNumber'],'form':row['form'],'error':repr(e)})
            print('ERROR',rb,e)
    pd.DataFrame(snapshots).to_csv(OUT/'snapshots.csv',index=False)
    Path(OUT/'errors.json').write_text(json.dumps(errs,indent=2),encoding='utf-8')
    if len(holdings_by_rb)<15:
        raise RuntimeError(f'Only {len(holdings_by_rb)} usable snapshots; see errors.json')

    # Resolve tickers. Keep NPORT tickers where supplied; resolve names only where absent.
    all_names=[]
    for h in holdings_by_rb.values():
        all_names += h.loc[h['ticker'].isna() | (h['ticker'].astype(str).str.len()<1),'name'].tolist()
    name_map=get_ticker_map(sorted(set(all_names)))
    tickers=[]
    for rb,h in list(holdings_by_rb.items()):
        h=h.copy()
        h['ticker_resolved']=h.apply(lambda r: (str(r['ticker']).strip().replace('.','-') if pd.notna(r['ticker']) and str(r['ticker']).strip() not in ('','nan','None') else name_map.get(r['name'])),axis=1)
        # Yahoo legacy fixes
        h['ticker_resolved']=h['ticker_resolved'].replace({'FB':'META','GOOG.L':'GOOG','BRK.B':'BRK-B','BF.B':'BF-B'})
        holdings_by_rb[rb]=h
        tickers += h['ticker_resolved'].dropna().tolist()
    (OUT/'ticker_map.json').write_text(json.dumps(name_map,indent=2,ensure_ascii=False),encoding='utf-8')

    data=download_prices(tickers,START,END+pd.Timedelta(days=7))
    uniq=sorted(set(tickers))
    close=field_df(data,'Close',uniq); adjclose=field_df(data,'Adj Close',uniq); open_=field_df(data,'Open',uniq); splits=field_df(data,'Stock Splits',uniq)
    # yfinance may omit Adj Close in some versions with certain combinations; derive adjusted OHLC download separately if needed.
    if adjclose.empty:
        adj=yf.download(uniq,start=(START-pd.Timedelta(days=10)).strftime('%Y-%m-%d'),end=(END+pd.Timedelta(days=10)).strftime('%Y-%m-%d'),auto_adjust=True,group_by='column',threads=True,progress=False)
        adjclose=field_df(adj,'Close',uniq); adjopen=field_df(adj,'Open',uniq)
    else:
        # ratio AdjClose/Close adjusts raw open consistently.
        factor=adjclose/close
        adjopen=open_*factor

    ranked={}
    details=[]
    for s in snapshots:
        rb=pd.Timestamp(s['rb']); snap=pd.Timestamp(s['reportDate'])
        if rb not in holdings_by_rb: continue
        h=estimate_rb_values(holdings_by_rb[rb],rb,snap,close,splits)
        ranked[rb]=h
        h2=h.copy(); h2.insert(0,'rebalance',str(rb.date())); h2.insert(1,'snapshot',str(snap.date()))
        details.append(h2)
    if details: pd.concat(details,ignore_index=True).to_csv(OUT/'ranked_holdings.csv',index=False)

    rows=[]; all_curves={}
    ns=[1,5,10,15,20]
    modes=['close','next_open']
    for n in ns:
        for mode in modes:
            curves=[]; period_rows=[]
            for i,rb in enumerate(rbs):
                if rb not in ranked: continue
                exitd=(rbs[i+1] if i+1<len(rbs) else END)
                tops=ranked[rb].head(n)['ticker_resolved'].dropna().tolist()
                pc=period_curve(tops,rb,exitd,adjclose,adjopen,mode)
                if pc is None: continue
                curve,good=pc
                curves.append(curve)
                period_rows.append({'n':n,'mode':mode,'rb':str(rb.date()),'exit':str(exitd.date()),'tickers':','.join(good),'period_multiple':float(curve.iloc[-1]/curve.iloc[0])})
            eq=stitch(curves)
            if eq is None or len(eq)<100: continue
            m=metrics(eq); m.update({'n':n,'mode':mode,'periods':len(curves)})
            rows.append(m); all_curves[(n,mode)]=eq.rename(f'top{n}_{mode}')
            pd.DataFrame(period_rows).to_csv(OUT/f'periods_top{n}_{mode}.csv',index=False)
    res=pd.DataFrame(rows)
    res.to_csv(OUT/'results.csv',index=False)
    if all_curves: pd.concat(all_curves.values(),axis=1).to_csv(OUT/'equity_curves.csv')

    # Stability / sensitivity: remove best and worst six-month period based on period multiples and chain remaining period returns.
    sens=[]
    for n in ns:
        for mode in modes:
            p=OUT/f'periods_top{n}_{mode}.csv'
            if not p.exists(): continue
            df=pd.read_csv(p)
            if len(df)<5: continue
            mult=df['period_multiple'].astype(float)
            for label,dropidx in [('drop_best',mult.idxmax()),('drop_worst',mult.idxmin())]:
                kept=mult.drop(dropidx)
                years=((pd.Timestamp(df.iloc[-1]['exit'])-pd.Timestamp(df.iloc[0]['rb'])).days/365.2425) * (len(kept)/len(mult))
                sens.append({'n':n,'mode':mode,'test':label,'multiple':float(kept.prod()),'approx_cagr':float(kept.prod()**(1/years)-1),'dropped_rb':df.loc[dropidx,'rb'],'dropped_period_multiple':float(mult.loc[dropidx])})
    pd.DataFrame(sens).to_csv(OUT/'sensitivity.csv',index=False)

    summary={'usable_snapshots':len(ranked),'expected_rebalances':len(rbs),'errors':errs,'results':rows}
    (OUT/'summary.json').write_text(json.dumps(summary,indent=2,default=str),encoding='utf-8')
    print('\nRESULTS\n',res.to_string(index=False))
    print('\nERRORS\n',json.dumps(errs,indent=2))

if __name__=='__main__':
    main()
