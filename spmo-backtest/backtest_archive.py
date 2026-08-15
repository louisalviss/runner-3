#!/usr/bin/env python3
import io, json, math, re, time
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import requests
import yfinance as yf
from bs4 import BeautifulSoup

OUT=Path('spmo-backtest/output-archive'); OUT.mkdir(parents=True,exist_ok=True)
CIK='1378872'; SERIES='S000050154'
START=pd.Timestamp('2016-03-18'); END=pd.Timestamp('2026-08-14')
UA='Louis independent SPMO research github.com/louisalviss/runner-3 contact@example.com'
S=requests.Session(); S.headers.update({'User-Agent':UA,'Accept-Encoding':'gzip, deflate'})
NAMES=['PowerShares S&P 500 Momentum Portfolio','Invesco S&P 500 Momentum ETF','Invesco S&P 500® Momentum ETF']


def get(url, *, stream=False, headers=None, tries=5, timeout=60):
    h={} if headers is None else dict(headers)
    last=None
    for i in range(tries):
        try:
            last=S.get(url,headers=h,timeout=timeout,stream=stream)
            if last.status_code in (200,206): return last
            print('HTTP',last.status_code,url)
        except Exception as e: print('GETERR',repr(e),url)
        time.sleep(0.8*(i+1))
    if last is not None: last.raise_for_status()
    raise RuntimeError('GET failed '+url)


def third_friday(y,m):
    d=date(y,m,15)
    while d.weekday()!=4:d+=timedelta(days=1)
    return pd.Timestamp(d)


def rebalances():
    return [third_friday(y,m) for y in range(2016,2027) for m in (3,9) if START<=third_friday(y,m)<=END]


def target_index_quarter(rb):
    # Post-rebalance portfolio snapshot: Apr/May for March rebalance (filed ~Q3),
    # Oct/Nov for September rebalance (filed ~Q1 next year).
    return (rb.year,3) if rb.month==3 else (rb.year+1,1)


def master_rows(year,q):
    url=f'https://www.sec.gov/Archives/edgar/full-index/{year}/QTR{q}/master.idx'
    print('INDEX',year,q)
    r=get(url,stream=True,timeout=90)
    rows=[]; started=False
    for raw in r.iter_lines(decode_unicode=True):
        if not raw or '|' not in raw: continue
        p=raw.split('|')
        if len(p)!=5: continue
        cik,company,form,filed,fn=p
        try: ic=int(cik)
        except: continue
        if ic<int(CIK): continue
        if ic>int(CIK):
            if started: break
            continue
        started=True
        if form in ('NPORT-P','NPORT-P/A','N-CSR','N-CSRS','N-Q'):
            rows.append({'cik':cik,'company':company,'form':form,'filed':pd.Timestamp(filed),'filename':fn})
    r.close()
    print('  candidates',len(rows))
    return rows


def accession_from_filename(fn):
    return Path(fn).stem


def folder_from_accession(acc): return acc.replace('-','')


def primary_xml_url(fn):
    acc=accession_from_filename(fn)
    return f'https://www.sec.gov/Archives/edgar/data/{CIK}/{folder_from_accession(acc)}/primary_doc.xml'


def complete_url(fn): return 'https://www.sec.gov/Archives/'+fn


def parse_nport_xml(xml):
    soup=BeautifulSoup(xml,'xml')
    sid=soup.find('seriesId')
    if not sid or sid.get_text(strip=True)!=SERIES:return None
    rd=soup.find('repPdDate')
    if not rd:return None
    report=pd.Timestamp(rd.get_text(strip=True))
    out=[]
    for n in soup.find_all('invstOrSec'):
        def g(tag):
            z=n.find(tag); return z.get_text(' ',strip=True) if z else None
        name=g('name'); val=g('valUSD'); sh=g('balance'); cusip=g('cusip')
        if not name or not val:continue
        try:v=float(val.replace(',',''))
        except:continue
        try:s=float(sh.replace(',','')) if sh else np.nan
        except:s=np.nan
        if v>0:out.append({'name':name,'cusip':cusip,'shares':s,'value':v})
    if len(out)<50:return None
    return report,pd.DataFrame(out)


