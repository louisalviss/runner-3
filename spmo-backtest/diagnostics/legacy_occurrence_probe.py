#!/usr/bin/env python3
import re
from pathlib import Path
import requests
from bs4 import BeautifulSoup
ACC='0001193125-16-644489'
compact=ACC.replace('-','')
url=f'https://r.jina.ai/https://www.sec.gov/Archives/edgar/data/1378872/{compact}/{ACC}.txt'
r=requests.get(url,timeout=240,headers={'User-Agent':'runner-3 spmo research'}); r.raise_for_status(); raw=r.text
out=[f'FETCH status={r.status_code} len={len(raw)}']
needle='PowerShares S&P 500 Momentum Portfolio'
for di,doc in enumerate(re.findall(r'<DOCUMENT>(.*?)</DOCUMENT>',raw,re.S|re.I)):
    if needle.lower() not in doc.lower(): continue
    fn=re.search(r'<FILENAME>([^\n<]+)',doc,re.I); typ=re.search(r'<TYPE>([^\n<]+)',doc,re.I)
    textm=re.search(r'<TEXT>(.*)</TEXT>',doc,re.S|re.I); html=textm.group(1) if textm else doc
    soup=BeautifulSoup(html,'lxml'); clean=' '.join(soup.stripped_strings)
    out.append(f'=== DOC {di} type={typ.group(1).strip() if typ else ""} file={fn.group(1).strip() if fn else ""} clean_len={len(clean)} ===')
    low=clean.lower(); n=needle.lower(); pos=[]; st=0
    while True:
        j=low.find(n,st)
        if j<0: break
        pos.append(j); st=j+len(n)
    out.append('OCCURRENCES '+repr(pos))
    for k,j in enumerate(pos):
        out.append(f'\n--- OCC {k} POS={j} ---')
        out.append(clean[max(0,j-1800):min(len(clean),j+9000)])
Path('/tmp/legacy_occurrences.txt').write_text('\n'.join(out),encoding='utf-8')
print('WROTE occurrences',sum(x.startswith('--- OCC') for x in out),'bytes',len('\n'.join(out)))
