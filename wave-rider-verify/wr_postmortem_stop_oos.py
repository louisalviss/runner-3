#!/usr/bin/env python3
import json,glob
from collections import defaultdict
from datetime import datetime,timezone,timedelta
from pathlib import Path

OUT=Path('/tmp/final'); OUT.mkdir(parents=True,exist_ok=True)
BPS=(4,6,8,10,12)
rows=[]
for p in glob.glob('/tmp/all/trades-*.jsonl'):
    with open(p) as f:
        for line in f:
            r=json.loads(line)
            dt=datetime.fromtimestamp(r['signal_time']/1000,timezone.utc)+timedelta(hours=7)
            y=dt.year
            if y not in (2022,2023): continue
            # Frozen postmortem hypothesis discovered only from 2024-26:
            # exact 00:xx VN, SHORT, original structural stop 1.0%-1.5%.
            if dt.hour!=0 or r['side']!='SHORT' or not (1.0<=r['stop_pct']<1.5): continue
            risk=abs(r['entry']-r['stop'])
            if risk<=0: continue
            q=dict(r); q['year']=y; q['vn_date']=dt.strftime('%Y-%m-%d'); q['vn_time']=dt.strftime('%Y-%m-%d %H:%M:%S')
            for bps in BPS:q[f'net{bps}']=r['R']-(r['entry']/risk)*bps/10000
            rows.append(q)

def stats(xs,key):
    vals=[x[key] for x in xs]
    if not vals:return {'n':0,'net':0.0,'avg':None,'positive_pct':None}
    return {'n':len(vals),'net':sum(vals),'avg':sum(vals)/len(vals),'positive_pct':100*sum(v>0 for v in vals)/len(vals)}

def portfolio(xs,key):
    # synchronized timestamp = one total 1R portfolio allocation, split equally across simultaneous signals
    g=defaultdict(list)
    for x in xs:g[x['signal_time']].append(x[key])
    vals=[sum(v)/len(v) for v in g.values()]
    return {'batches':len(vals),'net':sum(vals),'avg':sum(vals)/len(vals) if vals else None,'positive_pct':100*sum(v>0 for v in vals)/len(vals) if vals else None,'max_batch_size':max((len(v) for v in g.values()),default=0)}

rep={'status':'WR_POSTMORTEM_STOP_OOS_2022_2023','rule':'10m exact 00:xx VN + SHORT + structural stop_pct in [1.0,1.5); rule discovered retrospectively from 2024-2026, tested unchanged here','years':{}}
for y in (2022,2023):
    ys=[x for x in rows if x['year']==y]
    rep['years'][str(y)]={'gross':stats(ys,'R'),'costs':{},'symbols':len(set(x['symbol'] for x in ys))}
    for bps in BPS:
        rep['years'][str(y)]['costs'][str(bps)]={'trade':stats(ys,f'net{bps}'),'portfolio_1R_per_timestamp':portfolio(ys,f'net{bps}')}
rep['combined']={'gross':stats(rows,'R'),'costs':{}}
for bps in BPS:rep['combined']['costs'][str(bps)]={'trade':stats(rows,f'net{bps}'),'portfolio_1R_per_timestamp':portfolio(rows,f'net{bps}')}
rep['pass_definition']='PASS only if both 2022 and 2023 are net-positive at 6bps at trade level AND portfolio-normalized level, with >=30 trades/year.'
y22=rep['years']['2022']['costs']['6']; y23=rep['years']['2023']['costs']['6']
rep['pass']=all([y22['trade']['n']>=30,y23['trade']['n']>=30,y22['trade']['net']>0,y23['trade']['net']>0,y22['portfolio_1R_per_timestamp']['net']>0,y23['portfolio_1R_per_timestamp']['net']>0])
json.dump(rep,open(OUT/'wr_postmortem_stop_oos.json','w'),indent=2)
print(json.dumps(rep,indent=2))
