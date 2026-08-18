#!/usr/bin/env python3
import re,requests
ACC='0001752724-19-086759'
DOC='ETF_Trust_II.htm'
url=f'https://r.jina.ai/https://www.sec.gov/Archives/edgar/data/1378872/{ACC.replace("-","")}/{DOC}'
r=requests.get(url,timeout=300,headers={'User-Agent':'runner-3 SPMO research'})
print('FETCH',r.status_code,'LEN',len(r.text)); r.raise_for_status(); t=r.text
low=t.lower(); needles=['invesco s&p 500 momentum etf','s&p 500 momentum','spmo']
for n in needles:
    pos=[m.start() for m in re.finditer(re.escape(n),low)]
    print('NEEDLE',n,'COUNT',len(pos),'POS',pos[:20])
    for j in pos[:3]:
        print('\n--- CONTEXT',n,j,'---\n',t[max(0,j-3000):j+18000])
