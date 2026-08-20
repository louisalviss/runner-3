#!/usr/bin/env python3
import json,glob,os
from collections import defaultdict
from pathlib import Path
OUT=Path('/tmp/final'); OUT.mkdir(parents=True,exist_ok=True)
rows=[]
for fn in glob.glob('/tmp/all/**/trades-*.jsonl',recursive=True):
 with open(fn) as f:
  rows += [json.loads(x) for x in f if x.strip()]
# dedup defensively
uniq={ (r['symbol'],r['tf'],r['setup'],r['exit'],r['signal_time'],r['entry'],r['exit_time']):r for r in rows }; rows=list(uniq.values())

def year(ms):
 import datetime
 return datetime.datetime.fromtimestamp(ms/1000,datetime.timezone.utc).year
summary=[]
keys=sorted({(r['tf'],r['setup'],r['exit']) for r in rows})
for tf,setup,ex in keys:
 for y in (2024,2025,2026):
  xs=[r for r in rows if r['tf']==tf and r['setup']==setup and r['exit']==ex and year(r['signal_time'])==y]
  if not xs:continue
  raw=sum(r['net6'] for r in xs); batches=defaultdict(list)
  for r in xs:batches[r['signal_time']].append(r)
  port=sum(sum(z['net6'] for z in a)/len(a) for a in batches.values())
  summary.append({'tf':tf,'setup':setup,'exit':ex,'year':y,'trades':len(xs),'batches':len(batches),'raw_net6':raw,'portfolio_net6':port,'avg_net6':raw/len(xs),'win_pct':100*sum(r['net6']>0 for r in xs)/len(xs)})
# pass requires all 3 years >0 raw+portfolio and >=30 trades/year
passed=[]
for k in keys:
 ss=[x for x in summary if (x['tf'],x['setup'],x['exit'])==k]
 if len(ss)==3 and all(x['trades']>=30 and x['raw_net6']>0 and x['portfolio_net6']>0 for x in ss):passed.append(k)
summary.sort(key=lambda x:(x['tf'],x['setup'],x['exit'],x['year']))
json.dump({'pass':passed,'summary':summary},open(OUT/'summary.json','w'),indent=2)
with open(OUT/'report.md','w') as f:
 f.write('# Flow Trend Rider\n\nPASS configs: '+(str(passed) if passed else 'NONE')+'\n\n')
 f.write('|TF|Setup|Exit|Year|Trades|Batches|Raw net6|Portfolio net6|Avg|Win%|\n|---:|---|---|---:|---:|---:|---:|---:|---:|---:|\n')
 for x in summary:f.write(f"|{x['tf']}|{x['setup']}|{x['exit']}|{x['year']}|{x['trades']}|{x['batches']}|{x['raw_net6']:.2f}|{x['portfolio_net6']:.2f}|{x['avg_net6']:.3f}|{x['win_pct']:.1f}|\n")