def discover_nport(rows,rb):
    c=[x for x in rows if x['form'].startswith('NPORT-P')]
    c=sorted(c,key=lambda x:(x['filed'],x['filename']))
    for j,row in enumerate(c):
        u=primary_xml_url(row['filename'])
        try:
            # seriesId and report date are in the first KB; Range cuts discovery traffic sharply.
            rr=get(u,headers={'Range':'bytes=0-6000'},tries=2,timeout=20)
            head=rr.content
            if SERIES.encode() not in head: continue
            full=get(u,tries=3,timeout=40).text
            parsed=parse_nport_xml(full)
            if parsed is None:continue
            rd,f=parsed
            if rb < rd <= rb+pd.Timedelta(days=120):
                print('  NPORT HIT',j+1,'/',len(c),row['filed'].date(),rd.date(),Path(row['filename']).name,len(f))
                return {'source':'NPORT-P','reportDate':rd,'filingDate':row['filed'],'filename':row['filename'],'url':u},f
        except Exception as e:
            print('  nport candidate error',Path(row['filename']).name,repr(e))
        time.sleep(0.06)
    return None


def clean_num(s):
    s=str(s).replace(',','').replace('$','').replace('(','-').replace(')','').strip()
    s=re.sub(r'[^0-9eE+\-.]','',s)
    if not s or s in ('-','.'):return np.nan
    try:return float(s)
    except:return np.nan


def normalize_name(s):
    s=BeautifulSoup(str(s),'html.parser').get_text(' ',strip=True)
    s=re.sub(r'\([a-z]{1,3}\)$','',s,flags=re.I)
    s=re.sub(r'\[[a-z0-9]+\]$','',s,flags=re.I)
    s=re.sub(r'\s+',' ',s).strip(' *†‡')
    return s


def parse_legacy_submission(txt,rb):
    # Ignore SEC header occurrence; locate an actual report heading containing (SPMO), then
    # cut at the next anchored portfolio heading. Continued pages have no new anchor.
    low=txt.lower()
    candidates=[]
    for pat in ['momentum portfolio (spmo)','momentum etf (spmo)']:
        pos=0
        while True:
            i=low.find(pat,pos)
            if i<0:break
            after=low[i:i+25000]
            if 'schedule of investments' in after:
                candidates.append(i)
            pos=i+20
    if not candidates:return None
    # Prefer a report date after the rebalance and within 120d.
    for st in candidates:
        pre=txt[max(0,st-1000):st+3000]
        plain=BeautifulSoup(pre,'html.parser').get_text(' ',strip=True)
        m=re.search(r'(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{1,2}),\s+(20\d{2})',plain,re.I)
        if not m:continue
        rd=pd.Timestamp(pd.to_datetime(m.group(0)))
        if not (rb < rd <= rb+pd.Timedelta(days=120)):continue
        # Next anchor marks the next fund; allow enough bytes to include continued pages.
        nxt=re.search(r'<A\s+NAME="tx[^"]+"',txt[st+5000:],flags=re.I)
        en=st+5000+nxt.start() if nxt else min(len(txt),st+1200000)
        section=txt[st:en]
        soup=BeautifulSoup(section,'html.parser')
        out=[]
        for tr in soup.find_all('tr'):
            cells=[c.get_text(' ',strip=True) for c in tr.find_all('td')]
            vals=[x for x in cells if x and x not in ('\xa0','$')]
            if len(vals)<3:continue
            nums=[clean_num(v) for v in vals]
            ni=[(k,n) for k,n in enumerate(nums) if pd.notna(n)]
            if len(ni)<2:continue
            # Security rows: first numeric = shares, last numeric = value.
            k1,sh=ni[0]; k2,v=ni[-1]
            if k2<=k1 or sh<=0 or v<=0:continue
            mids=vals[k1+1:k2]
            names=[]
            for x in mids:
                if x in ('$','—','-'):continue
                if pd.notna(clean_num(x)):continue
                names.append(x)
            name=normalize_name(' '.join(names))
            if len(name)<2:continue
            nl=name.lower()
            if any(nl.startswith(x) for x in ['total ','common stocks','money market','other assets','net assets','cost ','number of shares','portfolio composition']):continue
            if '%' in name:continue
            # Sector/header rows usually don't have two proper numeric columns, but filter common labels too.
            if nl in {'consumer discretionary','consumer staples','energy','financials','health care','industrials','information technology','materials','real estate','telecommunication services','communication services','utilities'}:continue
            out.append({'name':name,'cusip':None,'shares':float(sh),'value':float(v)})
        f=pd.DataFrame(out)
        if len(f)>=50:
            f=f.drop_duplicates(['name','shares','value']).reset_index(drop=True)
            print('  LEGACY PARSE',rd.date(),'rows',len(f))
            return rd,f
    return None


