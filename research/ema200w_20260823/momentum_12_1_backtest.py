from __future__ import annotations

import json
import math
import time

import numpy as np
import pandas as pd

from backtest import load_prices, load_memberships, add_membership_flag

DISC_START = pd.Timestamp('2010-01-01')
DISC_END = pd.Timestamp('2016-12-31')
VAL_START = pd.Timestamp('2017-01-01')
VAL_END = pd.Timestamp('2024-12-31')
TOP_FRAC = 0.20
COST_BPS = 25.0


def annualized_return(r: pd.Series) -> float:
    x = r.dropna().astype(float)
    if x.empty:
        return np.nan
    years = len(x) / 12.0
    return float(np.prod(1.0 + x) ** (1.0 / years) - 1.0)


def annualized_vol(r: pd.Series) -> float:
    x = r.dropna().astype(float)
    return float(x.std(ddof=1) * math.sqrt(12)) if len(x) > 1 else np.nan


def sharpe0(r: pd.Series) -> float:
    x = r.dropna().astype(float)
    if len(x) < 2 or x.std(ddof=1) == 0:
        return np.nan
    return float(x.mean() / x.std(ddof=1) * math.sqrt(12))


def max_drawdown(r: pd.Series) -> float:
    x = r.dropna().astype(float)
    if x.empty:
        return np.nan
    eq = (1.0 + x).cumprod()
    return float((eq / eq.cummax() - 1.0).min())


def weight_turnover(prev: dict[str, float], cur: dict[str, float]) -> float:
    if not prev:
        return 1.0
    names = set(prev) | set(cur)
    return 0.5 * sum(abs(cur.get(s, 0.0) - prev.get(s, 0.0)) for s in names)


def realized_return_map(w: pd.DataFrame, formation_week: pd.Timestamp, next_formation_week: pd.Timestamp) -> dict[str, float]:
    """Return from first weekly open after formation to first weekly open after next formation.

    If a listing segment ends before the scheduled exit, use its final adjusted close as a conservative
    delisting/suspension fallback. No future membership information is used for selection.
    """
    start_rows = w[w['week'].eq(formation_week)][['symbol', 'series_id', 'next_open', 'next_week']].copy()
    exit_rows = w[w['week'].eq(next_formation_week)][['series_id', 'next_open']].rename(columns={'next_open': 'exit_open'})
    z = start_rows.merge(exit_rows, on='series_id', how='left')
    target_exit = next_formation_week + pd.Timedelta(days=10)
    fallback = z['exit_open'].isna() & (z['series_last_week'] < target_exit)
    # series_last_* are merged below by series_id
    return {}


