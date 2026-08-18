#!/usr/bin/env python3
import requests
url='https://r.jina.ai/https://www.sec.gov/cgi-bin/browse-edgar?CIK=S000050154&action=getcompany&count=100&start=100'
r=requests.get(url,timeout=90,headers={'User-Agent':'runner-3 spmo research'}); print('status',r.status_code,'len',len(r.text)); r.raise_for_status()
for line in r.text.splitlines():
 u=line.upper()
 if any(x in u for x in ['NPORT-P','N-Q','N-CSR','N-CSRS']): print(line[:3000])
