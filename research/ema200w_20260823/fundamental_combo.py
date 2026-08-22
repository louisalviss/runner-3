from __future__ import annotations

import json
import os
import time
from pathlib import Path

import numpy as np
import pandas as pd
import requests

from backtest import load_prices, load_memberships, add_membership_flag, add_indicators_and_outcomes, norm_ticker

OUT = Path(os.environ.get('FUND_OUT', 'artifacts/ema200w_20260823_fundamental'))
OUT.mkdir(parents=True, exist_ok=True)
HORIZONS = (13, 26, 52)
START = pd.Timestamp('2015-01-01')
END = pd.Timestamp('2024-12-31')
UA = 'ema200w-fundamental-research/1.0 contact-via-github-louisalviss-runner-3'
SEC_TICKERS = 'https://www.sec.gov/files/company_tickers.json'
FALLBACK_CIKS = 'https://raw.githubusercontent.com/K0D1Z/sp500-quantitative-dataset/main/data/config/fallback_ciks.json'

FLOW_CONCEPTS = {
    'revenue': ['RevenueFromContractWithCustomerExcludingAssessedTax', 'SalesRevenueNet', 'Revenues'],
    'net_income': ['NetIncomeLoss', 'ProfitLoss'],
    'ocf': ['NetCashProvidedByUsedInOperatingActivities'],
    'capex': ['PaymentsToAcquirePropertyPlantAndEquipment', 'PaymentsForAdditionsToPropertyPlantAndEquipment'],
}
POINT_CONCEPTS = {
    'assets': ['Assets'],
    'liabilities': ['Liabilities'],
    'equity': ['StockholdersEquity', 'StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest'],
    'cash': ['CashAndCashEquivalentsAtCarryingValue', 'CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents'],
}


def get_json(url: str, retries: int = 5, timeout: int = 60):
    headers = {'User-Agent': UA, 'Accept-Encoding': 'gzip, deflate'}
    err = None
    for k in range(retries):
        try:
            r = requests.get(url, headers=headers, timeout=timeout)
            if r.status_code in (429, 403, 502, 503, 504):
                time.sleep(1.0 + k * 1.5)
                continue
            r.raise_for_status()
            return r.json()
        except Exception as exc:
            err = exc
            time.sleep(1.0 + k * 1.5)
    raise RuntimeError(f'failed {url}: {err}')


def build_cik_map(symbols: set[str]) -> dict[str, str]:
    sec = get_json(SEC_TICKERS)
    out: dict[str, str] = {}
    for item in sec.values():
        t = norm_ticker(item.get('ticker', ''))
        if t in symbols:
            out[t] = str(item['cik_str']).zfill(10)
    try:
        fb = get_json(FALLBACK_CIKS)
        for t, v in fb.items():
            nt = norm_ticker(t)
            if nt in symbols and nt not in out:
                cik = v.get('CIK') or v.get('cik')
                if cik:
                    out[nt] = str(cik).zfill(10)
    except Exception as exc:
        (OUT / 'fallback_cik_error.txt').write_text(repr(exc), encoding='utf-8')
    return out


def _facts_for_concepts(companyfacts: dict, concepts: list[str], flow: bool) -> list[dict]:
    us = companyfacts.get('facts', {}).get('us-gaap', {})
    rows = []
    for rank, concept in enumerate(concepts):
        node = us.get(concept)
        if not node:
            continue
        vals = node.get('units', {}).get('USD') or []
        tmp = []
        for x in vals:
            if str(x.get('form', '')) not in ('10-K', '10-K/A'):
                continue
            try:
                end = pd.Timestamp(x['end']); filed = pd.Timestamp(x['filed']); val = float(x['val'])
            except Exception:
                continue
            if not np.isfinite(val):
                continue
            lag = (filed - end).days
            if lag < 0 or lag > 210:
                continue
            if flow:
                if not x.get('start'):
                    continue
                try:
                    start = pd.Timestamp(x['start'])
                except Exception:
                    continue
                dur = (end - start).days
                if dur < 250 or dur > 460:
                    continue
            tmp.append({'end': end, 'filed': filed, 'val': val, 'rank': rank})
        if tmp:
            rows.extend(tmp)
            break
    if not rows:
        return []
    d = pd.DataFrame(rows).sort_values(['end', 'filed', 'rank'])
    d = d.groupby('end', as_index=False).first()
    return d[['end', 'filed', 'val']].to_dict('records')


