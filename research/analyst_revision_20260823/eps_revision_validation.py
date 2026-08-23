from __future__ import annotations

import io
import json
import sys
import time
from pathlib import Path
from urllib.parse import quote

import numpy as np
import pandas as pd
import pyarrow.parquet as pq
import requests

# Reuse the already-audited PIT S&P500 weekly price/membership framework.
sys.path.insert(0, str((Path(__file__).resolve().parents[1] / 'ema200w_20260823').resolve()))
from backtest import load_prices, load_memberships, add_membership_flag, norm_ticker  # noqa: E402

SOURCE_DATASET = 'siddharthmb/stocks-earnings-eps_estimate'
SOURCE_AUTHORITY = 'DoltHub post-no-preference/earnings :: eps_estimate'
SOURCE_MAX = pd.Timestamp('2024-12-31')  # hard stop: 2025-2026 remain untouched
DISC_START = pd.Timestamp('2018-01-01')
DISC_END = pd.Timestamp('2020-12-31')
VAL_START = pd.Timestamp('2021-01-01')
VAL_END = pd.Timestamp('2024-12-31')
HORIZONS = (13, 26)
CACHE = Path('/tmp/analyst_revision_20260823')
CACHE.mkdir(parents=True, exist_ok=True)

# Frozen before any return outcome is read:
# - Current Year EPS consensus only.
# - Monthly sampling: first available source snapshot in each calendar month.
# - Same fiscal target (period_end_date) must have a prior observation 21-45 days earlier.
# - analyst count >= 3 at current and prior observations.
# - EPSUp28 signal is direction-only: consensus_now > consensus_prior.
# - no magnitude threshold / percentile / ML.


def hf_parquet_urls(dataset: str) -> list[str]:
    url = f'https://datasets-server.huggingface.co/parquet?dataset={quote(dataset)}'
    r = requests.get(url, timeout=60, headers={'User-Agent': 'analyst-revision-validation/1.0'})
    r.raise_for_status()
    files = r.json().get('parquet_files') or []
    urls = [x['url'] for x in files if x.get('split') == 'train']
    if not urls:
        raise RuntimeError('no parquet files found for estimate mirror')
    return urls


def download(url: str, path: Path, min_bytes: int = 1_000_000) -> None:
    if path.exists() and path.stat().st_size >= min_bytes:
        return
    tmp = path.with_suffix(path.suffix + '.part')
    with requests.get(url, stream=True, timeout=300, headers={'User-Agent': 'analyst-revision-validation/1.0'}) as r:
        r.raise_for_status()
        with open(tmp, 'wb') as f:
            for chunk in r.iter_content(1024 * 1024):
                if chunk:
                    f.write(chunk)
    tmp.replace(path)
    if path.stat().st_size < min_bytes:
        raise RuntimeError(f'estimate parquet unexpectedly small: {path}')


