#!/usr/bin/env python3
from pathlib import Path
import duckdb

OUT=Path('spmo-hf/filings-output'); OUT.mkdir(parents=True,exist_ok=True)
ROOT='hf://datasets/trader298/sec-nport'
con=duckdb.connect()
con.execute('INSTALL httpfs'); con.execute('LOAD httpfs')
sql=f"""
SELECT f.ACCESSION_NUMBER,f.SERIES_NAME,f.SERIES_ID,f.NET_ASSETS,
       s.FILING_DATE,s.SUB_TYPE,s.REPORT_ENDING_PERIOD,s.REPORT_DATE,s.IS_LAST_FILING,
       f.year,f.quarter
FROM '{ROOT}/FUND_REPORTED_INFO/**/*.parquet' f
JOIN '{ROOT}/SUBMISSION/**/*.parquet' s USING (ACCESSION_NUMBER)
WHERE f.SERIES_ID='S000050154' AND month(s.REPORT_DATE) IN (5,11)
ORDER BY s.REPORT_DATE,s.FILING_DATE,f.ACCESSION_NUMBER
"""
df=con.execute(sql).fetchdf()
print('ROWS',len(df),flush=True)
print(df.to_string(index=False),flush=True)
df.to_csv(OUT/'spmo_target_filings.csv',index=False)