def discover_legacy(rows,rb):
    c=[x for x in rows if x['form'] in ('N-CSR','N-CSRS','N-Q')]
    # Prefer certified shareholder reports; N-Q fallback.
    order={'N-CSRS':0,'N-CSR':1,'N-Q':2}
    c=sorted(c,key=lambda x:(order.get(x['form'],9),x['filed']))
    for row in c:
        try:
            u=complete_url(row['filename'])
            txt=get(u,tries=3,timeout=90).text
            if SERIES not in txt and 'SPMO' not in txt:continue
            p=parse_legacy_submission(txt,rb)
            if p:
                rd,f=p
                print('  LEGACY HIT',row['form'],row['filed'].date(),rd.date(),Path(row['filename']).name,len(f))
                return {'source':row['form'],'reportDate':rd,'filingDate':row['filed'],'filename':row['filename'],'url':u},f
        except Exception as e:print('  legacy error',Path(row['filename']).name,repr(e))
    return None


def build_snapshots(rbs):
    frames={}; meta=[]; errors=[]; idx_cache={}
    for rb in rbs:
        y,q=target_index_quarter(rb)
        if (y,q) not in idx_cache:idx_cache[(y,q)]=master_rows(y,q)
        rows=idx_cache[(y,q)]
        print('\nRB',rb.date(),'filing quarter',y,q)
        hit=discover_nport(rows,rb)
        if hit is None:hit=discover_legacy(rows,rb)
        if hit is None:
            errors.append({'rb':str(rb.date()),'error':f'no usable SPMO filing in {y} Q{q}'})
            print('  NO SNAPSHOT');continue
        m,f=hit; frames[rb]=f
        meta.append({'rb':str(rb.date()),'reportDate':str(m['reportDate'].date()),'filingDate':str(m['filingDate'].date()),'source':m['source'],'filename':m['filename'],'rows':len(f),'url':m['url']})
    pd.DataFrame(meta).to_csv(OUT/'snapshots.csv',index=False)
    Path(OUT/'errors.json').write_text(json.dumps(errors,indent=2))
    return frames,meta,errors


def yahoo_symbol(name,cusip=None):
    overrides={
      'Amazon.com, Inc.':'AMZN','Apple, Inc.':'AAPL','Apple Inc.':'AAPL','Microsoft Corp.':'MSFT','Microsoft Corporation':'MSFT',
      'Facebook, Inc., Class A':'META','Facebook, Inc. Class A':'META','Meta Platforms, Inc., Class A':'META','Meta Platforms, Inc.':'META',
      'Alphabet, Inc., Class A':'GOOGL','Alphabet Inc. Class A':'GOOGL','Alphabet, Inc. Class C':'GOOG','Alphabet, Inc., Class C':'GOOG',
      'Google, Inc., Class A':'GOOGL','Google Inc., Class A':'GOOGL','Berkshire Hathaway, Inc., Class B':'BRK-B','Berkshire Hathaway Inc. Class B':'BRK-B',
      'NVIDIA Corp.':'NVDA','NVIDIA Corporation':'NVDA','Broadcom Inc.':'AVGO','Broadcom, Inc.':'AVGO'
    }
    if name in overrides:return overrides[name]
    queries=[name]
    if cusip:queries.append(str(cusip))
    for q in queries:
        try:
            r=S.get('https://query1.finance.yahoo.com/v1/finance/search',params={'q':q,'quotesCount':8,'newsCount':0},headers={'User-Agent':'Mozilla/5.0'},timeout=15)
            if r.status_code!=200:continue
            js=r.json(); qs=[]
            for z in js.get('quotes',[]):
                if z.get('quoteType')!='EQUITY':continue
                sym=z.get('symbol'); exch=z.get('exchange','')
                if sym and exch in ('NMS','NYQ','NGM','NCM','ASE','PCX'):qs.append(z)
            if qs:return qs[0]['symbol'].replace('.','-')
        except:pass
    return None