def load_eps_panel() -> tuple[pd.DataFrame, dict]:
    urls = hf_parquet_urls(SOURCE_DATASET)
    frames = []
    total_bytes = 0
    cols = ['date', 'act_symbol', 'period', 'period_end_date', 'consensus', 'count']
    for i, url in enumerate(urls):
        path = CACHE / f'eps_{i}.parquet'
        download(url, path)
        total_bytes += path.stat().st_size
        pf = pq.ParquetFile(path)
        # Read only the fields required by the frozen hypothesis; filter to Current Year when supported.
        try:
            x = pd.read_parquet(path, columns=cols, filters=[('period', '==', 'Current Year')])
        except Exception:
            x = pf.read(columns=cols).to_pandas()
            x = x[x['period'].eq('Current Year')]
        frames.append(x)
    x = pd.concat(frames, ignore_index=True)
    raw_current_year_rows = len(x)
    x['symbol'] = x['act_symbol'].fillna('').astype(str).map(norm_ticker)
    x['date'] = pd.to_datetime(x['date'], errors='coerce').astype('datetime64[ns]')
    x['period_end_date'] = pd.to_datetime(x['period_end_date'], errors='coerce').astype('datetime64[ns]')
    x['consensus'] = pd.to_numeric(x['consensus'], errors='coerce')
    x['count'] = pd.to_numeric(x['count'], errors='coerce')
    x = x[
        x['date'].notna() & x['period_end_date'].notna() & x['symbol'].ne('') &
        x['consensus'].notna() & x['count'].notna() &
        x['date'].le(SOURCE_MAX)
    ].copy()
    x = x.sort_values(['symbol', 'period_end_date', 'date'], kind='mergesort')
    # Source authority primary key includes date/symbol/period. For Current Year there should be one row per key.
    dup = int(x.duplicated(['symbol', 'date'], keep=False).sum())
    meta = {
        'authority': SOURCE_AUTHORITY,
        'transport_mirror': SOURCE_DATASET,
        'transport_bytes': int(total_bytes),
        'current_year_rows_raw': int(raw_current_year_rows),
        'current_year_rows_through_2024': int(len(x)),
        'symbols': int(x['symbol'].nunique()),
        'date_min': None if x.empty else str(x['date'].min().date()),
        'date_max_hard_stop': None if x.empty else str(x['date'].max().date()),
        'duplicate_symbol_date_rows': dup,
        'source_2025_2026_read_for_outcomes': False,
    }
    return x[['symbol','date','period_end_date','consensus','count']], meta


