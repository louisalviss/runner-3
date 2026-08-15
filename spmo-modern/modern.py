#!/usr/bin/env python3
import sys,time,re
from pathlib import Path
import pandas as pd
import requests

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'spmo-backtest'))
import backtest_efts as bt

S=requests.Session(); S.headers.update(bt.UA)


def master(y,q):
    u=f'https://www.sec.gov/Archives/edgar/full-index/{y}/QTR{q}/master.idx'
    r=S.get(u,timeout=45); r.raise_for_status(); time.sleep(.12)
    out=[]; prefix=str(int(bt.CIK))+'|'
    for line in r.text.splitlines():
        if not line.startswith(prefix):continue
        p=line.split('|')
        if len(p)==5 and p[2]=='NPORT-P':
            out.append({'filed':pd.Timestamp(p[3]),'filename':p[4]})
    return out


def xml_for(filename):
    adsh=Path(filename).stem; folder=adsh.replace('-','')
    u=f'https://www.sec.gov/Archives/edgar/data/{int(bt.CIK)}/{folder}/primary_doc.xml'
    r=S.get(u,timeout=30); time.sleep(.12)
    return adsh,u,r


def repdate(txt):
    for pat in [r'<repPdDate>\s*(\d{4}-\d{2}-\d{2})',r'<reportDate>\s*(\d{4}-\d{2}-\d{2})']:
        m=re.search(pat,txt,re.I)
        if m:return pd.Timestamp(m.group(1))
    return pd.NaT


def inventory():
    rows=[]
    # 2019-09 uses 2019-11-30 snapshot filed in Q1 2020.
    targets=[]
    for rb in bt.rebalances():
        if rb < pd.Timestamp('2019-09-20'):continue
        rep=pd.Timestamp(rb.year,5,31) if rb.month==3 else pd.Timestamp(rb.year,11,30)
        fy=rep.year if rep.month==5 else rep.year+1
        fq=3 if rep.month==5 else 1
        targets.append((rb,rep,fy,fq))
    cache={}
    for rb,rep,y,q in targets:
        key=(y,q)
        if key not in cache:cache[key]=master(y,q)
        found=None
        # NPORT public filings for our desired snapshot are normally in Jul/Jan;
        # inspect only a tight date band around 45-75 days after report date.
        lo=rep+pd.Timedelta(days=45); hi=rep+pd.Timedelta(days=75)
        cand=[x for x in cache[key] if lo<=x['filed']<=hi]
        print('TARGET',rb.date(),rep.date(),'candidates',len(cand),flush=True)
        for x in cand:
            adsh,u,r=xml_for(x['filename'])
            if r.status_code!=200:continue
            txt=r.text.lower()
            if bt.SERIES.lower() not in txt and 'invesco s&p 500 momentum etf' not in txt:continue
            rd=repdate(r.text)
            if pd.isna(rd) or rd!=rep:continue
            found={'accessionNumber':adsh,'form':'NPORT-P','filingDate':x['filed'],'reportDate':rd,'source_url':u}
            print('FOUND',rb.date(),rd.date(),adsh,flush=True);break
        if found:rows.append(found)
    df=pd.DataFrame(rows).drop_duplicates('accessionNumber').sort_values('reportDate')
    df.to_csv(bt.OUT/'modern_filings.csv',index=False)
    print('MODERN_FOUND',len(df),'of',len(targets),flush=True)
    return df

if __name__=='__main__':
    bt.filing_inventory=inventory
    bt.main()
