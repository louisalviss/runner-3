#!/usr/bin/env python3
import re
from pathlib import Path
import requests
ACC='0001193125-16-644489'
compact=ACC.replace('-','')
url=f'https://r.jina.ai/https://www.sec.gov/Archives/edgar/data/1378872/{compact}/{ACC}.txt'
r=requests.get(url,timeout=300,headers={'User-Agent':'runner-3 spmo research'}); r.raise_for_status()
raw=r.text
needles=['s&p 500 momentum','spmo']
count=0
for di,doc in enumerate(re.findall(r'<DOCUMENT>(.*?)</DOCUMENT>',raw,re.S|re.I)):
    if not any(n in doc.lower() for n in needles): continue
    textm=re.search(r'<TEXT>(.*)</TEXT>',doc,re.S|re.I)
    html=textm.group(1) if textm else doc
    p=Path(f'/tmp/legacy_doc_{di}.html'); p.write_text(html,encoding='utf-8'); print('WROTE',p,len(html)); count+=1
if count==0: raise RuntimeError('No legacy document containing SPMO markers found')
