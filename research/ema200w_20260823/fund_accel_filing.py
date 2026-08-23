from __future__ import annotations

import json
import time
from pathlib import Path

import numpy as np
import pandas as pd
import requests

from backtest import load_prices, load_memberships, add_membership_flag, norm_ticker

HORIZONS = (13, 26, 52)
DISC_START = pd.Timestamp('2010-01-01')
DISC_END = pd.Timestamp('2016-12-31')
VAL_START = pd.Timestamp('2017-01-01')
VAL_END = pd.Timestamp('2024-12-31')
CACHE = Path('/tmp/openfundex_cache')
CACHE.mkdir(parents=True, exist_ok=True)
HF_BASE = 'https://huggingface.co/datasets/ttchopper/openfundex/resolve/main/'
HF_FILES = ('train_clean.parquet', 'validation_clean.parquet', 'test_clean.parquet', 'recent_clean.parquet')


def download(url: str, path: Path, min_bytes: int = 100_000) -> None:
    if path.exists() and path.stat().st_size >= min_bytes:
        return
    tmp = path.with_suffix(path.suffix + '.part')
    with requests.get(url, stream=True, timeout=180, headers={'User-Agent': 'Mozilla/5.0 fund-accel-research/1.0'}, allow_redirects=True) as r:
        r.raise_for_status()
        with open(tmp, 'wb') as f:
            for chunk in r.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    f.write(chunk)
    tmp.replace(path)
    if path.stat().st_size < min_bytes:
        raise RuntimeError(f'download too small: {path} {path.stat().st_size}')


def add_price_features(w: pd.DataFrame) -> pd.DataFrame:
    w = w.copy()
    w['week'] = pd.to_datetime(w['week']).astype('datetime64[ns]')
    g = w.groupby('series_id', sort=False, observed=True)
    w['ret52_pre'] = g['close'].shift(1) / g['close'].shift(53) - 1.0
    w['next_open'] = g['open'].shift(-1)
    for h in HORIZONS:
        w[f'ret{h}'] = g['close'].shift(-h) / w['next_open'] - 1.0
    return w


def load_openfundex(symbols: set[str]) -> pd.DataFrame:
    cols = [
        'ticker', 'fiscal_year', 'fiscal_quarter', 'filing_date', 'period_end_date',
        'net_income', 'operating_cash_flow', 'capex', 'free_cash_flow', 'qa_pass'
    ]
    frames = []
    for name in HF_FILES:
        path = CACHE / name
        print('OpenFundex download/read', name, flush=True)
        download(HF_BASE + name + '?download=true', path)
        x = pd.read_parquet(path, columns=cols)
        x['symbol'] = x['ticker'].fillna('').astype(str).map(norm_ticker)
        x = x[x['symbol'].isin(symbols)].copy()
        frames.append(x)
    f = pd.concat(frames, ignore_index=True)
    f['filing_date'] = pd.to_datetime(f['filing_date'], errors='coerce').astype('datetime64[ns]')
    f['period_end_date'] = pd.to_datetime(f['period_end_date'], errors='coerce').astype('datetime64[ns]')
    f['fiscal_year'] = pd.to_numeric(f['fiscal_year'], errors='coerce')
    f = f[
        f['fiscal_quarter'].astype(str).str.upper().eq('FY') &
        f['filing_date'].notna() &
        f['fiscal_year'].notna() &
        f['filing_date'].le(VAL_END) &
        f['qa_pass'].fillna(False)
    ].copy()

    # Annual acceleration must compare distinct fiscal years. Keep the first PIT filing
    # for each symbol/fiscal-year so later amendments cannot masquerade as a new year.
    f = f.sort_values(['symbol', 'fiscal_year', 'filing_date', 'period_end_date'])
    f = f.drop_duplicates(['symbol', 'fiscal_year'], keep='first')
    f = f.sort_values(['symbol', 'filing_date'])

    f['fcf'] = f['free_cash_flow']
    m = f['fcf'].isna() & f['operating_cash_flow'].notna() & f['capex'].notna()
    f.loc[m, 'fcf'] = f.loc[m, 'operating_cash_flow'] - f.loc[m, 'capex'].abs()

    g = f.groupby('symbol', sort=False, observed=True)
    f['prev_net_income'] = g['net_income'].shift(1)
    f['prev_fcf'] = g['fcf'].shift(1)
    f['ni_up'] = (
        f['net_income'].gt(0) & f['prev_net_income'].gt(0) &
        f['net_income'].gt(f['prev_net_income'])
    )
    f['fcf_up'] = (
        f['ni_up'] & f['fcf'].gt(0) & f['prev_fcf'].gt(0) &
        f['fcf'].gt(f['prev_fcf'])
    )
    return f[['symbol', 'filing_date', 'period_end_date', 'fiscal_year', 'net_income', 'fcf', 'prev_net_income', 'prev_fcf', 'ni_up', 'fcf_up']]


