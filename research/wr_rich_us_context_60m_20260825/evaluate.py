#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import math
import os
import sys
from collections import Counter, defaultdict
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

MIN_CROSS_SECTION = 62


def metric(rows: list[dict]) -> dict:
    rows = sorted(rows, key=lambda x: (int(x['signal']), str(x.get('symbol', ''))))
    vals = [float(x['R_exec']) for x in rows]
    if not vals:
        return {'n': 0, 'R': 0.0, 'mean_R': None, 'PF': None, 'win_rate': None, 'max_DD_R': 0.0}
    gp = sum(max(v, 0.0) for v in vals)
    gl = sum(max(-v, 0.0) for v in vals)
    eq = peak = 0.0
    dd = 0.0
    for v in vals:
        eq += v
        peak = max(peak, eq)
        dd = min(dd, eq - peak)
    return {
        'n': len(vals), 'R': sum(vals), 'mean_R': sum(vals) / len(vals),
        'PF': gp / gl if gl else None,
        'win_rate': 100.0 * sum(v > 0 for v in vals) / len(vals),
        'max_DD_R': dd,
    }


def year(row: dict) -> int:
    return pd.Timestamp(int(row['signal']), unit='ms', tz='UTC').tz_convert(ZoneInfo('America/New_York')).year


def load_parent(root: Path) -> list[dict]:
    hits = list(root.rglob('execution-trades.jsonl'))
    if len(hits) != 1:
        raise RuntimeError(f'expected one execution-trades.jsonl, got {hits}')
    rows = []
    for line in hits[0].read_text().splitlines():
        if not line.strip():
            continue
        x = json.loads(line)
        sym = x.get('_symbol') or x.get('symbol')
        if sym:
            x['symbol'] = sym
        rows.append(x)
    return rows


def load_probe(root: Path) -> dict | None:
    hits = list(root.rglob('probe.json'))
    return None if not hits else json.loads(hits[0].read_text())


def load_breadth(root: Path) -> pd.DataFrame:
    acc = defaultdict(lambda: [0, 0, 0, 0.0, 0.0])
    for p in root.rglob('breadth-shard-*.csv'):
        with p.open(newline='') as f:
            for row in csv.DictReader(f):
                ms = int(row['timestamp_ms'])
                a = acc[ms]
                a[0] += int(row['ema_valid_count'])
                a[1] += int(row['above_count'])
                a[2] += int(row['ret_count'])
                a[3] += float(row['ret_sum'])
                a[4] += float(row['ret_sumsq'])
    if not acc:
        return pd.DataFrame()
    idx = sorted(acc)
    df = pd.DataFrame(
        [acc[x] for x in idx],
        index=pd.to_datetime(idx, unit='ms', utc=True),
        columns=['ema_valid_count', 'above_count', 'ret_count', 'ret_sum', 'ret_sumsq'],
    )
    breadth = pd.Series(np.nan, index=df.index, dtype=float)
    mask_b = df.ema_valid_count >= MIN_CROSS_SECTION
    breadth.loc[mask_b] = df.loc[mask_b, 'above_count'] / df.loc[mask_b, 'ema_valid_count']
    valid_b = breadth.dropna()
    breadth_delta = valid_b.diff().reindex(df.index)

    dispersion = pd.Series(np.nan, index=df.index, dtype=float)
    mask_d = df.ret_count >= MIN_CROSS_SECTION
    n = df.loc[mask_d, 'ret_count'].astype(float)
    mean = df.loc[mask_d, 'ret_sum'] / n
    var = df.loc[mask_d, 'ret_sumsq'] / n - mean * mean
    dispersion.loc[mask_d] = np.sqrt(np.maximum(var, 0.0))
    valid_d = dispersion.dropna()
    disp_ref = valid_d.shift(1).rolling(100, min_periods=100).median().reindex(df.index)

    df['breadth'] = breadth
    df['breadth_delta'] = breadth_delta
    df['dispersion'] = dispersion
    df['dispersion_ref100'] = disp_ref
    return df


