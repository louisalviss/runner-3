#!/usr/bin/env python3
import json, glob, os
from collections import defaultdict
from pathlib import Path

OUT=Path('/tmp/final'); OUT.mkdir(parents=True,exist_ok=True)
rows=[]
for p in glob.glob('/tmp/all/**/trades-*.jsonl',recursive=True):
    with open(p) as f:
        for line in f:
            if line.strip(): rows.append(json.loads(line))

def year_of(ms):
    import datetime
    return datetime.datetime.utcfromtimestamp(ms/1000).year
summary=[]
keys=sorted(set((r['tf'],r['arch'],r['tp']) for r in rows))
for tf,arch,tp in keys:
    for year in (2024,2025,2026):
        xs=[r for r in rows if r['tf']==tf and r['arch']==arch and r['tp']==tp and year_of(r['signal_time'])==year]
        if not xs: continue
        # Portfolio-normalize synchronized signals: each timestamp gets 1R total risk split equally.
        by=defaultdict(list)
        for r in xs: by[r['signal_time']].append(r)
        port6=sum(sum(r['net6'] for r in g)/len(g) for g in by.values())
        raw={bps:sum(r[f'net{bps}'] for r in xs) for bps in (4,6,8,10,12)}
        summary.append({'tf':tf,'arch':arch,'tp':tp,'year':year,'trades':len(xs),'batches':len(by),
                        'avgR':sum(r['R'] for r in xs)/len(xs),'raw_net4':raw[4],'raw_net6':raw[6],
                        'raw_net8':raw[8],'raw_net10':raw[10],'raw_net12':raw[12],'portfolio_net6':port6})
# Strict pass: positive raw net6 and portfolio net6 in every available year 2024,2025,2026, min 30 trades/year.
combo=defaultdict(dict)
for s in summary: combo[(s['tf'],s['arch'],s['tp'])][s['year']]=s
rank=[]
for k,ys in combo.items():
    pass_all=all(y in ys and ys[y]['trades']>=30 and ys[y]['raw_net6']>0 and ys[y]['portfolio_net6']>0 for y in (2024,2025,2026))
    rank.append({'tf':k[0],'arch':k[1],'tp':k[2],'pass_all_years':pass_all,
                 'sum_portfolio_net6':sum(ys[y]['portfolio_net6'] for y in ys),
                 'sum_raw_net6':sum(ys[y]['raw_net6'] for y in ys)})
rank.sort(key=lambda x:(x['pass_all_years'],x['sum_portfolio_net6']),reverse=True)
json.dump(summary,open(OUT/'summary.json','w'),indent=2)
json.dump(rank,open(OUT/'ranking.json','w'),indent=2)
with open(OUT/'report.md','w') as f:
    f.write('# Wave Rider Next-Gen Trend Architecture\n\n')
    f.write('Primary pass = raw net @6bps >0 AND portfolio-normalized net @6bps >0 in each of 2024, 2025, 2026, minimum 30 trades/year.\n\n')
    for r in rank:
        f.write(f"- {r['tf']}m {r['arch']} TP {r['tp']}: PASS={r['pass_all_years']} | portfolio sum {r['sum_portfolio_net6']:.2f}R | raw sum {r['sum_raw_net6']:.2f}R\n")
    f.write('\n## Year detail\n')
    for s in summary:
        f.write(f"- {s['tf']}m {s['arch']} TP{s['tp']} {s['year']}: n={s['trades']} batches={s['batches']} raw6={s['raw_net6']:.2f}R port6={s['portfolio_net6']:.2f}R avgR={s['avgR']:.4f}\n")
print('rows',len(rows),'summary',len(summary),'rank',len(rank))
