#!/usr/bin/env python3
from __future__ import annotations
import argparse,json
from pathlib import Path
import numpy as np

def load_rows(root):
    rows=[]
    for p in Path(root).rglob('scored-shard-*.jsonl'):
        for line in p.read_text().splitlines():
            if line.strip(): rows.append(json.loads(line))
    return sorted(rows,key=lambda x:(int(x.get('signal',0)),str(x.get('symbol',''))))
def probe(root):
    h=list(Path(root).rglob('benchmark-probe.json')); return None if not h else json.loads(h[0].read_text())
def metric(rows):
    v=[float(x['R_exec']) for x in rows]
    if not v:return {'n':0,'R':0.0,'mean_R':None,'PF':None,'win_rate':None,'max_DD_R':0.0}
    gp=sum(max(x,0) for x in v);gl=sum(max(-x,0) for x in v);eq=peak=0.;dd=0.
    for x in v:eq+=x;peak=max(peak,eq);dd=min(dd,eq-peak)
    return {'n':len(v),'R':sum(v),'mean_R':sum(v)/len(v),'PF':gp/gl if gl else None,'win_rate':100*sum(x>0 for x in v)/len(v),'max_DD_R':dd}
def yr(x):return int(x.get('signal_year') or str(x['signal_date_ny'])[:4])
def bootstrap(A,B,reps=2000):
    aa={};bb={}
    for x in A:aa.setdefault(x['signal_date_ny'],[]).append(float(x['R_exec']))
    for x in B:bb.setdefault(x['signal_date_ny'],[]).append(float(x['R_exec']))
    days=sorted(aa); rng=np.random.default_rng(20260825); bm=[];dm=[]
    for _ in range(reps):
        av=[];bv=[]
        for d in rng.choice(days,size=len(days),replace=True):av+=aa[d];bv+=bb.get(d,[])
        if av and bv:
            a=float(np.mean(av));b=float(np.mean(bv));bm.append(b);dm.append(b-a)
    return {'days':len(days),'reps':len(bm),'B_mean_ci95':[float(np.percentile(bm,2.5)),float(np.percentile(bm,97.5))] if bm else [None,None],'delta_ci95':[float(np.percentile(dm,2.5)),float(np.percentile(dm,97.5))] if dm else [None,None]}
def breadth(B):
    d={}
    for x in B:d.setdefault(x['symbol'],[]).append(x)
    e={s:r for s,r in d.items() if len(r)>=5};p=sum(metric(r)['R']>0 for r in e.values())
    return {'eligible_symbols_ge5':len(e),'positive_symbols':p,'positive_fraction':p/len(e) if e else 0.0}
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--input',required=True);ap.add_argument('--out',required=True);a=ap.parse_args();out=Path(a.out);out.mkdir(parents=True,exist_ok=True)
    pr=probe(a.input); rows=load_rows(a.input)
    if not (pr and pr.get('ok')) or not rows:
        r={'status':'INFRASTRUCTURE_BLOCKED','probe':pr,'rows':len(rows),'PASS_SECTOR_RELATIVE_WR':False};(out/'report.json').write_text(json.dumps(r,indent=2));(out/'SUMMARY.md').write_text('# WR Sector Relative V2 — Infrastructure Blocked\n');print(json.dumps(r,indent=2));return
    all_oos=[x for x in rows if yr(x)>=2024];A=[x for x in all_oos if x.get('context_scoreable')];B=[x for x in A if x.get('sector_aligned')]
    cov=len(A)/len(all_oos) if all_oos else 0.;ret=len(B)/len(A) if A else 0.;am=metric(A);bm=metric(B);years={str(y):metric([x for x in B if yr(x)==y]) for y in (2024,2025,2026)};br=breadth(B);boot=bootstrap(A,B)
    recent=sum(years[str(y)]['R']>0 for y in (2024,2025,2026))
    gates={'coverage_ge_95pct':cov>=.95,'B_n_ge_150':bm['n']>=150,'retention_10_70pct':.10<=ret<=.70,'B_mean_positive':bm['mean_R'] is not None and bm['mean_R']>0,'B_PF_gt_1_05':bm['PF'] is not None and bm['PF']>1.05,'B_mean_ge_A_plus_0_10R':bm['mean_R'] is not None and am['mean_R'] is not None and bm['mean_R']>=am['mean_R']+.10,'B_total_R_positive':bm['R']>0,'positive_years_ge_2':recent>=2,'breadth_ge_50pct':br['eligible_symbols_ge5']>0 and br['positive_fraction']>=.5,'bootstrap_B_lower_gt_0':boot['B_mean_ci95'][0] is not None and boot['B_mean_ci95'][0]>0,'bootstrap_delta_lower_gt_0':boot['delta_ci95'][0] is not None and boot['delta_ci95'][0]>0}
    passed=all(gates.values());r={'status':'COMPLETE' if cov>=.95 else 'INFRASTRUCTURE_BLOCKED','candidate':'WR 60m + V2 sector-relative hierarchy','preregistration_v2_commit':'960bb2c91cc16c50784f424172d323f997741fb1','parent_run':32677300335,'coverage':cov,'retention':ret,'A':am,'B':bm,'mean_delta_R':None if bm['mean_R'] is None or am['mean_R'] is None else bm['mean_R']-am['mean_R'],'B_years':years,'B_breadth':br,'bootstrap':boot,'gates':gates,'probe':pr,'PASS_SECTOR_RELATIVE_WR':passed}
    (out/'report.json').write_text(json.dumps(r,indent=2));lines=['# WR Sector Relative V2 — Final',f'`PASS_SECTOR_RELATIVE_WR = {str(passed).lower()}`',f'coverage={cov:.2%}',f'retention={ret:.2%}',f'A={am}',f'B={bm}',f'delta={r["mean_delta_R"]}',f'years={years}',f'bootstrap={boot}',f'gates={gates}'];(out/'SUMMARY.md').write_text('\n\n'.join(lines)+'\n');print(json.dumps(r,indent=2))
if __name__=='__main__':main()