def company_annual_snapshots(symbol: str, cik: str) -> pd.DataFrame:
    cf = get_json(f'https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json')
    series: dict[str, pd.DataFrame] = {}
    for key, concepts in FLOW_CONCEPTS.items():
        rows = _facts_for_concepts(cf, concepts, True)
        if rows:
            series[key] = pd.DataFrame(rows).rename(columns={'filed': f'{key}_filed', 'val': key})
    for key, concepts in POINT_CONCEPTS.items():
        rows = _facts_for_concepts(cf, concepts, False)
        if rows:
            series[key] = pd.DataFrame(rows).rename(columns={'filed': f'{key}_filed', 'val': key})
    if not series:
        return pd.DataFrame()
    ends = sorted(set().union(*[set(x['end']) for x in series.values()]))
    base = pd.DataFrame({'end': ends})
    for key, x in series.items():
        base = base.merge(x, on='end', how='left')
    filed_cols = [c for c in base.columns if c.endswith('_filed')]
    base['filed'] = base[filed_cols].max(axis=1)
    base['symbol'] = symbol
    base = base.sort_values('end').reset_index(drop=True)
    base['revenue_yoy'] = base['revenue'] / base['revenue'].shift(1) - 1 if 'revenue' in base else np.nan
    base['ocf_yoy'] = base['ocf'] / base['ocf'].shift(1) - 1 if 'ocf' in base else np.nan
    base['fcf'] = base['ocf'] - base['capex'].abs() if 'ocf' in base and 'capex' in base else np.nan
    base['net_margin'] = base['net_income'] / base['revenue'].replace(0, np.nan) if 'revenue' in base and 'net_income' in base else np.nan
    base['liab_assets'] = base['liabilities'] / base['assets'].replace(0, np.nan) if 'assets' in base and 'liabilities' in base else np.nan
    keep = ['symbol','end','filed','revenue','net_income','ocf','capex','fcf','revenue_yoy','ocf_yoy','net_margin','assets','liabilities','equity','cash','liab_assets']
    for c in keep:
        if c not in base:
            base[c] = np.nan
    return base[keep].dropna(subset=['filed']).sort_values('filed')


def attach_fundamentals(w: pd.DataFrame, snaps: pd.DataFrame) -> pd.DataFrame:
    cols = ['revenue','net_income','ocf','capex','fcf','revenue_yoy','ocf_yoy','net_margin','assets','liabilities','equity','cash','liab_assets','fund_end','fund_filed']
    for c in cols:
        if c not in w:
            w[c] = pd.NaT if c.startswith('fund_') else np.nan
    if snaps.empty:
        return w
    for sym, idx in w.groupby('symbol', sort=False, observed=True).groups.items():
        s = snaps[snaps.symbol.eq(sym)].copy()
        if s.empty:
            continue
        s = s.sort_values('filed').rename(columns={'end':'fund_end','filed':'fund_filed'})
        left = w.loc[idx, ['week']].copy().sort_values('week')
        merged = pd.merge_asof(left, s.drop(columns=['symbol']).sort_values('fund_filed'), left_on='week', right_on='fund_filed', direction='backward')
        merged.index = left.index
        for c in cols:
            if c in merged:
                w.loc[merged.index, c] = merged[c].to_numpy()
    return w


def annotate_setup(w: pd.DataFrame) -> pd.DataFrame:
    w['prior52_touch'] = w['touch_ema'].groupby(w['series_id'], observed=True).transform(lambda s: s.shift(1).rolling(52, min_periods=52).max().fillna(True).astype(bool))
    w['no_touch52'] = ~w['prior52_touch']
    w['q_profit'] = w['net_income'].gt(0)
    w['q_cashprofit'] = w['net_income'].gt(0) & w['ocf'].gt(0)
    w['q_fcf'] = w['net_income'].gt(0) & w['fcf'].gt(0)
    w['q_durable'] = w['net_income'].gt(0) & w['fcf'].gt(0) & w['equity'].gt(0) & w['revenue_yoy'].ge(-0.10) & w['ocf_yoy'].ge(-0.25)
    w['dd10_40'] = w['dd52_close'].between(-0.40, -0.10, inclusive='both')
    return w


