#!/usr/bin/env python3
import io, requests, pandas as pd, yfinance as yf
URL='https://raw.githubusercontent.com/fja05680/sp500/master/S%26P%20500%20Historical%20Components%20%26%20Changes.csv'
r=requests.get(URL,timeout=60); print('membership status',r.status_code,'bytes',len(r.content)); print(r.text[:1000])
try:
    df=pd.read_csv(io.BytesIO(r.content)); print('columns',df.columns.tolist(),'rows',len(df)); print(df.head(3).to_string()); print(df.tail(3).to_string())
except Exception as e: print('membership parse err',repr(e))
for t in ['MSFT','CSCO','GE','XOM','INTC','WMT']:
    print('\n###',t)
    try:
      s=yf.Ticker(t).get_shares_full(start='1998-01-01',end='2005-01-01')
      print('shares type',type(s),'len',0 if s is None else len(s))
      if s is not None and len(s): print(s.head().to_string()); print(s.tail().to_string())
    except Exception as e: print('shares err',repr(e))
    try:
      h=yf.download(t,start='1998-01-01',end='2005-01-01',auto_adjust=False,progress=False,threads=False)
      print('price rows',len(h),'first',h.head(1).to_string(),'last',h.tail(1).to_string())
    except Exception as e: print('price err',repr(e))
