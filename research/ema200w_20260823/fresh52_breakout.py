from __future__ import annotations

import json
import time

import numpy as np
import pandas as pd

from backtest import load_prices, load_memberships, add_membership_flag

HORIZONS = (13, 26, 52)
DISC_START = pd.Timestamp('2010-01-01')
DISC_END = pd.Timestamp('2016-12-31')
VAL_START = pd.Timestamp('2017-01-01')
VAL_END = pd.Timestamp('2024-12-31')


def add_features(w: pd.DataFrame) -> pd.DataFrame:
    w = w.copy()
    w['week'] = pd.to_datetime(w['week']).astype('datetime64[ns]')
    g = w.groupby('series_id', sort=False, observed=True)

    # Frozen signal: weekly close exceeds the highest CLOSE of the prior 52 completed weeks.
    w['prev_hi52_close'] = g['close'].transform(
        lambda s: s.shift(1).rolling(52, min_periods=52).max()
    )
    w['dist_prev_hi52'] = w['close'] / w['prev_hi52_close'] - 1.0
    w['raw_breakout52'] = w['dist_prev_hi52'].gt(0)

    # Freshness: no other raw 52w close breakout in the previous 8 completed weeks.
    w['prior8_breakouts'] = g['raw_breakout52'].transform(
        lambda s: s.shift(1).rolling(8, min_periods=1).max()
    ).fillna(False).astype(bool)
    w['fresh_breakout52'] = w['raw_breakout52'] & (~w['prior8_breakouts'])

    # Pre-signal 52w return, used only for matched controls.
    w['ret52_pre'] = g['close'].shift(1) / g['close'].shift(53) - 1.0

    # Single pre-specified compression filter: prior 13 completed weekly CLOSE range <=20%.
    w['prior13_max'] = g['close'].transform(
        lambda s: s.shift(1).rolling(13, min_periods=13).max()
    )
    w['prior13_min'] = g['close'].transform(
        lambda s: s.shift(1).rolling(13, min_periods=13).min()
    )
    w['prior13_range'] = w['prior13_max'] / w['prior13_min'] - 1.0
    w['tight13'] = w['prior13_range'].le(0.20)

    # Causal execution: signal after completed week t; enter next week's adjusted open.
    g2 = w.groupby('series_id', sort=False, observed=True)
    w['next_open'] = g2['open'].shift(-1)
    for h in HORIZONS:
        w[f'ret{h}'] = g2['close'].shift(-h) / w['next_open'] - 1.0
    return w


def make_events(w: pd.DataFrame) -> pd.DataFrame:
    specs = [
        ('FreshBreakout52', w['fresh_breakout52'], 'base'),
        ('FreshBreakout52+Tight13', w['fresh_breakout52'] & w['tight13'], 'tight'),
    ]
    rows = []
    cols = [
        'symbol', 'series_id', 'week', 'dist_prev_hi52', 'ret52_pre',
        'prior13_range', 'tight13', 'next_open'
    ]
    for name, mask, code in specs:
        idx = w.index[(mask & w['is_member'] & w['week'].between(DISC_START, VAL_END)).fillna(False)]
        if not len(idx):
            continue
        e = w.loc[idx, cols].copy()
        e['strategy'] = name
        e['filter_code'] = code
        for h in HORIZONS:
            e[f'ret{h}'] = w.loc[idx, f'ret{h}'].to_numpy()
        rows.append(e)
    return pd.concat(rows, ignore_index=True).sort_values(['strategy', 'week', 'symbol']).reset_index(drop=True)


