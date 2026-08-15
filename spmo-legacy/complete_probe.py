#!/usr/bin/env python3
import requests,re
acc='0001193125-16-644489';f=acc.replace('-','')
u=f'https://r.jina.ai/https://www.sec.gov/Archives/edgar/data/1378872/{f}/{acc}.txt'
r=requests.get(u,timeout=180)
print('status',r.status_code,'bytes',len(r.content),flush=True)
t=r.text
for p in ['PowerShares S&P 500 Momentum Portfolio','(SPMO)','Common Stocks','Total Investments']:
 print(p,t.lower().count(p.lower()),t.lower().find(p.lower()),flush=True)
 i=t.lower().find(p.lower())
 if i>=0: print(t[i:i+1500],flush=True)
