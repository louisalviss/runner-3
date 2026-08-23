from __future__ import annotations

import json
import time
from pathlib import Path

import numpy as np
import pandas as pd

from backtest import load_prices, load_memberships, add_membership_flag, load_spy

HORIZONS = (13, 26, 52)
DISC_START = pd.Timestamp('2010-01-01')
DISC_END = pd.Timestamp('2016-12-31')
VAL_START = pd.Timestamp('2017-01-01')
VAL_END = pd.Timestamp('2024-12-31')


def add_features(w: pd.DataFrame) -> pd.DataFrame:
    w = w.copy()
    g = w.groupby('series_id', sort=False, observed=True)

    w['roll52_high'] = g['high'].transform(lambda s: s.rolling(52, min_periods=52).max())
    w['dd52'] = w['close'] / w['roll52_high'] - 1.0
    w['prev_dd52'] = g['dd52'].shift(1)
    w['dd52_4ago'] = g['dd52'].shift(4)

    # Fresh entry into moderate drawdown state.
    w['dip_trigger'] = w['prev_dd52'].gt(-0.10) & w['dd52'].between(-0.20, -0.10, inclusive='both')

    # Pre-shock relative strength: use t-1 information only.
    w['stock_ret52_pre'] = g['close'].shift(1) / g['close'].shift(53) - 1.0

    spy = load_spy()
    if spy is None or spy.empty:
        raise RuntimeError('SPY benchmark unavailable')
    spy = spy[['week', 'close']].copy().sort_values('week')
    spy['week'] = pd.to_datetime(spy['week']).astype('datetime64[ns]')
    spy['spy_ret52_pre'] = spy['close'].shift(1) / spy['close'].shift(53) - 1.0
    w['week'] = pd.to_datetime(w['week']).astype('datetime64[ns]')
    w = w.merge(spy[['week', 'spy_ret52_pre']], on='week', how='left', sort=False)

    w['rs52_pre'] = w['stock_ret52_pre'] - w['spy_ret52_pre']
    w['strong_rs52'] = w['rs52_pre'].gt(0.10)

    # Fast shock must add information beyond the fresh-dip condition itself.
    # Four completed weeks before the signal, the stock was within 5% of its 52w high;
    # now it is in the -10%..-20% drawdown band.
    w['fastshock4'] = w['dd52_4ago'].gt(-0.05)

    # Causal execution: enter next week's adjusted open.
    g2 = w.groupby('series_id', sort=False, observed=True)
    w['next_open'] = g2['open'].shift(-1)
    for h in HORIZONS:
        w[f'ret{h}'] = g2['close'].shift(-h) / w['next_open'] - 1.0
    return w


def make_events(w: pd.DataFrame) -> pd.DataFrame:
    specs = [
        ('Dip10_20', w['dip_trigger'], 'none'),
        ('Dip10_20+RS52', w['dip_trigger'] & w['strong_rs52'], 'rs'),
        ('Dip10_20+FastShock4', w['dip_trigger'] & w['fastshock4'], 'shock'),
        ('Dip10_20+RS52+FastShock4', w['dip_trigger'] & w['strong_rs52'] & w['fastshock4'], 'rs_shock'),
    ]
    rows = []
    cols = [
        'symbol', 'series_id', 'week', 'dd52', 'prev_dd52', 'dd52_4ago',
        'rs52_pre', 'strong_rs52', 'fastshock4', 'next_open'
    ]
    for name, mask, code in specs:
        idx = w.index[(mask & w['is_member'] & w['week'].between(DISC_START, VAL_END)).fillna(False)]
        if not len(idx):
            continue
        e = w.loc[idx, cols].copy()
        e['strategy'] = name
        e['filter_code'] = code
        e['source_index'] = idx
        for h in HORIZONS:
            e[f'ret{h}'] = w.loc[idx, f'ret{h}'].to_numpy()
        rows.append(e)
    return pd.concat(rows, ignore_index=True).sort_values(['strategy', 'week', 'symbol']).reset_index(drop=True)


def control_mask(pool: pd.DataFrame, code: str) -> np.ndarray:
    m = np.ones(len(pool), dtype=bool)
    if code in ('rs', 'rs_shock'):
        m &= pool['strong_rs52'].fillna(False).to_numpy(dtype=bool)
    if code in ('shock', 'rs_shock'):
        m &= pool['fastshock4'].fillna(False).to_numpy(dtype=bool)
    return m


def add_controls(ev: pd.DataFrame, w: pd.DataFrame) -> pd.DataFrame:
    eligible = w[
        w['is_member'] &
        w['dd52'].between(-0.20, -0.10, inclusive='both') &
        w['next_open'].notna() &
        w['week'].between(DISC_START, VAL_END)
    ]
    cols = ['symbol', 'dd52', 'dip_trigger', 'strong_rs52', 'fastshock4'] + [f'ret{h}' for h in HORIZONS]
    byweek = {d: g[cols] for d, g in eligible.groupby('week', sort=False)}

    for h in HORIZONS:
        ev[f'control{h}'] = np.nan
        ev[f'control_n{h}'] = 0
        ev[f'excess{h}'] = np.nan

    for j, r in enumerate(ev.itertuples(index=False)):
        p = byweek.get(r.week)
        if p is None or not np.isfinite(r.dd52):
            continue
        base = (p['symbol'].to_numpy() != r.symbol) & (~p['dip_trigger'].fillna(False).to_numpy(dtype=bool))
        base &= control_mask(p, r.filter_code)
        dd = p['dd52'].to_numpy(dtype=float)
        m = base & np.isfinite(dd) & (np.abs(dd - r.dd52) <= 0.025)
        if m.sum() < 10:
            m = base & np.isfinite(dd) & (np.abs(dd - r.dd52) <= 0.05)
        for h in HORIZONS:
            vals = p.loc[m, f'ret{h}'].to_numpy(dtype=float)
            vals = vals[np.isfinite(vals)]
            if len(vals) >= 5:
                ctrl = float(np.median(vals))
                ev.at[j, f'control{h}'] = ctrl
                ev.at[j, f'control_n{h}'] = len(vals)
                rr = getattr(r, f'ret{h}')
                if np.isfinite(rr):
                    ev.at[j, f'excess{h}'] = rr - ctrl
    return ev


def summarize_slice(ev: pd.DataFrame, label: str, a: str, b: str) -> list[dict]:
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
    print('adding winner/shock features...', flush=True)
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
    v['pass'] = (v['win_rate'] >= 0.60) & (v['median_excess'] > 0) & (v['beat_matched'] >= 0.55)
    cols = ['strategy', 'n', 'matched_n', 'win_rate', 'median_return', 'median_excess', 'beat_matched', 'mean_excess', 'ci_lo', 'ci_hi', 'pass']
    print('GATE13', v[cols].to_json(orient='records'), flush=True)
    print('META', json.dumps({'elapsed_sec': round(time.time() - t0, 2)}), flush=True)
    print('DONE', flush=True)


if __name__ == '__main__':
    main()
