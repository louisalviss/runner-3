from __future__ import annotations

import json
import time
from pathlib import Path

import numpy as np
import pandas as pd
import requests

from backtest import load_prices, load_memberships, add_membership_flag, norm_ticker

OUT = Path('artifacts/core_edge_decompose')
OUT.mkdir(parents=True, exist_ok=True)
CACHE = Path('/tmp/openfundex_cache')
CACHE.mkdir(parents=True, exist_ok=True)
HORIZONS = (13, 26, 52)
DISC_START = pd.Timestamp('2010-01-01')
DISC_END = pd.Timestamp('2016-12-31')
VAL_START = pd.Timestamp('2017-01-01')
VAL_END = pd.Timestamp('2024-12-31')
HF_BASE = 'https://huggingface.co/datasets/ttchopper/openfundex/resolve/main/'
HF_FILES = ('train_clean.parquet', 'validation_clean.parquet', 'test_clean.parquet', 'recent_clean.parquet')


def download(url: str, path: Path, min_bytes: int = 100_000) -> None:
    if path.exists() and path.stat().st_size >= min_bytes:
        return
    tmp = path.with_suffix(path.suffix + '.part')
    headers = {'User-Agent': 'Mozilla/5.0 core-edge-research/1.0'}
    with requests.get(url, stream=True, timeout=180, headers=headers, allow_redirects=True) as r:
        r.raise_for_status()
        with open(tmp, 'wb') as f:
            for chunk in r.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    f.write(chunk)
    tmp.replace(path)
    if path.stat().st_size < min_bytes:
        raise RuntimeError(f'download too small: {path} {path.stat().st_size}')


def add_price_features(w: pd.DataFrame) -> pd.DataFrame:
    g = w.groupby('series_id', sort=False, observed=True)
    w['roll52_high'] = g['high'].transform(lambda s: s.rolling(52, min_periods=52).max())
    w['dd52'] = w['close'] / w['roll52_high'] - 1.0
    w['prev_dd52'] = g['dd52'].shift(1)
    w['ret104'] = w['close'] / g['close'].shift(104) - 1.0
    w['dip_trigger'] = w['prev_dd52'].gt(-0.10) & w['dd52'].between(-0.20, -0.10, inclusive='both')
    w['trend104_pos'] = w['ret104'].gt(0)
    w['next_open'] = g['open'].shift(-1)
    for h in HORIZONS:
        exit_px = g['close'].shift(-h)
        w[f'ret{h}'] = exit_px / w['next_open'] - 1.0
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
    f['filing_date'] = pd.to_datetime(f['filing_date'], errors='coerce')
    f['period_end_date'] = pd.to_datetime(f['period_end_date'], errors='coerce')
    f = f[
        f['fiscal_quarter'].astype(str).str.upper().eq('FY') &
        f['filing_date'].notna() &
        f['filing_date'].le(VAL_END) &
        f['qa_pass'].fillna(False)
    ].copy()
    # Filing date is the PIT anchor. If several rows share a filing date, retain the latest period end.
    f = f.sort_values(['symbol', 'filing_date', 'period_end_date', 'fiscal_year'])
    f = f.drop_duplicates(['symbol', 'filing_date'], keep='last')
    f['fcf'] = f['free_cash_flow']
    missing_fcf = f['fcf'].isna() & f['operating_cash_flow'].notna() & f['capex'].notna()
    f.loc[missing_fcf, 'fcf'] = f.loc[missing_fcf, 'operating_cash_flow'] - f.loc[missing_fcf, 'capex'].abs()
    return f[['symbol', 'filing_date', 'period_end_date', 'net_income', 'operating_cash_flow', 'capex', 'fcf']]


def attach_fundamentals(w: pd.DataFrame, f: pd.DataFrame) -> pd.DataFrame:
    w['net_income'] = np.nan
    w['ocf'] = np.nan
    w['capex'] = np.nan
    w['fcf'] = np.nan
    w['fund_filed'] = pd.NaT
    w['fund_end'] = pd.NaT
    if f.empty:
        return w
    for sym, idx in w.groupby('symbol', sort=False, observed=True).groups.items():
        s = f[f['symbol'].eq(sym)].copy()
        if s.empty:
            continue
        s = s.sort_values('filing_date').rename(columns={
            'filing_date': 'fund_filed', 'period_end_date': 'fund_end', 'operating_cash_flow': 'ocf'
        })
        left = w.loc[idx, ['week']].sort_values('week')
        merged = pd.merge_asof(
            left,
            s[['fund_filed', 'fund_end', 'net_income', 'ocf', 'capex', 'fcf']].sort_values('fund_filed'),
            left_on='week', right_on='fund_filed', direction='backward'
        )
        merged.index = left.index
        for c in ['net_income', 'ocf', 'capex', 'fcf', 'fund_filed', 'fund_end']:
            w.loc[merged.index, c] = merged[c].to_numpy()
    return w


