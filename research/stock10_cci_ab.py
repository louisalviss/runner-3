#!/usr/bin/env python3
import json, os, sys
from pathlib import Path
sys.path[:0]=[os.environ['WR_PATCH_DIR'],os.environ['WR_BASE_DIR'],os.environ['WR_STRUCT_DIR']]
from close_confirm import run_case, assert_canonical_parity
import stock10_close_ab as old
import wr_dukascopy_expanded_matrix as exp
OUT=Path(os.getenv('WR_OUT','/tmp/wr-stock10-cci')); OUT.mkdir(parents=True,exist_ok=True)
SYM=os.environ['SYMBOL'].upper(); N=27; LB=18

def flags(bars):
    tp=[(b.h+b.l+b.c)/3 for b in bars]; cc=[None]*len(bars); out={}
    for i in range(N-1,len(bars)):
        w=tp[i-N+1:i+1]; ma=sum(w)/N; md=sum(abs(x-ma) for x in w)/N
        cc[i]=0 if md==0 else (tp[i]-ma)/(0.015*md)
    for i,b in enumerate(bars):
        if i<N+LB-2: continue
        w=cc[i-LB+1:i+1]
        if None not in w: out[int(b.ct)]=(cc[i],min(w),max(w))
    return out

def cmp(a,b):
    A=a['oos_2024_2026']['net_1bps']; B=b['oos_2024_2026']['net_1bps']
    return {'base_n':A['n'],'filtered_n':B['n'],'retention':B['n']/A['n'] if A['n'] else None,
            'base_R':A['R'],'filtered_R':B['R'],'delta_R':B['R']-A['R'],
            'base_avg_R':A['avg_R'],'filtered_avg_R':B['avg_R'],'delta_avg_R':(B['avg_R']-A['avg_R']) if A['avg_R'] is not None and B['avg_R'] is not None else None,
            'base_PF':A['PF'],'filtered_PF':B['PF'],'base_DD':A['max_DD_R'],'filtered_DD':B['max_DD_R']}

def main():
    inst=exp.resolve_symbol(SYM)
    if not inst: return
    raw,manifest,_=exp.load_mid(SYM,5)
    if raw is None or raw.empty: return
    df,reject=exp.aggregate(raw,5,10); base,ref=exp.load_modules(10); _,tick,_,_=exp.cfg(SYM); base.tv_tick=lambda _i,_v:tick
    bars=exp.to_bars(df,base.Bar,10); info=exp.provider_info(SYM); hist=exp.STATE_START.to_pydatetime(); start=exp.START.to_pydatetime(); end=exp.END.to_pydatetime()
    parity=assert_canonical_parity(base,ref,bars,info,hist,start,end,anchor='start',use_session=True); F=flags(bars)
    gl=lambda t,d:d==1
    gc=lambda t,d:d==1 and t in F and F[t][1] < -100
    gs=lambda t,d:t in F and ((d==1 and F[t][1] < -100) or (d==-1 and F[t][2] > 100))
    runs={}
    for name,gate in [('base_both',None),('base_long',gl),('cci_long_exact',gc),('cci_symmetric',gs)]:
        tr,rawx=run_case(base,ref,bars,info,hist,start,end,variant='canonical',anchor='start',use_session=True,eligible_signal=gate)
        runs[name]=(tr,old.report_variant(name,tr,rawx))
    reps={k:v[1] for k,v in runs.items()}
    payload={'status':'OK','symbol':SYM,'bars':len(bars),'rejected_10m_buckets':reject,'parity_n':parity,'instrument':inst,
             'rule':{'exact_long':'Lowest(CCI(27),18)<-100','short_extension':'Highest(CCI(27),18)>+100; not source-published'},
             'variants':reps,'comparisons':{'exact_long':cmp(reps['base_long'],reps['cci_long_exact']),'symmetric':cmp(reps['base_both'],reps['cci_symmetric'])},'manifest':manifest}
    (OUT/f'{SYM}.json').write_text(json.dumps(payload,indent=2,default=str))
    with (OUT/f'{SYM}-trades.jsonl').open('w') as f:
        for name,(tr,_) in runs.items():
            for t in tr:
                z=F.get(int(t['signal']),(None,None,None)); f.write(json.dumps({'symbol':SYM,'variant':name,'year':old.year_of(t),'cci':z[0],'cci_min18':z[1],'cci_max18':z[2],**t})+'\n')
    print('CCI_RESULT',SYM,json.dumps(payload['comparisons'],sort_keys=True),flush=True)
if __name__=='__main__': main()
