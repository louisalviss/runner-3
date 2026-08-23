from __future__ import annotations

import json
import math
import time

import numpy as np
import pandas as pd

from backtest import load_prices, load_memberships, add_membership_flag

DISC_START = pd.Timestamp('2010-01-01')
DISC_END = pd.Timestamp('2016-12-31')
VAL_START = pd.Timestamp('2017-01-01')
VAL_END = pd.Timestamp('2024-12-31')
BOTTOM_FRAC = 0.20
COST_BPS = 25.0


def ann_return(r):
    x = pd.Series(r).dropna().astype(float)
    if x.empty: return np.nan
    return float(np.prod(1+x) ** (12.0/len(x)) - 1)


def ann_vol(r):
    x = pd.Series(r).dropna().astype(float)
    return float(x.std(ddof=1) * math.sqrt(12)) if len(x) > 1 else np.nan


def sharpe0(r):
    x = pd.Series(r).dropna().astype(float)
    if len(x) < 2 or x.std(ddof=1) == 0: return np.nan
    return float(x.mean()/x.std(ddof=1)*math.sqrt(12))


def maxdd(r):
    x = pd.Series(r).dropna().astype(float)
    if x.empty: return np.nan
    eq = (1+x).cumprod()
    return float((eq/eq.cummax()-1).min())


def turnover(prev, cur):
    if not prev: return 1.0
    names = set(prev) | set(cur)
    return 0.5 * sum(abs(cur.get(s,0)-prev.get(s,0)) for s in names)


