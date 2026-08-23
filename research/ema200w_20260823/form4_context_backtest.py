from __future__ import annotations

import json
import time

import numpy as np
import pandas as pd

from form4_decomposition_backtest import (
    DISC_START, DISC_END, VAL_START, VAL_END,
    load_events, load_weekly_prices,
)
from form4_sec_backtest import map_to_prices, add_recent_buy_flag, summarize

HORIZONS = (13, 26, 52)


def add_drawdown(w: pd.DataFrame) -> pd.DataFrame:
    q = w.copy().sort_values(['series_id','week'])
    g = q.groupby('series_id', sort=False, observed=True)
    q['close_pre'] = g['close'].shift(1)
    q['high52_pre'] = g['close'].transform(lambda s: s.shift(1).rolling(52, min_periods=52).max())
    q['dd52_pre'] = q['close_pre'] / q['high52_pre'] - 1
    return q


def build_strategies(base: pd.DataFrame):
    b = base[base['filing_date'].between(DISC_START, VAL_END)].copy()
    out = []
    a = b.copy(); a['strategy'] = 'BaseBuyP'; out.append(a)
    # Frozen contextual rule: prior completed weekly close at least 20% below prior 52-week high.
    # The actual dd filter is applied after causal mapping to weekly price state.
    a = b.copy(); a['strategy'] = 'DeepDD20'; out.append(a)
    a = b[b['is_exec']].copy(); a['strategy'] = 'ExecDeepDD20'; out.append(a)
    return pd.concat(out, ignore_index=True)


def matched_excess_context(ev: pd.DataFrame, w: pd.DataFrame):
    for h in HORIZONS:
        ev[f'excess{h}'] = np.nan
        ev[f'control_n{h}'] = 0
    byweek = {wk: g for wk, g in w[w['is_member'].fillna(False)].groupby('week', sort=False)}
    for j, r in enumerate(ev.itertuples(index=False)):
        p = byweek.get(r.week)
        if p is None or not np.isfinite(r.ret52_pre) or not np.isfinite(r.dd52_pre):
            continue
        rr = p['ret52_pre'].to_numpy(float)
        dd = p['dd52_pre'].to_numpy(float)
        sy = p['symbol'].to_numpy(str)
        base = (
            np.isfinite(rr) & np.isfinite(dd)
            & (sy != r.symbol)
            & (p['recent_buy4'].to_numpy(float) == 0)
        )
        # Pre-registered context matching: same prior-52w return +/-15pp AND drawdown +/-10pp.
        m = base & (np.abs(rr-r.ret52_pre) <= .15) & (np.abs(dd-r.dd52_pre) <= .10)
        if m.sum() < 5:
            m = base & (np.abs(rr-r.ret52_pre) <= .25) & (np.abs(dd-r.dd52_pre) <= .15)
        for h in HORIZONS:
            vals = p.loc[m, f'ret{h}'].to_numpy(float)
            vals = vals[np.isfinite(vals)]
            rv = getattr(r, f'ret{h}')
            if len(vals) >= 3 and np.isfinite(rv):
                ev.at[j, f'excess{h}'] = rv - float(np.median(vals))
                ev.at[j, f'control_n{h}'] = len(vals)
    return ev


def main():
    t=time.time()
    w = add_drawdown(load_weekly_prices())
    universe=set(w.loc[w['is_member'].fillna(False) & w['week'].between(DISC_START,VAL_END),'symbol'].dropna().astype(str).unique())
    base, meta = load_events(universe)
    events = build_strategies(base)
    mapped = map_to_prices(events,w)
    state = w[['series_id','week','dd52_pre']].drop_duplicates(['series_id','week'])
    mapped = mapped.merge(state,on=['series_id','week'],how='left')
    # Apply the contextual drawdown criterion only to contextual variants; BaseBuyP retained solely for recent-buy control exclusion.
    keep = mapped['strategy'].eq('BaseBuyP') | (mapped['dd52_pre'] <= -0.20)
    mapped = mapped[keep].copy().reset_index(drop=True)
    w2 = add_recent_buy_flag(w,mapped)
    matched = matched_excess_context(mapped,w2)
    meta.update({
        'mapped_context_rows':len(mapped),
        'strategy_counts':mapped.groupby('strategy').size().to_dict(),
        'elapsed_sec':round(time.time()-t,2),
    })
    print('META',json.dumps(meta),flush=True)
    print('MAPPED_EVENTS',json.dumps(mapped.groupby('strategy').size().to_dict()),flush=True)
    s=pd.DataFrame(
        summarize(matched,'discovery_2010_2016',DISC_START,DISC_END)
        + summarize(matched,'validation_2017_2024',VAL_START,VAL_END)
    )
    print(s.to_string(index=False),flush=True)
    gate=s[(s['slice']=='validation_2017_2024') & (s['horizon']==26) & s['strategy'].isin(['DeepDD20','ExecDeepDD20'])].copy()
    gate['pass']=(
        (gate['n']>=300)
        & (gate['median_excess']>.01)
        & (gate['beat_matched']>=.525)
        & (gate['ci_lo']>0)
    )
    print('GATE26',gate[['strategy','n','matched_n','win_rate','median_return','median_excess','beat_matched','mean_excess','ci_lo','ci_hi','pass']].to_json(orient='records'),flush=True)
    print('DONE',flush=True)

if __name__=='__main__':
    main()
