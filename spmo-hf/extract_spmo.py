#!/usr/bin/env python3
from pathlib import Path
import duckdb
import pandas as pd

OUT=Path('spmo-hf/output'); OUT.mkdir(parents=True,exist_ok=True)
SERIES='S000050154'
ROOT='hf://datasets/trader298/sec-nport'

con=duckdb.connect()
con.execute('INSTALL httpfs')
con.execute('LOAD httpfs')

info=f"{ROOT}/FUND_REPORTED_INFO/**/*.parquet"
sub=f"{ROOT}/SUBMISSION/**/*.parquet"

q=f"""
WITH f AS (
  SELECT ACCESSION_NUMBER,SERIES_NAME,SERIES_ID,NET_ASSETS,year,quarter
  FROM '{info}'
  WHERE SERIES_ID='{SERIES}'
), s AS (
  SELECT ACCESSION_NUMBER,FILING_DATE,SUB_TYPE,REPORT_ENDING_PERIOD,REPORT_DATE,
         IS_LAST_FILING,year,quarter
  FROM '{sub}'
)
SELECT f.ACCESSION_NUMBER,f.SERIES_NAME,f.SERIES_ID,f.NET_ASSETS,
       s.FILING_DATE,s.SUB_TYPE,s.REPORT_ENDING_PERIOD,s.REPORT_DATE,s.IS_LAST_FILING,
       f.year,f.quarter
FROM f JOIN s USING (ACCESSION_NUMBER)
WHERE month(s.REPORT_DATE) IN (5,11)
ORDER BY s.REPORT_DATE,s.FILING_DATE,f.ACCESSION_NUMBER
"""
filings=con.execute(q).fetchdf()
print('SPMO_TARGET_FILINGS',len(filings),flush=True)
print(filings.to_string(index=False),flush=True)
filings.to_csv(OUT/'spmo_filings.csv',index=False)

filings['REPORT_DATE']=pd.to_datetime(filings['REPORT_DATE'])
filings['FILING_DATE']=pd.to_datetime(filings['FILING_DATE'])
filings['last_rank']=(filings['IS_LAST_FILING'].astype(str).str.upper()=='Y').astype(int)
canon=(filings.sort_values(['REPORT_DATE','last_rank','FILING_DATE','ACCESSION_NUMBER'])
       .groupby('REPORT_DATE',as_index=False).tail(1)
       .sort_values('REPORT_DATE').reset_index(drop=True))
canon.to_csv(OUT/'spmo_filings_canonical.csv',index=False)
print('\nCANONICAL_TARGETS',len(canon),flush=True)
print(canon[['REPORT_DATE','FILING_DATE','ACCESSION_NUMBER','NET_ASSETS','year','quarter']].to_string(index=False),flush=True)

all_hold=[]
for _,r in canon.iterrows():
    y=int(r['year']); qtr=int(r['quarter']); acc=r['ACCESSION_NUMBER']
    hp=f"{ROOT}/FUND_REPORTED_HOLDING/year={y}/quarter={qtr}/*.parquet"
    ip=f"{ROOT}/IDENTIFIERS/year={y}/quarter={qtr}/*.parquet"
    sql=f"""
    SELECT h.ACCESSION_NUMBER,h.HOLDING_ID,h.ISSUER_NAME,h.ISSUER_TITLE,h.ISSUER_CUSIP,
           h.BALANCE,h.UNIT,h.CURRENCY_CODE,h.CURRENCY_VALUE,h.PERCENTAGE,h.ASSET_CAT,
           h.ISSUER_TYPE,h.INVESTMENT_COUNTRY,h.FAIR_VALUE_LEVEL,
           i.IDENTIFIER_ISIN,i.IDENTIFIER_TICKER,
           DATE '{r['REPORT_DATE'].date()}' AS REPORT_DATE,
           {y}::INTEGER AS source_year,{qtr}::INTEGER AS source_quarter
    FROM '{hp}' h
    LEFT JOIN '{ip}' i USING (HOLDING_ID)
    WHERE h.ACCESSION_NUMBER='{acc}'
    ORDER BY h.CURRENCY_VALUE DESC NULLS LAST,h.HOLDING_ID
    """
    d=con.execute(sql).fetchdf()
    print('HOLDINGS',r['REPORT_DATE'].date(),acc,'rows',len(d),'equities',int((d.ASSET_CAT=='EC').sum()) if len(d) else 0,flush=True)
    all_hold.append(d)

holdings=pd.concat(all_hold,ignore_index=True) if all_hold else pd.DataFrame()
holdings.to_csv(OUT/'spmo_holdings.csv',index=False)
print('TOTAL_HOLDING_ROWS',len(holdings),flush=True)

if len(holdings):
    eq=holdings[holdings.ASSET_CAT.eq('EC')].copy()
    eq['rank']=eq.groupby('REPORT_DATE')['CURRENCY_VALUE'].rank(method='first',ascending=False)
    top=eq[eq['rank']<=5].sort_values(['REPORT_DATE','rank'])
    top[['REPORT_DATE','rank','ISSUER_NAME','IDENTIFIER_TICKER','ISSUER_CUSIP','BALANCE','CURRENCY_VALUE','PERCENTAGE']].to_csv(OUT/'spmo_reported_top5.csv',index=False)
    print('\nREPORTED_TOP5\n',top[['REPORT_DATE','rank','ISSUER_NAME','IDENTIFIER_TICKER','CURRENCY_VALUE','PERCENTAGE']].to_string(index=False),flush=True)