def attach_fundamentals(w: pd.DataFrame, f: pd.DataFrame) -> pd.DataFrame:
    cols_init = {
        'fund_filed': pd.NaT, 'fund_end': pd.NaT, 'fiscal_year': np.nan,
        'net_income': np.nan, 'fcf': np.nan, 'prev_net_income': np.nan, 'prev_fcf': np.nan,
    }
    for c, v in cols_init.items():
        w[c] = v
    # Object dtype accepts the NaN/bool mixture produced by merge_asof under pandas 3;
    # flags are normalized to bool immediately after attachment.
    w['ni_up'] = None
    w['fcf_up'] = None

    for sym, idx in w.groupby('symbol', sort=False, observed=True).groups.items():
        s = f[f['symbol'].eq(sym)].copy()
        if s.empty:
            continue
        s['filing_date'] = pd.to_datetime(s['filing_date']).astype('datetime64[ns]')
        s = s.sort_values('filing_date').rename(columns={'filing_date': 'fund_filed', 'period_end_date': 'fund_end'})
        left = w.loc[idx, ['week']].sort_values('week').copy()
        left['week'] = pd.to_datetime(left['week']).astype('datetime64[ns]')
        merged = pd.merge_asof(
            left,
            s[['fund_filed', 'fund_end', 'fiscal_year', 'net_income', 'fcf', 'prev_net_income', 'prev_fcf', 'ni_up', 'fcf_up']].sort_values('fund_filed'),
            left_on='week', right_on='fund_filed', direction='backward'
        )
        merged.index = left.index
        for c in ['fund_filed', 'fund_end', 'fiscal_year', 'net_income', 'fcf', 'prev_net_income', 'prev_fcf', 'ni_up', 'fcf_up']:
            w.loc[merged.index, c] = merged[c].to_numpy()
    w['ni_up'] = w['ni_up'].fillna(False).astype(bool)
    w['fcf_up'] = w['fcf_up'].fillna(False).astype(bool)
    g = w.groupby('series_id', sort=False, observed=True)
    prev_filed = g['fund_filed'].shift(1)
    w['new_filing'] = w['fund_filed'].notna() & (w['fund_filed'] != prev_filed)
    # Prevent a stale first attached filing at the beginning of a ticker series from being labeled new.
    w['new_filing'] &= (w['week'] - w['fund_filed']).dt.days.between(0, 7, inclusive='both')
    return w