def resolve_all(frames):
    keys={}
    for f in frames.values():
        for _,r in f.iterrows():keys[(r['name'],r.get('cusip'))]=None
    print('RESOLVE',len(keys),'unique issuer records')
    for i,(k,_) in enumerate(list(keys.items())):
        name,cusip=k; keys[k]=yahoo_symbol(name,cusip)
        if i%50==0:print('  resolved',i,'/',len(keys))
        time.sleep(.035)
    # second-pass canonicalized names for misses
    for k,v in list(keys.items()):
        if v:continue
        name,cusip=k
        q=re.sub(r'\b(Class [A-Z]|Common Stock|REIT|PLC|Ltd\.?|Inc\.?|Corp\.?|Corporation|Co\.? \(The\))\b',' ',name,flags=re.I)
        q=re.sub(r'\s+',' ',q).strip(' ,')
        if q and q!=name:keys[k]=yahoo_symbol(q,cusip)
        time.sleep(.03)
    Path(OUT/'ticker_map.json').write_text(json.dumps({f'{k[0]}|{k[1]}':v for k,v in keys.items()},indent=2,ensure_ascii=False))
    for rb,f in frames.items():
        z=f.copy(); z['ticker']=[keys.get((r['name'],r.get('cusip'))) for _,r in z.iterrows()]
        frames[rb]=z
    return keys


def field_df(d,field):
    if isinstance(d.columns,pd.MultiIndex):
        if field not in d.columns.get_level_values(0):return pd.DataFrame(index=d.index)
        x=d[field]; return x.to_frame() if isinstance(x,pd.Series) else x
    if field in d.columns:return d[[field]]
    return pd.DataFrame(index=d.index)


def before(df,d,t):
    if t not in df.columns:return np.nan
    s=df[t].dropna();s=s[s.index<=d]
    return float(s.iloc[-1]) if len(s) else np.nan


def after(df,d,t):
    if t not in df.columns:return None,np.nan
    s=df[t].dropna();s=s[s.index>=d]
    return (s.index[0],float(s.iloc[0])) if len(s) else (None,np.nan)


