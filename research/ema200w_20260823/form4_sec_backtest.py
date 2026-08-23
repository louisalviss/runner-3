from __future__ import annotations

import io
import json
import time
import zipfile
from collections import deque

import numpy as np
import pandas as pd
import requests

from backtest import load_prices, load_memberships, add_membership_flag, norm_ticker

HORIZONS = (13, 26, 52)
DISC_START = pd.Timestamp('2010-01-01')
DISC_END = pd.Timestamp('2016-12-31')
VAL_START = pd.Timestamp('2017-01-01')
VAL_END = pd.Timestamp('2024-12-31')
SEC_BASE = 'https://www.sec.gov/files/structureddata/data/insider-transactions-data-sets/{year}q{q}_form345.zip'
UA = 'Louis-Alviss-research-backtest/1.0'


def truthy(s: pd.Series) -> pd.Series:
    return s.fillna('').astype(str).str.strip().str.lower().isin({'1', 'true', 't', 'yes', 'y'})


def load_weekly_prices():
    w = load_prices()
    _, periods = load_memberships()
    w = add_membership_flag(w, periods)
    w['week'] = pd.to_datetime(w['week']).astype('datetime64[ns]')
    g = w.groupby('series_id', sort=False, observed=True)
    w['ret52_pre'] = g['close'].shift(1) / g['close'].shift(53) - 1
    w['next_open'] = g['open'].shift(-1)
    for h in HORIZONS:
        w[f'ret{h}'] = g['close'].shift(-h) / w['next_open'] - 1
    return w


def read_tsv(z: zipfile.ZipFile, name: str) -> pd.DataFrame:
    with z.open(name) as f:
        return pd.read_csv(f, sep='\t', dtype=str, low_memory=False)