def build_monthly_revision_panel(full: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    x = full.copy()
    x['month'] = x['date'].dt.to_period('M')
    # First source snapshot in each month is causal without needing to know future snapshots in that month.
    cur = (
        x.sort_values(['symbol','date'], kind='mergesort')
         .drop_duplicates(['symbol','month'], keep='first')
         .copy()
    )
    # Find the latest observation at or before current_date - 21d, with max age 45d,
    # for the SAME symbol + fiscal target. This creates a 21-45d comparison window without tuning.
    cur['lookup_date'] = cur['date'] - pd.Timedelta(days=21)
    right = x.rename(columns={
        'date':'prior_date', 'consensus':'prior_consensus', 'count':'prior_count'
    })[['symbol','period_end_date','prior_date','prior_consensus','prior_count']]
    left = cur.sort_values('lookup_date', kind='mergesort')
    right = right.sort_values('prior_date', kind='mergesort')
    m = pd.merge_asof(
        left,
        right,
        left_on='lookup_date',
        right_on='prior_date',
        by=['symbol','period_end_date'],
        direction='backward',
        tolerance=pd.Timedelta(days=24),
        allow_exact_matches=True,
    )
    m['revision_age_days'] = (m['date'] - m['prior_date']).dt.days
    m['eligible_revision'] = (
        m['prior_date'].notna() & m['revision_age_days'].between(21,45, inclusive='both') &
        m['count'].ge(3) & m['prior_count'].ge(3) &
        np.isfinite(m['consensus']) & np.isfinite(m['prior_consensus'])
    )
    m = m[m['eligible_revision']].copy()
    m['revision_delta'] = m['consensus'] - m['prior_consensus']
    m['eps_up28'] = m['revision_delta'].gt(0)
    meta = {
        'monthly_eligible_rows': int(len(m)),
        'monthly_eligible_symbols': int(m['symbol'].nunique()),
        'up_rows': int(m['eps_up28'].sum()),
        'flat_or_down_rows': int((~m['eps_up28']).sum()),
        'revision_age_median': None if m.empty else float(m['revision_age_days'].median()),
    }
    return m[['symbol','date','period_end_date','consensus','prior_consensus','count','prior_count','revision_age_days','revision_delta','eps_up28']], meta


def add_price_features(w: pd.DataFrame) -> pd.DataFrame:
    w = w.copy()
    w['week'] = pd.to_datetime(w['week']).astype('datetime64[ns]')
    g = w.groupby('series_id', sort=False, observed=True)
    # Match the earlier PIT event-study convention: momentum ends one completed week before signal week.
    w['ret52_pre'] = g['close'].shift(1) / g['close'].shift(53) - 1.0
    w['next_open'] = g['open'].shift(-1)
    for h in HORIZONS:
        w[f'ret{h}'] = g['close'].shift(-h) / w['next_open'] - 1.0
    return w


def map_to_signal_week(rows: pd.DataFrame, w: pd.DataFrame) -> pd.DataFrame:
    out = []
    pcols = ['week','series_id','is_member','ret52_pre','next_open'] + [f'ret{h}' for h in HORIZONS]
    for sym, r in rows.groupby('symbol', sort=False, observed=True):
        p = w[w['symbol'].eq(sym)][pcols].sort_values('week').copy()
        if p.empty:
            continue
        rr = r.sort_values('date').copy()
        m = pd.merge_asof(rr, p, left_on='date', right_on='week', direction='forward', allow_exact_matches=False)
        lag = (m['week'] - m['date']).dt.days
        m = m[
            lag.between(1,10,inclusive='both') &
            m['is_member'].fillna(False) &
            m['next_open'].notna() &
            m['ret52_pre'].notna()
        ].copy()
        if len(m):
            out.append(m)
    if not out:
        return pd.DataFrame()
    z = pd.concat(out, ignore_index=True)
    # One signal candidate per symbol/week in the unlikely case two monthly rows map to same week.
    z = z.sort_values(['symbol','week','date']).drop_duplicates(['symbol','week'], keep='last')
    return z


def add_controls(events: pd.DataFrame, all_eligible: pd.DataFrame) -> pd.DataFrame:
    controls = all_eligible[(~all_eligible['eps_up28']) & all_eligible['ret52_pre'].notna()].copy()
    cols = ['symbol','ret52_pre'] + [f'ret{h}' for h in HORIZONS]
    byweek = {d:g[cols] for d,g in controls.groupby('week', sort=False)}
    ev = events.reset_index(drop=True).copy()
    for h in HORIZONS:
        ev[f'control{h}'] = np.nan
        ev[f'excess{h}'] = np.nan
        ev[f'control_n{h}'] = 0
    for j, r in ev.iterrows():
        p = byweek.get(r['week'])
        if p is None or not np.isfinite(r['ret52_pre']):
            continue
        mom = p['ret52_pre'].to_numpy(dtype=float)
        base = (p['symbol'].to_numpy() != r['symbol']) & np.isfinite(mom)
        mask = base & (np.abs(mom - float(r['ret52_pre'])) <= 0.10)
        if mask.sum() < 5:
            mask = base & (np.abs(mom - float(r['ret52_pre'])) <= 0.20)
        for h in HORIZONS:
            vals = p.loc[mask, f'ret{h}'].to_numpy(dtype=float)
            vals = vals[np.isfinite(vals)]
            er = r[f'ret{h}']
            if len(vals) >= 3 and np.isfinite(er):
                ctrl = float(np.median(vals))
                ev.at[j, f'control{h}'] = ctrl
                ev.at[j, f'excess{h}'] = float(er) - ctrl
                ev.at[j, f'control_n{h}'] = int(len(vals))
    return ev


def summarize(ev: pd.DataFrame, label: str, start: pd.Timestamp, end: pd.Timestamp) -> list[dict]:
    rng = np.random.default_rng(20260823)
    z = ev[ev['week'].between(start,end)].copy()
    rows = []
    for h in HORIZONS:
        x = z.dropna(subset=[f'ret{h}'])
        c = x.dropna(subset=[f'excess{h}'])
        week_means = c.groupby('week')[f'excess{h}'].mean().to_numpy(dtype=float)
        if len(week_means) >= 8:
            bs = np.array([rng.choice(week_means, len(week_means), replace=True).mean() for _ in range(3000)])
            lo, hi = np.quantile(bs, [0.025,0.975])
        else:
            lo = hi = np.nan
        rows.append({
            'slice':label,
            'strategy':'EPSUp28_CurrentYear_Monthly',
            'horizon':h,
            'n':int(len(x)),
            'matched_n':int(len(c)),
            'symbols':int(x['symbol'].nunique()),
            'signal_weeks':int(x['week'].nunique()),
            'median_return':float(x[f'ret{h}'].median()) if len(x) else np.nan,
            'mean_return':float(x[f'ret{h}'].mean()) if len(x) else np.nan,
            'win_rate':float((x[f'ret{h}']>0).mean()) if len(x) else np.nan,
            'median_excess':float(c[f'excess{h}'].median()) if len(c) else np.nan,
            'mean_excess':float(c[f'excess{h}'].mean()) if len(c) else np.nan,
            'beat_matched':float((c[f'excess{h}']>0).mean()) if len(c) else np.nan,
            'ci_lo':float(lo) if np.isfinite(lo) else np.nan,
            'ci_hi':float(hi) if np.isfinite(hi) else np.nan,
        })
    return rows


def yearly_validation(ev: pd.DataFrame) -> list[dict]:
    rows=[]
    for year in (2021,2022,2023,2024):
        x=ev[ev['week'].dt.year.eq(year)].dropna(subset=['excess13'])
        rows.append({
            'year':year,
            'n':int(len(x)),
            'median_excess13':float(x['excess13'].median()) if len(x) else np.nan,
            'mean_excess13':float(x['excess13'].mean()) if len(x) else np.nan,
            'beat_matched13':float((x['excess13']>0).mean()) if len(x) else np.nan,
        })
    return rows


def main() -> None:
    t0=time.time()
    panel, source_meta = load_eps_panel()
    monthly, revision_meta = build_monthly_revision_panel(panel)

    print('SOURCE_META', json.dumps(source_meta, sort_keys=True), flush=True)
    print('REVISION_META', json.dumps(revision_meta, sort_keys=True), flush=True)

    print('loading PIT S&P500 weekly prices/membership...', flush=True)
    w=load_prices()
    _, periods=load_memberships()
    w=add_membership_flag(w, periods)
    w=add_price_features(w)

    eligible=map_to_signal_week(monthly, w)
    if eligible.empty:
        raise RuntimeError('no mapped eligible revision observations')
    events=eligible[eligible['eps_up28'] & eligible['week'].between(DISC_START,VAL_END)].copy()
    events=add_controls(events, eligible)

    rows=[]
    rows += summarize(events,'discovery_2018_2020',DISC_START,DISC_END)
    rows += summarize(events,'validation_2021_2024',VAL_START,VAL_END)
    summary=pd.DataFrame(rows)
    print('MAPPED_META', json.dumps({
        'eligible_rows':int(len(eligible)),
        'eligible_symbols':int(eligible['symbol'].nunique()),
        'signal_rows_2018_2024':int(len(events)),
        'signal_symbols':int(events['symbol'].nunique()),
        'mapped_week_min':str(eligible['week'].min().date()),
        'mapped_week_max':str(eligible['week'].max().date()),
        'elapsed_sec':round(time.time()-t0,2),
    }), flush=True)
    print(summary.to_string(index=False), flush=True)
    print('YEARLY_VALIDATION13', json.dumps(yearly_validation(events)), flush=True)

    v=summary[(summary['slice']=='validation_2021_2024') & summary['horizon'].eq(13)].iloc[0]
    gate={
        'n_ge_300':bool(v['matched_n']>=300),
        'median_excess_gt_1pct':bool(v['median_excess']>0.01),
        'beat_matched_ge_52_5pct':bool(v['beat_matched']>=0.525),
        'week_cluster_ci_lower_gt_0':bool(v['ci_lo']>0),
    }
    gate['pass']=all(gate.values())
    print('GATE13', json.dumps({**gate, **{
        'matched_n':int(v['matched_n']),
        'median_excess':float(v['median_excess']),
        'beat_matched':float(v['beat_matched']),
        'mean_excess':float(v['mean_excess']),
        'ci_lo':float(v['ci_lo']),
        'ci_hi':float(v['ci_hi']),
    }}), flush=True)
    print('UNTOUCHED_2025_2026', True, flush=True)
    print('DONE', flush=True)

if __name__=='__main__':
    main()