def bootstrap_days(A: list[dict], B: list[dict], reps=2000, seed=20260825) -> dict:
    aa, bb = {}, {}
    for x in A:
        aa.setdefault(x['signal_date_ny'], []).append(float(x['R_exec']))
    for x in B:
        bb.setdefault(x['signal_date_ny'], []).append(float(x['R_exec']))
    days = sorted(aa)
    if not days:
        return {'days': 0, 'reps': 0, 'B_mean_ci95': [None, None], 'delta_ci95': [None, None]}
    rng = np.random.default_rng(seed)
    bm, dm = [], []
    for _ in range(reps):
        av, bv = [], []
        for d in rng.choice(days, size=len(days), replace=True):
            av.extend(aa[d])
            bv.extend(bb.get(d, []))
        if av and bv:
            am = float(np.mean(av)); bmean = float(np.mean(bv))
            bm.append(bmean); dm.append(bmean - am)
    return {
        'days': len(days), 'reps': len(bm),
        'B_mean_ci95': [float(np.percentile(bm, 2.5)), float(np.percentile(bm, 97.5))] if bm else [None, None],
        'delta_ci95': [float(np.percentile(dm, 2.5)), float(np.percentile(dm, 97.5))] if dm else [None, None],
    }


def symbol_breadth(rows: list[dict]) -> dict:
    by = defaultdict(list)
    for x in rows:
        by[str(x['symbol'])].append(x)
    eligible = {s: xs for s, xs in by.items() if len(xs) >= 5}
    positive = sum(metric(xs)['R'] > 0 for xs in eligible.values())
    return {
        'eligible_symbols_ge5': len(eligible),
        'positive_symbols': positive,
        'positive_fraction': positive / len(eligible) if eligible else 0.0,
        'per_symbol': {s: metric(xs) for s, xs in sorted(by.items())},
    }


def configure_exp(helper_dir: str):
    sys.path.insert(0, helper_dir)
    import exp
    exp.STATE_START = pd.Timestamp('2023-10-01T00:00:00Z')
    exp.START = pd.Timestamp('2024-01-01T00:00:00Z')
    exp.END = pd.Timestamp('2026-08-21T00:00:00Z')
    return exp


def load60_symbol(exp, symbol: str) -> pd.DataFrame | None:
    raw, _, _ = exp.load_mid(symbol, 5)
    if raw is None or raw.empty:
        return None
    out, _ = exp.aggregate(raw, 5, 60)
    return None if out is None or out.empty else out[['close']].sort_index()


def load60_instrument(exp, instrument: str) -> pd.DataFrame | None:
    bidc = exp.pick_const(('OFFER_SIDE_BID', 'PRICE_TYPE_BID', 'BID'))
    askc = exp.pick_const(('OFFER_SIDE_ASK', 'PRICE_TYPE_ASK', 'ASK'))
    frames = []
    for a, b in exp.month_chunks(exp.STATE_START, exp.END):
        try:
            bid = exp.fetch_side(instrument, bidc, a, b, 5)
            ask = exp.fetch_side(instrument, askc, a, b, 5)
            idx = bid.index.intersection(ask.index)
            if len(idx):
                frames.append((bid.loc[idx, ['open','high','low','close']] + ask.loc[idx, ['open','high','low','close']]) / 2.0)
        except Exception:
            continue
    if not frames:
        return None
    raw = pd.concat(frames).sort_index()
    raw = raw[~raw.index.duplicated(keep='last')]
    out, _ = exp.aggregate(raw, 5, 60)
    return None if out is None or out.empty else out[['close']].sort_index()


def build_market_context(exp, vix_instrument: str):
    spy = load60_symbol(exp, 'SPY')
    qqq = load60_symbol(exp, 'QQQ')
    vix = load60_instrument(exp, vix_instrument)
    if spy is None or qqq is None or vix is None:
        return None, {'spy': spy is not None, 'qqq': qqq is not None, 'vix': vix is not None}

    idx_sq = spy.index.intersection(qqq.index)
    sq = pd.DataFrame(index=idx_sq)
    sq['spy'] = spy.loc[idx_sq, 'close'].astype(float)
    sq['qqq'] = qqq.loc[idx_sq, 'close'].astype(float)
    sq['spy_ema50'] = sq.spy.ewm(span=50, adjust=False, min_periods=50).mean()
    sq['spy_slope'] = sq.spy_ema50.diff()
    sq['qqq_spy'] = sq.qqq / sq.spy
    sq['qqq_spy_ema50'] = sq.qqq_spy.ewm(span=50, adjust=False, min_periods=50).mean()
    sq['qqq_spy_slope'] = sq.qqq_spy_ema50.diff()

    vx = pd.DataFrame(index=vix.index)
    vx['vix'] = vix['close'].astype(float)
    vx['vix_ema20'] = vx.vix.ewm(span=20, adjust=False, min_periods=20).mean()
    vx['vix_slope'] = vx.vix_ema20.diff()

    ctx = sq.join(vx, how='inner')
    return ctx, {'spy': True, 'qqq': True, 'vix': True, 'rows': int(len(ctx))}


