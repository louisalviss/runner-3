#!/usr/bin/env python3
import json, os
from collections import defaultdict
from pathlib import Path
ROOT=Path(os.getenv('MERGE_ROOT','/tmp/all')); OUT=Path(os.getenv('FINAL_OUT','/tmp/final')); OUT.mkdir(parents=True,exist_ok=True)
V=('base_both','base_long','cci_long_exact','cci_symmetric')

def cost(t,bps):
    d=abs(float(t['e'])-float(t['s'])); return 0 if d<=0 else float(t['e'])/d*bps/10000

def met(ts,bps):
    vals=[float(t['R'])-cost(t,bps) for t in ts]; gp=sum(max(x,0) for x in vals); gl=sum(max(-x,0) for x in vals); eq=peak=0.;dd=0.
    for x in sorted(zip(ts,vals),key=lambda z:int(z[0]['signal'])):
        eq+=x[1]; peak=max(peak,eq); dd=min(dd,eq-peak)
    return {'n':len(vals),'R':sum(vals),'avg_R':sum(vals)/len(vals) if vals else None,'PF':gp/gl if gl else None,'max_DD_R':dd}

def rep(ts):
    o=[t for t in ts if 2024<=int(t['year'])<=2026]; tr=[t for t in ts if int(t['year']) in (2022,2023)]
    return {'train':{str(b):met(tr,b) for b in (0,.5,1,2)},'oos':{str(b):met(o,b) for b in (0,.5,1,2)},
            'years':{str(y):{str(b):met([t for t in o if int(t['year'])==y],b) for b in (0,1,2)} for y in (2024,2025,2026)}}
def cmp(a,b):
    A=a['oos']['1'];B=b['oos']['1'];return {'base_n':A['n'],'filtered_n':B['n'],'retention':B['n']/A['n'] if A['n'] else None,'base_R':A['R'],'filtered_R':B['R'],'delta_R':B['R']-A['R'],'base_avg_R':A['avg_R'],'filtered_avg_R':B['avg_R'],'delta_avg_R':B['avg_R']-A['avg_R'] if A['avg_R'] is not None and B['avg_R'] is not None else None,'base_PF':A['PF'],'filtered_PF':B['PF'],'base_DD':A['max_DD_R'],'filtered_DD':B['max_DD_R']}
rows=defaultdict(list); syms=[]; errors=[]
for p in ROOT.rglob('*.json'):
    if p.name.endswith('-trades.jsonl'): continue
    try:
        d=json.load(open(p))
        if d.get('status')=='OK' and 'symbol' in d: syms.append(d['symbol'])
    except Exception as e: errors.append([str(p),repr(e)])
for p in ROOT.rglob('*-trades.jsonl'):
    for line in open(p):
        t=json.loads(line); rows[t['variant']].append(t)
R={v:rep(rows[v]) for v in V}; out={'status':'COMPLETE' if len(set(syms))==68 else 'PARTIAL','symbols_ok':len(set(syms)),'symbols':sorted(set(syms)),'errors':errors,'rule':{'exact_long':'Lowest(CCI(27),18)<-100','symmetric_short_extension':'Highest(CCI(27),18)>+100'},'variants':R,'comparisons':{'exact_long':cmp(R['base_long'],R['cci_long_exact']),'symmetric':cmp(R['base_both'],R['cci_symmetric'])}}
(OUT/'summary.json').write_text(json.dumps(out,indent=2));
with (OUT/'trades.jsonl').open('w') as f:
    for v in V:
        for t in rows[v]: f.write(json.dumps(t)+'\n')
print('FINAL',json.dumps(out['comparisons'],sort_keys=True))