def main():
    t0=time.time()
    w=load_prices()
    _, periods=load_memberships()
    w=add_membership_flag(w, periods)
    w['week']=pd.to_datetime(w['week']).astype('datetime64[ns]')
    w=w.sort_values(['series_id','week']).reset_index(drop=True)
    g=w.groupby('series_id',sort=False,observed=True)
    w['weekly_ret']=g['close'].pct_change(fill_method=None)
    w['vol52']=w['weekly_ret'].groupby(w['series_id'],observed=True).transform(lambda s:s.rolling(52,min_periods=40).std(ddof=1)*math.sqrt(52))
    w['next_open']=g['open'].shift(-1)
    w['next_week']=g['week'].shift(-1)
    meta=w.groupby('series_id',observed=True).agg(series_last_week=('week','max'),series_last_close=('close','last'))

    cal=w.loc[w['week'].between(DISC_START-pd.Timedelta(days=400),VAL_END),['week']].drop_duplicates().copy()
    cal['month']=cal['week'].dt.to_period('M')
    forms=cal.groupby('month',as_index=False)['week'].max().sort_values('week').reset_index(drop=True)
    forms['next_form_week']=forms['week'].shift(-1)
    forms=forms[forms['week'].between(DISC_START,VAL_END)&forms['next_form_week'].notna()]

    rows=[]; prev_low={}; prev_bench={}
    c=COST_BPS/10000.0
    for rr in forms.itertuples(index=False):
        fw=pd.Timestamp(rr.week); nfw=pd.Timestamp(rr.next_form_week)
        f=w[w['week'].eq(fw)&w['is_member'].fillna(False)&w['vol52'].notna()&w['next_open'].notna()][['symbol','series_id','vol52','next_open']].copy()
        if len(f)<100: continue
        ex=w[w['week'].eq(nfw)][['series_id','next_open']].rename(columns={'next_open':'exit_open'})
        f=f.merge(ex,on='series_id',how='left').merge(meta,on='series_id',how='left')
        target=nfw+pd.Timedelta(days=10)
        ended=f['series_last_week']<target
        mask=f['exit_open'].isna()&ended
        f.loc[mask,'exit_open']=f.loc[mask,'series_last_close']
        f['hold_ret']=f['exit_open']/f['next_open']-1
        f=f.replace([np.inf,-np.inf],np.nan).dropna(subset=['hold_ret'])
        if len(f)<100: continue
        f=f.sort_values(['vol52','symbol'],ascending=[True,True]).reset_index(drop=True)
        k=max(1,int(math.floor(len(f)*BOTTOM_FRAC)))
        low=f.iloc[:k].copy()
        lw={s:1/len(low) for s in low['symbol'].astype(str)}
        bw={s:1/len(f) for s in f['symbol'].astype(str)}
        lto=turnover(prev_low,lw); bto=turnover(prev_bench,bw)
        prev_low=lw; prev_bench=bw
        lg=float(low['hold_ret'].mean()); bg=float(f['hold_ret'].mean())
        ln=(1+lg)*(1-c*lto)-1; bn=(1+bg)*(1-c*bto)-1
        rows.append({'formation_week':fw,'universe_n':len(f),'low_n':len(low),'low_turnover':lto,'bench_turnover':bto,'low_gross':lg,'bench_gross':bg,'low_net25':ln,'bench_net25':bn,'gross_excess':lg-bg,'vol_cutoff':float(low['vol52'].max())})

    p=pd.DataFrame(rows).sort_values('formation_week').reset_index(drop=True)
    if p.empty: raise RuntimeError('no low-vol periods')
    print('META',json.dumps({'periods':len(p),'min':str(p.formation_week.min().date()),'max':str(p.formation_week.max().date()),'median_universe':float(p.universe_n.median()),'median_low_n':float(p.low_n.median()),'mean_low_turnover':float(p.low_turnover.mean()),'elapsed_sec':round(time.time()-t0,2)}),flush=True)

    def summ(label,start,end):
        x=p[p.formation_week.between(start,end)].copy()
        yearly={}
        for y,q in x.groupby(x.formation_week.dt.year):
            lr=float(np.prod(1+q.low_gross)-1); br=float(np.prod(1+q.bench_gross)-1)
            yearly[str(y)]={'low':lr,'bench':br,'excess':lr-br,'months':len(q)}
        return {'slice':label,'months':len(x),'low_cagr_gross':ann_return(x.low_gross),'bench_cagr_gross':ann_return(x.bench_gross),'cagr_diff_gross':ann_return(x.low_gross)-ann_return(x.bench_gross),'low_sharpe_gross':sharpe0(x.low_gross),'bench_sharpe_gross':sharpe0(x.bench_gross),'sharpe_improvement_gross':sharpe0(x.low_gross)-sharpe0(x.bench_gross),'low_vol_gross':ann_vol(x.low_gross),'bench_vol_gross':ann_vol(x.bench_gross),'low_maxdd_gross':maxdd(x.low_gross),'bench_maxdd_gross':maxdd(x.bench_gross),'maxdd_improvement':maxdd(x.low_gross)-maxdd(x.bench_gross),'low_cagr_net25':ann_return(x.low_net25),'bench_cagr_net25':ann_return(x.bench_net25),'cagr_diff_net25':ann_return(x.low_net25)-ann_return(x.bench_net25),'low_sharpe_net25':sharpe0(x.low_net25),'bench_sharpe_net25':sharpe0(x.bench_net25),'sharpe_improvement_net25':sharpe0(x.low_net25)-sharpe0(x.bench_net25),'mean_low_turnover':float(x.low_turnover.mean()),'monthly_excess_median':float(x.gross_excess.median()),'monthly_beat_rate':float((x.gross_excess>0).mean()),'yearly':yearly}

    d=summ('discovery_2010_2016',DISC_START,DISC_END); v=summ('validation_2017_2024',VAL_START,VAL_END)
    print('DISCOVERY',json.dumps(d),flush=True); print('VALIDATION',json.dumps(v),flush=True)
    gate={'months_ge_90':v['months']>=90,'gross_cagr_shortfall_ge_minus_1pct':v['cagr_diff_gross']>=-0.01,'gross_sharpe_improvement_ge_0_15':v['sharpe_improvement_gross']>=0.15,'maxdd_improvement_ge_5pp':v['maxdd_improvement']>=0.05,'net25_cagr_shortfall_ge_minus_1_5pct':v['cagr_diff_net25']>=-0.015,'net25_sharpe_improvement_ge_0_10':v['sharpe_improvement_net25']>=0.10}
    gate['pass']=bool(all(gate.values()))
    print('GATE',json.dumps(gate),flush=True); print('DONE',flush=True)

if __name__=='__main__': main()
