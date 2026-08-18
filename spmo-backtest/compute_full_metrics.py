#!/usr/bin/env python3
import json, math
from pathlib import Path
import pandas as pd
import numpy as np
import yfinance as yf

SRC=Path('spmo-backtest/validated/period_checks.csv')
OUT=Path('spmo-backtest/validated')
p= pd.read_csv(SRC)
p['rebalance_date']=pd.to_datetime(p['rebalance_date'])
p['exit_date']=pd.to_datetime(p['exit_date'])
p=p.sort_values('rebalance_date').reset_index(drop=True)
assert len(p)==21, f'Expected 21 periods, got {len(p)}'
assert p.iloc[0].rebalance_date == pd.Timestamp('2016-03-18')
assert p.iloc[-1].exit_date == pd.Timestamp('2026-08-14')

# Verify periods are contiguous: each exit is next rebalance, except final partial.
for i in range(len(p)-1):
    assert p.loc[i,'exit_date']==p.loc[i+1,'rebalance_date'], (i,p.loc[i,'exit_date'],p.loc[i+1,'rebalance_date'])

def get_adj(ticker,start,end):
    d=yf.download(ticker,start=(start-pd.Timedelta(days=5)).strftime('%Y-%m-%d'),end=(end+pd.Timedelta(days=5)).strftime('%Y-%m-%d'),auto_adjust=False,actions=True,progress=False,threads=False)
    if d.empty: raise RuntimeError(f'No price data {ticker}')
    x=d['Adj Close']
    if isinstance(x,pd.DataFrame): x=x.iloc[:,0]
    x=x.dropna()
    x.index=pd.to_datetime(x.index).tz_localize(None)
    return x

cache={}
for t in sorted(p.top1.unique()):
    cache[t]=get_adj(t,p.rebalance_date.min(),p.exit_date.max())

segments=[]
checks=[]
equity_start=1.0
for i,r in p.iterrows():
    s=cache[r.top1]
    seg=s[(s.index>=r.rebalance_date)&(s.index<=r.exit_date)].copy()
    if seg.empty: raise RuntimeError(f'Empty segment {r.top1} {r.rebalance_date} {r.exit_date}')
    if seg.index[0] != r.rebalance_date or seg.index[-1] != r.exit_date:
        raise RuntimeError(f'Endpoint mismatch {r.top1}: got {seg.index[0]}..{seg.index[-1]}, expected {r.rebalance_date}..{r.exit_date}')
    norm=seg/seg.iloc[0]
    curve=equity_start*norm
    calc=float(norm.iloc[-1]-1.0)
    stored=float(r.close_to_close_return)
    diff=calc-stored
    checks.append({
        'rebalance_date':r.rebalance_date.strftime('%Y-%m-%d'),
        'exit_date':r.exit_date.strftime('%Y-%m-%d'),
        'ticker':r.top1,
        'stored_return':stored,
        'price_recheck_return':calc,
        'difference':diff,
        'abs_difference':abs(diff),
    })
    # At a switch date, retain the closing equity once, then new ticker begins at that same close.
    if i>0: curve=curve.iloc[1:]
    segments.append(curve.rename('equity'))
    equity_start=float((equity_start*norm.iloc[-1]))

curve=pd.concat(segments).sort_index()
curve=curve[~curve.index.duplicated(keep='first')]
daily=curve.pct_change().dropna()
start=p.iloc[0].rebalance_date
end=p.iloc[-1].exit_date
years=(end-start).days/365.2425
multiple=float(curve.iloc[-1]/curve.iloc[0])
cagr=float(multiple**(1/years)-1)
vol=float(daily.std(ddof=1)*math.sqrt(252))
ann_arith=float(daily.mean()*252)
sharpe0=float(ann_arith/vol)
# Also report CAGR/vol as a transparent geometric-return/risk ratio; this is NOT conventional Sharpe.
cagr_over_vol=float(cagr/vol)
rolling_peak=curve.cummax()
dd=curve/rolling_peak-1
trough=dd.idxmin(); maxdd=float(dd.loc[trough])
peak=curve.loc[:trough].idxmax()
period_multiple=float(np.prod(1+p.close_to_close_return.astype(float).values))
period_cagr=float(period_multiple**(1/years)-1)
max_check_error=float(max(x['abs_difference'] for x in checks))

metrics={
    'start_date':start.strftime('%Y-%m-%d'),
    'end_date':end.strftime('%Y-%m-%d'),
    'years_365_2425':years,
    'period_count':int(len(p)),
    'total_multiple_daily_curve':multiple,
    'total_return_pct':(multiple-1)*100,
    'cagr':cagr,
    'annualized_volatility_daily_252':vol,
    'annualized_arithmetic_mean_return_daily_252':ann_arith,
    'sharpe_rf0_daily_252':sharpe0,
    'cagr_over_vol_not_sharpe':cagr_over_vol,
    'max_drawdown':maxdd,
    'max_drawdown_peak_date':peak.strftime('%Y-%m-%d'),
    'max_drawdown_trough_date':trough.strftime('%Y-%m-%d'),
    'period_return_compound_multiple':period_multiple,
    'period_return_compound_cagr':period_cagr,
    'max_abs_period_return_recheck_error':max_check_error,
    'transaction_costs':0,
    'taxes':0,
    'risk_free_rate_for_sharpe':0,
    'price_field':'Yahoo Finance Adjusted Close',
}
OUT.mkdir(parents=True,exist_ok=True)
(OUT/'full_backtest_metrics.json').write_text(json.dumps(metrics,indent=2))
pd.DataFrame(checks).to_csv(OUT/'period_return_recheck.csv',index=False)
pd.DataFrame({'date':curve.index.strftime('%Y-%m-%d'),'equity':curve.values,'drawdown':dd.values}).to_csv(OUT/'daily_equity.csv',index=False)
print('FULL_METRICS')
print(json.dumps(metrics,indent=2))
print('\nPERIOD_RECHECK')
print(pd.DataFrame(checks).to_string(index=False))
