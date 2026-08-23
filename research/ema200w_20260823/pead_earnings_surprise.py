from __future__ import annotations

import json
import time
from pathlib import Path

import numpy as np
import pandas as pd
import requests

from backtest import load_prices, load_memberships, add_membership_flag, norm_ticker

HORIZONS = (4, 8, 13, 26)
DISC_START = pd.Timestamp('2017-01-01')
DISC_END = pd.Timestamp('2020-12-31')
VAL_START = pd.Timestamp('2021-01-01')
VAL_END = pd.Timestamp('2024-12-31')
EARN_URL = 'https://huggingface.co/datasets/sovai/earnings_surprise/resolve/main/earnings_surprise.parquet?download=true'
CACHE = Path('/tmp/sovai_earnings_surprise.parquet')


def download(url: str, path: Path, min_bytes: int = 1_000_000) -> None:
    if path.exists() and path.stat().st_size >= min_bytes:
        return
    tmp = path.with_suffix('.part')
    with requests.get(url, stream=True, timeout=180, headers={'User-Agent': 'Mozilla/5.0 pead-research/1.0'}, allow_redirects=True) as r:
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


def load_reports(symbols: set[str]) -> tuple[pd.DataFrame, dict]:
    print('downloading SOVAI earnings surprise...', flush=True)
    download(EARN_URL, CACHE)
    cols = ['ticker', 'date', 'eps_surprise', 'actual_earning_result', 'estimated_earning', 'date_pub', 'market_cap']
    x = pd.read_parquet(CACHE, columns=cols)
    raw_rows = len(x)
    x['symbol'] = x['ticker'].fillna('').astype(str).map(norm_ticker)
    x = x[x['symbol'].isin(symbols)].copy()
    x['date'] = pd.to_datetime(x['date'], errors='coerce').astype('datetime64[ns]')
    x['date_pub'] = pd.to_datetime(x['date_pub'], errors='coerce').astype('datetime64[ns]')
    x['actual'] = pd.to_numeric(x['actual_earning_result'], errors='coerce')
    x['estimate'] = pd.to_numeric(x['estimated_earning'], errors='coerce')

    # Use only a snapshot that existed on or before the publication date. The dataset
    # contains future report values in earlier weekly snapshots; we never trade before
    # date_pub, and this selection prevents later post-publication revisions from defining
    # the event record.
    x = x[
        x['date_pub'].notna() & x['date'].notna() & (x['date'] <= x['date_pub']) &
        x['actual'].notna() & x['estimate'].notna() &
        x['date_pub'].between(DISC_START - pd.Timedelta(days=15), VAL_END) &
        x['actual'].abs().le(100) & x['estimate'].abs().le(100)
    ].copy()
    x = x.sort_values(['symbol', 'date_pub', 'date'])
    x = x.drop_duplicates(['symbol', 'date_pub'], keep='last')

    # Robust scaled surprise. The 0.10 denominator floor prevents near-zero estimates
    # from exploding the ratio. Clip is a data-quality safeguard, not a trading filter.
    den = np.maximum(x['estimate'].abs().to_numpy(dtype=float), 0.10)
    x['surprise_score'] = np.clip((x['actual'].to_numpy(dtype=float) - x['estimate'].to_numpy(dtype=float)) / den, -5.0, 5.0)
    x['raw_surprise'] = x['actual'] - x['estimate']

    meta = {
        'source': 'sovai/earnings_surprise public parquet',
        'raw_rows': int(raw_rows),
        'sp500_symbol_rows_after_filter': int(len(x)),
        'report_symbols': int(x['symbol'].nunique()),
        'date_pub_min': None if x.empty else str(x['date_pub'].min().date()),
        'date_pub_max': None if x.empty else str(x['date_pub'].max().date()),
    }
    return x[['symbol','date_pub','actual','estimate','raw_surprise','surprise_score']], meta


def attach_event_week(reports: pd.DataFrame, w: pd.DataFrame) -> pd.DataFrame:
    rows = []
    pcols = ['week','symbol','series_id','is_member','ret52_pre','next_open'] + [f'ret{h}' for h in HORIZONS]
    for sym, r in reports.groupby('symbol', sort=False, observed=True):
        p = w[w['symbol'].eq(sym)][pcols].sort_values('week').copy()
        if p.empty:
            continue
        rr = r.sort_values('date_pub').copy()
        m = pd.merge_asof(
            rr,
            p,
            left_on='date_pub', right_on='week',
            direction='forward', allow_exact_matches=False
        )
        lag = (m['week'] - m['date_pub']).dt.days
        m = m[lag.between(1, 10, inclusive='both') & m['is_member'].fillna(False) & m['next_open'].notna()].copy()
        if len(m):
            rows.append(m)
    if not rows:
        return pd.DataFrame()
    e = pd.concat(rows, ignore_index=True)
    # Cross-sectional surprise rank among PIT S&P reporters mapped to the same completed week.
    counts = e.groupby('week')['symbol'].transform('size')
    e['surprise_rank'] = e.groupby('week')['surprise_score'].rank(pct=True, method='average')
    e['week_reporters'] = counts
    e = e[e['week_reporters'] >= 10].copy()
    return e


def make_events(all_reports: pd.DataFrame) -> pd.DataFrame:
    specs = [
        ('PositiveEPSBeat', all_reports['raw_surprise'].gt(0)),
        ('TopQuartileEPSBeat', all_reports['raw_surprise'].gt(0) & all_reports['surprise_rank'].ge(0.75)),
    ]
    rows = []
    base_cols = ['symbol','week','date_pub','ret52_pre','actual','estimate','raw_surprise','surprise_score','surprise_rank','week_reporters']
    for name, mask in specs:
        z = all_reports.loc[mask & all_reports['week'].between(DISC_START, VAL_END), base_cols].copy()
        z['strategy'] = name
        for h in HORIZONS:
            z[f'ret{h}'] = all_reports.loc[z.index, f'ret{h}'].to_numpy()
        rows.append(z)
    return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()