def parse_quarter(year: int, q: int, universe_symbols: set[str], session: requests.Session):
    url = SEC_BASE.format(year=year, q=q)
    r = session.get(url, headers={'User-Agent': UA, 'Accept-Encoding': 'gzip, deflate'}, timeout=90)
    r.raise_for_status()
    z = zipfile.ZipFile(io.BytesIO(r.content))
    sub = read_tsv(z, 'SUBMISSION.tsv')
    ro = read_tsv(z, 'REPORTINGOWNER.tsv')
    tr = read_tsv(z, 'NONDERIV_TRANS.tsv')

    sub.columns = [c.upper() for c in sub.columns]
    ro.columns = [c.upper() for c in ro.columns]
    tr.columns = [c.upper() for c in tr.columns]

    needed_sub = ['ACCESSION_NUMBER', 'FILING_DATE', 'DOCUMENT_TYPE', 'ISSUERTRADINGSYMBOL']
    if not all(c in sub.columns for c in needed_sub):
        raise RuntimeError(f'missing submission columns {year}q{q}')

    sub['symbol'] = sub['ISSUERTRADINGSYMBOL'].fillna('').astype(str).map(norm_ticker)
    sub['filing_date'] = pd.to_datetime(sub['FILING_DATE'], format='%d-%b-%Y', errors='coerce')
    sub = sub[(sub['DOCUMENT_TYPE'].astype(str).str.strip() == '4') & sub['symbol'].isin(universe_symbols)].copy()
    if 'AFF10B5ONE' in sub.columns:
        sub = sub[~truthy(sub['AFF10B5ONE'])].copy()
    sub = sub[['ACCESSION_NUMBER', 'filing_date', 'symbol']].dropna(subset=['filing_date'])
    if sub.empty:
        return pd.DataFrame(), {'zip_bytes': len(r.content), 'sub_rows': 0, 'p_rows': 0, 'events': 0}

    rel = ro.get('RPTOWNER_RELATIONSHIP', pd.Series('', index=ro.index)).fillna('').astype(str)
    title = ro.get('RPTOWNER_TITLE', pd.Series('', index=ro.index)).fillna('').astype(str)
    owner_ok = rel.str.contains('director|officer', case=False, regex=True) | title.str.strip().ne('')
    roq = ro.loc[owner_ok, ['ACCESSION_NUMBER', 'RPTOWNERCIK']].copy()
    roq['RPTOWNERCIK'] = roq['RPTOWNERCIK'].fillna('').astype(str).str.strip()
    roq = roq[roq['RPTOWNERCIK'].ne('')]
    owner_map = roq.groupby('ACCESSION_NUMBER')['RPTOWNERCIK'].agg(lambda s: tuple(sorted(set(s)))).to_dict()
    valid_acc = set(owner_map)

    for c in ['TRANS_FORM_TYPE', 'TRANS_CODE', 'TRANS_ACQUIRED_DISP_CD']:
        if c not in tr.columns:
            raise RuntimeError(f'missing transaction column {c} {year}q{q}')
    x = tr[
        tr['ACCESSION_NUMBER'].isin(valid_acc)
        & tr['TRANS_FORM_TYPE'].fillna('').astype(str).str.strip().eq('4')
        & tr['TRANS_CODE'].fillna('').astype(str).str.strip().eq('P')
        & tr['TRANS_ACQUIRED_DISP_CD'].fillna('').astype(str).str.strip().eq('A')
    ].copy()
    x['shares'] = pd.to_numeric(x.get('TRANS_SHARES'), errors='coerce')
    x['price'] = pd.to_numeric(x.get('TRANS_PRICEPERSHARE'), errors='coerce')
    x['trans_date'] = pd.to_datetime(x.get('TRANS_DATE'), format='%d-%b-%Y', errors='coerce')
    x = x[(x['shares'] > 0) & (x['price'] > 0)].copy()
    x['value'] = x['shares'] * x['price']
    x = x.merge(sub, on='ACCESSION_NUMBER', how='inner')
    # Reject physically impossible future transaction dates; historical/stale disclosures remain causal at filing_date.
    x = x[x['trans_date'].isna() | (x['trans_date'] <= x['filing_date'])].copy()
    if x.empty:
        return pd.DataFrame(), {'zip_bytes': len(r.content), 'sub_rows': len(sub), 'p_rows': 0, 'events': 0}

    e = x.groupby(['ACCESSION_NUMBER', 'symbol', 'filing_date'], as_index=False).agg(
        event_value=('value', 'sum'),
        transaction_rows=('value', 'size'),
        trans_date_min=('trans_date', 'min'),
        trans_date_max=('trans_date', 'max'),
    )
    e['owner_ids'] = e['ACCESSION_NUMBER'].map(owner_map)
    e['owner_count'] = e['owner_ids'].map(lambda v: len(v) if isinstance(v, tuple) else 0)
    meta = {'zip_bytes': len(r.content), 'sub_rows': len(sub), 'p_rows': len(x), 'events': len(e)}
    return e, meta


def load_sec_events(universe_symbols: set[str]):
    sess = requests.Session()
    all_events = []
    meta = {'quarters': 0, 'zip_bytes': 0, 'sub_rows': 0, 'p_rows': 0, 'events_raw': 0}
    for year in range(2010, 2025):
        for q in range(1, 5):
            e, m = parse_quarter(year, q, universe_symbols, sess)
            meta['quarters'] += 1
            meta['zip_bytes'] += m['zip_bytes']
            meta['sub_rows'] += m['sub_rows']
            meta['p_rows'] += m['p_rows']
            meta['events_raw'] += m['events']
            if not e.empty:
                all_events.append(e)
            time.sleep(0.12)
        print('SEC_YEAR', year, 'events_so_far', meta['events_raw'], flush=True)
    if not all_events:
        raise RuntimeError('no SEC insider-buy events parsed')
    e = pd.concat(all_events, ignore_index=True)
    e = e.sort_values(['symbol', 'filing_date', 'ACCESSION_NUMBER']).drop_duplicates('ACCESSION_NUMBER', keep='first')
    meta.update({
        'events_dedup': len(e),
        'symbols': int(e['symbol'].nunique()),
        'filing_min': str(e['filing_date'].min().date()),
        'filing_max': str(e['filing_date'].max().date()),
        'event_value_q': {str(k): float(v) for k, v in e['event_value'].quantile([0, .1, .25, .5, .75, .9, .95, .99, 1]).items()},
    })
    return e, meta


