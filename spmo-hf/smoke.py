#!/usr/bin/env python3
import duckdb

con=duckdb.connect()
con.execute("INSTALL httpfs")
con.execute("LOAD httpfs")
paths={
    'submission':'hf://datasets/trader298/sec-nport/SUBMISSION/year=2024/quarter=1/*.parquet',
    'fund_info':'hf://datasets/trader298/sec-nport/FUND_REPORTED_INFO/year=2024/quarter=1/*.parquet',
    'holding':'hf://datasets/trader298/sec-nport/FUND_REPORTED_HOLDING/year=2024/quarter=1/*.parquet',
    'identifiers':'hf://datasets/trader298/sec-nport/IDENTIFIERS/year=2024/quarter=1/*.parquet',
}
for name,path in paths.items():
    print('\n###',name,path,flush=True)
    try:
        df=con.execute(f"DESCRIBE SELECT * FROM '{path}'").fetchdf()
        print(df.to_string(index=False),flush=True)
        sample=con.execute(f"SELECT * FROM '{path}' LIMIT 2").fetchdf()
        print('SAMPLE',sample.to_dict('records'),flush=True)
    except Exception as e:
        print('ERROR',type(e).__name__,str(e),flush=True)
        raise
