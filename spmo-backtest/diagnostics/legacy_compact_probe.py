#!/usr/bin/env python3
import re
from io import StringIO
from pathlib import Path
import requests
import pandas as pd
from bs4 import BeautifulSoup

ACC='0001193125-16-644489'
compact=ACC.replace('-','')
url=f'https://r.jina.ai/https://www.sec.gov/Archives/edgar/data/1378872/{compact}/{ACC}.txt'
r=requests.get(url,timeout=240,headers={'User-Agent':'runner-3 spmo research'})
r.raise_for_status(); raw=r.text
print('FETCH',r.status_code,'LEN',len(raw))
needles=['PowerShares S&P 500 Momentum','S&P 500 Momentum Portfolio','S&P 500 Momentum','SPMO']
docs=re.findall(r'<DOCUMENT>(.*?)</DOCUMENT>',raw,re.S|re.I)
print('DOCS',len(docs))
out=[]
for di,doc in enumerate(docs):
    low=doc.lower()
    if not any(n.lower() in low for n in needles):
        continue
    typ=re.search(r'<TYPE>([^\n<]+)',doc,re.I)
    fn=re.search(r'<FILENAME>([^\n<]+)',doc,re.I)
    out.append(f'=== DOCUMENT {di} TYPE={typ.group(1).strip() if typ else ""} FILE={fn.group(1).strip() if fn else ""} LEN={len(doc)} ===')
    textm=re.search(r'<TEXT>(.*)</TEXT>',doc,re.S|re.I)
    html=textm.group(1) if textm else doc
    soup=BeautifulSoup(html,'lxml')
    clean=' '.join(soup.stripped_strings)
    for needle in needles:
        j=clean.lower().find(needle.lower())
        if j>=0:
            out.append(f'NEEDLE={needle} POS={j}')
            out.append(clean[max(0,j-1200):j+8000])
            break
    # Table summaries: keep tables containing phrase and following 8 tables.
    tables=soup.find_all('table')
    hit_idxs=[]
    for i,t in enumerate(tables):
        tx=' '.join(t.stripped_strings)
        if any(n.lower() in tx.lower() for n in needles): hit_idxs.append(i)
    out.append(f'TABLE_COUNT={len(tables)} HIT_TABLES={hit_idxs[:20]}')
    chosen=set()
    for h in hit_idxs[:5]:
        for i in range(max(0,h-1),min(len(tables),h+9)): chosen.add(i)
    for i in sorted(chosen):
        tx=' | '.join(tables[i].stripped_strings)
        out.append(f'--- TABLE {i} ---')
        out.append(tx[:12000])
    # pandas table parse previews
    try:
        dfs=pd.read_html(StringIO(html))
        out.append(f'PANDAS_TABLES={len(dfs)}')
        for i,df in enumerate(dfs):
            s=df.astype(str).to_string(index=False)
            if any(n.lower() in s.lower() for n in needles):
                out.append(f'+++ PANDAS HIT {i} shape={df.shape} +++')
                out.append(s[:16000])
                for k in range(i+1,min(len(dfs),i+8)):
                    out.append(f'+++ PANDAS NEXT {k} shape={dfs[k].shape} +++')
                    out.append(dfs[k].astype(str).to_string(index=False)[:16000])
    except Exception as e:
        out.append('PANDAS_ERROR '+repr(e))

Path('/tmp').mkdir(exist_ok=True)
Path('/tmp/legacy_compact_probe.txt').write_text('\n'.join(out),encoding='utf-8')
print('WROTE',len('\n'.join(out)))
