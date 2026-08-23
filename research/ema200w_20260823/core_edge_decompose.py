from __future__ import annotations

import json
import time
from pathlib import Path

import numpy as np
import pandas as pd

from backtest import load_prices, load_memberships, add_membership_flag
from fundamental_combo import build_cik_map, company_annual_snapshots, attach_fundamentals

OUT = Path('artifacts/core_edge_decompose')
OUT.mkdir(parents=True, exist_ok=True)
HORIZONS = (13, 26, 52)
DISC_START = pd.Timestamp('2010-01-01')
DISC_END = pd.Timestamp('2016-12-31')
VAL_START = pd.Timestamp('2017-01-01')
VAL_END = pd.Timestamp('2024-12-31')


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
        # Signal at completed week t; enter next week's open; exit at close t+h.
        exit_px = g['close'].shift(-h)
        w[f'ret{h}'] = exit_px / w['next_open'] - 1.0
    return w


def add_quality_flags(w: pd.DataFrame) -> pd.DataFrame:
    w['q_profit'] = w['net_income'].gt(0)
    w['q_fcf'] = w['net_income'].gt(0) & w['fcf'].gt(0)
    return w


def load_fundamentals(w: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    relevant = w[w['is_member'] & w['week'].between(DISC_START, VAL_END)]
    symbols = set(relevant['symbol'].dropna().astype(str).unique())
    cik_map = build_cik_map(symbols)
    allsnaps = []
    failed = []
    for i, sym in enumerate(sorted(symbols)):
        cik = cik_map.get(sym)
        if not cik:
            failed.append((sym, 'no_cik'))
            continue
        try:
            s = company_annual_snapshots(sym, cik)
            if not s.empty:
                allsnaps.append(s)
            else:
                failed.append((sym, 'no_annual_facts'))
        except Exception as exc:
            failed.append((sym, repr(exc)[:180]))
        if (i + 1) % 50 == 0:
            print('SEC', i + 1, '/', len(symbols), 'snap companies', len(allsnaps), flush=True)
        time.sleep(0.10)
    snaps = pd.concat(allsnaps, ignore_index=True) if allsnaps else pd.DataFrame()
    if not snaps.empty:
        snaps.to_csv(OUT / 'fundamental_snapshots.csv', index=False)
    pd.DataFrame(failed, columns=['symbol','reason']).to_csv(OUT / 'fundamental_failures.csv', index=False)
    w = attach_fundamentals(w, snaps)
    meta = {
        'member_symbols': len(symbols),
        'cik_mapped': len(cik_map),
        'snapshot_rows': len(snaps),
        'failed_symbols': len(failed),
    }
    return w, meta


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
    if not rows:
        return pd.DataFrame()
    return pd.concat(rows, ignore_index=True).sort_values(['strategy','week','symbol']).reset_index(drop=True)


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


def write_report(summary: pd.DataFrame, meta: dict):
    lines = [
        '# Non-EMA core-edge decomposition', '',
        'Pre-specified rules (frozen before results):',
        '- Entry trigger: previous weekly DD52 > -10%, current weekly DD52 between -20% and -10%.',
        '- Execution: signal after completed week; enter next week adjusted open.',
        '- Long-term trend: current close > close 104 weeks ago (104-week return > 0).',
        '- Profit quality: latest PIT SEC annual 10-K net income > 0.',
        '- FCF quality: latest PIT SEC annual 10-K net income > 0 and OCF - |CapEx| > 0.',
        '- Matched control: same week, PIT S&P500, same DD10-20 state, same strategy filters, NOT a fresh dip trigger; DD matched ±2.5pp then ±5pp.',
        '- Discovery: 2010-2016. Validation: 2017-2024.', '',
        f"Fundamental coverage metadata: {json.dumps(meta, ensure_ascii=False)}", '',
        '| Slice | Strategy | H | N | Win | Median ret | Median excess | Beat matched | Mean excess 95% CI |',
        '|---|---|---:|---:|---:|---:|---:|---:|---:|'
    ]
    for _,r in summary.iterrows():
        lines.append(f"| {r['slice']} | {r.strategy} | {int(r.horizon)}w | {int(r.n):,} | {pct(r.win_rate)} | {pct(r.median_return)} | {pct(r.median_excess)} | {pct(r.beat_matched)} | [{pct(r.ci_lo)}, {pct(r.ci_hi)}] |")
    # Mechanical decision: no cherry-picking. Focus 13w because prior EMA work's useful horizon was 13w.
    v = summary[(summary['slice']=='validation_2017_2024') & (summary['horizon']==13)].copy()
    v['pass'] = (v['median_excess'] > 0) & (v['beat_matched'] >= 0.55) & (v['win_rate'] >= 0.60)
    passing = v[v['pass']]
    lines += ['', '## Mechanical decision (13w validation)', '']
    if passing.empty:
        lines += ['No pre-specified non-EMA rule passes all validation gates: median matched excess > 0, beat matched >=55%, win >=60%. Do not proceed to 2025-2026 as a production candidate.']
    else:
        # Prefer simplest passing rule by predefined complexity order.
        order = ['Dip10_20','Dip10_20+Trend104','Dip10_20+Trend104+Profit','Dip10_20+Trend104+FCF']
        passing['ord'] = passing['strategy'].map({x:i for i,x in enumerate(order)})
        pick = passing.sort_values('ord').iloc[0]
        lines += [f"Frozen candidate for later OOS: `{pick.strategy}`. It is the simplest pre-specified rule passing the validation gates."]
    (OUT/'REPORT.md').write_text('\n'.join(lines), encoding='utf-8')


def main():
    t0 = time.time()
    print('loading price...', flush=True)
    w = load_prices()
    _, periods = load_memberships()
    w = add_membership_flag(w, periods)
    w = add_price_features(w)
    print('loading PIT fundamentals...', flush=True)
    w, meta = load_fundamentals(w)
    w = add_quality_flags(w)
    ev = make_events(w)
    print('events', ev.groupby('strategy').size().to_dict(), flush=True)
    ev = add_controls(ev, w)
    rows = []
    rows += summarize_slice(ev, 'discovery_2010_2016', '2010-01-01', '2016-12-31')
    rows += summarize_slice(ev, 'validation_2017_2024', '2017-01-01', '2024-12-31')
    S = pd.DataFrame(rows)
    S.to_csv(OUT/'summary.csv', index=False)
    ev.to_csv(OUT/'events.csv', index=False)
    meta['elapsed_sec'] = time.time()-t0
    (OUT/'meta.json').write_text(json.dumps(meta, indent=2), encoding='utf-8')
    write_report(S, meta)
    print(S.to_string(index=False), flush=True)
    print('DONE', json.dumps(meta), flush=True)

if __name__ == '__main__':
    main()
