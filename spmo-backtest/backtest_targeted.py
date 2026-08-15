#!/usr/bin/env python3
"""Targeted SPMO filing inventory using only SEC static Archives.

Modern N-PORT:
- SPMO reports public portfolio snapshots for Feb/May/Aug/Nov.
- For a Mar rebalance we need the first post-rebalance public snapshot: May 31,
  normally filed in Jul.
- For a Sep rebalance we need Nov 30, normally filed in Jan of the next year.
So only Jan/Jul NPORT-P candidates need inspection.

Legacy filings are much less frequent and are scanned separately.
"""
import re, time
from pathlib import Path
import pandas as pd
import requests
import backtest_efts as bt

UA=bt.UA


def sec_get(url, **kw):
    # Explicit pacing on every SEC request; do not depend on response latency.
    r=bt.get(url, **kw)
    time.sleep(0.14)
    return r


def period_from_text(txt):
    for p in [
        r'<repPdDate>\s*(\d{4}-\d{2}-\d{2})\s*</repPdDate>',
        r'<reportDate>\s*(\d{4}-\d{2}-\d{2})\s*</reportDate>',
        r'CONFORMED PERIOD OF REPORT:\s*(\d{8})',
    ]:
        m=re.search(p,txt,re.I)
        if m:return pd.to_datetime(m.group(1),errors='coerce')
    return pd.NaT


def target_report_date_for_rb(rb):
    if rb.month==3:return pd.Timestamp(rb.year,5,31)
    return pd.Timestamp(rb.year,11,30)


def master_rows(year, q):
    u=f'https://www.sec.gov/Archives/edgar/full-index/{year}/QTR{q}/master.idx'
    txt=sec_get(u).text
    rows=[]
    prefix=str(int(bt.CIK))+'|'
    for line in txt.splitlines():
        if not line.startswith(prefix):continue
        p=line.split('|')
        if len(p)!=5:continue
        cik,company,form,filed,filename=p
        rows.append(dict(company=company,form=form,filingDate=pd.to_datetime(filed),filename=filename))
    return rows


def primary_xml_url(filename):
    # master filename: edgar/data/1378872/0001752724-25-180531.txt
    adsh=Path(filename).stem
    folder=adsh.replace('-','')
    return adsh, f'https://www.sec.gov/Archives/edgar/data/{int(bt.CIK)}/{folder}/primary_doc.xml'


def full_submission_url(filename):
    return 'https://www.sec.gov/Archives/'+filename


def build_inventory():
    rbs=bt.rebalances()
    targets={target_report_date_for_rb(rb) for rb in rbs if rb.year>=2019}
    rows=[]

    # Read each quarterly index once.
    allidx=[]
    for y in range(2016,2027):
        for q in range(1,5):
            if pd.Timestamp(y,3*(q-1)+1,1)>bt.END+pd.Timedelta(days=180):continue
            try: allidx.extend(master_rows(y,q))
            except Exception as e: print('MASTER_FAIL',y,q,repr(e))
    print('CIK_INDEX_ROWS',len(allidx))

    # Modern: only Jan/Jul NPORT-P filings. Fetch small primary_doc.xml first.
    modern=[r for r in allidx if r['form']=='NPORT-P' and r['filingDate'].month in (1,7) and r['filingDate'].year>=2020]
    print('MODERN_CANDIDATES',len(modern))
    for i,r in enumerate(modern,1):
        adsh,u=primary_xml_url(r['filename'])
        try:
            resp=requests.get(u,headers=UA,timeout=30)
            time.sleep(0.14)
            if resp.status_code!=200:continue
            txt=resp.text
        except Exception:continue
        if bt.SERIES.lower() not in txt.lower() and 'invesco s&p 500 momentum etf' not in txt.lower():continue
        rep=period_from_text(txt)
        if pd.isna(rep) or rep not in targets:continue
        rows.append(dict(accessionNumber=adsh,form='NPORT-P',filingDate=r['filingDate'],reportDate=rep,source_url=u))
        print('MODERN_SPMO',rep.date(),adsh)

    # Legacy through 2019: N-Q/N-CSR/N-CSRS are trust-wide but low frequency.
    # Scan filings whose filing dates are plausibly after Mar/Sep rebalances.
    legacy=[]
    for r in allidx:
        if r['form'] not in {'N-Q','N-CSR','N-CSRS'} or r['filingDate'].year>2019:continue
        if r['filingDate'].month not in {1,2,4,5,6,7,10,11,12}:continue
        legacy.append(r)
    print('LEGACY_CANDIDATES',len(legacy))
    for r in legacy:
        adsh=Path(r['filename']).stem
        u=full_submission_url(r['filename'])
        try:txt=sec_get(u).text
        except Exception:continue
        low=txt.lower()
        if not any(n.lower() in low for n in bt.NAMES):continue
        rep=period_from_text(txt)
        if pd.isna(rep):continue
        # Keep only reports close enough to any rebalance to be selected later.
        if not any(rb<=rep<=rb+pd.Timedelta(days=100) for rb in rbs if rb.year<=2019):continue
        rows.append(dict(accessionNumber=adsh,form=r['form'],filingDate=r['filingDate'],reportDate=rep,source_url=u))
        print('LEGACY_SPMO',r['form'],rep.date(),adsh)

    df=pd.DataFrame(rows)
    if df.empty:raise RuntimeError('No SPMO filings found')
    df=df.drop_duplicates('accessionNumber').sort_values(['reportDate','filingDate'])
    df.to_csv(bt.OUT/'targeted_filings.csv',index=False)
    print('TARGETED_FILINGS',len(df))
    print(df[['form','reportDate','filingDate','accessionNumber']].to_string(index=False))
    return df


if __name__=='__main__':
    bt.filing_inventory=build_inventory
    bt.main()
