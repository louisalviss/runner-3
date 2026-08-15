#!/usr/bin/env python3
import re, sys, time, zipfile
from pathlib import Path
import pandas as pd
import requests
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'spmo-backtest'))
import backtest_efts as bt

ZIP=Path('MasterIndex_20260318.zip')
S=requests.Session(); S.headers.update(bt.UA)
TARGET_RBS=[x for x in bt.rebalances() if pd.Timestamp('2019-09-20') <= x <= pd.Timestamp('2025-03-21')]
PRIMARY={}
ORIG_SUBMISSION=bt.submission_url

def report_target(rb):
    return pd.Timestamp(rb.year,5,31) if rb.month==3 else pd.Timestamp(rb.year,11,30)

def load_rows():
    out=[]
    with zipfile.ZipFile(ZIP) as z:
        for name in z.namelist():
            b=Path(name).name
            m=re.match(r'master_(\d{4})_QTR([1-4])\.idx$',b,re.I)
            if not m: continue
            y=int(m.group(1))
            if not 2019 <= y <= 2025: continue
            txt=z.read(name).decode('latin-1','replace')
            for line in txt.splitlines():
                if not line.startswith('1378872|'):continue
                p=line.split('|')
                if len(p)==5 and p[2]=='NPORT-P':
                    out.append({'filed':pd.Timestamp(p[3]),'filename':p[4]})
    return out

def primary_url(filename):
    adsh=Path(filename).stem; folder=adsh.replace('-','')
    return adsh,f'https://www.sec.gov/Archives/edgar/data/1378872/{folder}/primary_doc.xml'

def repdate(txt):
    for pat in [r'<repPdDate>\s*(\d{4}-\d{2}-\d{2})',r'<reportDate>\s*(\d{4}-\d{2}-\d{2})']:
        m=re.search(pat,txt,re.I)
        if m:return pd.Timestamp(m.group(1))
    return pd.NaT

def get_small(url):
    try:
        r=S.get(url,timeout=12)
        if r.status_code==200:return r
        print('HTTP',r.status_code,url,flush=True)
    except Exception as e:
        print('ERR',type(e).__name__,url,flush=True)
    return None

def inventory():
    rows=load_rows(); print('MIRROR_NPORT_ROWS',len(rows),flush=True)
    found=[]; total_http=0; ok_http=0
    for rb in TARGET_RBS:
        target=report_target(rb)
        expected_file_month=7 if target.month==5 else 1
        expected_file_year=target.year if target.month==5 else target.year+1
        cand=[r for r in rows if r['filed'].year==expected_file_year and r['filed'].month==expected_file_month]
        cand=[r for r in cand if 45 <= (r['filed']-target).days <= 75]
        print('TARGET',rb.date(),target.date(),'candidates',len(cand),flush=True)
        hit=None
        for j,x in enumerate(cand,1):
            adsh,u=primary_url(x['filename'])
            total_http+=1
            r=get_small(u); time.sleep(.16)
            if r is None:continue
            ok_http+=1
            low=r.text.lower()
            if bt.SERIES.lower() not in low and 'invesco s&p 500 momentum etf' not in low:continue
            rd=repdate(r.text)
            if pd.isna(rd) or rd!=target:continue
            PRIMARY[adsh]=u
            hit={'accessionNumber':adsh,'form':'NPORT-P','filingDate':x['filed'],'reportDate':rd}
            print('FOUND',rb.date(),adsh,'candidate',j,'/',len(cand),flush=True)
            break
        if hit:found.append(hit)
        else:print('MISS',rb.date(),flush=True)
        # If the runner is globally blocked, stop immediately and get a fresh runner.
        if total_http>=12 and ok_http==0:
            raise RuntimeError('SEC Archives blocked on this runner: first 12 primary XML requests all failed')
    df=pd.DataFrame(found)
    if len(df):df.to_csv(bt.OUT/'modern_mirror_filings.csv',index=False)
    print('FOUND_TOTAL',len(df),'/',len(TARGET_RBS),'HTTP_OK',ok_http,'/',total_http,flush=True)
    return df

def submission(adsh):
    return PRIMARY.get(adsh,ORIG_SUBMISSION(adsh))

if __name__=='__main__':
    bt.rebalances=lambda: TARGET_RBS
    bt.START=TARGET_RBS[0]
    bt.END=pd.Timestamp('2025-09-19')
    bt.filing_inventory=inventory
    bt.submission_url=submission
    bt.main()
