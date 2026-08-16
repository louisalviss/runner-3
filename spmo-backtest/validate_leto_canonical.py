#!/usr/bin/env python3
import json, math
from pathlib import Path
import pandas as pd
import yfinance as yf

ROOT=Path('spmo-backtest/validated')
p=pd.read_csv(ROOT/'leto_live_period_checks.csv')
m=json.loads((ROOT/'leto_live_metrics.json').read_text())
assert len(p)==21
assert p.iloc[0].entry_date=='2016-03-21'
assert p.iloc[-1].exit_date=='2026-08-12'
for i in range(len(p)-1): assert p.iloc[i].exit_date==p.iloc[i+1].entry_date
switches=sum(a!=b for a,b in zip(p.top1,p.top1.iloc[1:]))
assert switches==16==m['switch_count']

errs=[]
for _,r in p.iterrows():
    d=yf.download(r.top1,start=(pd.Timestamp(r.entry_date)-pd.Timedelta(days=2)).strftime('%Y-%m-%d'),end=(pd.Timestamp(r.exit_date)+pd.Timedelta(days=3)).strftime('%Y-%m-%d'),auto_adjust=False,progress=False,threads=False)
    a=d['Adj Close'];
    if isinstance(a,pd.DataFrame): a=a.iloc[:,0]
    a.index=pd.to_datetime(a.index).tz_localize(None)
    calc=float(a.loc[pd.Timestamp(r.exit_date)]/a.loc[pd.Timestamp(r.entry_date)]-1)
    err=calc-float(r.close_to_close_return)
    errs.append(abs(err))
    print(r.entry_date,r.exit_date,r.top1,'stored',r.close_to_close_return,'calc',calc,'err',err)

period_multiple=float((1+p.close_to_close_return.astype(float)).prod())
print('period_multiple_from_rounded_csv',period_multiple)
print('canonical_daily_multiple',m['total_multiple'])
print('max_endpoint_error',max(errs))
print('switches',switches)
assert max(errs)<1e-6
assert abs(period_multiple-m['total_multiple'])<5e-6

# Recheck cost sensitivity formula.
sides=2+2*switches
for bps,key in [(1,'1_bps_per_side'),(5,'5_bps_per_side'),(10,'10_bps_per_side'),(20,'20_bps_per_side'),(50,'50_bps_per_side')]:
    mult=m['total_multiple']*(1-bps/10000)**sides
    assert abs(mult-m['transaction_cost_sensitivity'][key]['multiple'])<1e-10
print('CANONICAL_VALIDATION_PASS')
