#!/usr/bin/env python3
from __future__ import annotations
import importlib.util, sys, json
from datetime import timedelta
from pathlib import Path

HERE=Path(__file__).resolve().parent
bspec=importlib.util.spec_from_file_location('base_tv',HERE/'wr_tv_parity.py')
base=importlib.util.module_from_spec(bspec);sys.modules[bspec.name]=base;bspec.loader.exec_module(base)
rspec=importlib.util.spec_from_file_location('recent',HERE/'wr_tv_recent_cases.py')
recent=importlib.util.module_from_spec(rspec);sys.modules[rspec.name]=recent;rspec.loader.exec_module(recent)
base.START=recent.base.START;base.END=recent.base.END

SPECS=[
 ('OANDA:GBPUSD','regular'),
 ('OANDA:AUDUSD','regular'),
 ('OANDA:XAGUSD','regular'),
 ('ICMARKETS:USTEC','regular'),
 ('NASDAQ:TSLA','regular'),
]

def pine_rightmost_pivots(v,left,right,high=True):
    out=[None]*len(v)
    for conf in range(left+right,len(v)):
        c=conf-right; x=v[c]; L=v[c-left:c]; R=v[c+1:c+right+1]
        if high: ok=all(x>=z for z in L) and all(x>z for z in R)
        else: ok=all(x<=z for z in L) and all(x<z for z in R)
        if ok: out[conf]=x
    return [None]+out[:-1],0

def main():
    ref=base.load_ref(); ref.pivots=pine_rightmost_pivots
    rows=[]
    for sym,sess in SPECS:
        bars,info=recent.fetch(sym,sess)
        tr,m=base.run_case(ref,bars,info,base.START-timedelta(days=10),'start',True)
        row={'symbol':sym,'n':m['n'],'R':m['R'],'tick':m['tick'],'session':m['session'],'timezone':m['timezone'],'trades':tr}
        rows.append(row); print('NEXT5',row,flush=True)
    out=HERE/'output'/'tv-next5';out.mkdir(parents=True,exist_ok=True)
    (out/'next5.json').write_text(json.dumps(rows,indent=2,default=str))
if __name__=='__main__':main()
