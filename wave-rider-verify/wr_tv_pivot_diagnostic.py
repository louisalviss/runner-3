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

def make_pivots(mode):
 def piv(v,left,right,high=True):
  out=[None]*len(v)
  for conf in range(left+right,len(v)):
   c=conf-right; x=v[c]; L=v[c-left:c]; R=v[c+1:c+right+1]
   if high:
    if mode=='unique': ok=all(x>z for z in L+R)
    elif mode=='equal': ok=all(x>=z for z in L+R)
    elif mode=='rightmost': ok=all(x>=z for z in L) and all(x>z for z in R)
    elif mode=='leftmost': ok=all(x>z for z in L) and all(x>=z for z in R)
    else: raise ValueError(mode)
   else:
    if mode=='unique': ok=all(x<z for z in L+R)
    elif mode=='equal': ok=all(x<=z for z in L+R)
    elif mode=='rightmost': ok=all(x<=z for z in L) and all(x<z for z in R)
    elif mode=='leftmost': ok=all(x<z for z in L) and all(x<=z for z in R)
    else: raise ValueError(mode)
   if ok: out[conf]=x
  return [None]+out[:-1],0
 return piv

def main():
 datasets={}
 for sym,sess in SPECS:
  bars,info=recent.fetch(sym,sess);datasets[sym]=(bars,info)
  print('FETCHED',sym,len(bars),flush=True)
 ref=base.load_ref(); original=ref.pivots; allres={}
 for mode in ('unique','equal','rightmost','leftmost'):
  ref.pivots=make_pivots(mode); res={}; score=0.0
  for sym,_ in SPECS:
   bars,info=datasets[sym]
   tr,m=base.run_case(ref,bars,info,base.START-timedelta(days=10),'start',True)
   expn,expr=EXPECTED[sym]
   rec={'n':m['n'],'R':m['R'],'dn':m['n']-expn,'dR':m['R']-expr,'trades':tr}
   res[sym]=rec;score += abs(rec['dn'])*10+abs(rec['dR'])
   print('PIVOT',mode,sym,'=>',m['n'],m['R'],'expected',expn,expr,flush=True)
  allres[mode]={'score':score,'results':res};print('SCORE',mode,score,flush=True)
 ref.pivots=original
 out=HERE/'output'/'tv-pivot-diagnostic';out.mkdir(parents=True,exist_ok=True)
 (out/'pivot-diagnostic.json').write_text(json.dumps(allres,indent=2,default=str))
 print('BEST',min(allres,key=lambda k:allres[k]['score']),flush=True)
if __name__=='__main__':main()