def add_controls(ev: pd.DataFrame, all_reports: pd.DataFrame) -> pd.DataFrame:
    # Neutral controls are same-week PIT S&P earnings reporters in the middle 40-60%
    # of scaled surprise, matched on PRE-event 52w return. This isolates post-report
    # surprise information from general earnings-week and momentum effects.
    neutral = all_reports[
        all_reports['surprise_rank'].between(0.40, 0.60, inclusive='both') &
        all_reports['ret52_pre'].notna()
    ].copy()
    cols = ['symbol','ret52_pre'] + [f'ret{h}' for h in HORIZONS]
    byweek = {d: g[cols] for d, g in neutral.groupby('week', sort=False)}
    for h in HORIZONS:
        ev[f'control{h}'] = np.nan
        ev[f'excess{h}'] = np.nan
        ev[f'control_n{h}'] = 0

    for j, r in enumerate(ev.itertuples(index=False)):
        p = byweek.get(r.week)
        if p is None or not np.isfinite(r.ret52_pre):
            continue
        rr = p['ret52_pre'].to_numpy(dtype=float)
        base = (p['symbol'].to_numpy() != r.symbol) & np.isfinite(rr)
        m = base & (np.abs(rr - r.ret52_pre) <= 0.15)
        if m.sum() < 5:
            m = base & (np.abs(rr - r.ret52_pre) <= 0.25)
        for h in HORIZONS:
            vals = p.loc[m, f'ret{h}'].to_numpy(dtype=float)
            vals = vals[np.isfinite(vals)]
            if len(vals) >= 3:
                ctrl = float(np.median(vals))
                ev.at[j, f'control{h}'] = ctrl
                ev.at[j, f'control_n{h}'] = len(vals)
                er = getattr(r, f'ret{h}')
                if np.isfinite(er):
                    ev.at[j, f'excess{h}'] = er - ctrl
    return ev


def summarize(ev: pd.DataFrame, label: str, start: pd.Timestamp, end: pd.Timestamp) -> list[dict]:
    out = []
    rng = np.random.default_rng(20260823)
    z = ev[ev['week'].between(start, end)]
    for st, x0 in z.groupby('strategy', sort=False):
        for h in HORIZONS:
            x = x0.dropna(subset=[f'ret{h}'])
            c = x.dropna(subset=[f'excess{h}'])
            wm = c.groupby('week')[f'excess{h}'].mean().to_numpy(dtype=float)
            if len(wm) >= 8:
                bs = np.array([rng.choice(wm, len(wm), replace=True).mean() for _ in range(2000)])
                lo, hi = np.quantile(bs, [0.025, 0.975])
            else:
                lo = hi = np.nan
            out.append({
                'slice': label, 'strategy': st, 'horizon': h,
                'n': int(len(x)), 'matched_n': int(len(c)), 'signal_weeks': int(x['week'].nunique()),
                'median_return': x[f'ret{h}'].median(), 'mean_return': x[f'ret{h}'].mean(),
                'win_rate': (x[f'ret{h}'] > 0).mean(),
                'median_excess': c[f'excess{h}'].median(), 'mean_excess': c[f'excess{h}'].mean(),
                'beat_matched': (c[f'excess{h}'] > 0).mean(), 'ci_lo': lo, 'ci_hi': hi,
            })
    return out


def main():
    t0 = time.time()
    print('loading prices...', flush=True)
    w = load_prices()
    _, periods = load_memberships()
    w = add_membership_flag(w, periods)
    w = add_price_features(w)
    symbols = set(w.loc[w['is_member'] & w['week'].between(DISC_START, VAL_END), 'symbol'].dropna().astype(str).unique())

    reports, meta = load_reports(symbols)
    all_reports = attach_event_week(reports, w)
    if all_reports.empty:
        raise RuntimeError('no mapped earnings events')
    meta['mapped_pit_sp500_reports'] = int(len(all_reports))
    meta['mapped_symbols'] = int(all_reports['symbol'].nunique())
    meta['mapped_week_min'] = str(all_reports['week'].min().date())
    meta['mapped_week_max'] = str(all_reports['week'].max().date())

    ev = make_events(all_reports)
    print('EVENTS', json.dumps(ev.groupby('strategy').size().to_dict()), flush=True)
    ev = add_controls(ev, all_reports)

    rows = []
    rows += summarize(ev, 'discovery_2017_2020', DISC_START, DISC_END)
    rows += summarize(ev, 'validation_2021_2024', VAL_START, VAL_END)
    s = pd.DataFrame(rows)
    meta['elapsed_sec'] = round(time.time() - t0, 2)
    print('META', json.dumps(meta), flush=True)
    print(s.to_string(index=False), flush=True)

    v = s[(s['slice'] == 'validation_2021_2024') & (s['horizon'] == 13)].copy()
    v['pass'] = (
        (v['n'] >= 300) &
        (v['median_excess'] > 0.01) &
        (v['beat_matched'] >= 0.525) &
        (v['ci_lo'] > 0)
    )
    cols = ['strategy','n','matched_n','win_rate','median_return','median_excess','beat_matched','mean_excess','ci_lo','ci_hi','pass']
    print('GATE13', v[cols].to_json(orient='records'), flush=True)
    print('DONE', flush=True)


if __name__ == '__main__':
    main()
