#!/usr/bin/env python3
import csv, io, os, zipfile
from pathlib import Path

CIK='1378872'
FORMS={'NPORT-P','N-Q','N-CSR','N-CSRS'}
ZIP=Path(os.environ.get('MASTER_ZIP','MasterIndex_20260318.zip'))
OUT=Path('spmo-index/output'); OUT.mkdir(parents=True,exist_ok=True)
rows=[]
with zipfile.ZipFile(ZIP) as z:
    names=[n for n in z.namelist() if n.lower().endswith('.idx')]
    print('IDX_FILES',len(names),flush=True)
    for name in names:
        base=Path(name).name
        # Notre Dame names files master_YYYY_QTR#.idx.
        try:
            year=int(base.split('_')[1]); q=int(base.upper().split('QTR')[1].split('.')[0])
        except Exception:
            continue
        if not (2016 <= year <= 2025):
            continue
        text=z.read(name).decode('latin-1','replace')
        prefix=CIK+'|'
        for line in text.splitlines():
            if not line.startswith(prefix):
                continue
            p=line.split('|')
            if len(p)!=5 or p[2] not in FORMS:
                continue
            rows.append([year,q,*p])
print('FILTERED_ROWS',len(rows),flush=True)
out=OUT/'spmo_cik_master_2016_2025.csv'
with out.open('w',newline='',encoding='utf-8') as f:
    w=csv.writer(f); w.writerow(['year','quarter','cik','company','form','filed','filename']); w.writerows(rows)
print('OUT',out,'bytes',out.stat().st_size,flush=True)
