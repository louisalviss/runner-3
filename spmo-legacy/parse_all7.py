#!/usr/bin/env python3
import re,time,json
from pathlib import Path
import pandas as pd
import requests

OUT=Path('spmo-legacy7/output');OUT.mkdir(parents=True,exist_ok=True)
SPECS=[
 ('2016-03-18','2016-04-30','0001193125-16-644489',None),
 ('2016-09-16','2016-10-31','0001193125-17-002614','d269293dncsr.htm'),
 ('2017-03-17','2017-04-30','0001193125-17-221822',None),
 ('2017-09-15','2017-10-31','0001193125-18-002695','d473179dncsr.htm'),
 ('2018-03-16','2018-04-30','0001193125-18-214392',None),
 ('2018-09-21','2018-10-31','0001193125-19-002456','d525171dncsr.htm'),
 ('2019-03-15','2019-04-30','0001193125-19-190405','d740133dncsrs.htm'),
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

def primary_for(acc,known=None):
 folder=acc.replace('-','')
 if known:return f'https://www.sec.gov/Archives/edgar/data/1378872/{folder}/{known}',known
 complete=f'https://www.sec.gov/Archives/edgar/data/1378872/{folder}/{acc}.txt'
 t,_=jina(complete,180)
 blocks=re.findall(r'<DOCUMENT>([\s\S]*?)</DOCUMENT>',t,re.I)
 for b in blocks:
  tm=re.search(r'<TYPE>\s*([^\r\n<]+)',b,re.I)
  fm=re.search(r'<FILENAME>\s*([^\r\n<]+)',b,re.I)
  typ=tm.group(1).strip().upper() if tm else ''
  if fm and typ in ('N-CSRS','N-CSR'):
   doc=fm.group(1).strip()
   print('RESOLVED_FROM_COMPLETE',acc,typ,doc,flush=True)
   return f'https://www.sec.gov/Archives/edgar/data/1378872/{folder}/{doc}',doc
 raise RuntimeError('No N-CSRS/N-CSR document in complete submission '+complete)

def stock_line_count(z):
 n=0
 for line in z.splitlines():
  x=line.replace('\xa0',' ').strip().strip('*')
  if re.match(r'^[\d,]+\s+.+(?:\$)?[\d][\d,]*$',x):n+=1
  elif '\t' in line and re.match(r'^\s*\t?[\d,]+\t',line.replace('\xa0',' ')):n+=1
 return n

def segment(t):
 occ=[m.start() for m in re.finditer(r'(?:PowerShares|Invesco) S&P 500(?:®)? Momentum (?:Portfolio|ETF)[^\n]{0,80}\(SPMO\)',t,re.I)]
 if not occ:raise RuntimeError('No SPMO occurrence')
 candidates=[]
 for s0 in occ:
  line=t[s0:t.find('\n',s0) if t.find('\n',s0)>=0 else s0+300]
  if 'continued' in line.lower():continue
  prev=t.rfind('Schedule of Investments',max(0,s0-1200),s0)
  s=prev if prev>=0 else s0
  m=re.search(r'(?:\*\*)?Schedule of Investments(?:\([^\n]*\))?',t[s0+1500:],re.I)
  e=s0+1500+m.start() if m else min(len(t),s0+120000)
  z=t[s:e]
  n=stock_line_count(z)
  score=n + 200*('Total Investments' in z) + 100*('Net Assets' in z) + 50*('Common Stocks' in z)
  candidates.append((score,n,s,e,z))
 if not candidates:raise RuntimeError('No non-continuation SPMO schedule candidate')
 candidates.sort(reverse=True,key=lambda x:x[0])
 score,n,s,e,z=candidates[0]
 print('SEGMENT_CHOSEN','score',score,'stock_lines',n,'range',s,e,'candidates',[(x[0],x[1],x[2]) for x in candidates],flush=True)
 if n<80:raise RuntimeError('SPMO segment has too few stock-like lines: '+str(n))
 return z

def clean_name(name):
 name=name.strip().strip('*_ ')
 name=re.sub(r'\s*\([a-z](?:,[a-z])*\)\s*$','',name,flags=re.I).strip()
 return name

def parse(z):
 rows=[]
 for line in z.splitlines():
  p=[x.strip() for x in line.replace('\xa0',' ').split('\t')]
  p=[x for x in p if x not in ('','$')]
  if len(p)>=3 and re.fullmatch(r'[\d,]+',p[0]) and re.fullmatch(r'[\d,]+',p[-1]) and re.search(r'\d',p[-1]):
   names=[x for x in p[1:-1] if re.search('[A-Za-z]',x)]
   if names:
    name=clean_name(max(names,key=len));low=name.lower()
    if not any(x in low for x in ['common stocks','total investments','net assets','money market fund','other assets less']):
     rows.append((int(p[0].replace(',','')),name,int(p[-1].replace(',',''))));continue
  x=line.replace('\xa0',' ').strip().strip('*')
  m=re.match(r'^([\d][\d,]*)\s+(.+?)(?:\$)?([\d][\d,]*)$',x)
  if not m:continue
  shares=int(m.group(1).replace(',',''));name=clean_name(m.group(2));value=int(m.group(3).replace(',',''))
  low=name.lower()
  if not re.search('[A-Za-z]',name) or any(q in low for q in ['common stocks','total investments','net assets','money market fund','other assets less']):continue
  rows.append((shares,name,value))
 return pd.DataFrame(rows,columns=['shares','name','value']).drop_duplicates().reset_index(drop=True)

def stated_total(z):
 for pat in [r'Total Common Stocks(?: and Other Equity Interests)?[\s\S]{0,400}?\t\s*\$?\s*([\d,]+)\s*\t',r'Total Investments[\s\S]{0,400}?\t\s*\$?\s*([\d,]+)\s*\t']:
  ms=list(re.finditer(pat,z,re.I))
  if ms:return int(ms[-1].group(1).replace(',',''))
 for pat in [r'Total Common Stocks[^\n]{0,300}?(?:\)|\*\*)\s*\$?([\d,]+)\s*(?:\n|$)',r'Total Investments[\s\S]{0,250}?[\d.]+%\s*\$?([\d,]+)']:
  ms=list(re.finditer(pat,z,re.I))
  if ms:return int(ms[-1].group(1).replace(',',''))
 return None

alls=[];meta=[]
for rb,rd,acc,known in SPECS:
 print('\nRESOLVE',rb,rd,acc,flush=True)
 u,doc=primary_for(acc,known);print('PRIMARY',doc,u,flush=True)
 t,relay=jina(u);(OUT/f'raw-{rd}.txt').write_text(t)
 z=segment(t);(OUT/f'segment-{rd}.txt').write_text(z)
 d=parse(z);st=stated_total(z);sm=int(d.value.sum()) if len(d) else 0;cov=sm/st if st else None
 print('PARSED',rd,'rows',len(d),'sum',sm,'stated',st,'coverage',cov,flush=True)
 if len(d):print(d.sort_values('value',ascending=False).head(8).to_string(index=False),flush=True)
 d.insert(0,'rebalance',rb);d.insert(1,'report_date',rd);d['accession']=acc;d['source_url']=u
 d.to_csv(OUT/f'holdings-{rd}.csv',index=False);alls.append(d)
 meta.append({'rebalance':rb,'report_date':rd,'accession':acc,'doc':doc,'rows':len(d),'sum':sm,'stated_total':st,'coverage':cov,'source_url':u})
allh=pd.concat(alls,ignore_index=True);allh.to_csv(OUT/'legacy7_holdings.csv',index=False)
pd.DataFrame(meta).to_csv(OUT/'legacy7_meta.csv',index=False);Path(OUT/'legacy7_meta.json').write_text(json.dumps(meta,indent=2))
bad=[m for m in meta if m['rows']<90 or m['coverage'] is None or not (.98<=m['coverage']<=1.015)]
if bad:raise RuntimeError('GATE_FAIL '+json.dumps(bad))
print('\nALL7_GATE PASS',flush=True)
