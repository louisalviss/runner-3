#!/usr/bin/env python3
from __future__ import annotations
import hashlib, importlib.util, json, math
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SELECTOR_PATH = ROOT / 'frozen_family_20260817.json'
AUDIT_PATH = ROOT / 'full_universe_audit.py'
OUT = Path('family_holdout_out')
OUT.mkdir(parents=True, exist_ok=True)
BASE_START = date(2025, 1, 1)
HOLDOUT_START = datetime(2026, 8, 15, tzinfo=timezone.utc)


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def dt(s: str) -> datetime:
    x = datetime.fromisoformat(s.replace('Z', '+00:00'))
    return x if x.tzinfo else x.replace(tzinfo=timezone.utc)


def fsum(xs):
    return sum(xs) if xs else 0.0


def main():
    selector_bytes = SELECTOR_PATH.read_bytes()
    selector = json.loads(selector_bytes)
    selector_sha256 = hashlib.sha256(selector_bytes).hexdigest()
    audit = load_module(AUDIT_PATH, 'wr_audit')

    assert selector['status'] == 'FROZEN_RESEARCH_FAMILY_FOR_UNTOUCHED_HOLDOUT'
    assert selector['holdout_start_utc'] == '2026-08-15T00:00:00Z'
    assert selector['reference_engine_blob_sha'] == audit.REFERENCE_BLOB_SHA
    assert selector['selected_count'] == len(selector['symbols']) == 14

    # data.binance.vision daily archives are complete-day files; stop at yesterday UTC.
    end_date = datetime.now(timezone.utc).date() - timedelta(days=1)
    if end_date < HOLDOUT_START.date():
        raise RuntimeError('No completed holdout day available yet')

    # Reuse the exact frozen audit data loader and pinned v2.5.13 reference engine.
    audit.START = BASE_START
    audit.END = end_date
    audit.WARMUP_DAYS = 3
    wr = audit.load_reference()

    base_sm = int(datetime.combine(BASE_START, datetime.min.time(), tzinfo=timezone.utc).timestamp() * 1000)
    en = int((datetime.combine(end_date + timedelta(days=1), datetime.min.time(), tzinfo=timezone.utc) - timedelta(milliseconds=1)).timestamp() * 1000)

    all_trades = []
    per_symbol = []
    errors = []

    for i, symbol in enumerate(selector['symbols'], 1):
        try:
            bars5, prices, src = audit.fetch_native(wr, symbol, '5m')
            if not bars5:
                raise RuntimeError('no 5m bars')
            bars10 = audit.agg_10m_from_5m(wr, bars5)
            tick = wr.infer_tick(prices)
            wr.SYMBOL = symbol
            trades, _base = wr.run(10, bars10, tick, base_sm, en)

            kept = []
            for t in trades:
                if dt(t.exit_time) < HOLDOUT_START:
                    continue
                sp = abs(t.entry - t.stop) / abs(t.entry) * 100.0 if t.entry else 0.0
                if sp <= 0:
                    continue
                row = {
                    'symbol': symbol,
                    'tf': 10,
                    'signal_time': t.signal_time,
                    'entry_time': t.entry_time,
                    'exit_time': t.exit_time,
                    'gross_r': float(t.canon_r),
                    'entry': float(t.entry),
                    'stop': float(t.stop),
                    'target': float(t.target),
                    'exit_reason': t.exit_reason,
                    'stop_pct': sp,
                }
                for bps in (4, 6, 8):
                    row[f'net_{bps}bps_r'] = float(t.canon_r) - (bps / 100.0) / sp
                kept.append(row)
                all_trades.append(row)

            per_symbol.append({
                'symbol': symbol,
                'closed_trades': len(kept),
                'gross_r': fsum([x['gross_r'] for x in kept]),
                'net_4bps_r': fsum([x['net_4bps_r'] for x in kept]),
                'net_6bps_r': fsum([x['net_6bps_r'] for x in kept]),
                'net_8bps_r': fsum([x['net_8bps_r'] for x in kept]),
                'source_files': src,
                'bars_10m': len(bars10),
                'last_bar_close': wr.iso(bars10[-1].ct),
            })
            print(f'[{i}/14] {symbol}: holdout closed={len(kept)} last={wr.iso(bars10[-1].ct)}', flush=True)
        except Exception as e:
            errors.append({'symbol': symbol, 'error': repr(e)})
            print(f'[{i}/14] {symbol}: ERROR {e}', flush=True)

    all_trades.sort(key=lambda x: (x['exit_time'], x['symbol'], x['entry_time']))
    gross = [x['gross_r'] for x in all_trades]
    net4 = [x['net_4bps_r'] for x in all_trades]
    net6 = [x['net_6bps_r'] for x in all_trades]
    net8 = [x['net_8bps_r'] for x in all_trades]

    result = {
        'schema': 1,
        'status': 'UNTOUCHED_HOLDOUT_SNAPSHOT',
        'generated_at_utc': datetime.now(timezone.utc).isoformat(),
        'data_through_utc_date': end_date.isoformat(),
        'holdout_start_utc': selector['holdout_start_utc'],
        'selector_sha256': selector_sha256,
        'reference_engine_blob_sha': audit.REFERENCE_BLOB_SHA,
        'symbols': selector['symbols'],
        'timeframe_minutes': 10,
        'friction_bps_are_total_round_trip': True,
        'closed_trades': len(all_trades),
        'gross_total_r': fsum(gross),
        'gross_avg_r': fsum(gross) / len(gross) if gross else None,
        'net_4bps_total_r': fsum(net4),
        'net_4bps_avg_r': fsum(net4) / len(net4) if net4 else None,
        'net_6bps_total_r': fsum(net6),
        'net_6bps_avg_r': fsum(net6) / len(net6) if net6 else None,
        'net_8bps_total_r': fsum(net8),
        'net_8bps_avg_r': fsum(net8) / len(net8) if net8 else None,
        'per_symbol': per_symbol,
        'errors': errors,
        'trades': all_trades,
        'evaluation_warning': 'Do not retune selector from this holdout. Small early samples are descriptive only.'
    }
    (OUT / 'snapshot.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    (OUT / 'trades.jsonl').write_text(''.join(json.dumps(x, separators=(',', ':')) + '\n' for x in all_trades), encoding='utf-8')
    print(json.dumps({k: result[k] for k in ['closed_trades','gross_avg_r','net_6bps_avg_r','data_through_utc_date','errors']}, indent=2), flush=True)


if __name__ == '__main__':
    main()
