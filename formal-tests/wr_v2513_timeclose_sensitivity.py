#!/usr/bin/env python3
from __future__ import annotations
import argparse, importlib.util, json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACK = ROOT / 'formal-tests' / 'wr_v2513_parity_pack.py'
spec = importlib.util.spec_from_file_location('pack', PACK)
assert spec and spec.loader
p = importlib.util.module_from_spec(spec)
spec.loader.exec_module(p)
wr = p.wr
base = p.base


def run(symbol: str):
    bars, tick, missing = p.fetch_symbol(symbol)
    raw, rs = wr.run_window_exact(
        p.TF, bars, tick, p.ms(p.REPORT_START), p.ms(p.REPORT_END_EXCL), engine_start_ms=p.ms(p.ENGINE_START)
    )
    normbars = [base.Bar(b.ot, b.ot + p.TF * 60_000, b.o, b.h, b.l, b.c) for b in bars]
    norm, ns = wr.run_window_exact(
        p.TF, normbars, tick, p.ms(p.REPORT_START), p.ms(p.REPORT_END_EXCL), engine_start_ms=p.ms(p.ENGINE_START)
    )

    # Compare economic trade sequence after accounting for the expected +1ms close-label shift.
    # Entry time is bar open and should not shift. Signal/exit close timestamps may shift +1ms.
    def sig(t):
        return (t.side, t.entry_time, t.entry, t.stop, t.target, t.exit_price, t.exit_reason, round(float(t.canon_r), 12))

    first = None
    for i in range(min(len(raw), len(norm))):
        if sig(raw[i]) != sig(norm[i]):
            first = {
                'index_zero_based': i,
                'trade_number_one_based': i+1,
                'raw': raw[i].__dict__,
                'pine_close_normalized': norm[i].__dict__,
            }
            break
    if first is None and len(raw) != len(norm):
        i = min(len(raw), len(norm))
        first = {
            'index_zero_based': i,
            'trade_number_one_based': i+1,
            'raw': raw[i].__dict__ if i < len(raw) else None,
            'pine_close_normalized': norm[i].__dict__ if i < len(norm) else None,
        }

    time_shift_examples = []
    for a,b in zip(raw[:3], norm[:3]):
        time_shift_examples.append({
            'raw_signal': a.signal_time, 'norm_signal': b.signal_time,
            'raw_entry': a.entry_time, 'norm_entry': b.entry_time,
            'raw_exit': a.exit_time, 'norm_exit': b.exit_time,
        })

    return {
        'symbol': symbol,
        'tf': p.TF,
        'test': 'Binance raw close timestamp vs Pine-style time_close=open+timeframe',
        'missing_units': missing,
        'raw_summary': rs,
        'normalized_summary': ns,
        'trade_count_delta': ns['trades'] - rs['trades'],
        'total_r_delta': ns['total_r'] - rs['total_r'],
        'economic_sequence_equal': first is None,
        'first_economic_divergence': first,
        'time_shift_examples': time_shift_examples,
        'interpretation': 'If economic_sequence_equal=true and only signal/exit close labels shift +1ms, patching exported/Pine-close timestamps is low risk. If false, time_close is a real strategy/report-boundary semantic and must be resolved against TradingView before parity PASS.'
    }


def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--symbol', required=True); ap.add_argument('--out', required=True); a=ap.parse_args()
    x=run(a.symbol.upper())
    Path(a.out).write_text(json.dumps(x, indent=2), encoding='utf-8')
    print(json.dumps(x, indent=2))

if __name__=='__main__': main()