def load_fundamentals(w: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    relevant = w[w['is_member'] & w['week'].between(DISC_START, VAL_END)]
    symbols = set(relevant['symbol'].dropna().astype(str).unique())
    f = load_openfundex(symbols)
    w = attach_fundamentals(w, f)
    covered_symbols = int(f['symbol'].nunique()) if not f.empty else 0
    meta = {
        'fund_source': 'OpenFundex clean filing-level SEC data',
        'member_symbols': len(symbols),
        'fund_symbols': covered_symbols,
        'annual_filing_rows': int(len(f)),
        'fund_date_min': None if f.empty else str(f['filing_date'].min().date()),
        'fund_date_max': None if f.empty else str(f['filing_date'].max().date()),
    }
    return w, meta


def add_quality_flags(w: pd.DataFrame) -> pd.DataFrame:
    w['q_profit'] = w['net_income'].gt(0)
    w['q_fcf'] = w['net_income'].gt(0) & w['fcf'].gt(0)
    return w


def make_events(w: pd.DataFrame) -> pd.DataFrame:
    specs = [
        ('Dip10_20', w['dip_trigger'], 'none'),
        ('Dip10_20+Trend104', w['dip_trigger'] & w['trend104_pos'], 'trend'),
        ('Dip10_20+Trend104+Profit', w['dip_trigger'] & w['trend104_pos'] & w['q_profit'], 'trend_profit'),
        ('Dip10_20+Trend104+FCF', w['dip_trigger'] & w['trend104_pos'] & w['q_fcf'], 'trend_fcf'),
    ]
    rows = []
    cols = ['symbol','series_id','week','close','next_open','dd52','prev_dd52','ret104','trend104_pos','q_profit','q_fcf','fund_filed']
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
    return pd.concat(rows, ignore_index=True).sort_values(['strategy','week','symbol']).reset_index(drop=True) if rows else pd.DataFrame()


def control_mask(pool: pd.DataFrame, code: str) -> np.ndarray:
    m = np.ones(len(pool), dtype=bool)
    if code in ('trend','trend_profit','trend_fcf'):
        m &= pool['trend104_pos'].fillna(False).to_numpy(dtype=bool)
    if code == 'trend_profit':
        m &= pool['q_profit'].fillna(False).to_numpy(dtype=bool)
    if code == 'trend_fcf':
        m &= pool['q_fcf'].fillna(False).to_numpy(dtype=bool)
    return m


def add_controls(ev: pd.DataFrame, w: pd.DataFrame) -> pd.DataFrame:
    eligible = w[
        w['is_member'] &
        w['dd52'].between(-0.20, -0.10, inclusive='both') &
        w['next_open'].notna() &
        w['week'].between(DISC_START, VAL_END)
    ]
    cols = ['symbol','dd52','dip_trigger','trend104_pos','q_profit','q_fcf'] + [f'ret{h}' for h in HORIZONS]
    byweek = {d: g[cols] for d,g in eligible.groupby('week', sort=False)}
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
                if np.isfinite(getattr(r, f'ret{h}')):
                    ev.at[j, f'excess{h}'] = getattr(r, f'ret{h}') - ctrl
    return ev


def summarize_slice(ev: pd.DataFrame, label: str, a: str, b: str) -> list[dict]:
    out = []
    rng = np.random.default_rng(20260823)
    z = ev[ev['week'].between(a,b)]
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
                'median_return': x[f'ret{h}'].median(),
                'mean_return': x[f'ret{h}'].mean(),
                'win_rate': (x[f'ret{h}'] > 0).mean(),
                'median_excess': c[f'excess{h}'].median(),
                'mean_excess': c[f'excess{h}'].mean(),
                'beat_matched': (c[f'excess{h}'] > 0).mean(),
                'ci_lo': lo, 'ci_hi': hi,
                'matched_n': len(c),
            })
    return out


def pct(x):
    return 'NA' if pd.isna(x) else f'{100*x:.2f}%'


def main():
    t0 = time.time()
    print('loading price...', flush=True)
    w = load_prices()
    _, periods = load_memberships()
    w = add_membership_flag(w, periods)
    w = add_price_features(w)
    print('loading OpenFundex PIT fundamentals...', flush=True)
    w, meta = load_fundamentals(w)
    w = add_quality_flags(w)
    meta['weeks_with_fundamentals'] = int(w['fund_filed'].notna().sum())
    ev = make_events(w)
    print('events', ev.groupby('strategy').size().to_dict(), flush=True)
    ev = add_controls(ev, w)
    rows = []
    rows += summarize_slice(ev, 'discovery_2010_2016', '2010-01-01', '2016-12-31')
    rows += summarize_slice(ev, 'validation_2017_2024', '2017-01-01', '2024-12-31')
    s = pd.DataFrame(rows)
    meta['elapsed_sec'] = round(time.time()-t0, 2)
    print('META', json.dumps(meta), flush=True)
    print(s.to_string(index=False), flush=True)
    v = s[(s['slice']=='validation_2017_2024') & (s['horizon']==13)].copy()
    v['pass'] = (v['median_excess'] > 0) & (v['beat_matched'] >= 0.55) & (v['win_rate'] >= 0.60)
    print('GATE13', v[['strategy','n','win_rate','median_return','median_excess','beat_matched','mean_excess','ci_lo','ci_hi','pass']].to_json(orient='records'), flush=True)
    print('DONE', flush=True)


if __name__ == '__main__':
    main()
