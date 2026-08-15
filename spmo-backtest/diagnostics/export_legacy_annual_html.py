#!/usr/bin/env python3
import re
from pathlib import Path
import requests
ACC='0001193125-17-002614'
compact=ACC.replace('-','')
url=f'https://r.jina.ai/https://www.sec.gov/Archives/edgar/data/1378872/{compact}/{ACC}.txt'
for attempt in range(5):
    r=requests.get(url,timeout=300,headers={'User-Agent':'runner-3 spmo research'})
    print('attempt',attempt+1,'status',r.status_code,'len',len(r.text))
    if r.status_code==200: break
else: r.raise_for_status()
raw=r.text; count=0
for di,doc in enumerate(re.findall(r'<DOCUMENT>(.*?)</DOCUMENT>',raw,re.S|re.I)):
    if 's&p 500 momentum' not in doc.lower() and 'spmo' not in doc.lower(): continue
    m=re.search(r'<TEXT>(.*)</TEXT>',doc,re.S|re.I); html=m.group(1) if m else doc
    p=Path(f'/tmp/annual_doc_{di}.html'); p.write_text(html,encoding='utf-8'); print('WROTE',p,len(html)); count+=1
if not count: raise RuntimeError('No annual document with SPMO markers')
