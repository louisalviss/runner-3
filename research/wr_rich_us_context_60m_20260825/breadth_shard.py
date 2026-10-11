#!/usr/bin/env python3
from __future__ import annotations

import csv
import json
import math
import os
import sys
from collections import defaultdict
from pathlib import Path

import pandas as pd

sys.path.insert(0, os.environ.get('WR_CTX_HELPER_DIR', '/tmp/wrctx'))
import exp

# Only primary OOS 2024+ is evaluated. This warmup is frozen before results.
exp.STATE_START = pd.Timestamp('2023-10-01T00:00:00Z')
exp.START = pd.Timestamp('2024-01-01T00:00:00Z')
exp.END = pd.Timestamp('2026-08-21T00:00:00Z')

OUT = Path(os.environ.get('WR_CTX_OUT', '/tmp/wr-rich-context'))
OUT.mkdir(parents=True, exist_ok=True)

UNIVERSE = "AAPL ADBE ADI ADP ADSK AEP ALNY AMAT AMD AMGN AMZN AVGO BKR CDNS CMCSA COST CPRT CSCO CSGP CSX CTSH DXCM EA EXC FANG FTNT GILD GOOG GOOGL HON IDXX INTC INTU ISRG KHC LRCX MAR MCHP MDLZ META MPWR MRVL MSFT MU NFLX NVDA ODFL ORLY PANW PAYX PCAR PEP PLTR PYPL QCOM REGN ROST SBUX SNPS TMUS TSLA TTWO TXN VRTX WDAY WDC WMT ZS".split()


def load60(symbol: str):
    raw, manifest, instrument = exp.load_mid(symbol, 5)
    if raw is None or raw.empty:
        return None, manifest, instrument
    frame, rejected = exp.aggregate(raw, 5, 60)
    if frame is None or frame.empty:
        return None, manifest, instrument
    frame = frame[['close']].copy().sort_index()
    return frame, manifest, instrument


def main():
    shard = int(os.environ.get('SHARD', '0'))
    shards = int(os.environ.get('SHARDS', '8'))
    mine = [s for i, s in enumerate(UNIVERSE) if i % shards == shard]

    # ts_ms -> [ema_valid_count, above_count, ret_count, ret_sum, ret_sumsq]
    agg = defaultdict(lambda: [0, 0, 0, 0.0, 0.0])
    diag = []

    for symbol in mine:
        frame, manifest, instrument = load60(symbol)
        if frame is None:
            diag.append({'symbol': symbol, 'ok': False, 'instrument': instrument, 'reason': 'no_60m_midpoint'})
            print('UNAVAILABLE', symbol, instrument, flush=True)
            continue

        close = frame['close'].astype(float)
        ema50 = close.ewm(span=50, adjust=False, min_periods=50).mean()
        ret = close.pct_change()
        valid_ema = close.notna() & ema50.notna()
        valid_ret = ret.notna()

        for ts in frame.index:
            ms = int(ts.timestamp() * 1000)
            a = agg[ms]
            if bool(valid_ema.loc[ts]):
                a[0] += 1
                if float(close.loc[ts]) > float(ema50.loc[ts]):
                    a[1] += 1
            if bool(valid_ret.loc[ts]):
                r = float(ret.loc[ts])
                if math.isfinite(r):
                    a[2] += 1
                    a[3] += r
                    a[4] += r * r

        diag.append({
            'symbol': symbol,
            'ok': True,
            'instrument': instrument,
            'bars60': int(len(frame)),
            'first': frame.index.min().isoformat(),
            'last': frame.index.max().isoformat(),
            'months': len(manifest),
        })
        print('DONE', symbol, len(frame), flush=True)

    out_csv = OUT / f'breadth-shard-{shard}.csv'
    with out_csv.open('w', newline='') as f:
        w = csv.writer(f)
        w.writerow(['timestamp_ms', 'ema_valid_count', 'above_count', 'ret_count', 'ret_sum', 'ret_sumsq'])
        for ms in sorted(agg):
            w.writerow([ms, *agg[ms]])
    (OUT / f'diagnostics-shard-{shard}.json').write_text(json.dumps(diag, indent=2))
    print('SHARD_DONE', shard, 'symbols', len(mine), 'timestamps', len(agg), flush=True)


if __name__ == '__main__':
    main()
