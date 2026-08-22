#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import requests

PINNED_RESEARCH_COMMIT = "2f1f1df817297d6011cfe83354a2e6c4076c29e7"
PINNED_REFERENCE_COMMIT = "8192984ad6a3e5f99b49020c79b5758ef2ac44a7"
HOLDOUT_START = pd.Timestamp("2026-08-22T00:00:00Z")
HOLDOUT_END_EXCLUSIVE = pd.Timestamp("2027-01-01T00:00:00Z")
WARMUP_START = pd.Timestamp("2026-05-01T00:00:00Z")
FILES = [
    "wr_tv_parity.py",
    "wr_dukascopy_expanded_matrix.py",
    "wr_market_state_oos.py",
]


def download(url: str, dest: Path) -> str:
    r = requests.get(url, timeout=60, headers={"User-Agent": "wr-market-state-forward/1.0"})
    r.raise_for_status()
    dest.write_bytes(r.content)
    return hashlib.sha256(r.content).hexdigest()


def next_utc_midnight() -> pd.Timestamp:
    now = datetime.now(timezone.utc)
    d = datetime(now.year, now.month, now.day, tzinfo=timezone.utc) + timedelta(days=1)
    return pd.Timestamp(d)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbol", required=True)
    ap.add_argument("--output", required=True)
    args = ap.parse_args()
    symbol = args.symbol.upper()
    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)
    os.environ["WR_OUT"] = str(out)

    effective_end = min(next_utc_midnight(), HOLDOUT_END_EXCLUSIVE)
    if effective_end <= HOLDOUT_START:
        raise RuntimeError("holdout has not started")

    with tempfile.TemporaryDirectory(prefix="wr-forward-pinned-") as td:
        tdir = Path(td)
        hashes = {}
        for name in FILES:
            url = f"https://raw.githubusercontent.com/louisalviss/runner-3/{PINNED_RESEARCH_COMMIT}/wave-rider-verify/{name}"
            hashes[name] = download(url, tdir / name)
        ref_url = f"https://raw.githubusercontent.com/louisalviss/runner-3/{PINNED_REFERENCE_COMMIT}/wave-rider-verify/reference_verify.py"
        hashes["reference_verify.py"] = download(ref_url, Path("/tmp/reference_verify.py"))

        sys.path.insert(0, str(tdir))
        import wr_dukascopy_expanded_matrix as exp
        import wr_market_state_oos as oos

        # Only runtime data boundaries change. Strategy code and market-state feature code are pinned above.
        exp.STATE_START = WARMUP_START
        exp.START = HOLDOUT_START
        exp.END = effective_end
        oos.run_symbol(symbol)

    feature_files = sorted(out.glob(f"features-{symbol}-*m.jsonl"))
    feature_rows = 0
    for p in feature_files:
        feature_rows += sum(1 for ln in p.read_text(encoding="utf-8").splitlines() if ln.strip())

    meta = {
        "schema_version": 1,
        "status": "OK",
        "symbol": symbol,
        "generated_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "holdout_start_utc": HOLDOUT_START.isoformat(),
        "collection_end_exclusive_utc": effective_end.isoformat(),
        "warmup_start_utc": WARMUP_START.isoformat(),
        "pinned_research_commit": PINNED_RESEARCH_COMMIT,
        "pinned_reference_commit": PINNED_REFERENCE_COMMIT,
        "source_sha256": hashes,
        "feature_rows": feature_rows,
        "feature_files": [p.name for p in feature_files],
    }
    (out / f"collector-meta-{symbol}.json").write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"symbol": symbol, "feature_rows": feature_rows, "end": effective_end.isoformat()}))


if __name__ == "__main__":
    main()
