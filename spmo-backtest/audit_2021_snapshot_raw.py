#!/usr/bin/env python3
import requests,re,json
from bs4 import BeautifulSoup
ACC='000175272421161170'
H={'User-Agent':'SPMO research audit contact@example.com'}

def get(u):
 r=requests.get(u,headers=H,timeout=60); print('GET',r.status_code,len(r.content),u); return r

base=None; idx=None
for cik in ['1378872','1752724']:
 u=f'https://www.sec.gov/Archives/edgar/data/{cik}/{ACC}/index.json'
 r=get(u)
 if r.status_code==200:
  base=u.rsplit('/',1)[0]; idx=r.json(); break
if not idx: raise SystemExit('index not found')
items=idx['directory']['item']; print('FILES',[(x['name'],x.get('size')) for x in items])

texts=[]
for x in items:
 n=x['name']
 if not n.lower().endswith(('.xml','.htm','.html','.txt')): continue
 r=get(base+'/'+n)
 if r.status_code!=200: continue
 tx=r.text
 score=sum(w.lower() in tx.lower() for w in ['SPMO','S000050154','Apple','Amazon','Microsoft'])
 print('FILE_SCORE',n,score)
 if score: texts.append((score,n,tx))
if not texts: raise SystemExit('no relevant docs')
texts.sort(reverse=True,key=lambda x:x[0])
for score,n,tx in texts:
 print('\n===== DOC',n,'score',score,'=====')
 # text normalized for context
 soup=BeautifulSoup(tx,'lxml-xml' if n.endswith('.xml') else 'lxml')
 plain=' '.join(soup.stripped_strings)
 for target in ['SPMO','S000050154','Apple','Amazon','Microsoft']:
  poss=[m.start() for m in re.finditer(target,plain,re.I)]
  print('TARGET',target,'COUNT',len(poss))
  for p in poss[:8]: print('CTX',repr(plain[max(0,p-350):p+550]))
 # For XML print investment nodes containing target names.
 if n.endswith('.xml'):
  for inv in soup.find_all(lambda tag: tag.name and tag.name.lower().endswith('invstorsec')):
   s=' '.join(inv.stripped_strings)
   if any(t.lower() in s.lower() for t in ['Apple','Amazon','Microsoft']): print('INV_NODE',s)