def score_trade(row: dict, market: pd.DataFrame, breadth: pd.DataFrame) -> dict:
    out = dict(row)
    ts = pd.Timestamp(int(row['signal']), unit='ms', tz='UTC')
    bo = ts - pd.Timedelta(minutes=60)
    out['signal_date_ny'] = ts.tz_convert(ZoneInfo('America/New_York')).date().isoformat()
    out['signal_bar_open'] = bo.isoformat()
    out['context_scoreable'] = False
    out['context_score'] = None
    out['rich_context_aligned'] = False

    if bo not in market.index or bo not in breadth.index:
        return out
    m = market.loc[bo]
    b = breadth.loc[bo]
    needed_m = ['spy','spy_ema50','spy_slope','qqq_spy','qqq_spy_ema50','qqq_spy_slope','vix','vix_ema20','vix_slope']
    needed_b = ['breadth','breadth_delta','dispersion','dispersion_ref100']
    if any(pd.isna(m[k]) for k in needed_m) or any(pd.isna(b[k]) for k in needed_b):
        return out

    side = str(row.get('side', '')).upper()
    if side == 'L':
        c_spy = m.spy > m.spy_ema50 and m.spy_slope > 0
        c_qqq = m.qqq_spy > m.qqq_spy_ema50 and m.qqq_spy_slope > 0
        c_vix = m.vix < m.vix_ema20 and m.vix_slope < 0
        c_breadth = b.breadth > 0.55 and b.breadth_delta > 0
    elif side == 'S':
        c_spy = m.spy < m.spy_ema50 and m.spy_slope < 0
        c_qqq = m.qqq_spy < m.qqq_spy_ema50 and m.qqq_spy_slope < 0
        c_vix = m.vix > m.vix_ema20 and m.vix_slope > 0
        c_breadth = b.breadth < 0.45 and b.breadth_delta < 0
    else:
        return out
    c_disp = b.dispersion > b.dispersion_ref100

    comps = {
        'component_spy': bool(c_spy),
        'component_qqq_spy': bool(c_qqq),
        'component_vix': bool(c_vix),
        'component_breadth': bool(c_breadth),
        'component_dispersion': bool(c_disp),
    }
    out.update(comps)
    out['context_score'] = sum(comps.values())
    out['context_scoreable'] = True
    out['rich_context_aligned'] = out['context_score'] >= 4
    out['breadth_fraction'] = float(b.breadth)
    out['dispersion'] = float(b.dispersion)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--input', required=True)
    ap.add_argument('--parent', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--helper-dir', default='/tmp/wrctx')
    args = ap.parse_args()
    root = Path(args.input); outdir = Path(args.out); outdir.mkdir(parents=True, exist_ok=True)

    probe = load_probe(root)
    if not probe or not probe.get('primary_ok'):
        report = {'status': 'INFRASTRUCTURE_BLOCKED', 'reason': 'QQQ or permitted true VIX source unavailable', 'probe': probe, 'PASS_RICH_US_CONTEXT_WR': False}
        (outdir/'report.json').write_text(json.dumps(report, indent=2))
        (outdir/'SUMMARY.md').write_text('# WR Rich US Context — Infrastructure Blocked\n\nQQQ or permitted true VIX source unavailable before PnL evaluation.\n')
        print(json.dumps(report, indent=2)); return

    breadth = load_breadth(root)
    if breadth.empty:
        report = {'status': 'INFRASTRUCTURE_BLOCKED', 'reason': 'no breadth shard data', 'probe': probe, 'PASS_RICH_US_CONTEXT_WR': False}
        (outdir/'report.json').write_text(json.dumps(report, indent=2)); print(json.dumps(report, indent=2)); return

    exp = configure_exp(args.helper_dir)
    market, market_diag = build_market_context(exp, str(probe['vix_instrument']))
    if market is None or market.empty:
        report = {'status': 'INFRASTRUCTURE_BLOCKED', 'reason': 'market context history unavailable', 'probe': probe, 'market_diag': market_diag, 'PASS_RICH_US_CONTEXT_WR': False}
        (outdir/'report.json').write_text(json.dumps(report, indent=2)); print(json.dumps(report, indent=2)); return

    parent = [x for x in load_parent(Path(args.parent)) if year(x) >= 2024]
    scored = [score_trade(x, market, breadth) for x in parent]
    A = [x for x in scored if x['context_scoreable']]
    B = [x for x in A if x['rich_context_aligned']]
    coverage = len(A) / len(parent) if parent else 0.0
    retention = len(B) / len(A) if A else 0.0
    Am, Bm = metric(A), metric(B)
    B_years = {str(y): metric([x for x in B if year(x) == y]) for y in (2024, 2025, 2026)}
    recent_positive = sum(B_years[str(y)]['R'] > 0 for y in (2024, 2025, 2026))
    sb = symbol_breadth(B)
    boot = bootstrap_days(A, B)
    score_dist = dict(sorted(Counter(int(x['context_score']) for x in A).items()))
    component_hits = {}
    for k in ('component_spy','component_qqq_spy','component_vix','component_breadth','component_dispersion'):
        component_hits[k] = sum(bool(x[k]) for x in A) / len(A) if A else None

    gates = {
        'coverage_ge_95pct': coverage >= 0.95,
        'B_n_ge_150': Bm['n'] >= 150,
        'retention_10_70pct': 0.10 <= retention <= 0.70,
        'B_mean_positive': Bm['mean_R'] is not None and Bm['mean_R'] > 0,
        'B_PF_gt_1_05': Bm['PF'] is not None and Bm['PF'] > 1.05,
        'B_mean_ge_A_plus_0_10R': Bm['mean_R'] is not None and Am['mean_R'] is not None and Bm['mean_R'] >= Am['mean_R'] + 0.10,
        'B_total_R_positive': Bm['R'] > 0,
        'positive_years_ge_2': recent_positive >= 2,
        'breadth_ge_50pct': sb['eligible_symbols_ge5'] > 0 and sb['positive_fraction'] >= 0.50,
        'bootstrap_B_lower_gt_0': boot['B_mean_ci95'][0] is not None and boot['B_mean_ci95'][0] > 0,
        'bootstrap_delta_lower_gt_0': boot['delta_ci95'][0] is not None and boot['delta_ci95'][0] > 0,
    }
    status = 'COMPLETE' if gates['coverage_ge_95pct'] else 'INFRASTRUCTURE_BLOCKED'
    passed = status == 'COMPLETE' and all(gates.values())
    report = {
        'status': status,
        'candidate': 'WR v2.5.13 60m + frozen 5-component rich US market context',
        'preregistration_commit': '3192a2f3a151a2d32b5a9cfafaaf0b2bde90517b',
        'parent_run': 32677300335,
        'parent_oos_n': len(parent),
        'scoreable_n': len(A),
        'coverage': coverage,
        'retention': retention,
        'A': Am,
        'B': Bm,
        'mean_delta_R': None if Bm['mean_R'] is None or Am['mean_R'] is None else Bm['mean_R'] - Am['mean_R'],
        'A_long': metric([x for x in A if str(x.get('side','')).upper() == 'L']),
        'A_short': metric([x for x in A if str(x.get('side','')).upper() == 'S']),
        'B_long': metric([x for x in B if str(x.get('side','')).upper() == 'L']),
        'B_short': metric([x for x in B if str(x.get('side','')).upper() == 'S']),
        'B_years': B_years,
        'B_symbol_breadth': sb,
        'score_distribution_A': score_dist,
        'component_hit_rates_A': component_hits,
        'bootstrap': boot,
        'gates': gates,
        'probe': probe,
        'market_diag': market_diag,
        'PASS_RICH_US_CONTEXT_WR': passed,
    }
    (outdir/'report.json').write_text(json.dumps(report, indent=2))
    with (outdir/'scored-trades.jsonl').open('w') as f:
        for x in scored:
            f.write(json.dumps(x, default=str) + '\n')
    lines = [
        '# WR Rich US Market Context — Final', '',
        f'Status: **{status}**',
        f'`PASS_RICH_US_CONTEXT_WR = {str(passed).lower()}`', '',
        f'- coverage: {len(A)}/{len(parent)} = {coverage:.2%}',
        f'- A: {Am}',
        f'- B: {Bm}',
        f'- retention: {retention:.2%}',
        f'- B-A mean delta: {report["mean_delta_R"]}',
        f'- B years: {B_years}',
        f'- bootstrap: {boot}',
        f'- score distribution: {score_dist}',
        f'- component hit rates: {component_hits}', '',
        '## Gates',
    ] + [f'- {k}: {"PASS" if v else "FAIL"}' for k, v in gates.items()]
    (outdir/'SUMMARY.md').write_text('\n'.join(lines) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
