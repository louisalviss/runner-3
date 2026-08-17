#!/usr/bin/env python3
from __future__ import annotations
import importlib.util, json
from pathlib import Path
from datetime import date, datetime, timezone

ROOT=Path(__file__).resolve().parents[1]
P=ROOT/'formal-tests'/'wr_v2513_parity_pack.py'
spec=importlib.util.spec_from_file_location('pack',P)
pack=importlib.util.module_from_spec(spec); spec.loader.exec_module(pack)
wr=pack.wr; base=pack.base

REPORT_START_MS=int(datetime(2026,7,27,17,0,tzinfo=timezone.utc).timestamp()*1000) # 28 Jul 00:00 VN
REPORT_END_MS=int(datetime(2026,8,15,17,0,tzinfo=timezone.utc).timestamp()*1000)   # 16 Aug 00:00 VN
ENGINE_START_MS=int(datetime(2024,12,1,tzinfo=timezone.utc).timestamp()*1000)


def make_pivots(mode):
    def piv(v,left,right,high=True):
        basearr=[None]*len(v); ties=0
        for conf in range(left+right,len(v)):
            c=conf-right; w=v[c-left:c+right+1]; x=v[c]
            L=v[c-left:c]; R=v[c+1:c+right+1]
            ext=max(w) if high else min(w)
            if x==ext and sum(a==ext for a in w)>1: ties+=1
            ok=False
            if mode=='unique':
                ok=x==ext and sum(a==ext for a in w)==1
            elif mode=='any_equal':
                ok=x==ext
            elif mode=='left_strict':
                ok=(all(x>a for a in L) and all(x>=a for a in R)) if high else (all(x<a for a in L) and all(x<=a for a in R))
            elif mode=='right_strict':
                ok=(all(x>=a for a in L) and all(x>a for a in R)) if high else (all(x<=a for a in L) and all(x<a for a in R))
            elif mode=='both_strict':
                ok=(all(x>a for a in L+R)) if high else (all(x<a for a in L+R))
            if ok: basearr[conf]=x
        return [None]+basearr[:-1],ties
    return piv

bars,tick,missing=pack.fetch_symbol('BNBUSDT')
orig_piv=base.pivots
orig_session=base.SESSION_GUARD
rows=[]
for mode in ['unique','any_equal','left_strict','right_strict','both_strict']:
    base.pivots=make_pivots(mode)
    for sess in [True,False]:
        base.SESSION_GUARD=sess
        tr,s=wr.run_window_exact(5,bars,tick,REPORT_START_MS,REPORT_END_MS,engine_start_ms=ENGINE_START_MS)
        rows.append(dict(mode=mode,session=sess,trades=s['trades'],total_r=s['total_r'],avg_r=s['avg_r'],wins=s['wins'],losses=s['losses'],diag=s['diagnostics']))
base.pivots=orig_piv; base.SESSION_GUARD=orig_session
print(json.dumps({'target_tv':{'trades':14,'total_r':5.8},'missing':missing,'rows':rows},indent=2))
Path('wr_bnb_pivot_diagnostics.json').write_text(json.dumps({'target_tv':{'trades':14,'total_r':5.8},'missing':missing,'rows':rows},indent=2))
