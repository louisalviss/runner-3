#!/usr/bin/env python3
"""Data-semantics correction for Derivatives Trend Rider v1.

Strategy logic is unchanged. This wrapper fixes one data-layer issue:
OI change must use Binance `sum_open_interest` (contract quantity), not
`sum_open_interest_value` (USDT notional, mechanically contaminated by price).
It also runs both intended execution timeframes: native 5m and deterministic
5m->10m resampling from the frozen base implementation.
"""
from __future__ import annotations
import argparse
import importlib.util
from pathlib import Path
import pandas as pd

HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("dtr_base", HERE / "derivatives_trend_rider_v1.py")
base = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(base)

_orig_findcol = base.findcol

def strict_findcol(df, alternatives):
    # The frozen base asked for OI via alternatives beginning with
    # sumopeninterestvalue. Correct that one semantic lookup only.
    if alternatives and alternatives[0] == ['sumopeninterestvalue']:
        if df is None:
            return None
        for c in df.columns:
            if base.norm(c) == 'sumopeninterest':
                return c
        return None  # no notional fallback; missing quantity => no signal
    return _orig_findcol(df, alternatives)

base.findcol = strict_findcol

# Cache hourly derivatives state so 5m and 10m share the exact same OI/funding
# download and transformation. Execution timeframe is the only difference.
_orig_derivatives_hourly = base.derivatives_hourly
_der_cache = {}

def cached_derivatives_hourly(sym, year, k1):
    key = (sym, int(year))
    if key not in _der_cache:
        _der_cache[key] = _orig_derivatives_hourly(sym, year, k1)
    d, diag = _der_cache[key]
    # base.run mutates diag by adding tf/symbol/price flags. Return a fresh copy
    # so the 10m pass cannot overwrite diagnostics already recorded for 5m.
    return d, dict(diag)

base.derivatives_hourly = cached_derivatives_hourly

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--year', type=int, required=True)
    ap.add_argument('--out', required=True)
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)

    all_trades = []
    diags = []
    for tf in ['5m', '10m']:
        d, g = base.run(a.year, tf)
        diags += g
        if len(d):
            all_trades.append(d)

    x = pd.concat(all_trades, ignore_index=True) if all_trades else pd.DataFrame()
    x.to_csv(out / 'trades.csv', index=False)
    cov = pd.DataFrame(diags)
    cov.to_csv(out / 'coverage.csv', index=False)

    eligible = {}
    for tf in ['5m', '10m']:
        q = cov[cov.tf.astype(str) == tf] if len(cov) and 'tf' in cov.columns else pd.DataFrame()
        eligible[tf] = int(q.query('derivatives_ok == True').symbol.nunique()) if len(q) and 'derivatives_ok' in q.columns else 0

    oi_cols = sorted(set(str(v) for v in cov.get('oi_col', pd.Series(dtype=str)).dropna().unique()))
    print('year', a.year, 'rows', len(x), 'eligible', eligible, 'oi_cols', oi_cols,
          'timeframes', sorted(x.tf.astype(str).unique()) if len(x) else [])

    if min(eligible.values()) < 6:
        raise SystemExit(f'DATA_QUALITY_FAIL eligible={eligible}')
    if set(oi_cols) != {'sum_open_interest'}:
        raise SystemExit(f'DATA_SEMANTICS_FAIL oi_cols={oi_cols}')
    if len(x) == 0 or set(x.tf.astype(str)) != {'5m', '10m'}:
        raise SystemExit('DATA_QUALITY_FAIL missing_5m_or_10m_trades')

if __name__ == '__main__':
    main()