def rank_frames(frames,meta):
    tickers=sorted(set(t for f in frames.values() for t in f.ticker.dropna()))
    print('DOWNLOAD PRICE',len(tickers),'tickers')
    raw=yf.download(tickers,start='2016-03-01',end='2026-08-25',auto_adjust=False,actions=True,threads=True,progress=False)
    rc=field_df(raw,'Close'); ac=field_df(raw,'Adj Close'); ro=field_df(raw,'Open'); sp=field_df(raw,'Stock Splits')
    if ac.empty:
        adj=yf.download(tickers,start='2016-03-01',end='2026-08-25',auto_adjust=True,threads=True,progress=False)
        ac=field_df(adj,'Close'); ao=field_df(adj,'Open')
    else:ao=ro*(ac/rc)
    md={pd.Timestamp(x['rb']):pd.Timestamp(x['reportDate']) for x in meta}
    ranked={}; allz=[]
    for rb,f in frames.items():
        snap=md[rb]; z=f.copy(); rv=[]
        for _,r in z.iterrows():
            t=r.ticker
            if not t or t not in rc.columns:rv.append(np.nan);continue
            # Use snapshot shares when available; translate them backwards across any split between rb and snapshot.
            sh=float(r.shares) if pd.notna(r.shares) else np.nan
            if np.isfinite(sh) and sh>0:
                sf=1.0
                if t in sp.columns:
                    ss=sp[t].fillna(0);ss=ss[(ss.index>rb)&(ss.index<=snap)&(ss!=0)]
                    for x in ss:sf*=float(x)
                shrb=sh/sf
                p=before(rc,rb,t); val=shrb*p if np.isfinite(p) else np.nan
            else:
                ps=before(rc,snap,t);pr=before(rc,rb,t)
                val=float(r.value)*pr/ps if np.isfinite(ps) and ps>0 and np.isfinite(pr) else np.nan
            rv.append(val)
        z['rb_value']=rv;z=z[z.rb_value.notna() & (z.rb_value>0)].sort_values('rb_value',ascending=False).reset_index(drop=True)
        z['rank']=np.arange(1,len(z)+1);z['weight']=z.rb_value/z.rb_value.sum();ranked[rb]=z
        zz=z.copy();zz.insert(0,'rebalance',str(rb.date()));zz.insert(1,'snapshot',str(snap.date()));allz.append(zz)
        print('RANK',rb.date(),'resolved',len(z),'top1',z.iloc[0].ticker if len(z) else None,z.iloc[0]['name'] if len(z) else None)
    pd.concat(allz,ignore_index=True).to_csv(OUT/'ranked_holdings.csv',index=False)
    return ranked,ac,ao


def period_curve(top,rb,ex,ac,ao,mode,wm,last=False):
    top=top[top.ticker.notna()].copy()
    if top.empty:return None
    if wm=='equal':weights=np.repeat(1/len(top),len(top))
    else:weights=(top.weight/top.weight.sum()).to_numpy()
    parts=[];w2=[]
    for (_,r),w in zip(top.iterrows(),weights):
        t=r.ticker
        if t not in ac.columns:continue
        if mode=='close':
            ep=before(ac,rb,t); start=rb; terminal_date=ex
            if not np.isfinite(ep):continue
            idx=ac.index[(ac.index>=start)&(ac.index<=terminal_date)]
            s=ac[t].reindex(idx).ffill()/ep
        else:
            ent,ep=after(ao,rb+pd.Timedelta(days=1),t)
            if ent is None or not np.isfinite(ep):continue
            if last:
                idx=ac.index[(ac.index>=ent)&(ac.index<=ex)]
                s=ac[t].reindex(idx).ffill()/ep
            else:
                outd,outp=after(ao,ex+pd.Timedelta(days=1),t)
                if outd is None or not np.isfinite(outp):continue
                idx=ac.index[(ac.index>=ent)&(ac.index<outd)]
                s=ac[t].reindex(idx).ffill()/ep
                s.loc[outd]=outp/ep
        if len(s)>=2:parts.append(s.rename(t));w2.append(w)
    if not parts:return None
    mat=pd.concat(parts,axis=1).ffill();w2=np.array(w2);w2=w2/w2.sum()
    return mat.mul(w2,axis=1).sum(axis=1)


def stitch(cs):
    out=None;lvl=1.0
    for c in cs:
        c=c.dropna()
        if len(c)<2:continue
        x=c/c.iloc[0]*lvl
        if out is not None and x.index[0] in out.index:x=x.iloc[1:]
        out=x if out is None else pd.concat([out,x]);lvl=float(out.iloc[-1])
    return out


def metrics(eq):
    eq=eq[~eq.index.duplicated(keep='last')].sort_index().dropna();r=eq.pct_change().dropna();yrs=(eq.index[-1]-eq.index[0]).days/365.2425
    dd=eq/eq.cummax()-1
    return {'start':str(eq.index[0].date()),'end':str(eq.index[-1].date()),'multiple':float(eq.iloc[-1]/eq.iloc[0]),'cagr':float((eq.iloc[-1]/eq.iloc[0])**(1/yrs)-1),'vol':float(r.std(ddof=1)*np.sqrt(252)),'sharpe_rf0':float(r.mean()/r.std(ddof=1)*np.sqrt(252)),'max_dd':float(dd.min()),'trading_days':len(eq)}


