#!/usr/bin/env python3
from __future__ import annotations
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
STATUS = ROOT / "PARITY_STATUS.json"
EXPECTED_EXACT_BLOB = "72c3d36bc41e9efefb085bf010c7f5ba0abc8e30"
EXPECTED_ADAPTER_BLOB = "57b67ff2795d4aab97494f01a6398ffe3118699b"


def main() -> None:
    x = json.loads(STATUS.read_text(encoding="utf-8"))
    if x.get("exact_reference_blob_sha") != EXPECTED_EXACT_BLOB:
        raise SystemExit(
            "WR PARITY BLOCKED: parity status references an unexpected exact-engine blob; "
            "review reference lineage before running downstream research."
        )
    if x.get("tv_parity_adapter_blob_sha") != EXPECTED_ADAPTER_BLOB:
        raise SystemExit(
            "WR PARITY BLOCKED: parity status references an unexpected TradingView parity adapter; "
            "review Pine time_close/input semantics before downstream research."
        )
    if x.get("status") != "PASS":
        raise SystemExit(
            "WR PARITY BLOCKED: TradingView v2.5.13 trade-by-trade parity has not been proven. "
            "Full-universe, family holdout and forward lineage must remain suspended."
        )
    print("WR_PARITY_GATE PASS", EXPECTED_EXACT_BLOB, EXPECTED_ADAPTER_BLOB)


if __name__ == "__main__":
    main()
