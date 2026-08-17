#!/usr/bin/env python3
from __future__ import annotations
import argparse, csv, importlib.util, io, json, zipfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
EXACT = ROOT / 'wave-rider-verify' / 'reference_verify_v2513_exact.py'
spec = importlib.util.spec_from_file_location('wrexact', EXACT)
assert spec and spec.loader
wr = importlib.util.module_from_spec(spec)
spec.loader.exec_module(wr)
base = wr.base

REPORT_START = date(2025, 1, 1)
REPORT_END_EXCL = date(2026, 8, 15)
ENGINE_START = date(2024, 12, 1)
FETCH_END = date(2026, 8, 17)
TF = 5
S3 = 'https://data.binance.vision/data/futures/um'
UA = 'wr-v2513-parity-pack/1.0'
DEFAULT_SYMBOLS = ['BNBUSDT','TRXUSDT','BATUSDT','ADAUSDT','NEARUSDT','ZECUSDT','SOLUSDT']


def month_iter(a: date, b: date):
    y, m = a.year, a.month
    while (y, m) <= (b.year, b.month):
        yield y, m
        m += 1
        if m == 13:
            y += 1
            m = 1


def parse_zip(content: bytes):
    rows, prices = [], []
    with zipfile.ZipFile(io.BytesIO(content)) as z:
        text = z.read(z.namelist()[0]).decode()
    for row in csv.reader(io.StringIO(text)):
        if not row or not row[0].isdigit():
            continue
        ot, ct = int(row[0]), int(row[6])
        o, h, l, c = map(float, row[1:5])
        rows.append(base.Bar(ot, ct, o, h, l, c))
        prices.extend(row[1:5])
    return rows, prices


def fetch_symbol(symbol: str):
    sess = requests.Session()
    sess.headers['User-Agent'] = UA
    bars, prices, missing = [], [], []

    for y, m in month_iter(ENGINE_START, date(2026, 7, 31)):
        ym = f'{y:04d}-{m:02d}'
        url = f'{S3}/monthly/klines/{symbol}/{TF}m/{symbol}-{TF}m-{ym}.zip'
        r = sess.get(url, timeout=45)
        if r.status_code == 404:
            missing.append(ym)
            continue
        r.raise_for_status()
        rr, pp = parse_zip(r.content)
        bars.extend(rr)
        prices.extend(pp)

    d = date(2026, 8, 1)
    while d <= FETCH_END:
        ds = d.isoformat()
        url = f'{S3}/daily/klines/{symbol}/{TF}m/{symbol}-{TF}m-{ds}.zip'
        r = sess.get(url, timeout=45)
        if r.status_code == 404:
            missing.append(ds)
            d += timedelta(days=1)
            continue
        r.raise_for_status()
        rr, pp = parse_zip(r.content)
        bars.extend(rr)
        prices.extend(pp)
        d += timedelta(days=1)

    ded = {b.ot: b for b in bars}
    bars = [ded[k] for k in sorted(ded)]
    if not bars:
        raise RuntimeError(f'no data for {symbol}')
    return bars, base.infer_tick(prices), missing


def ms(d: date):
    return int(datetime(d.year, d.month, d.day, tzinfo=timezone.utc).timestamp() * 1000)


def run_symbol(symbol: str, outdir: Path):
    bars, tick, missing = fetch_symbol(symbol)
    start_ms = ms(REPORT_START)
    end_ms = ms(REPORT_END_EXCL)
    engine_ms = ms(ENGINE_START)
    trades, summary = wr.run_window_exact(TF, bars, tick, start_ms, end_ms, engine_start_ms=engine_ms)

    payload = {
        'strategy': 'Wave Rider v2.5.13 exact parity reference',
        'symbol': symbol,
        'timeframe': '5m',
        'report_start_utc': REPORT_START.isoformat() + 'T00:00:00Z',
        'report_end_exclusive_utc': REPORT_END_EXCL.isoformat() + 'T00:00:00Z',
        'engine_start_utc': ENGINE_START.isoformat() + 'T00:00:00Z',
        'data_fetch_through': FETCH_END.isoformat(),
        'tick': tick,
        'missing_units': missing,
        'summary': summary,
        'first_5': [
            {'signal_time': t.signal_time, 'entry_time': t.entry_time, 'exit_time': t.exit_time,
             'side': t.side, 'canon_r': t.canon_r, 'exit_reason': t.exit_reason}
            for t in trades[:5]
        ],
        'last_5': [
            {'signal_time': t.signal_time, 'entry_time': t.entry_time, 'exit_time': t.exit_time,
             'side': t.side, 'canon_r': t.canon_r, 'exit_reason': t.exit_reason}
            for t in trades[-5:]
        ],
    }
    outdir.mkdir(parents=True, exist_ok=True)
    (outdir / f'{symbol}.json').write_text(json.dumps(payload, indent=2), encoding='utf-8')

    with (outdir / f'{symbol}_trades.csv').open('w', newline='') as f:
        fields = list(base.Trade.__dataclass_fields__)
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for t in trades:
            w.writerow({k: getattr(t, k) for k in fields})

    print(json.dumps(payload, indent=2))
    return payload


def merge(indir: Path, outfile: Path):
    rows = []
    for p in sorted(indir.glob('*.json')):
        x = json.loads(p.read_text(encoding='utf-8'))
        s = x['summary']
        rows.append({
            'symbol': x['symbol'],
            'tf': x['timeframe'],
            'trades': s['trades'],
            'total_r': s['total_r'],
            'avg_r': s['avg_r'],
            'win_rate': s['win_rate'],
            'pf': s['profit_factor'],
            'max_dd_pct': s['max_dd_pct'],
            'max_losing_streak': s['max_losing_streak'],
            'news_exits': s['diagnostics']['news'],
            'session_exits': s['diagnostics']['session'],
            'ambiguous': s['diagnostics']['ambiguous'],
        })

    outfile.write_text(json.dumps({
        'period': [REPORT_START.isoformat(), REPORT_END_EXCL.isoformat()],
        'end_exclusive': True,
        'rows': rows,
        'manual_verification': {
            'chart': 'BINANCE:<SYMBOL>.P',
            'timeframe': '5m',
            'pine': 'Wave Rider Strategy v2.5.13 WINDOW REPORT',
            'compare': ['WIN TRADES', 'Total R'],
            'commission': 0,
            'slippage': 0,
            'bar_magnifier': False,
        }
    }, indent=2), encoding='utf-8')

    csv_path = outfile.with_suffix('.csv')
    with csv_path.open('w', newline='') as f:
        cols = list(rows[0]) if rows else []
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)
    print(json.dumps(rows, indent=2))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--symbol')
    ap.add_argument('--outdir', default='parity_out')
    ap.add_argument('--merge')
    ap.add_argument('--merged-out', default='wr_v2513_parity_pack.json')
    args = ap.parse_args()

    if args.merge:
        merge(Path(args.merge), Path(args.merged_out))
    else:
        if not args.symbol:
            raise SystemExit('--symbol required')
        run_symbol(args.symbol.upper(), Path(args.outdir))


if __name__ == '__main__':
    main()