def event_table(w: pd.DataFrame) -> pd.DataFrame:
    specs = [
        ('NoTouch52', w['touch_ema'] & w['no_touch52'], 'none'),
        ('NoTouch52+Profit', w['touch_ema'] & w['no_touch52'] & w['q_profit'], 'profit'),
        ('NoTouch52+CashProfit', w['touch_ema'] & w['no_touch52'] & w['q_cashprofit'], 'cashprofit'),
        ('NoTouch52+FCF', w['touch_ema'] & w['no_touch52'] & w['q_fcf'], 'fcf'),
        ('NoTouch52+Durable', w['touch_ema'] & w['no_touch52'] & w['q_durable'], 'durable'),
        ('NoTouch52+Durable+Rising+DD10-40', w['touch_ema'] & w['no_touch52'] & w['q_durable'] & w['rising_ema'] & w['dd10_40'], 'durable_tech'),
    ]
    rows = []
    for name, mask, filt in specs:
        idx = w.index[(mask & w['is_member'] & w['week'].between(START, END)).fillna(False)]
        if not len(idx):
            continue
        e = w.loc[idx, ['symbol','series_id','week','close','roll52_high','dd52_close','prev_ema','rising_ema','q_profit','q_cashprofit','q_fcf','q_durable','revenue_yoy','ocf_yoy','net_margin','liab_assets','fund_filed']].copy()
        e['strategy'] = name; e['filter_code'] = filt; e['source_index'] = idx; e['entry'] = e['prev_ema']; e['entrydd'] = e['entry'] / e['roll52_high'] - 1
        for h in HORIZONS:
            e[f'ret{h}'] = w.loc[idx, f'exit_{h}'].to_numpy() / e['entry'].to_numpy() - 1
        rows.append(e)
    return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()


def control_filter(pool: pd.DataFrame, code: str) -> np.ndarray:
    m = pool['no_touch52'].to_numpy(dtype=bool)
    if code == 'profit': m &= pool['q_profit'].to_numpy(dtype=bool)
    elif code == 'cashprofit': m &= pool['q_cashprofit'].to_numpy(dtype=bool)
    elif code == 'fcf': m &= pool['q_fcf'].to_numpy(dtype=bool)
    elif code == 'durable': m &= pool['q_durable'].to_numpy(dtype=bool)
    elif code == 'durable_tech':
        m &= pool['q_durable'].to_numpy(dtype=bool); m &= pool['rising_ema'].fillna(False).to_numpy(dtype=bool); m &= pool['dd10_40'].fillna(False).to_numpy(dtype=bool)
    return m


def add_controls(ev: pd.DataFrame, w: pd.DataFrame) -> pd.DataFrame:
    for h in HORIZONS: w[f'r{h}'] = w[f'exit_{h}'] / w['close'] - 1
    cols = ['symbol','dd52_close','touch_ema','no_touch52','q_profit','q_cashprofit','q_fcf','q_durable','rising_ema','dd10_40'] + [f'r{h}' for h in HORIZONS]
    byw = {d:p[cols] for d,p in w[w['is_member'] & w['ema200'].notna() & w['week'].between(START, END)].groupby('week', sort=False)}
    ctrl = np.full((len(ev), len(HORIZONS)), np.nan); cn = np.zeros((len(ev), len(HORIZONS)), dtype=np.int16)
    for j, r in enumerate(ev.itertuples(index=False)):
        p = byw.get(r.week)
        if p is None or not np.isfinite(r.entrydd): continue
        base = (p['symbol'].to_numpy() != r.symbol) & (~p['touch_ema'].fillna(False).to_numpy(dtype=bool)); base &= control_filter(p, r.filter_code)
        dd = p['dd52_close'].to_numpy(dtype=float); m = base & np.isfinite(dd) & (np.abs(dd-r.entrydd) <= 0.05)
        if m.sum() < 10: m = base & np.isfinite(dd) & (np.abs(dd-r.entrydd) <= 0.10)
        for k,h in enumerate(HORIZONS):
            vals = p[f'r{h}'].to_numpy(dtype=float)[m]; vals = vals[np.isfinite(vals)]
            if len(vals) >= 5: ctrl[j,k] = np.median(vals); cn[j,k] = len(vals)
        if (j+1) % 1000 == 0: print('controls', j+1, '/', len(ev), flush=True)
    for k,h in enumerate(HORIZONS): ev[f'ctrl{h}'] = ctrl[:,k]; ev[f'ctrln{h}'] = cn[:,k]; ev[f'excess{h}'] = ev[f'ret{h}'] - ev[f'ctrl{h}']
    return ev


