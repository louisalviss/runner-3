#!/usr/bin/env python3
from __future__ import annotations
import argparse,json
from pathlib import Path
import numpy as np
ELIGIBLE=set('AAPL ADBE ADI ADP ADSK AEP ALNY AMAT AMD AMGN AMZN AVGO BKR CDNS CMCSA COST CPRT CSCO CSX CTSH DXCM EA EXC FANG FTNT GILD GOOG GOOGL HON IDXX INTC INTU ISRG KHC LRCX MAR MCHP MDLZ META MPWR MRVL MSFT MU NFLX NVDA ODFL ORLY PANW PAYX PCAR PEP PLTR QCOM REGN ROST SBUX SNPS TMUS TSLA TTWO TXN VRTX WDAY WDC WMT ZS'.split())
def rows(root):
    a=[]
    for p in Path(root).rglob('scored-*.jsonl'):
        for l in p.read_text().splitlines():
            if l.strip():a.append(json.loads(l))
    return sorted(a,key=lambda x:(int(x['signal']),x['symbol']))
def parent_expected(root):
    h=list(Path(root).rglob('execution-trades.jsonl'));n=0
    if len(h)!=1:return None
    for l in h[0].read_text().splitlines():
        if not l.strip():continue
        x=json.loads(l);sym=x.get('_symbol') or x.get('symbol');y=int(x.get('signal_year',0))
        if sym in ELIGIBLE and y>=2024:n+=1
    return n
def metric(r):
    v=[float(x['R_exec']) for x in r]
    if not v:return {'n':0,'R':0.,'mean_R':None,'PF':None,'win_rate':None,'max_DD_R':0.}
    gp=sum(max(x,0) for x in v);gl=sum(max(-x,0) for x in v);eq=peak=0.;dd=0.
    for x in v:eq+=x;peak=max(peak,eq);dd=min(dd,eq-peak)
    return {'n':len(v),'R':sum(v),'mean_R':sum(v)/len(v),'PF':gp/gl if gl else None,'win_rate':100*sum(x>0 for x in v)/len(v),'max_DD_R':dd}
def yr(x):return int(x.get('signal_year') or str(x['signal_date_ny'])[:4])
def bootstrap(A,B,reps=2000):
    aa={};bb={}
    for x in A:aa.setdefault(x['signal_date_ny'],[]).append(float(x['R_exec']))
    for x in B:bb.setdefault(x['signal_date_ny'],[]).append(float(x['R_exec']))
    d=sorted(aa);rng=np.random.default_rng(20260825);bm=[];dm=[]
    for _ in range(reps):
        av=[];bv=[]
        for z in rng.choice(d,size=len(d),replace=True):av+=aa[z];bv+=bb.get(z,[])
        if av and bv:a=float(np.mean(av));b=float(np.mean(bv));bm.append(b);dm.append(b-a)
    return {'days':len(d),'reps':len(bm),'B_mean_ci95':[float(np.percentile(bm,2.5)),float(np.percentile(bm,97.5))] if bm else [None,None],'delta_ci95':[float(np.percentile(dm,2.5)),float(np.percentile(dm,97.5))] if dm else [None,None]}
def breadth(B):
    d={}
    for x in B:d.setdefault(x['symbol'],[]).append(x)
    e={s:r for s,r in d.items() if len(r)>=5};p=sum(metric(r)['R']>0 for r in e.values())
    return {'eligible_symbols_ge5':len(e),'positive_symbols':p,'positive_fraction':p/len(e) if e else 0.}
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--input',required=True);ap.add_argument('--parent',required=True);ap.add_argument('--out',required=True);a=ap.parse_args();out=Path(a.out);out.mkdir(parents=True,exist_ok=True)
    r=rows(a.input);expected=parent_expected(a.parent)
    all_oos=[x for x in r if yr(x)>=2024];A=[x for x in all_oos if x.get('context_scoreable')];B=[x for x in A if x.get('sector_aligned')]
    cov=len(A)/expected if expected else 0.;ret=len(B)/len(A) if A else 0.;am=metric(A);bm=metric(B);years={str(y):metric([x for x in B if yr(x)==y]) for y in (2024,2025,2026)};br=breadth(B);boot=bootstrap(A,B);recent=sum(years[str(y)]['R']>0 for y in (2024,2025,2026))
    gates={'coverage_ge_95pct':cov>=.95,'B_n_ge_150':bm['n']>=150,'retention_10_70pct':.10<=ret<=.70,'B_mean_positive':bm['mean_R'] is not None and bm['mean_R']>0,'B_PF_gt_1_05':bm['PF'] is not None and bm['PF']>1.05,'B_mean_ge_A_plus_0_10R':bm['mean_R'] is not None and am['mean_R'] is not None and bm['mean_R']>=am['mean_R']+.10,'B_total_R_positive':bm['R']>0,'positive_years_ge_2':recent>=2,'breadth_ge_50pct':br['eligible_symbols_ge5']>0 and br['positive_fraction']>=.5,'bootstrap_B_lower_gt_0':boot['B_mean_ci95'][0] is not None and boot['B_mean_ci95'][0]>0,'bootstrap_delta_lower_gt_0':boot['delta_ci95'][0] is not None and boot['delta_ci95'][0]>0}
    passed=all(gates.values());status='COMPLETE' if cov>=.95 else 'INFRASTRUCTURE_BLOCKED';rep={'status':status,'candidate':'WR 60m + V4 synthetic LOO sector alignment','preregistration_v4_commit':'8a72113ddb2136af44241b9a32238b73eab2edf8','parent_run':32677300335,'excluded_singletons':['PYPL','CSGP'],'expected_oos_eligible':expected,'rows_oos':len(all_oos),'coverage':cov,'retention':ret,'A':am,'B':bm,'mean_delta_R':None if bm['mean_R'] is None or am['mean_R'] is None else bm['mean_R']-am['mean_R'],'B_years':years,'B_breadth':br,'bootstrap':boot,'gates':gates,'PASS_SECTOR_RELATIVE_WR':passed}
    (out/'report.json').write_text(json.dumps(rep,indent=2));(out/'SUMMARY.md').write_text('# WR Sector Relative V4 — Final\n\n'+json.dumps(rep,indent=2)+'\n');print(json.dumps(rep,indent=2))
if __name__=='__main__':main()