def run_tests(rbs,ranked,ac,ao):
    rows=[];periods=[];equities=[]
    for n in (1,5,10,15,20):
      for mode in ('close','next_open'):
       for wm in ('equal','spmo_weight'):
        cs=[];prs=[]
        for i,rb in enumerate(rbs):
            if rb not in ranked:continue
            ex=rbs[i+1] if i+1<len(rbs) else END
            c=period_curve(ranked[rb].head(n),rb,ex,ac,ao,mode,wm,last=(i==len(rbs)-1))
            if c is None:continue
            cs.append(c);prs.append({'n':n,'mode':mode,'weight_mode':wm,'rb':str(rb.date()),'exit':str(ex.date()),'multiple':float(c.iloc[-1]/c.iloc[0]),'tickers':','.join(ranked[rb].head(n).ticker.dropna().tolist())})
        eq=stitch(cs)
        if eq is None or len(eq)<100:continue
        m=metrics(eq);m.update({'n':n,'mode':mode,'weight_mode':wm,'periods':len(cs)});rows.append(m)
        equities.append((f'top{n}_{mode}_{wm}',eq));periods+=prs
    pd.DataFrame(rows).to_csv(OUT/'results.csv',index=False);pd.DataFrame(periods).to_csv(OUT/'periods.csv',index=False)
    if equities:pd.concat([x.rename(n) for n,x in equities],axis=1).to_csv(OUT/'equity_curves.csv')
    # Remove-best / remove-worst 6m sensitivity using period multiples.
    sens=[];p=pd.DataFrame(periods)
    if len(p):
      for (n,mode,wm),g in p.groupby(['n','mode','weight_mode']):
        if len(g)<5:continue
        g=g.reset_index(drop=True); mult=g.multiple.astype(float)
        total_years=(END-START).days/365.2425
        for label,ix in [('drop_best',mult.idxmax()),('drop_worst',mult.idxmin())]:
            kept=mult.drop(ix); years=total_years*(len(kept)/len(mult)); M=float(kept.prod())
            sens.append({'n':n,'mode':mode,'weight_mode':wm,'test':label,'multiple':M,'approx_cagr':M**(1/years)-1,'dropped_rb':g.loc[ix,'rb'],'dropped_multiple':float(mult.loc[ix])})
    pd.DataFrame(sens).to_csv(OUT/'sensitivity.csv',index=False)
    return rows,periods,sens


def main():
    rbs=rebalances();print('REBALANCES',len(rbs),[str(x.date()) for x in rbs])
    frames,meta,errors=build_snapshots(rbs)
    print('SNAPSHOTS',len(frames),'ERRORS',len(errors))
    if len(frames)<15:raise RuntimeError(f'Only {len(frames)} snapshots; cannot claim full reproduction')
    resolve_all(frames)
    ranked,ac,ao=rank_frames(frames,meta)
    topseq=pd.DataFrame([{'rb':str(rb.date()),'top1':z.iloc[0].ticker if len(z) else None,'issuer':z.iloc[0]['name'] if len(z) else None,'resolved_count':len(z)} for rb,z in ranked.items()])
    topseq.to_csv(OUT/'top1_sequence.csv',index=False);print('\nTOP1\n'+topseq.to_string(index=False))
    rows,periods,sens=run_tests(rbs,ranked,ac,ao)
    res=pd.DataFrame(rows);print('\nRESULTS\n'+res.to_string(index=False))
    summary={'expected_rebalances':len(rbs),'usable_snapshots':len(frames),'errors':errors,'snapshots':meta,'results':rows,'top1':topseq.to_dict('records')}
    Path(OUT/'summary.json').write_text(json.dumps(summary,indent=2,default=str))

if __name__=='__main__':main()
