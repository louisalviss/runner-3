#!/usr/bin/env python3
import requests,re
url='https://r.jina.ai/https://www.sec.gov/Archives/edgar/data/1378872/000119312517002614/d269293dncsr.htm'
r=requests.get(url,timeout=120)
print('STATUS',r.status_code,'BYTES',len(r.content),'CTYPE',r.headers.get('content-type'),flush=True)
text=r.text
for pat in ['PowerShares S&P 500 Momentum Portfolio','S&P 500 Momentum','SPMO','Microsoft Corp.']:
    print('PAT',pat,'COUNT',text.lower().count(pat.lower()),flush=True)
    i=text.lower().find(pat.lower())
    if i>=0:print(text[max(0,i-500):i+1500],flush=True)
open('spmo-legacy-jina.txt','w').write(text)
