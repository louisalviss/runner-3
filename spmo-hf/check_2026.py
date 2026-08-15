#!/usr/bin/env python3
import duckdb
ROOT='hf://datasets/trader298/sec-nport'
c=duckdb.connect();c.execute('INSTALL httpfs');c.execute('LOAD httpfs')
for q in [2,3,4]:
 try:
  p=f'{ROOT}/FUND_REPORTED_INFO/year=2026/quarter={q}/*.parquet';s=f'{ROOT}/SUBMISSION/year=2026/quarter={q}/*.parquet'
  d=c.execute(f"SELECT f.ACCESSION_NUMBER,f.SERIES_NAME,s.FILING_DATE,s.REPORT_DATE,f.NET_ASSETS FROM '{p}' f JOIN '{s}' s USING(ACCESSION_NUMBER) WHERE f.SERIES_ID='S000050154' AND s.REPORT_DATE=DATE '2026-05-31'").fetchdf()
  print('Q',q,'rows',len(d),flush=True);print(d.to_string(index=False),flush=True)
 except Exception as e:print('Q',q,'ERR',type(e).__name__,str(e)[:400],flush=True)
