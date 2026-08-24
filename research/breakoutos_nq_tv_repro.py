#!/usr/bin/env python3
import csv, json, os
from pathlib import Path
from breakoutos_nq_repro import Bar, parse_ts, evaluate, compact

src = Path(os.getenv('TV_CSV', '/tmp/nq_tv.csv'))
out = Path(os.getenv('OUT', 'evidence/breakoutos-nq-repro'))
out.mkdir(parents=True, exist_ok=True)
bars = []
with src.open(newline='') as f:
    for row in csv.DictReader(f):
        try:
            bars.append(Bar(parse_ts(row['time']), float(row['open']), float(row['high']), float(row['low']), float(row['close'])))
        except Exception:
            pass
bars.sort(key=lambda b: b.ts)
meta = {
    'source': 'TradingView export from Wendigooor/nq_analyze',
    'instrument': 'CME_MINI:NQ1! continuous futures',
    'rows': len(bars),
    'first': bars[0].dt.isoformat(),
    'last': bars[-1].dt.isoformat(),
    'source_commit': '152cfcfebf2340dbe663775ad264b229fdd741b0'
}
r = evaluate('NQ_TRADINGVIEW_60M_2021_2025', bars, meta, 20.0, True)
(out / 'tradingview-summary.json').write_text(json.dumps(r, indent=2, default=str))
(out / 'tradingview-compact.json').write_text(json.dumps(compact(r), indent=2))
print('TV_RESULT', json.dumps(compact(r), separators=(',', ':')))
