#!/usr/bin/env python3
import csv,json,os
from pathlib import Path
from collections import defaultdict

ROOT=Path(os.getenv('INPUT_DIR','/tmp/all')); OUT=Path(os.getenv('OUT_DIR','/tmp/final')); OUT.mkdir(parents=True,exist_ok=True)
rows=[]
for p in ROOT.rglob('summary-*.json'):
    try: rows += json.load(open(p))
    except Exception as e: print('READ_ERR',p,e)

keyf=lambda r:(r['tf'],r['alpha'],r['entry'],float(r['tp']))
by=defaultdict(dict)
for r in rows:by[keyf(r)][int(r['year'])]=r

final=[]
for k,yrs in sorted(by.items()):
    if not all(y in yrs for y in (2022,2023,2024,2025,2026)):continue
    tf,a,e,tp=k
    dev_raw=sum(yrs[y].get('raw_net6',0) for y in (2022,2023,2024))
    dev_port=sum(yrs[y].get('port_net6',0) for y in (2022,2023,2024))
    val=yrs[2025]; oos=yrs[2026]
    passed=(dev_raw>0 and dev_port>0 and val.get('raw_net6',0)>0 and val.get('port_net6',0)>0 and oos.get('raw_net6',0)>0 and oos.get('port_net6',0)>0 and val.get('port_selected6',0)>=30 and oos.get('port_selected6',0)>=30)
    rec={'tf':tf,'alpha':a,'entry':e,'tp':tp,'dev_2022_24_raw6':dev_raw,'dev_2022_24_port6':dev_port,'val_2025_raw6':val.get('raw_net6',0),'val_2025_port6':val.get('port_net6',0),'val_2025_selected':val.get('port_selected6',0),'oos_2026_raw6':oos.get('raw_net6',0),'oos_2026_port6':oos.get('port_net6',0),'oos_2026_selected':oos.get('port_selected6',0),'PASS':passed}
    for y in (2022,2023,2024,2025,2026):
        rec[f'{y}_raw6']=yrs[y].get('raw_net6',0); rec[f'{y}_port6']=yrs[y].get('port_net6',0); rec[f'{y}_selected']=yrs[y].get('port_selected6',0)
    final.append(rec)

final.sort(key=lambda r:(not r['PASS'],-min(r['val_2025_port6'],r['oos_2026_port6'])))
json.dump(final,open(OUT/'trend-state-rider-final.json','w'),indent=2)
if final:
    with open(OUT/'trend-state-rider-final.csv','w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(final[0].keys())); w.writeheader(); w.writerows(final)

passes=[r for r in final if r['PASS']]
with open(OUT/'REPORT.md','w') as f:
    f.write('# Trend State Rider v1 — frozen multi-period validation\n\n')
    f.write('Primary PASS is predeclared: dev 2022–24 aggregate raw+portfolio net6 > 0; 2025 validation raw+portfolio > 0; 2026 OOS raw+portfolio > 0; >=30 portfolio-selected trades in both 2025 and 2026.\n\n')
    f.write(f'Configs evaluated: {len(final)}  \\nPASS configs: {len(passes)}\n\n')
    f.write('|TF|Alpha|Entry|TP|Dev port6|2025 port6|2026 port6|2025 n|2026 n|PASS|\n|---:|---|---|---:|---:|---:|---:|---:|---:|---|\n')
    for r in final:
        f.write(f"|{r['tf']}|{r['alpha']}|{r['entry']}|{r['tp']:.1f}|{r['dev_2022_24_port6']:.2f}|{r['val_2025_port6']:.2f}|{r['oos_2026_port6']:.2f}|{r['val_2025_selected']}|{r['oos_2026_selected']}|{'YES' if r['PASS'] else 'NO'}|\n")
print('CONFIGS',len(final),'PASS',len(passes))
for r in final[:10]:print(r)
