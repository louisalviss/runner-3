#!/usr/bin/env python3
import argparse, re, requests, xml.etree.ElementTree as ET
from pathlib import Path
import pandas as pd

p=argparse.ArgumentParser()
p.add_argument('--accession',required=True, help='e.g. 0001752724-22-170575')
p.add_argument('--output',required=True)
p.add_argument('--min-pct',type=float,default=1.0)
a=p.parse_args()
acc=a.accession
compact=acc.replace('-','')
url=f'https://r.jina.ai/https://www.sec.gov/Archives/edgar/data/1378872/{compact}/{acc}.txt'
r=requests.get(url,timeout=120,headers={'User-Agent':'runner-3 spmo research'})
print('FETCH',r.status_code,'LEN',len(r.text),'ACC',acc)
r.raise_for_status()
text=r.text
if 'S000050154' not in text:
    raise RuntimeError('SPMO series marker not found')

def local(tag): return tag.split('}',1)[-1]
def child_text(el,name):
    for x in el.iter():
        if local(x.tag)==name and x.text is not None:
            return x.text.strip()
    return None

def ticker_from(el):
    for x in el.iter():
        if local(x.tag).lower() in ('ticker','tickerid'):
            if x.get('value'): return x.get('value').strip()
            if x.text and x.text.strip(): return x.text.strip()
    return None

xmls=re.findall(r'<XML>(.*?)</XML>',text,re.S|re.I)
print('XML_BLOCKS',len(xmls))
rows=[]
for idx,s in enumerate(xmls):
    if 'S000050154' not in s or 'invstOrSec' not in s:
        continue
    try: root=ET.fromstring(s.strip())
    except Exception as e:
        print('XML_PARSE_FAIL',idx,e); continue
    report=child_text(root,'repPd') or child_text(root,'reportDate')
    series=child_text(root,'seriesId')
    print('MATCH_XML',idx,'series',series,'report',report)
    for el in root.iter():
        if local(el.tag)!='invstOrSec': continue
        name=child_text(el,'name')
        ticker=ticker_from(el)
        val=child_text(el,'valUSD')
        pct=child_text(el,'pctVal')
        bal=child_text(el,'balance')
        cusip=child_text(el,'cusip')
        if not val: continue
        try: val=float(val)
        except: continue
        try: pct=float(pct) if pct is not None else float('nan')
        except: pct=float('nan')
        rows.append({'ticker':ticker,'name':name,'snapshot_value':val,'snapshot_pct':pct,'balance':bal,'cusip':cusip,'source_accession':acc,'report_date':report})
if not rows: raise RuntimeError('No SPMO holdings parsed')
df=pd.DataFrame(rows).sort_values('snapshot_value',ascending=False)
print(df.head(20).to_string(index=False))
out=df[(df.snapshot_pct.isna()) | (df.snapshot_pct>=a.min_pct)].copy()
Path(a.output).parent.mkdir(parents=True,exist_ok=True)
out.to_csv(a.output,index=False)
print('PARSED',len(df),'OUTPUT',len(out),a.output)
