#!/usr/bin/env python3
from __future__ import annotations
import importlib.util, json, sys
from datetime import timedelta
from pathlib import Path

HERE=Path(__file__).resolve().parent
bspec=importlib.util.spec_from_file_location('base_tv',HERE/'wr_tv_parity.py')
base=importlib.util.module_from_spec(bspec);sys.modules[bspec.name]=base;bspec.loader.exec_module(base)
rspec=importlib.util.spec_from_file_location('recent',HERE/'wr_tv_recent_cases.py')
recent=importlib.util.module_from_spec(rspec);sys.modules[rspec.name]=recent;rspec.loader.exec_module(recent)
base.START=recent.base.START;base.END=recent.base.END

EXPECTED={
 'OANDA:EURUSD':(5,-4.42),
 'OANDA:USDJPY':(4,5.90),
 'OANDA:XAUUSD':(7,-3.70),
 'ICMARKETS:US500':(2,-2.00),
 'NASDAQ:AAPL':(1,-0.4303797468354312),
}
SPECS=[('OANDA:EURUSD','regular'),('OANDA:USDJPY','regular'),('OANDA:XAUUSD','regular'),('ICMARKETS:US500','regular'),('NASDAQ:AAPL','regular')]

def pine_rightmost_pivots(v,left,right,high=True):
    # Match ta.pivothigh/ta.pivotlow tie semantics: the candidate may equal
    # older/left values, but must be strictly beyond every newer/right value.
    out=[None]*len(v)
    for conf in range(left+right,len(v)):
        c=conf-right; x=v[c]; L=v[c-left:c]; R=v[c+1:c+right+1]
        if high:
            ok=all(x>=z for z in L) and all(x>z for z in R)
        else:
            ok=all(x<=z for z in L) and all(x<z for z in R)
        if ok: out[conf]=x
    return [None]+out[:-1],0

def main():
    ref=base.load_ref(); ref.pivots=pine_rightmost_pivots
    results=[]
    for sym,sess in SPECS:
        bars,info=recent.fetch(sym,sess)
        trades,m=base.run_case(ref,bars,info,base.START-timedelta(days=10),'start',True)
        expn,expr=EXPECTED[sym]
        row={'symbol':sym,'n':m['n'],'R':m['R'],'expected_n':expn,'expected_R':expr,'delta_n':m['n']-expn,'delta_R':m['R']-expr,'trades':trades}
        results.append(row); print('FINAL',row,flush=True)
        if m['n']!=expn or abs(m['R']-expr)>0.005:
            raise SystemExit(f'PARITY_FAIL {sym}: got {m["n"]}/{m["R"]}, expected {expn}/{expr}')
    out=HERE/'output'/'tv-rightmost-final';out.mkdir(parents=True,exist_ok=True)
    (out/'final-5of5.json').write_text(json.dumps(results,indent=2,default=str))
    print('PARITY_PASS 5/5',flush=True)
if __name__=='__main__': main()
