#!/usr/bin/env python3
import argparse, json, urllib.request
from pathlib import Path

RAW='https://raw.githubusercontent.com/louisalviss/runner-3/{ref}/vbook/louis-vbook.json'

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--ref',required=True,help='Immutable git ref/SHA on runner-3')
    ap.add_argument('--out',required=True,help='Output meta list JSON')
    ap.add_argument('--registry-out',required=True,help='Output canonical registry JSON')
    a=ap.parse_args()
    url=RAW.format(ref=a.ref)
    with urllib.request.urlopen(url,timeout=30) as r:
        reg=json.load(r)
    rows=reg.get('data') if isinstance(reg,dict) else reg
    if not isinstance(rows,list) or not rows:
        raise SystemExit('registry has no data list')
    out=[]
    for i,row in enumerate(rows):
        if not isinstance(row,dict): raise SystemExit(f'row {i} not object')
        x=dict(row); x['registry_ref']=a.ref; x['registry_index']=i
        out.append(x)
    Path(a.out).write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8')
    Path(a.registry_out).write_text(json.dumps(reg,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'ref':a.ref,'count':len(out),'url':url},ensure_ascii=False))

if __name__=='__main__': main()