def add_controls(ev: pd.DataFrame, w: pd.DataFrame) -> pd.DataFrame:
    # Controls are strong stocks in the SAME WEEK sitting within 3% below their prior 52w high,
    # but not breaking out. Match pre-signal 52w return ±10pp, widened to ±20pp if needed.
    eligible = w[
        w['is_member'] &
        w['dist_prev_hi52'].between(-0.03, 0.0, inclusive='both') &
        (~w['raw_breakout52'].fillna(False)) &
        w['ret52_pre'].notna() &
        w['next_open'].notna() &
        w['week'].between(DISC_START, VAL_END)
    ]
    cols = ['symbol', 'ret52_pre', 'tight13'] + [f'ret{h}' for h in HORIZONS]
    byweek = {d: g[cols] for d, g in eligible.groupby('week', sort=False)}

    for h in HORIZONS:
        ev[f'control{h}'] = np.nan
        ev[f'control_n{h}'] = 0
        ev[f'excess{h}'] = np.nan

    for j, r in enumerate(ev.itertuples(index=False)):
        p = byweek.get(r.week)
        if p is None or not np.isfinite(r.ret52_pre):
            continue
        base = p['symbol'].to_numpy() != r.symbol
        if r.filter_code == 'tight':
            base &= p['tight13'].fillna(False).to_numpy(dtype=bool)

        rr = p['ret52_pre'].to_numpy(dtype=float)
        m = base & np.isfinite(rr) & (np.abs(rr - r.ret52_pre) <= 0.10)
        if m.sum() < 10:
            m = base & np.isfinite(rr) & (np.abs(rr - r.ret52_pre) <= 0.20)

        for h in HORIZONS:
            vals = p.loc[m, f'ret{h}'].to_numpy(dtype=float)
            vals = vals[np.isfinite(vals)]
            if len(vals) >= 5:
                ctrl = float(np.median(vals))
                ev.at[j, f'control{h}'] = ctrl
                ev.at[j, f'control_n{h}'] = len(vals)
                er = getattr(r, f'ret{h}')
                if np.isfinite(er):
                    ev.at[j, f'excess{h}'] = er - ctrl
    return ev


def summarize_slice(ev: pd.DataFrame, label: str, a: pd.Timestamp, b: pd.Timestamp) -> list[dict]:
    out = []
    rng = np.random.default_rng(20260823)
    z = ev[ev['week'].between(a, b)]
    for st, x0 in z.groupby('strategy', sort=False):
        for h in HORIZONS:
            x = x0.dropna(subset=[f'ret{h}'])
            c = x.dropna(subset=[f'excess{h}'])
            wm = c.groupby('week')[f'excess{h}'].mean().to_numpy(dtype=float)
            if len(wm) >= 8:
                bs = np.array([rng.choice(wm, len(wm), replace=True).mean() for _ in range(1000)])
                lo, hi = np.quantile(bs, [0.025, 0.975])
            else:
                lo = hi = np.nan
            out.append({
                'slice': label,
                'strategy': st,
                'horizon': h,
                'n': len(x),
                'signal_weeks': x['week'].nunique(),
                'median_return': x[f'ret{h}'].median(),
                'mean_return': x[f'ret{h}'].mean(),
                'win_rate': (x[f'ret{h}'] > 0).mean(),
                'matched_n': len(c),
                'median_excess': c[f'excess{h}'].median(),
                'mean_excess': c[f'excess{h}'].mean(),
                'beat_matched': (c[f'excess{h}'] > 0).mean(),
                'ci_lo': lo,
                'ci_hi': hi,
            })
    return out


def main():
    t0 = time.time()
    print('loading price...', flush=True)
    w = load_prices()
    _, periods = load_memberships()
    w = add_membership_flag(w, periods)
    print('adding breakout features...', flush=True)
    w = add_features(w)

    ev = make_events(w)
    print('EVENTS', json.dumps(ev.groupby('strategy').size().to_dict()), flush=True)
    ev = add_controls(ev, w)

    rows = []
    rows += summarize_slice(ev, 'discovery_2010_2016', DISC_START, DISC_END)
    rows += summarize_slice(ev, 'validation_2017_2024', VAL_START, VAL_END)
    s = pd.DataFrame(rows)
    print(s.to_string(index=False), flush=True)

    v = s[(s['slice'] == 'validation_2017_2024') & (s['horizon'] == 13)].copy()
    v['pass'] = (
        (v['win_rate'] >= 0.60) &
        (v['median_excess'] > 0) &
        (v['beat_matched'] >= 0.55)
    )
    cols = [
        'strategy', 'n', 'matched_n', 'win_rate', 'median_return',
        'median_excess', 'beat_matched', 'mean_excess', 'ci_lo', 'ci_hi', 'pass'
    ]
    print('GATE13', v[cols].to_json(orient='records'), flush=True)
    print('META', json.dumps({'elapsed_sec': round(time.time() - t0, 2)}), flush=True)
    print('DONE', flush=True)


if __name__ == '__main__':
    main()
