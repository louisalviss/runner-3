#!/usr/bin/env python3
import requests,re
u='https://r.jina.ai/https://www.sec.gov/Archives/edgar/data/1378872/000137887226001362/primary_doc.xml'
r=requests.get(u,timeout=120)
print('status',r.status_code,'bytes',len(r.content),'ctype',r.headers.get('content-type'),flush=True)
t=r.text
for p in ['S000050154','Invesco S&P 500 Momentum ETF','invstOrSec','Micron','NVIDIA']:
 print(p,t.lower().count(p.lower()),t.lower().find(p.lower()),flush=True)
 i=t.lower().find(p.lower())
 if i>=0:print(t[max(0,i-500):i+2000],flush=True)
open('spmo-2026-jina.txt','w').write(t)
