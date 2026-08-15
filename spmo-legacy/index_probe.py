#!/usr/bin/env python3
import requests,re
for acc in ['0001193125-16-644489','0001193125-17-221822','0001193125-18-214392']:
 f=acc.replace('-','')
 u=f'https://r.jina.ai/https://www.sec.gov/Archives/edgar/data/1378872/{f}/{acc}-index.htm'
 t=requests.get(u,timeout=90).text
 print('\n###',acc,'bytes',len(t),flush=True)
 for line in t.splitlines():
  if '.htm' in line.lower() or 'N-CSRS' in line.upper() or 'Document Format' in line:
   print(line[:1000],flush=True)
