#!/usr/bin/env python3
"""Wave Rider external parity engine.

This wrapper intentionally preserves wave-rider-verify/reference_verify.py as the
frozen historical evidence blob and overrides exactly one proven semantic:
TradingView/Pine pivot tie handling.

Verified against native TradingView v2.5.13 5m ledgers on 2026-08-17:
- BNBUSDT: 14/14 entry timestamps through 2026-08-16
- TRXUSDT: 13/14 entry timestamps through 2026-08-16

Do not add unrelated fixes here without a one-semantic parity probe first.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

FROZEN = Path(__file__).with_name("reference_verify.py")
SPEC = importlib.util.spec_from_file_location("wave_rider_frozen_reference", FROZEN)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(f"cannot load frozen reference: {FROZEN}")
ref = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ref)


def pine_pivots(v, left, right, high=True):
    """Match Pine ta.pivothigh/ta.pivotlow(...)[1] tie semantics.

    Equal extremes on the older/left side are allowed. An equal extreme on the
    newer/right side disqualifies the candidate pivot. Output is shifted one bar
    because canonical Pine uses ta.pivothigh/low(...)[1].
    """
    base = [None] * len(v)
    ties = 0
    for conf in range(left + right, len(v)):
        c = conf - right
        w = v[c - left : c + right + 1]
        ext = max(w) if high else min(w)
        if v[c] == ext:
            if all(x != ext for x in v[c + 1 : c + right + 1]):
                base[conf] = v[c]
            else:
                ties += 1
    return [None] + base[:-1], ties


ref.pivots = pine_pivots

if __name__ == "__main__":
    raise SystemExit(ref.main())
