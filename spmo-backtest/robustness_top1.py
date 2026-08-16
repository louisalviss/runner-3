#!/usr/bin/env python3
import json, math
from pathlib import Path
import numpy as np
import pandas as pd
import yfinance as yf

ROOT=Path('spmo-backtest/validated')
OUT=Path('spmo-backtest/robustness')
OUT.mkdir(parents=True,exist_ok=True)
p=pd.read_csv(ROOT/'leto_live_period_checks.csv')
p['entry_date']=pd.to_datetime(p.entry_date)
p['exit_date']=pd.to_datetime(p.exit_date)

START=p.entry_date.iloc[0]
END=p.exit_date.iloc[-1]
tickers=sorted(set(p.top1.tolist()+['SPY','QQQ','SPMO']))
raw=yf.download(tickers,start=(START-pd.Timedelta(days=20)).strftime('%Y-%m-%d'),end=(END+pd.Timedelta(days=20)).strftime('%Y-%m-%d'),auto_adjust=False,progress=False,threads=False)
adj=raw['Adj Close']
if isinstance(adj,pd.Series): adj=adj.to_frame(tickers[0])
adj.index=pd.to_datetime(adj.index).tz_localize(None)
adj=adj.sort_index()
calendar=adj['SPY'].dropna().index

def px(t,d):
    d=pd.Timestamp(d)
    s=adj[t].dropna()
    if d in s.index: return float(s.loc[d])
    # nearest previous trading day only
    z=s[s.index<=d]
    if z.empty: raise ValueError((t,d))
    return float(z.iloc[-1])

def shift_trade_day(d,k):
    d=pd.Timestamp(d)
    # canonical dates are trading days; shift by k positions on SPY calendar
    i=calendar.get_indexer([d])[0]
    if i<0:
        i=calendar.searchsorted(d)
        if i>=len(calendar): i=len(calendar)-1
    j=max(0,min(len(calendar)-1,i+k))
    return pd.Timestamp(calendar[j])

def cagr(mult,start,end):
    years=(pd.Timestamp(end)-pd.Timestamp(start)).days/365.2425
    return mult**(1/years)-1

def compound_for_shift(k):
    mult=1.0
    rows=[]
    for _,r in p.iterrows():
        en=shift_trade_day(r.entry_date,k)
        ex=shift_trade_day(r.exit_date,k)
        ret=px(r.top1,ex)/px(r.top1,en)-1
        mult*=1+ret
        rows.append((en,ex,r.top1,ret))
    return mult,cagr(mult,rows[0][0],rows[-1][1])

# Canonical daily wealth curve.
wealth=[]
w=1.0
for idx,r in p.iterrows():
    s=adj[r.top1].dropna()
    seg=s[(s.index>=r.entry_date)&(s.index<=r.exit_date)]
    base=float(seg.iloc[0])
    for d,v in seg.items():
        val=w*float(v)/base
        if wealth and d==wealth[-1][0]: wealth[-1]=(d,val)
        else: wealth.append((d,val))
    w*=float(seg.iloc[-1])/base
curve=pd.Series(dict(wealth)).sort_index()
curve.name='wealth'

# Shift sensitivity.
shift_rows=[]
for k in range(-5,11):
    mult,cg=compound_for_shift(k)
    shift_rows.append({'trading_day_shift':k,'multiple':mult,'cagr':cg})
shift_df=pd.DataFrame(shift_rows)
shift_df.to_csv(OUT/'date_shift_sensitivity.csv',index=False)

# Rolling CAGR with fixed trading-day windows.
roll={}
for yrs,n in [(1,252),(3,756),(5,1260)]:
    vals=(curve/curve.shift(n))**(252/n)-1
    vals=vals.dropna()
    roll[str(yrs)+'y']={
      'observations':int(len(vals)),
      'min':float(vals.min()),
      'p10':float(vals.quantile(.10)),
      'median':float(vals.median()),
      'p90':float(vals.quantile(.90)),
      'max':float(vals.max()),
      'positive_fraction':float((vals>0).mean()),
      'negative_fraction':float((vals<0).mean()),
      'min_end_date':str(vals.idxmin().date()),
      'max_end_date':str(vals.idxmax().date())
    }

# Drawdown and time-under-water.
peak=curve.cummax(); dd=curve/peak-1
maxdd=float(dd.min()); trough=dd.idxmin(); peak_date=curve.loc[:trough].idxmax()
# longest run below prior high in trading days
under=dd<0
longest=0; cur=0; end_long=None
for d,b in under.items():
    if b:
        cur+=1
        if cur>longest: longest=cur; end_long=d
    else: cur=0
start_long=curve.index[max(0,curve.index.get_loc(end_long)-longest+1)] if end_long is not None else None

# Regime splits aligned to canonical boundaries.
regimes=[
 ('pre_covid','2016-03-21','2020-03-23'),
 ('covid_to_2022_bear_end','2020-03-23','2022-09-19'),
 ('post_2022_ai_bull','2022-09-19','2026-08-12'),
 ('first_half','2016-03-21','2021-09-20'),
 ('second_half','2021-09-20','2026-08-12')
]
reg_rows=[]
for name,a,b in regimes:
    a=pd.Timestamp(a); b=pd.Timestamp(b)
    va=float(curve.loc[a]); vb=float(curve.loc[b]); m=vb/va
    reg_rows.append({'regime':name,'start':str(a.date()),'end':str(b.date()),'multiple':m,'cagr':cagr(m,a,b)})
