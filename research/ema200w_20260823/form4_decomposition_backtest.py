from __future__ import annotations

import io
import json
import time
import zipfile

import numpy as np
import pandas as pd
import requests

from backtest import load_prices, load_memberships, add_membership_flag, norm_ticker
from form4_sec_backtest import map_to_prices, add_recent_buy_flag, matched_excess, summarize, read_tsv

HORIZONS = (13, 26, 52)
DISC_START = pd.Timestamp('2010-01-01')
DISC_END = pd.Timestamp('2016-12-31')
VAL_START = pd.Timestamp('2017-01-01')
VAL_END = pd.Timestamp('2024-12-31')
WARMUP_START_YEAR = 2006
SEC_BASE = 'https://www.sec.gov/files/structureddata/data/insider-transactions-data-sets/{year}q{q}_form345.zip'
SEC_PAGE = 'https://www.sec.gov/data-research/sec-markets-data/insider-transactions-data-sets'
UA = 'research backtest contact example@example.com'

EXEC_RE = r'\bCEO\b|chief executive|\bCFO\b|chief financial'
STAKE_COL_CANDIDATES = [
    'SHRS_OWND_FOLWG_TRANS',
    'SHARES_OWNED_FOLLOWING_TRANSACTION',
    'TRANS_SHARES_OWNED_FOLLOWING_TRANS',
]


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


def parse_quarter(year: int, q: int, universe_symbols: set[str], session: requests.Session):
    url = SEC_BASE.format(year=year, q=q)
    r = session.get(url, timeout=90)
    r.raise_for_status()
    z = zipfile.ZipFile(io.BytesIO(r.content))
    sub = read_tsv(z, 'SUBMISSION.tsv')
    ro = read_tsv(z, 'REPORTINGOWNER.tsv')
    tr = read_tsv(z, 'NONDERIV_TRANS.tsv')
    sub.columns = [c.upper() for c in sub.columns]
    ro.columns = [c.upper() for c in ro.columns]
    tr.columns = [c.upper() for c in tr.columns]

    sub['symbol'] = sub['ISSUERTRADINGSYMBOL'].fillna('').astype(str).map(norm_ticker)
    sub['filing_date'] = pd.to_datetime(sub['FILING_DATE'], format='%d-%b-%Y', errors='coerce').astype('datetime64[ns]')
    sub = sub[(sub['DOCUMENT_TYPE'].astype(str).str.strip() == '4') & sub['symbol'].isin(universe_symbols)].copy()
    if 'AFF10B5ONE' in sub.columns:
        sub = sub[~truthy(sub['AFF10B5ONE'])].copy()
    sub = sub[['ACCESSION_NUMBER', 'filing_date', 'symbol']].dropna(subset=['filing_date'])
    if sub.empty:
        return pd.DataFrame(), {'bytes': len(r.content), 'events': 0, 'stake_col': None}

    rel = ro.get('RPTOWNER_RELATIONSHIP', pd.Series('', index=ro.index)).fillna('').astype(str)
    title = ro.get('RPTOWNER_TITLE', pd.Series('', index=ro.index)).fillna('').astype(str)
    owner_ok = rel.str.contains('director|officer', case=False, regex=True) | title.str.strip().ne('')
    roq = ro.loc[owner_ok, ['ACCESSION_NUMBER', 'RPTOWNERCIK']].copy()
    roq['title'] = title.loc[roq.index]
    roq['is_exec'] = roq['title'].str.contains(EXEC_RE, case=False, regex=True, na=False)
    roq['RPTOWNERCIK'] = roq['RPTOWNERCIK'].fillna('').astype(str).str.strip()
    roq = roq[roq['RPTOWNERCIK'].ne('')]
    owner_map = roq.groupby('ACCESSION_NUMBER')['RPTOWNERCIK'].agg(lambda s: tuple(sorted(set(s)))).to_dict()
    exec_map = roq.groupby('ACCESSION_NUMBER')['is_exec'].max().to_dict()
    valid_acc = set(owner_map)

    x = tr[
        tr['ACCESSION_NUMBER'].isin(valid_acc)
        & tr['TRANS_FORM_TYPE'].fillna('').astype(str).str.strip().eq('4')
        & tr['TRANS_CODE'].fillna('').astype(str).str.strip().eq('P')
        & tr['TRANS_ACQUIRED_DISP_CD'].fillna('').astype(str).str.strip().eq('A')
    ].copy()
    x['shares'] = pd.to_numeric(x.get('TRANS_SHARES'), errors='coerce')
    x['price'] = pd.to_numeric(x.get('TRANS_PRICEPERSHARE'), errors='coerce')
    x['trans_date'] = pd.to_datetime(x.get('TRANS_DATE'), format='%d-%b-%Y', errors='coerce').astype('datetime64[ns]')
    x = x[(x['shares'] > 0) & (x['price'] > 0)].copy()
    x['value'] = x['shares'] * x['price']

    stake_col = next((c for c in STAKE_COL_CANDIDATES if c in tr.columns), None)
    if stake_col is not None:
        x['following_shares'] = pd.to_numeric(x[stake_col], errors='coerce')
        valid = (x['following_shares'] > 0) & (x['following_shares'] >= x['shares'])
        x['stake_increase_ratio'] = np.where(valid, x['shares'] / x['following_shares'], np.nan)
    else:
        x['stake_increase_ratio'] = np.nan

    x = x.merge(sub, on='ACCESSION_NUMBER', how='inner')
    x = x[x['trans_date'].isna() | (x['trans_date'] <= x['filing_date'])].copy()
    if x.empty:
        return pd.DataFrame(), {'bytes': len(r.content), 'events': 0, 'stake_col': stake_col}

    e = x.groupby(['ACCESSION_NUMBER', 'symbol', 'filing_date'], as_index=False).agg(
        event_value=('value', 'sum'),
        event_shares=('shares', 'sum'),
        stake_increase_ratio=('stake_increase_ratio', 'max'),
    )
    e['owner_ids'] = e['ACCESSION_NUMBER'].map(owner_map)
    e['owner_count'] = e['owner_ids'].map(lambda v: len(v) if isinstance(v, tuple) else 0)
    e['is_exec'] = e['ACCESSION_NUMBER'].map(exec_map).fillna(False).astype(bool)
    return e, {'bytes': len(r.content), 'events': len(e), 'stake_col': stake_col}


