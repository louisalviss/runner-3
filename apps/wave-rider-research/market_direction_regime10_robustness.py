#!/usr/bin/env python3
from __future__ import annotations
import hashlib, json, os, sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
import numpy as np
import pandas as pd

HELPER=Path(os.getenv('WR_HELPER_DIR','/tmp/wr-helper')); sys.path.insert(0,str(HELPER))
import wr_dukascopy_expanded_matrix as exp
SRC=Path(os.getenv('WR_SOURCE_ROOT','/tmp/source'))
OUT=Path(os.getenv('WR_OUT','/tmp/out')); OUT.mkdir(parents=True,exist_ok=True)
TF_MIN=10; EMA_LEN=200; COSTS=(0.0,0.5,1.0); SOURCE_RUN=32507430808
N_SIM=20_000; BLOCK_DAYS=5; SEED=20260823


def parse_side(t):
    s=str(t.get('side','')).strip().upper()
    if s in ('L','LONG'): return 'LONG'
    if s in ('S','SHORT'): return 'SHORT'
    raise ValueError(f'unknown side={s!r}')


def read_all_trades():
    out=[]
    for p in sorted(SRC.rglob(f'trades-*-{TF_MIN}m.jsonl')):
        if p.name==f'trades-US500-{TF_MIN}m.jsonl': continue
        for ln in p.read_text().splitlines():
            if not ln.strip(): continue
            t=json.loads(ln); parse_side(t); out.append(t)
    if not out: raise RuntimeError('no 10m stock trades found')
    return out


def load_us500_close():
    df,manifest,instrument=exp.load_mid('US500',TF_MIN)
    if df is None or df.empty: raise RuntimeError('no US500 midpoint data')
    s=df['close'].copy().dropna().sort_index()
    if s.index.tz is None: s.index=s.index.tz_localize('UTC')
    else: s.index=s.index.tz_convert('UTC')
    return s


def feature_ts(t):
    return pd.Timestamp(int(t['signal']),unit='ms',tz='UTC')-pd.Timedelta(minutes=TF_MIN)


def build_bull(close):
    ema=close.ewm(span=EMA_LEN,adjust=False,min_periods=EMA_LEN).mean()
    slope=ema.diff()
    return (close>ema)&(slope>0), ema, slope


def cost_r(t,bps):
    d=abs(float(t['e'])-float(t['s']))
    return 0.0 if d<=0 else (float(t['e'])/d)*(bps/10000.0)


def net_r(t,bps): return float(t['R'])-cost_r(t,bps)
def symbol(t): return str(t.get('symbol','')).upper()
def year(t): return datetime.fromtimestamp(int(t['signal'])/1000,tz=timezone.utc).year
def day(t): return datetime.fromtimestamp(int(t['signal'])/1000,tz=timezone.utc).date().isoformat()


def metrics(trades,bps=0.0):
    xs=[net_r(t,bps) for t in trades]
    if not xs: return {'n':0,'R':0.0,'avg_R':None,'PF':None,'win_rate':None,'max_DD_R':0.0}
    gp=sum(max(x,0.0) for x in xs); gl=sum(max(-x,0.0) for x in xs)
    eq=peak=0.0; mdd=0.0
    for x in xs:
        eq+=x; peak=max(peak,eq); mdd=min(mdd,eq-peak)
    return {'n':len(xs),'R':sum(xs),'avg_R':sum(xs)/len(xs),'PF':gp/gl if gl else None,
            'win_rate':100.0*sum(x>0 for x in xs)/len(xs),'max_DD_R':mdd}


def pack(trades): return {f'{b:g}bps':metrics(trades,b) for b in COSTS}


def percentile_summary(xs, actual=None):
    a=np.asarray(xs,dtype=float)
    out={'n':int(a.size),'p2_5':float(np.percentile(a,2.5)),'p50':float(np.percentile(a,50)),
         'p97_5':float(np.percentile(a,97.5)),'p_gt_0':float(np.mean(a>0))}
    if actual is not None:
        out['actual']=float(actual)
        out['actual_percentile']=float(100.0*np.mean(a<=actual))
        out['one_sided_p_random_ge_actual']=float((1+np.sum(a>=actual))/(a.size+1))
    return out


def symbol_fold(sym):
    h=int(hashlib.sha256(sym.encode()).hexdigest()[:16],16)
    return h%5


def select_long_bull(trades,bull,ema,slope):
    base=[]; kept=[]; missing=[]
    for t in trades:
        if parse_side(t)!='LONG': continue
        ts=feature_ts(t)
        if ts not in bull.index or pd.isna(ema.loc[ts]) or pd.isna(slope.loc[ts]):
            missing.append(t); continue
        base.append(t)
        if bool(bull.loc[ts]): kept.append(t)
    if len(missing)>max(20,int(0.01*max(1,len(base)+len(missing)))):
        raise RuntimeError(f'material missing causal rows: {len(missing)}')
    return base,kept,missing


def placebo_same_year_counts(base,kept,rng,bps):
    base_by_year={y:[t for t in base if year(t)==y] for y in range(2022,2027)}
    k_by_year={y:sum(1 for t in kept if year(t)==y) for y in range(2022,2027)}
    vals=np.empty(N_SIM,dtype=float)
    net_by_year={y:np.asarray([net_r(t,bps) for t in base_by_year[y]],dtype=float) for y in base_by_year}
    for i in range(N_SIM):
        total=0.0
        for y in range(2022,2027):
            arr=net_by_year[y]; k=k_by_year[y]
            if k:
                idx=rng.choice(arr.size,size=k,replace=False)
                total+=float(arr[idx].sum())
        vals[i]=total
    return vals