def main() -> None:
    t0 = time.time()
    print('loading PIT weekly prices...', flush=True)
    w = load_prices()
    _, periods = load_memberships()
    w = add_membership_flag(w, periods)
    w['week'] = pd.to_datetime(w['week']).astype('datetime64[ns]')
    w = w.sort_values(['series_id', 'week']).reset_index(drop=True)

    g = w.groupby('series_id', sort=False, observed=True)
    # Canonical 12-1 score using completed weekly data: price at t-4w / price at t-52w - 1.
    w['mom_12_1'] = g['close'].shift(4) / g['close'].shift(52) - 1.0
    w['next_open'] = g['open'].shift(-1)
    w['next_week'] = g['week'].shift(-1)
    w['series_last_week'] = g['week'].transform('max')
    w['series_last_close'] = g['close'].transform('last')

    # One formation date per calendar month: the last completed W-FRI bar in that month.
    cal = w.loc[w['week'].between(DISC_START - pd.Timedelta(days=400), VAL_END), ['week']].drop_duplicates().copy()
    cal['month'] = cal['week'].dt.to_period('M')
    forms = cal.groupby('month', as_index=False)['week'].max().sort_values('week').reset_index(drop=True)
    forms['next_form_week'] = forms['week'].shift(-1)
    forms = forms[forms['week'].between(DISC_START, VAL_END) & forms['next_form_week'].notna()].copy()

    periods_out = []
    top_weight_history: list[dict[str, float]] = []
    bench_weight_history: list[dict[str, float]] = []

    # lookup final series info for delisting fallback
    series_meta = w.groupby('series_id', observed=True).agg(
        series_last_week=('week', 'max'),
        series_last_close=('close', 'last'),
    )

    for rr in forms.itertuples(index=False):
        fw = pd.Timestamp(rr.week)
        nfw = pd.Timestamp(rr.next_form_week)
        formation = w[
            w['week'].eq(fw)
            & w['is_member'].fillna(False)
            & w['mom_12_1'].notna()
            & w['next_open'].notna()
            & w['next_week'].notna()
        ][['symbol', 'series_id', 'mom_12_1', 'next_open', 'next_week']].copy()
        if len(formation) < 100:
            continue

        # Exit at the first weekly open after the next month's formation week.
        exit_px = w[w['week'].eq(nfw)][['series_id', 'next_open']].rename(columns={'next_open': 'exit_open'})
        formation = formation.merge(exit_px, on='series_id', how='left').merge(series_meta, on='series_id', how='left')
        target_exit = nfw + pd.Timedelta(days=10)
        ended = formation['series_last_week'] < target_exit
        formation.loc[formation['exit_open'].isna() & ended, 'exit_open'] = formation.loc[
            formation['exit_open'].isna() & ended, 'series_last_close'
        ]
        formation['hold_ret'] = formation['exit_open'] / formation['next_open'] - 1.0
        formation = formation.replace([np.inf, -np.inf], np.nan).dropna(subset=['hold_ret']).copy()
        if len(formation) < 100:
            continue

        # Frozen top-quintile selection, deterministic tie-break by symbol.
        formation = formation.sort_values(['mom_12_1', 'symbol'], ascending=[False, True]).reset_index(drop=True)
        k = max(1, int(math.floor(len(formation) * TOP_FRAC)))
        top = formation.iloc[:k].copy()

        top_weights = {s: 1.0 / len(top) for s in top['symbol'].astype(str)}
        bench_weights = {s: 1.0 / len(formation) for s in formation['symbol'].astype(str)}
        prev_top = top_weight_history[-1] if top_weight_history else {}
        prev_bench = bench_weight_history[-1] if bench_weight_history else {}
        top_to = weight_turnover(prev_top, top_weights)
        bench_to = weight_turnover(prev_bench, bench_weights)
        top_weight_history.append(top_weights)
        bench_weight_history.append(bench_weights)

        gross_top = float(top['hold_ret'].mean())
        gross_bench = float(formation['hold_ret'].mean())
        c = COST_BPS / 10000.0
        net_top = (1.0 + gross_top) * (1.0 - c * top_to) - 1.0
        net_bench = (1.0 + gross_bench) * (1.0 - c * bench_to) - 1.0

        periods_out.append({
            'formation_week': fw,
            'entry_week': pd.Timestamp(formation['next_week'].mode().iloc[0]),
            'next_formation_week': nfw,
            'universe_n': len(formation),
            'top_n': len(top),
            'top_turnover': top_to,
            'bench_turnover': bench_to,
            'top_gross': gross_top,
            'bench_gross': gross_bench,
            'gross_excess': gross_top - gross_bench,
            'top_net25': net_top,
            'bench_net25': net_bench,
            'net25_excess': net_top - net_bench,
            'top_mom_min': float(top['mom_12_1'].min()),
            'top_mom_median': float(top['mom_12_1'].median()),
        })

    p = pd.DataFrame(periods_out).sort_values('formation_week').reset_index(drop=True)
    if p.empty:
        raise RuntimeError('no monthly momentum periods produced')

    print('META', json.dumps({
        'periods': len(p),
        'formation_min': str(p['formation_week'].min().date()),
        'formation_max': str(p['formation_week'].max().date()),
        'median_universe_n': float(p['universe_n'].median()),
        'median_top_n': float(p['top_n'].median()),
        'mean_top_turnover': float(p['top_turnover'].mean()),
        'mean_bench_turnover': float(p['bench_turnover'].mean()),
        'elapsed_sec': round(time.time() - t0, 2),
    }), flush=True)

    def summarize(label: str, start: pd.Timestamp, end: pd.Timestamp) -> dict:
        x = p[p['formation_week'].between(start, end)].copy()
        years = {}
        for year, q in x.groupby(x['formation_week'].dt.year):
            pt = float(np.prod(1 + q['top_gross']) - 1)
            pb = float(np.prod(1 + q['bench_gross']) - 1)
            years[str(year)] = {'top': pt, 'bench': pb, 'excess': pt - pb, 'positive': bool(pt > pb), 'months': len(q)}
        out = {
            'slice': label,
            'months': len(x),
            'top_cagr_gross': annualized_return(x['top_gross']),
            'bench_cagr_gross': annualized_return(x['bench_gross']),
            'annualized_excess_gross': annualized_return(x['top_gross']) - annualized_return(x['bench_gross']),
            'top_sharpe_gross': sharpe0(x['top_gross']),
            'bench_sharpe_gross': sharpe0(x['bench_gross']),
            'sharpe_improvement': sharpe0(x['top_gross']) - sharpe0(x['bench_gross']),
            'top_vol_gross': annualized_vol(x['top_gross']),
            'bench_vol_gross': annualized_vol(x['bench_gross']),
            'top_maxdd_gross': max_drawdown(x['top_gross']),
            'bench_maxdd_gross': max_drawdown(x['bench_gross']),
            'top_cagr_net25': annualized_return(x['top_net25']),
            'bench_cagr_net25': annualized_return(x['bench_net25']),
            'annualized_excess_net25': annualized_return(x['top_net25']) - annualized_return(x['bench_net25']),
            'monthly_excess_mean': float(x['gross_excess'].mean()),
            'monthly_excess_median': float(x['gross_excess'].median()),
            'monthly_beat_rate': float((x['gross_excess'] > 0).mean()),
            'mean_top_turnover': float(x['top_turnover'].mean()),
            'positive_excess_years': int(sum(v['positive'] for v in years.values())),
            'year_count': int(len(years)),
            'yearly': years,
        }
        return out

    disc = summarize('discovery_2010_2016', DISC_START, DISC_END)
    val = summarize('validation_2017_2024', VAL_START, VAL_END)
    print('DISCOVERY', json.dumps(disc), flush=True)
    print('VALIDATION', json.dumps(val), flush=True)

    gate = {
        'months_ge_90': val['months'] >= 90,
        'gross_ann_excess_gt_1_5pct': val['annualized_excess_gross'] > 0.015,
        'sharpe_improvement_gt_0': val['sharpe_improvement'] > 0,
        'positive_excess_years_ge_5_of_8': val['positive_excess_years'] >= 5 and val['year_count'] >= 8,
        'net25_ann_excess_gt_0': val['annualized_excess_net25'] > 0,
    }
    gate['pass'] = bool(all(gate.values()))
    print('GATE', json.dumps(gate), flush=True)
    print('DONE', flush=True)


if __name__ == '__main__':
    main()