def load_events(universe_symbols: set[str]):
    sess = requests.Session()
    sess.headers.update({
        'User-Agent': UA,
        'Accept': 'text/html,application/xhtml+xml,application/zip,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9',
        'Referer': SEC_PAGE,
    })
    warm = sess.get(SEC_PAGE, timeout=30)
    warm.raise_for_status()
    all_events = []
    meta = {'quarters': 0, 'zip_bytes': 0, 'stake_cols': {}}
    for year in range(WARMUP_START_YEAR, 2025):
        for q in range(1, 5):
            e, m = parse_quarter(year, q, universe_symbols, sess)
            meta['quarters'] += 1
            meta['zip_bytes'] += m['bytes']
            meta['stake_cols'][f'{year}q{q}'] = m['stake_col']
            if not e.empty:
                all_events.append(e)
            time.sleep(0.5)
        print('SEC_YEAR', year, flush=True)
    base = pd.concat(all_events, ignore_index=True)
    base = base.sort_values(['symbol', 'filing_date', 'ACCESSION_NUMBER']).drop_duplicates('ACCESSION_NUMBER', keep='first')
    base['prev_buy_date'] = base.groupby('symbol', sort=False)['filing_date'].shift(1)
    base['days_since_prev_buy'] = (base['filing_date'] - base['prev_buy_date']).dt.days
    base['dormant365'] = base['prev_buy_date'].notna() & (base['days_since_prev_buy'] >= 365)
    base['stake10'] = base['stake_increase_ratio'].notna() & (base['stake_increase_ratio'] >= 0.10)
    meta.update({
        'base_events_all': len(base),
        'base_events_2010_2024': int((base['filing_date'] >= DISC_START).sum()),
        'symbols': int(base['symbol'].nunique()),
        'exec_events_2010_2024': int(((base['filing_date'] >= DISC_START) & base['is_exec']).sum()),
        'dormant365_events_2010_2024': int(((base['filing_date'] >= DISC_START) & base['dormant365']).sum()),
        'stake10_events_2010_2024': int(((base['filing_date'] >= DISC_START) & base['stake10']).sum()),
        'stake_coverage_2010_2024': int(((base['filing_date'] >= DISC_START) & base['stake_increase_ratio'].notna()).sum()),
    })
    return base, meta


def build_strategies(base: pd.DataFrame):
    b = base[base['filing_date'].between(DISC_START, VAL_END)].copy()
    out = []
    a = b.copy(); a['strategy'] = 'BaseBuyP'; out.append(a)
    a = b[b['is_exec']].copy(); a['strategy'] = 'ExecCEO_CFO'; out.append(a)
    a = b[b['dormant365']].copy(); a['strategy'] = 'Dormant365'; out.append(a)
    a = b[b['stake10']].copy(); a['strategy'] = 'StakeIncrease10'; out.append(a)
    a = b[b['is_exec'] & b['dormant365'] & b['stake10']].copy(); a['strategy'] = 'ExecDormantStake10'; out.append(a)
    return pd.concat(out, ignore_index=True)


def main():
    t = time.time()
    w = load_weekly_prices()
    # Include historical PIT members in the evaluated period; warmup SEC data is only for dormancy state.
    universe = set(w.loc[w['is_member'].fillna(False) & w['week'].between(DISC_START, VAL_END), 'symbol'].dropna().astype(str).unique())
    print('UNIVERSE', len(universe), flush=True)
    base, meta = load_events(universe)
    events = build_strategies(base)
    print('RAW_STRATEGY_EVENTS', json.dumps(events.groupby('strategy').size().to_dict()), flush=True)
    mapped = map_to_prices(events, w)
    w2 = add_recent_buy_flag(w, mapped)
    matched = matched_excess(mapped, w2)
    meta.update({
        'mapped_rows': len(mapped),
        'mapped_symbols': int(mapped['symbol'].nunique()),
        'elapsed_sec': round(time.time() - t, 2),
    })
    print('META', json.dumps(meta), flush=True)
    print('MAPPED_EVENTS', json.dumps(mapped.groupby('strategy').size().to_dict()), flush=True)
    s = pd.DataFrame(
        summarize(matched, 'discovery_2010_2016', DISC_START, DISC_END)
        + summarize(matched, 'validation_2017_2024', VAL_START, VAL_END)
    )
    print(s.to_string(index=False), flush=True)
    gate = s[(s['slice'] == 'validation_2017_2024') & (s['horizon'] == 26)].copy()
    gate['pass'] = (
        (gate['n'] >= 300)
        & (gate['median_excess'] > .01)
        & (gate['beat_matched'] >= .525)
        & (gate['ci_lo'] > 0)
    )
    print('GATE26', gate[['strategy','n','matched_n','win_rate','median_return','median_excess','beat_matched','mean_excess','ci_lo','ci_hi','pass']].to_json(orient='records'), flush=True)
    print('DONE', flush=True)


if __name__ == '__main__':
    main()