def summarize(ev: pd.DataFrame):
    rows=[]; rng=np.random.default_rng(20260823)
    for st,x0 in ev.groupby('strategy', sort=False):
        for h in HORIZONS:
            x=x0.dropna(subset=[f'ret{h}']); c=x.dropna(subset=[f'excess{h}']); wm=c.groupby('week')[f'excess{h}'].mean().to_numpy(dtype=float)
            if len(wm)>=10:
                b=np.array([rng.choice(wm,len(wm),replace=True).mean() for _ in range(1200)]); lo,hi=np.quantile(b,[.025,.975])
            else: lo=hi=np.nan
            rows.append({'strategy':st,'horizon':h,'n':len(x),'signal_weeks':x.week.nunique(),'median_return':x[f'ret{h}'].median(),'mean_return':x[f'ret{h}'].mean(),'win_rate':(x[f'ret{h}']>0).mean(),'matched_n':len(c),'mean_excess':c[f'excess{h}'].mean(),'median_excess':c[f'excess{h}'].median(),'beat_matched':(c[f'excess{h}']>0).mean(),'excess_ci_lo':lo,'excess_ci_hi':hi})
    S=pd.DataFrame(rows); eras=[]
    for st,x0 in ev.groupby('strategy', sort=False):
        for label,a,b in [('2015-2019','2015-01-01','2019-12-31'),('2020-2024','2020-01-01','2024-12-31')]:
            for h in (13,52):
                x=x0[x0.week.between(a,b)].dropna(subset=[f'ret{h}']); c=x.dropna(subset=[f'excess{h}'])
                if len(x): eras.append({'strategy':st,'era':label,'horizon':h,'n':len(x),'median_return':x[f'ret{h}'].median(),'win_rate':(x[f'ret{h}']>0).mean(),'mean_excess':c[f'excess{h}'].mean(),'median_excess':c[f'excess{h}'].median(),'beat_matched':(c[f'excess{h}']>0).mean()})
    return S,pd.DataFrame(eras)


def pct(x): return 'NA' if pd.isna(x) else f'{100*x:.2f}%'


