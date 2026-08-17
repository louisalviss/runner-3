#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACK_PATH = ROOT / 'formal-tests' / 'wr_v2513_parity_pack.py'
ADAPTER_PATH = ROOT / 'wave-rider-verify' / 'reference_v2513_tv_adapter.py'


def load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def blob_sha(path: Path) -> str:
    raw = path.read_bytes()
    return hashlib.sha1(f'blob {len(raw)}\0'.encode() + raw).hexdigest()


pack = load(PACK_PATH, 'wr_pack')
adapter = load(ADAPTER_PATH, 'wr_tv_adapter')
pack.wr.run_window_exact = adapter.run_window_exact
ADAPTER_BLOB = blob_sha(ADAPTER_PATH)


def annotate_json(path: Path):
    x = json.loads(path.read_text(encoding='utf-8'))
    x['tv_parity_adapter_path'] = str(ADAPTER_PATH.relative_to(ROOT))
    x['tv_parity_adapter_blob_sha'] = ADAPTER_BLOB
    x['time_close_semantics'] = 'Pine time_close = bar open + timeframe; Binance archive interval_end-1ms normalized before strategy/report/session/news logic'
    path.write_text(json.dumps(x, indent=2), encoding='utf-8')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--symbol')
    ap.add_argument('--outdir', default='parity_out')
    ap.add_argument('--merge')
    ap.add_argument('--merged-out', default='wr_v2513_tv_exact_parity_investigation.json')
    args = ap.parse_args()

    if args.merge:
        out = Path(args.merged_out)
        pack.merge(Path(args.merge), out)
        annotate_json(out)
    else:
        if not args.symbol:
            raise SystemExit('--symbol required')
        outdir = Path(args.outdir)
        pack.run_symbol(args.symbol.upper(), outdir)
        annotate_json(outdir / f'{args.symbol.upper()}.json')


if __name__ == '__main__':
    main()