def build_strategy_events(base: pd.DataFrame):
    out = []
    a = base.copy(); a['strategy'] = 'BaseBuyP'; out.append(a)
    b = base[base['event_value'] >= 100_000].copy(); b['strategy'] = 'LargeBuy100k'; out.append(b)

    eligible = base[base['event_value'] >= 25_000].copy().sort_values(['symbol', 'filing_date', 'ACCESSION_NUMBER'])
    cluster_idx = []
    for sym, g in eligible.groupby('symbol', sort=False, observed=True):
        window = deque()
        for idx, r in g.iterrows():
            cutoff = r['filing_date'] - pd.Timedelta(days=30)
            while window and window[0][0] < cutoff:
                window.popleft()
            window.append((r['filing_date'], r['ACCESSION_NUMBER'], tuple(r['owner_ids']) if isinstance(r['owner_ids'], tuple) else tuple()))
            accessions = {x[1] for x in window}
            owners = set()
            for x in window:
                owners.update(x[2])
            if len(accessions) >= 2 and len(owners) >= 2:
                cluster_idx.append(idx)
    c = eligible.loc[cluster_idx].copy() if cluster_idx else eligible.iloc[0:0].copy()
    c['strategy'] = 'Cluster2_30d'; out.append(c)
    return pd.concat(out, ignore_index=True)


def map_to_prices(events: pd.DataFrame, w: pd.DataFrame):
    rows = []
    pcols = ['week', 'series_id', 'is_member', 'ret52_pre', 'next_open'] + [f'ret{h}' for h in HORIZONS]
    for sym, r in events.groupby('symbol', sort=False, observed=True):
        p = w[w['symbol'].eq(sym)][pcols].sort_values('week')
        if p.empty:
            continue
        m = pd.merge_asof(
            r.sort_values('filing_date'), p,
            left_on='filing_date', right_on='week',
            direction='forward', allow_exact_matches=False,
        )
        lag = (m['week'] - m['filing_date']).dt.days
        m = m[lag.between(1, 10, inclusive='both') & m['is_member'].fillna(False) & m['next_open'].notna()].copy()
        if not m.empty:
            rows.append(m)
    if not rows:
        raise RuntimeError('no mapped Form4 events')
    a = pd.concat(rows, ignore_index=True)
    # One ticker/strategy signal per week; multiple filings that week are one trade opportunity.
    a = a.sort_values(['strategy', 'symbol', 'week', 'event_value'], ascending=[True, True, True, False])
    a = a.drop_duplicates(['strategy', 'symbol', 'week'], keep='first').reset_index(drop=True)
    return a


def add_recent_buy_flag(w: pd.DataFrame, mapped: pd.DataFrame):
    base = mapped[mapped['strategy'].eq('BaseBuyP')][['symbol', 'week']].drop_duplicates()
    event_set = set(map(tuple, base[['symbol', 'week']].itertuples(index=False, name=None)))
    q = w.copy()
    q['buy_event'] = [1 if (s, wk) in event_set else 0 for s, wk in zip(q['symbol'], q['week'])]
    q = q.sort_values(['series_id', 'week'])
    q['recent_buy4'] = q.groupby('series_id', sort=False, observed=True)['buy_event'].transform(lambda s: s.rolling(4, min_periods=1).max())
    return q


