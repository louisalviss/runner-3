#!/usr/bin/env python3
import duckdb
con=duckdb.connect();con.execute('INSTALL httpfs');con.execute('LOAD httpfs')
root='hf://datasets/paperswithbacktest/Stocks-Daily-Price/**/*.parquet'
for t in ['PXD','FISV','ATVI','HES','SIVB','DFS','FRC','CTRA','MRO']:
    try:
        d=con.execute(f"""SELECT symbol,date,open,high,low,close,adj_close,volume
                          FROM '{root}'
                          WHERE symbol='{t}' AND date BETWEEN '2019-01-01' AND '2026-04-01'
                          ORDER BY date""").fetchdf()
        print(t,'rows',len(d),'first',None if d.empty else d.date.iloc[0], 'last',None if d.empty else d.date.iloc[-1],flush=True)
        if t=='PXD' and len(d):
            print(d[d.date.isin(['2022-09-16','2022-09-19','2022-11-30','2023-03-17','2023-03-20'])].to_string(index=False),flush=True)
    except Exception as e:
        print(t,'ERR',type(e).__name__,str(e)[:500],flush=True)