def write_report(S: pd.DataFrame, E: pd.DataFrame, meta: dict):
    lines=['# EMA200W + point-in-time fundamental quality backtest','','Generated: 2026-08-23','','## Data / methodology','',
           '- Test window: 2015-01-01 to 2024-12-31; price history starts in 2000 to warm up EMA200W.',
           '- PIT S&P 500 membership; adjusted weekly OHLC; causal entry at prior completed week EMA200W.',
           '- SEC fundamentals are annual 10-K facts and become usable only from original filing date; no report-period look-ahead.',
           f"- SEC CIK coverage: {meta['mapped_symbols']}/{meta['member_symbols']} member symbols; annual snapshot rows: {meta['snapshot_rows']}; weekly PIT fundamental coverage: {meta['fund_coverage']:.1%}.",
           '- Matched control: same week, PIT S&P500 member, no EMA touch in prior 52 weeks, same quality/technical filter, similar 52-week drawdown (±5pp, widened to ±10pp if needed), excluding simultaneous EMA touches.','',
           'Quality definitions: Profit = annual NI>0; CashProfit = NI>0 & OCF>0; FCF = NI>0 & (OCF-|CapEx|)>0; Durable = FCF + positive equity + revenue YoY>=-10% + OCF YoY>=-25%.','',
           '## Main results','','| Strategy | H | N | Median | Win | Mean excess | Median excess | Beat matched | 95% CI mean excess |','|---|---:|---:|---:|---:|---:|---:|---:|---:|']
    for _,r in S.iterrows(): lines.append(f"| {r.strategy} | {int(r.horizon)}w | {int(r.n):,} | {pct(r.median_return)} | {pct(r.win_rate)} | {pct(r.mean_excess)} | {pct(r.median_excess)} | {pct(r.beat_matched)} | [{pct(r.excess_ci_lo)}, {pct(r.excess_ci_hi)}] |")
    lines += ['', '## Era stability (13w and 52w)','','| Strategy | Era | H | N | Median | Win | Mean excess | Median excess | Beat matched |','|---|---|---:|---:|---:|---:|---:|---:|---:|']
    for _,r in E.iterrows(): lines.append(f"| {r.strategy} | {r.era} | {int(r.horizon)}w | {int(r.n):,} | {pct(r.median_return)} | {pct(r.win_rate)} | {pct(r.mean_excess)} | {pct(r.median_excess)} | {pct(r.beat_matched)} |")
    lines += ['', '## Decision rule','', 'Promising only if raw win rate improves AND median matched excess is positive with beat-matched materially above 50% across both eras. Raw win rate alone is not treated as edge.','']
    (OUT/'fundamental_combo_report.md').write_text('\n'.join(lines), encoding='utf-8')


def main():
    t0=time.time(); print('Loading prices...', flush=True)
    w=load_prices(); _,periods=load_memberships(); w=add_membership_flag(w,periods); w=add_indicators_and_outcomes(w)
    test=w[w.week.between(START,END)&w.is_member]; symbols=set(test.symbol.unique()); print('member symbols',len(symbols),flush=True)
    cik_map=build_cik_map(symbols); print('CIK mapped',len(cik_map),flush=True)
    allsnaps=[]; failed=[]
    for i,sym in enumerate(sorted(symbols)):
        cik=cik_map.get(sym)
        if not cik: failed.append((sym,'no_cik')); continue
        try:
            s=company_annual_snapshots(sym,cik)
            if not s.empty: allsnaps.append(s)
            else: failed.append((sym,'no_annual_facts'))
        except Exception as exc: failed.append((sym,repr(exc)[:180]))
        if (i+1)%50==0: print('SEC',i+1,'/',len(symbols),'snap companies',len(allsnaps),flush=True)
        time.sleep(.12)
    snaps=pd.concat(allsnaps,ignore_index=True) if allsnaps else pd.DataFrame(); snaps.to_csv(OUT/'fundamental_snapshots.csv',index=False); pd.DataFrame(failed,columns=['symbol','reason']).to_csv(OUT/'fundamental_failures.csv',index=False)
    print('snapshot rows',len(snaps),'failures',len(failed),flush=True)
    w=attach_fundamentals(w,snaps); w=annotate_setup(w); ev=event_table(w); print('events',ev.groupby('strategy').size().to_dict(),flush=True)
    ev=add_controls(ev,w); S,E=summarize(ev); S.to_csv(OUT/'fundamental_combo_summary.csv',index=False); E.to_csv(OUT/'fundamental_combo_eras.csv',index=False); ev.to_csv(OUT/'fundamental_combo_events.csv',index=False)
    tw=w[w.week.between(START,END)&w.is_member]; meta={'member_symbols':len(symbols),'mapped_symbols':len(cik_map),'snapshot_rows':len(snaps),'fund_coverage':float(tw.fund_filed.notna().mean()),'failed_symbols':len(failed),'elapsed_sec':time.time()-t0}; (OUT/'meta.json').write_text(json.dumps(meta,indent=2),encoding='utf-8'); write_report(S,E,meta)
    print(S.to_string(index=False),flush=True); print('DONE',json.dumps(meta),flush=True)

if __name__=='__main__': main()