def make_events(w: pd.DataFrame) -> pd.DataFrame:
    specs = [
        ('AnnualFiling+NIUp', w['new_filing'] & w['ni_up'], 'ni'),
        ('AnnualFiling+NIUp+FCFUp', w['new_filing'] & w['fcf_up'], 'fcf'),
    ]
    rows = []
    cols = ['symbol', 'series_id', 'week', 'fund_filed', 'fiscal_year', 'ret52_pre', 'net_income', 'fcf', 'prev_net_income', 'prev_fcf']
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
    eligible = w[
        w['is_member'] & w['ret52_pre'].notna() & w['next_open'].notna() &
        w['week'].between(DISC_START, VAL_END) & w['fund_filed'].notna()
    ]
    cols = ['symbol', 'ret52_pre', 'new_filing', 'net_income', 'fcf'] + [f'ret{h}' for h in HORIZONS]
    byweek = {d: g[cols] for d, g in eligible.groupby('week', sort=False)}
    for h in HORIZONS:
        ev[f'control{h}'] = np.nan
        ev[f'control_n{h}'] = 0
        ev[f'excess{h}'] = np.nan

    for j, r in enumerate(ev.itertuples(index=False)):
        p = byweek.get(r.week)
        if p is None or not np.isfinite(r.ret52_pre):
            continue
        base = (p['symbol'].to_numpy() != r.symbol)
        # Preserve broad quality state so this tests the NEW filing acceleration event, not simply profitable-vs-unprofitable firms.
        base &= p['net_income'].gt(0).fillna(False).to_numpy(dtype=bool)
        if r.filter_code == 'fcf':
            base &= p['fcf'].gt(0).fillna(False).to_numpy(dtype=bool)
        rr = p['ret52_pre'].to_numpy(dtype=float)
        m = base & np.isfinite(rr) & (np.abs(rr - r.ret52_pre) <= 0.10)
        if m.sum() < 10:
            m = base & np.isfinite(rr) & (np.abs(rr - r.ret52_pre) <= 0.20)
        # Exclude peers experiencing the same annual filing week to isolate event timing.
        m &= ~p['new_filing'].fillna(False).to_numpy(dtype=bool)
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
                'slice': label, 'strategy': st, 'horizon': h,
                'n': len(x), 'signal_weeks': x['week'].nunique(),
                'median_return': x[f'ret{h}'].median(), 'mean_return': x[f'ret{h}'].mean(),
                'win_rate': (x[f'ret{h}'] > 0).mean(), 'matched_n': len(c),
                'median_excess': c[f'excess{h}'].median(), 'mean_excess': c[f'excess{h}'].mean(),
                'beat_matched': (c[f'excess{h}'] > 0).mean(), 'ci_lo': lo, 'ci_hi': hi,
            })
    return out


def main():
    t0 = time.time()
    print('loading price...', flush=True)
    w = load_prices()
    _, periods = load_memberships()
    w = add_membership_flag(w, periods)
    w = add_price_features(w)

    symbols = set(w.loc[w['is_member'] & w['week'].between(DISC_START, VAL_END), 'symbol'].dropna().astype(str).unique())
    print('loading OpenFundex filing data...', flush=True)
    f = load_openfundex(symbols)
    w = attach_fundamentals(w, f)

    ev = make_events(w)
    print('EVENTS', json.dumps(ev.groupby('strategy').size().to_dict()), flush=True)
    ev = add_controls(ev, w)

    rows = []
    rows += summarize_slice(ev, 'discovery_2010_2016', DISC_START, DISC_END)
    rows += summarize_slice(ev, 'validation_2017_2024', VAL_START, VAL_END)
    s = pd.DataFrame(rows)
    print('META', json.dumps({
        'fund_source': 'OpenFundex clean annual filing-level SEC data',
        'member_symbols': len(symbols), 'fund_symbols': int(f['symbol'].nunique()),
        'annual_filing_rows': int(len(f)), 'elapsed_sec': round(time.time() - t0, 2)
    }), flush=True)
    print(s.to_string(index=False), flush=True)

    v = s[(s['slice'] == 'validation_2017_2024') & (s['horizon'] == 13)].copy()
    v['pass'] = (v['win_rate'] >= 0.60) & (v['median_excess'] > 0) & (v['beat_matched'] >= 0.55)
    cols = ['strategy', 'n', 'matched_n', 'win_rate', 'median_return', 'median_excess', 'beat_matched', 'mean_excess', 'ci_lo', 'ci_hi', 'pass']
    print('GATE13', v[cols].to_json(orient='records'), flush=True)
    print('DONE', flush=True)


if __name__ == '__main__':
    main()