def moving_block_bootstrap_daily(kept,rng,bps):
    d=defaultdict(float)
    for t in kept: d[day(t)]+=net_r(t,bps)
    days=sorted(d); vals=np.asarray([d[x] for x in days],dtype=float)
    n=len(vals)
    if n==0: return np.zeros(N_SIM),0
    starts=np.arange(n)
    out=np.empty(N_SIM,dtype=float)
    blocks=int(np.ceil(n/BLOCK_DAYS))
    offsets=np.arange(BLOCK_DAYS)
    for i in range(N_SIM):
        st=rng.choice(starts,size=blocks,replace=True)
        idx=((st[:,None]+offsets[None,:])%n).ravel()[:n]
        out[i]=float(vals[idx].sum())
    return out,n


def main():
    trades=read_all_trades(); close=load_us500_close(); bull,ema,slope=build_bull(close)
    base,kept,missing=select_long_bull(trades,bull,ema,slope)
    rng=np.random.default_rng(SEED)

    years={}
    for y in range(2022,2027):
        b=[t for t in base if year(t)==y]; k=[t for t in kept if year(t)==y]
        years[str(y)]={'base':pack(b),'bull':pack(k),'retention_pct':100*len(k)/len(b) if b else None}

    loo={}
    for y in range(2022,2027):
        k=[t for t in kept if year(t)!=y]
        loo[str(y)]={'excluded_year':y,'remaining':pack(k)}

    syms=sorted(set(symbol(t) for t in base))
    sym_rows={}; pos_counts={f'{b:g}bps':0 for b in COSTS}; medians={}; contrib={}
    for s in syms:
        k=[t for t in kept if symbol(t)==s]
        row=pack(k); sym_rows[s]=row
        for b in COSTS:
            if row[f'{b:g}bps']['R']>0: pos_counts[f'{b:g}bps']+=1
    for b in COSTS:
        rs=np.asarray([sym_rows[s][f'{b:g}bps']['R'] for s in syms],dtype=float)
        medians[f'{b:g}bps']=float(np.median(rs))
        abs_sum=float(np.abs(rs).sum())
        top5=float(np.sort(np.abs(rs))[-5:].sum()) if rs.size>=5 else abs_sum
        contrib[f'{b:g}bps']={'top5_abs_share_pct':100*top5/abs_sum if abs_sum else None,
                              'positive_symbols':pos_counts[f'{b:g}bps'],'negative_or_zero_symbols':len(syms)-pos_counts[f'{b:g}bps']}

    folds={}
    for f in range(5):
        fs={s for s in syms if symbol_fold(s)==f}
        k=[t for t in kept if symbol(t) in fs]
        folds[str(f)]={'symbols':sorted(fs),'metrics':pack(k)}

    placebo={}; bootstrap={}
    for b in COSTS:
        actual=metrics(kept,b)['R']
        pvals=placebo_same_year_counts(base,kept,rng,b)
        placebo[f'{b:g}bps']=percentile_summary(pvals,actual)
        boot,n_days=moving_block_bootstrap_daily(kept,rng,b)
        bootstrap[f'{b:g}bps']={'trading_days':n_days,'block_days':BLOCK_DAYS,**percentile_summary(boot)}

    report={
      'status':'COMPLETE',
      'candidate':'WR US stocks 10m LONG only + causal US500 EMA200 bullish regime',
      'source_wr_run':SOURCE_RUN,
      'rule':{'timeframe':'10m','ema_length':EMA_LEN,'bull':'US500 close > EMA200 and EMA200 slope > 0',
              'causal_feature_bar':'signal_timestamp - 10m exact row','parameter_sweep':False},
      'robustness_preregistration':{'costs_bps':list(COSTS),'placebo_draws':N_SIM,'placebo':'same selected count within each calendar year',
                                    'moving_block_bootstrap_draws':N_SIM,'moving_block_days':BLOCK_DAYS,
                                    'symbol_folds':'sha256(symbol) mod 5','seed':SEED},
      'integrity':{'missing_exact_causal_rows':len(missing),'future_fallback':False,'base_long_rows':len(base),'selected_long_rows':len(kept)},
      'aggregate':{'base_long':pack(base),'long_bull':pack(kept),'retention_pct':100*len(kept)/len(base)},
      'years':years,'leave_one_year_out':loo,
      'symbol_breadth':{'symbols':len(syms),'median_symbol_R':medians,'concentration':contrib,'rows':sym_rows},
      'symbol_folds':folds,'placebo_same_year_counts':placebo,'moving_block_bootstrap_daily':bootstrap
    }
    (OUT/'robustness.json').write_text(json.dumps(report,indent=2))
    print('LONG_BULL',report['aggregate']['long_bull'])
    print('YEARS', {y:{b:v['bull'][b]['R'] for b in ('0bps','0.5bps','1bps')} for y,v in years.items()})
    print('PLACEBO',placebo)
    print('BOOTSTRAP',bootstrap)
    print('BREADTH', {k:v for k,v in contrib.items()})

if __name__=='__main__': main()