reg_df=pd.DataFrame(reg_rows)
reg_df.to_csv(OUT/'regime_splits.csv',index=False)

# Benchmark comparison on same full window and regimes.
def bench_stats(t,a,b):
    a=pd.Timestamp(a); b=pd.Timestamp(b)
    s=adj[t].dropna(); a0=s.index[s.index>=a][0]; b0=s.index[s.index<=b][-1]
    m=float(s.loc[b0]/s.loc[a0]); return m,cagr(m,a0,b0)
bench=[]
for t in ['SPY','QQQ','SPMO']:
    m,cg=bench_stats(t,START,END)
    bench.append({'asset':t,'window':'full','multiple':m,'cagr':cg})
    for name,a,b in regimes[:3]:
        m,cg=bench_stats(t,a,b)
        bench.append({'asset':t,'window':name,'multiple':m,'cagr':cg})
bench_df=pd.DataFrame(bench)
bench_df.to_csv(OUT/'benchmark_comparison.csv',index=False)

# Leave-one-out and leave-top-winners-out dependence.
period_returns=p.close_to_close_return.astype(float).to_numpy()
base_mult=float(np.prod(1+period_returns))
loo=[]
for i,r in p.iterrows():
    m=base_mult/(1+float(r.close_to_close_return))
    loo.append({'removed_period':f"{r.entry_date.date()}->{r.exit_date.date()} {r.top1}",'removed_return':float(r.close_to_close_return),'remaining_multiple':m,'remaining_cagr_same_window':cagr(m,START,END)})
loo_df=pd.DataFrame(loo).sort_values('remaining_multiple')
loo_df.to_csv(OUT/'leave_one_out.csv',index=False)
win_idx=np.argsort(period_returns)[::-1]
remove_top={}
for n in [1,2,3,5]:
    keep=np.ones(len(period_returns),dtype=bool); keep[win_idx[:n]]=False
    m=float(np.prod(1+period_returns[keep]))
    remove_top[str(n)]={'multiple':m,'cagr_same_full_window':cagr(m,START,END),'removed_period_returns':[float(x) for x in period_returns[win_idx[:n]]]}

# Random timing delays: at each actual ticker switch, delay the switch 0..5 trading days,
# holding the previous ticker until the delayed close. Initial entry is canonical Monday.
rng=np.random.default_rng(20260817)
bounds=[p.entry_date.iloc[0]]+p.exit_date.tolist()
seq=p.top1.tolist()
# Build exact price-based simulator for delayed switch dates.
def sim_delays(max_delay):
    w=1.0
    cur_t=seq[0]
    cur_date=bounds[0]
    for i in range(1,len(bounds)):
        boundary=pd.Timestamp(bounds[i])
        next_t=seq[i] if i<len(seq) else None
        if i<len(seq) and next_t!=cur_t:
            k=int(rng.integers(0,max_delay+1))
            sw=shift_trade_day(boundary,k)
            w*=px(cur_t,sw)/px(cur_t,cur_date)
            cur_t=next_t; cur_date=sw
        elif i<len(seq):
            # no switch, continue; do not reset cost basis/date
            pass
        else:
            w*=px(cur_t,boundary)/px(cur_t,cur_date)
    return w
mc={}
for md in [1,3,5]:
    vals=np.array([sim_delays(md) for _ in range(2000)])
    mc[str(md)]={'runs':2000,'min_multiple':float(vals.min()),'p10_multiple':float(np.quantile(vals,.1)),'median_multiple':float(np.median(vals)),'p90_multiple':float(np.quantile(vals,.9)),'max_multiple':float(vals.max()),'median_cagr':cagr(float(np.median(vals)),START,END)}

summary={
 'canonical_multiple':float(curve.iloc[-1]),
 'canonical_cagr':cagr(float(curve.iloc[-1]),START,END),
 'max_drawdown':maxdd,
 'max_drawdown_peak':str(peak_date.date()),
 'max_drawdown_trough':str(trough.date()),
 'longest_underwater_trading_days':int(longest),
 'longest_underwater_start':str(start_long.date()) if start_long is not None else None,
 'longest_underwater_end':str(end_long.date()) if end_long is not None else None,
 'rolling':roll,
 'remove_top_winners':remove_top,
 'random_switch_delay':mc,
 'topn_status':'not independently testable from currently recovered source because exact historical rebalance ranks 2..20 are not present; later SEC snapshots are not a valid substitute',
 'source_top20_claim':{'cagr':0.2283,'sharpe':0.95,'max_drawdown':-0.293,'status':'Leto claim only; not independently reproduced in this run'}
}
(OUT/'robustness_summary.json').write_text(json.dumps(summary,indent=2))
curve.to_csv(OUT/'canonical_daily_curve.csv')
print(json.dumps(summary,indent=2))
print('\nDATE SHIFT\n',shift_df.to_string(index=False))
print('\nREGIMES\n',reg_df.to_string(index=False))
print('\nBENCHMARKS\n',bench_df.to_string(index=False))
print('ROBUSTNESS_TOP1_PASS')