def matched_excess(ev: pd.DataFrame, w: pd.DataFrame):
    for h in HORIZONS:
        ev[f'excess{h}'] = np.nan
        ev[f'control_n{h}'] = 0
    byweek = {wk: g for wk, g in w[w['is_member'].fillna(False)].groupby('week', sort=False)}
    for j, r in enumerate(ev.itertuples(index=False)):
        p = byweek.get(r.week)
        if p is None or not np.isfinite(r.ret52_pre):
            continue
        rr = p['ret52_pre'].to_numpy(float)
        sy = p['symbol'].to_numpy(str)
        base = np.isfinite(rr) & (sy != r.symbol) & (p['recent_buy4'].to_numpy(float) == 0)
        m = base & (np.abs(rr - r.ret52_pre) <= .15)
        if m.sum() < 5:
            m = base & (np.abs(rr - r.ret52_pre) <= .25)
        for h in HORIZONS:
            vals = p.loc[m, f'ret{h}'].to_numpy(float)
            vals = vals[np.isfinite(vals)]
            rv = getattr(r, f'ret{h}')
            if len(vals) >= 3 and np.isfinite(rv):
                ev.at[j, f'excess{h}'] = rv - float(np.median(vals))
                ev.at[j, f'control_n{h}'] = len(vals)
    return ev


def summarize(ev: pd.DataFrame, label: str, start: pd.Timestamp, end: pd.Timestamp):
    out = []
    rng = np.random.default_rng(20260823)
    z = ev[ev['week'].between(start, end)]
    for st, x0 in z.groupby('strategy', sort=False):
        for h in HORIZONS:
            x = x0.dropna(subset=[f'ret{h}'])
            c = x.dropna(subset=[f'excess{h}'])
            wm = c.groupby('week')[f'excess{h}'].mean().to_numpy(float)
            if len(wm) >= 8:
                bs = np.array([rng.choice(wm, len(wm), replace=True).mean() for _ in range(2000)])
                lo, hi = np.quantile(bs, [.025, .975])
            else:
                lo = hi = np.nan
            out.append({
                'slice': label, 'strategy': st, 'horizon': h,
                'n': len(x), 'matched_n': len(c), 'signal_weeks': int(x['week'].nunique()),
                'median_return': x[f'ret{h}'].median(), 'mean_return': x[f'ret{h}'].mean(),
                'win_rate': (x[f'ret{h}'] > 0).mean(),
                'median_excess': c[f'excess{h}'].median(), 'mean_excess': c[f'excess{h}'].mean(),
                'beat_matched': (c[f'excess{h}'] > 0).mean(), 'ci_lo': lo, 'ci_hi': hi,
            })
    return out


def main():
    t = time.time()
    print('loading prices...', flush=True)
    w = load_weekly_prices()
    universe = set(w.loc[w['is_member'].fillna(False) & w['week'].between(DISC_START, VAL_END), 'symbol'].dropna().astype(str).unique())
    print('universe_symbols', len(universe), flush=True)
    print('loading official SEC Form345 quarterly data...', flush=True)
    base, meta = load_sec_events(universe)
    events = build_strategy_events(base)
    print('RAW_STRATEGY_EVENTS', json.dumps(events.groupby('strategy').size().to_dict()), flush=True)
    mapped = map_to_prices(events, w)
    w2 = add_recent_buy_flag(w, mapped)
    matched = matched_excess(mapped, w2)
    meta.update({
        'mapped_rows': len(mapped),
        'mapped_symbols': int(mapped['symbol'].nunique()),
        'mapped_week_min': str(mapped['week'].min().date()),
        'mapped_week_max': str(mapped['week'].max().date()),
        'elapsed_sec': round(time.time() - t, 2),
    })
    print('MAPPED_EVENTS', json.dumps(mapped.groupby('strategy').size().to_dict()), flush=True)
    print('META', json.dumps(meta), flush=True)
    s = pd.DataFrame(
        summarize(matched, 'discovery_2010_2016', DISC_START, DISC_END)
        + summarize(matched, 'validation_2017_2024', VAL_START, VAL_END)
    )
    print(s.to_string(index=False), flush=True)
    v = s[(s['slice'] == 'validation_2017_2024') & (s['horizon'] == 26)].copy()
    v['pass'] = (v['n'] >= 300) & (v['median_excess'] > .01) & (v['beat_matched'] >= .525) & (v['ci_lo'] > 0)
    print('GATE26', v[['strategy','n','matched_n','win_rate','median_return','median_excess','beat_matched','mean_excess','ci_lo','ci_hi','pass']].to_json(orient='records'), flush=True)
    print('DONE', flush=True)


if __name__ == '__main__':
    main()
