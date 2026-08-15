#!/usr/bin/env python3
"""Run the SPMO backtest without data.sec.gov/EFTS.

Build filing inventory from SEC's static EDGAR full-index master.idx files, then
reuse the parsing/ranking/price logic in backtest_efts.py.
"""
import re
import time
from pathlib import Path

import pandas as pd

import backtest_efts as bt

FORMS={'NPORT-P','N-Q','N-CSR','N-CSRS'}


def _candidate_filing_date(d):
    """Only inspect filings plausibly covering one of the 21 rebalance windows."""
    d=pd.Timestamp(d)
    for rb in bt.rebalances():
        # Portfolio report can lag the rebalance and the filing can lag report date.
        if rb-pd.Timedelta(days=10) <= d <= rb+pd.Timedelta(days=175):
            return True
    return False


def _period_from_submission(txt):
    pats=[
        r'CONFORMED PERIOD OF REPORT:\s*(\d{8})',
        r'<reportDate>\s*(\d{4}-\d{2}-\d{2})\s*</reportDate>',
        r'<repPdDate>\s*(\d{4}-\d{2}-\d{2})\s*</repPdDate>',
    ]
    for p in pats:
        m=re.search(p,txt,re.I)
        if m:
            return pd.to_datetime(m.group(1),errors='coerce')
    return pd.NaT


def _is_spmo(txt,form):
    low=txt.lower()
    if form=='NPORT-P':
        return bt.SERIES.lower() in low or 'invesco s&p 500 momentum etf' in low
    return any(n.lower() in low for n in bt.NAMES)


def filing_inventory_static():
    raw=[]
    # Need indices through 2026; Sep rebalances can have filings in following Q1,
    # but our final rebalance is Mar-2026.
    for y in range(2016,2027):
        for q in range(1,5):
            # Avoid future quarter directories relative to the research end date.
            q_start=pd.Timestamp(y,3*(q-1)+1,1)
            if q_start > bt.END + pd.Timedelta(days=180):
                continue
            url=f'https://www.sec.gov/Archives/edgar/full-index/{y}/QTR{q}/master.idx'
            try:
                text=bt.get(url).text
            except Exception as e:
                print('MASTER_FAIL',url,repr(e)); continue
            n=0
            for line in text.splitlines():
                if not line.startswith(str(int(bt.CIK))+'|'):
                    continue
                parts=line.split('|')
                if len(parts)!=5:
                    continue
                cik,company,form,filed,filename=parts
                if form not in FORMS:
                    continue
                fd=pd.to_datetime(filed,errors='coerce')
                if pd.isna(fd) or not _candidate_filing_date(fd):
                    continue
                raw.append({'form':form,'filingDate':fd,'filename':filename,'company':company})
                n+=1
            if n:
                print('MASTER',y,q,'candidates',n)

    print('STATIC_CANDIDATES',len(raw))
    rows=[]
    seen=set()
    for i,r in enumerate(raw,1):
        filename=r['filename']
        if filename in seen: continue
        seen.add(filename)
        url='https://www.sec.gov/Archives/'+filename
        try:
            txt=bt.get(url).text
        except Exception as e:
            print('SUBMISSION_FAIL',url,repr(e)); continue
        if not _is_spmo(txt,r['form']):
            continue
        report=_period_from_submission(txt)
        if pd.isna(report):
            print('NO_PERIOD',url); continue
        adsh=Path(filename).stem
        rows.append({'accessionNumber':adsh,'form':r['form'],
                     'filingDate':r['filingDate'],'reportDate':report,
                     'filename':filename,'url':url})
        print('SPMO_FILING',r['form'],report.date(),r['filingDate'].date(),adsh)
        # Stay comfortably below SEC's published request-rate ceiling.
        time.sleep(.13)

    df=pd.DataFrame(rows)
    if df.empty:
        raise RuntimeError('Static SEC inventory found no SPMO filings')
    df=df.drop_duplicates('accessionNumber').sort_values(['reportDate','filingDate'])
    df.to_csv(bt.OUT/'static_filings.csv',index=False)
    print('STATIC_SPMO_FILINGS',len(df))
    print(df[['form','reportDate','filingDate','accessionNumber']].to_string(index=False))
    return df


if __name__=='__main__':
    bt.filing_inventory=filing_inventory_static
    bt.main()
