#!/usr/bin/env python3
from pathlib import Path
import duckdb
import pandas as pd

OUT=Path('spmo-hf/filings-output'); OUT.mkdir(parents=True,exist_ok=True)
ROOT='hf://datasets/trader298/sec-nport'
SERIES='S000050154'
con=duckdb.connect(); con.execute('INSTALL httpfs'); con.execute('LOAD httpfs')

targets=[]
for y in range(2019,2026): targets.append((pd.Timestamp(y,11,30),y+1,1))
for y in range(2020,2026): targets.append((pd.Timestamp(y,5,31),y,3))
targets=sorted(targets)
rows=[]
for d,y,q in targets:
    info=f"{ROOT}/FUND_REPORTED_INFO/year={y}/quarter={q}/*.parquet"
    sub=f"{ROOT}/SUBMISSION/year={y}/quarter={q}/*.parquet"
    sql=f"""
    SELECT f.ACCESSION_NUMBER,f.SERIES_NAME,f.SERIES_ID,f.NET_ASSETS,
           s.FILING_DATE,s.SUB_TYPE,s.REPORT_ENDING_PERIOD,s.REPORT_DATE,s.IS_LAST_FILING,
           f.year,f.quarter
    FROM '{info}' f JOIN '{sub}' s USING (ACCESSION_NUMBER)
    WHERE f.SERIES_ID='{SERIES}' AND s.REPORT_DATE=DATE '{d.date()}'
    ORDER BY s.FILING_DATE,f.ACCESSION_NUMBER
    """
    try: df=con.execute(sql).fetchdf()
    except Exception as e:
        print('TARGET_FAIL',d.date(),y,q,type(e).__name__,str(e)[:300],flush=True); continue
    print('TARGET',d.date(),'partition',y,q,'rows',len(df),flush=True)
    if len(df):
        print(df.to_string(index=False),flush=True)
        rows.append(df)
out=pd.concat(rows,ignore_index=True) if rows else pd.DataFrame()
print('TOTAL_ROWS',len(out),flush=True)
out.to_csv(OUT/'spmo_target_filings.csv',index=False)
