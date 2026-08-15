#!/usr/bin/env python3
import re,time,json
from pathlib import Path
import pandas as pd
import requests

OUT=Path('spmo-legacy7/output');OUT.mkdir(parents=True,exist_ok=True)
# post-rebalance reporting snapshot for each legacy rebalance
SPECS=[
 ('2016-03-18','2016-04-30','0001193125-16-644489'),
 ('2016-09-16','2016-10-31','0001193125-17-002614'),
 ('2017-03-17','2017-04-30','0001193125-17-221822'),
 ('2017-09-15','2017-10-31','0001193125-18-002695'),
 ('2018-03-16','2018-04-30','0001193125-18-214392'),
 ('2018-09-21','2018-10-31','0001193125-19-002456'),
 ('2019-03-15','2019-04-30','0001193125-19-190405'),
]
H={'User-Agent':'Mozilla/5.0'}

def jina(u,timeout=180):
 ju='https://r.jina.ai/'+u
 for i in range(4):
  try:
   r=requests.get(ju,headers=H,timeout=timeout)
   if r.status_code==200 and len(r.text)>200:return r.text,ju
   print('HTTP',r.status_code,'bytes',len(r.content),ju,flush=True)
  except Exception as e:print('ERR',type(e).__name__,str(e)[:200],ju,flush=True)
  time.sleep(2+3*i)
 raise RuntimeError('Jina fetch failed '+u)

def primary_for(acc):
 folder=acc.replace('-','')
 idx=f'https://www.sec.gov/Archives/edgar/data/1378872/{folder}/{acc}-index.htm'
 t,_=jina(idx,90)
 # Jina index table includes the primary N-CSR/N-CSRS htm filename.
 cand=re.findall(r'\b([A-Za-z0-9_-]+dncsr[s]?\.htm)\b',t,re.I)
 if not cand:
  cand=re.findall(r'\b([A-Za-z0-9_-]+ncsr[s]?\.htm)\b',t,re.I)
 if not cand:raise RuntimeError('No NCSR primary doc in '+idx+' head='+t[:3000])
 doc=cand[0]
 return f'https://www.sec.gov/Archives/edgar/data/1378872/{folder}/{doc}',idx,doc

def segment(t):
 pats=[r'Schedule of Investments(?:\([^\n]*\))?\s*\n+\s*(?:PowerShares|Invesco) S&P 500(?:®)? Momentum (?:Portfolio|ETF) \(SPMO\)',
       r'Schedule of Investments(?:\([^\n]*\))?\s*\n+\s*(?:PowerShares|Invesco) S&P 500(?:®)? Momentum[^\n]*\(SPMO\)']
 starts=sorted(set(m.start() for p in pats for m in re.finditer(p,t,re.I)))
 if not starts:raise RuntimeError('No SPMO schedule')
 best=None
 for s in starts:
  m=re.search(r'\nSchedule of Investments(?:\([^\n]*\))?\s*\n',t[s+100:],re.I)
  e=s+100+m.start() if m else min(len(t),s+100000)
  z=t[s:e]
  score=z.count('\t')+1000*('Total Investments' in z)+1000*('Net Assets' in z)
  if best is None or score>best[0]:best=(score,s,e,z)
 print('SEGMENTS',[(s, e, score) for score,s,e,z in [best]],flush=True)
 return best[3]

def parse(z):
 rows=[]
 for line in z.splitlines():
  p=[x.strip() for x in line.replace('\xa0',' ').split('\t')]
  p=[x for x in p if x not in ('','$')]
  if len(p)<3 or not re.fullmatch(r'[\d,]+',p[0]) or not re.fullmatch(r'[\d,]+',p[-1]):continue
  names=[x for x in p[1:-1] if re.search('[A-Za-z]',x)]
  if not names:continue
  name=max(names,key=len)
  name=re.sub(r'\s*\([a-z](?:,[a-z])*\)\s*$','',name,flags=re.I).strip()
  low=name.lower()
  if any(x in low for x in ['common stocks','total investments','net assets','money market fund','other assets less']):continue
  rows.append((int(p[0].replace(',','')),name,int(p[-1].replace(',',''))))
 return pd.DataFrame(rows,columns=['shares','name','value']).drop_duplicates().reset_index(drop=True)

def total(z):
 for pat in [r'Total Common Stocks(?: and Other Equity Interests)?[\s\S]{0,400}?\t\s*\$?\s*([\d,]+)\s*\t',r'Total Investments[\s\S]{0,400}?\t\s*\$?\s*([\d,]+)\s*\t']:
  m=list(re.finditer(pat,z,re.I))
  if m:return int(m[-1].group(1).replace(',',''))
 return None

alls=[];meta=[]
for rb,rd,acc in SPECS:
 print('\nRESOLVE',rb,rd,acc,flush=True)
 u,idx,doc=primary_for(acc);print('PRIMARY',doc,u,flush=True)
 t,relay=jina(u);(OUT/f'raw-{rd}.txt').write_text(t)
 z=segment(t);(OUT/f'segment-{rd}.txt').write_text(z)
 d=parse(z);st=total(z);sm=int(d.value.sum());cov=sm/st if st else None
 print('PARSED',rd,'rows',len(d),'sum',sm,'stated',st,'coverage',cov,flush=True)
 print(d.sort_values('value',ascending=False).head(8).to_string(index=False),flush=True)
 d.insert(0,'rebalance',rb);d.insert(1,'report_date',rd);d['accession']=acc;d['source_url']=u
 d.to_csv(OUT/f'holdings-{rd}.csv',index=False);alls.append(d)
 meta.append({'rebalance':rb,'report_date':rd,'accession':acc,'doc':doc,'rows':len(d),'sum':sm,'stated_total':st,'coverage':cov,'source_url':u})
allh=pd.concat(alls,ignore_index=True);allh.to_csv(OUT/'legacy7_holdings.csv',index=False)
pd.DataFrame(meta).to_csv(OUT/'legacy7_meta.csv',index=False);Path(OUT/'legacy7_meta.json').write_text(json.dumps(meta,indent=2))
bad=[m for m in meta if m['rows']<90 or m['coverage'] is None or not (.985<=m['coverage']<=1.015)]
if bad:raise RuntimeError('GATE_FAIL '+json.dumps(bad))
print('\nALL7_GATE PASS',flush=True)
