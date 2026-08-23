#!/usr/bin/env python3
from __future__ import annotations
import json, os
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
ROOT=Path(os.getenv('MERGE_ROOT','/tmp/all')); OUT=Path(os.getenv('FINAL_OUT','/tmp/final'));OUT.mkdir(parents=True,exist_ok=True)

def cost_r(t,bps):
    d=abs(float(t['e'])-float(t['s']));return 0.0 if d<=0 else (float(t['e'])/d)*(bps/10000.0)
def met(xs,bps):
    a=[float(t['R'])-cost_r(t,bps) for t in xs];n=len(a);gp=sum(max(x,0) for x in a);gl=sum(max(-x,0) for x in a);eq=peak=0.;dd=0.
    for x in a:eq+=x;peak=max(peak,eq);dd=min(dd,eq-peak)
    return {'n':n,'R':sum(a),'avg_R':sum(a)/n if n else None,'PF':gp/gl if gl else None,'max_DD_R':dd}
def year(t):return datetime.fromtimestamp(int(t['signal'])/1000,tz=timezone.utc).year
def episode(xs,bps=1):
    by=defaultdict(list)
    for t in xs:by[int(t['signal'])].append(float(t['R'])-cost_r(t,bps))
    vals=[sum(v)/len(v) for v in by.values()]
    return {'episodes':len(vals),'episode_normalized_R':sum(vals),'peak_same_signal':max((len(v) for v in by.values()),default=0)}

def main():
    summaries=[];tr=[]
    for p in ROOT.rglob('*.json'):
        if p.name.endswith('-trades.jsonl'):continue
        try:
            x=json.loads(p.read_text())
            if isinstance(x,dict) and 'symbol' in x:summaries.append(x)
        except Exception:pass
    for p in ROOT.rglob('*-trades.jsonl'):
        for ln in p.read_text().splitlines():
            if ln.strip():tr.append(json.loads(ln))
    report={'status':'COMPLETE','research_question':'Does a single close-confirmed entry change improve WR on the clean 68-stock 10m research universe?','symbols_expected':68,'symbols_ok':sum(x.get('status')=='OK' for x in summaries),'symbols_unavailable':sum(x.get('status')!='OK' for x in summaries),'source_note':'Dukascopy structural midpoint research; not final executable BID/ASK proof','cost_units':'modeled round-trip-equivalent bps sensitivity','variants':{}}
    for v in ('baseline','close_confirmed'):
        xs=[t for t in tr if t['variant']==v]
        train=[t for t in xs if year(t) in (2022,2023)];oos=[t for t in xs if year(t) in (2024,2025,2026)]
        report['variants'][v]={'train_2022_2023':{'net_1bps':met(train,1),'net_2bps':met(train,2),'long_1bps':met([t for t in train if t['side']=='L'],1),'short_1bps':met([t for t in train if t['side']=='S'],1)},'oos_2024_2026':{'net_1bps':met(oos,1),'net_2bps':met(oos,2),'long_1bps':met([t for t in oos if t['side']=='L'],1),'short_1bps':met([t for t in oos if t['side']=='S'],1),'episode_1bps':episode(oos,1),'by_year':{str(y):{'net_1bps':met([t for t in oos if year(t)==y],1),'net_2bps':met([t for t in oos if year(t)==y],2)} for y in (2024,2025,2026)}}}
    a=report['variants']['baseline']['oos_2024_2026']['net_1bps'];b=report['variants']['close_confirmed']['oos_2024_2026']['net_1bps'];report['delta_close_minus_baseline_oos_1bps']={'R':b['R']-a['R'],'n':b['n']-a['n'],'avg_R':b['avg_R']-a['avg_R'] if a['avg_R'] is not None and b['avg_R'] is not None else None}
    report['promotion_gate_predeclared']={'requires':['close-confirm OOS net_1bps R > baseline OOS net_1bps R','close-confirm OOS net_1bps PF > 1.0','2024-2026 not dominated by one positive year','net_2bps not catastrophically negative','no parity failures'],'note':'Improvement alone is not sufficient to call deployable edge.'}
    (OUT/'report.json').write_text(json.dumps(report,indent=2));(OUT/'symbol-summaries.json').write_text(json.dumps(summaries,indent=2,default=str))
    with (OUT/'trades.jsonl').open('w') as f:
        for t in tr:f.write(json.dumps(t,separators=(',',':'))+'\n')
    print(json.dumps(report,indent=2),flush=True)
if __name__=='__main__':main()
