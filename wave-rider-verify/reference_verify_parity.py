#!/usr/bin/env python3
"""Wave Rider external parity engine under incremental TradingView repair.

The historical reference file remains untouched. This loader verifies its frozen
Git blob, applies only semantics proven by one-change probes, then executes the
patched module in memory.

Verified repairs as of 2026-08-17:
1. Pine pivot ties: equal extremes on the older/left side are allowed; an equal
   extreme on the newer/right side disqualifies the candidate pivot.
2. Pending stop-entry touch: compare market and order prices in integer tick
   space so binary float representation cannot turn an exact touch into a miss.

Current 5m entry-timestamp regression through 2026-08-16:
- BNBUSDT: 14/14 TradingView entries
- TRXUSDT: 14/14 TradingView entries

This is NOT a declaration of full trade-ledger parity. Price, size, exit fill,
report-window, news and other lifecycle semantics remain subject to regression.
"""
from __future__ import annotations

import hashlib
import sys
import types
from pathlib import Path

FROZEN = Path(__file__).with_name("reference_verify.py")
EXPECTED_GIT_BLOB = "2ba5f66d33e2e483a4c669c95f3b97778c80fcd0"
MODULE_NAME = "wave_rider_frozen_reference_parity"

raw = FROZEN.read_bytes()
git_blob = hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()
if git_blob != EXPECTED_GIT_BLOB:
    raise RuntimeError(f"frozen reference drift: {git_blob} != {EXPECTED_GIT_BLOB}")

src = raw.decode("utf-8")

PIVOT_OLD = """        if v[c]==ext:\n            if sum(x==ext for x in w)==1: base[conf]=v[c]\n            else: ties+=1\n"""
PIVOT_NEW = """        if v[c]==ext:\n            # TradingView/Pine parity: ties on the older/left side are allowed;\n            # an equal extreme on the newer/right side rejects this candidate.\n            if all(x!=ext for x in v[c+1:c+right+1]): base[conf]=v[c]\n            else: ties+=1\n"""
FILL_OLD = """            fill=(pending.d==1 and x.h>=pending.e) or (pending.d==-1 and x.l<=pending.e)\n"""
FILL_NEW = """            # TradingView/Pine parity: exact tick touches must fill.\n            # Compare integer tick indices, not binary floating-point decimals.\n            fill=(pending.d==1 and round(x.h/tick)>=round(pending.e/tick)) or (pending.d==-1 and round(x.l/tick)<=round(pending.e/tick))\n"""

if src.count(PIVOT_OLD) != 1:
    raise RuntimeError(f"pivot patch anchor count={src.count(PIVOT_OLD)}")
if src.count(FILL_OLD) != 1:
    raise RuntimeError(f"fill patch anchor count={src.count(FILL_OLD)}")
patched = src.replace(PIVOT_OLD, PIVOT_NEW, 1).replace(FILL_OLD, FILL_NEW, 1)

ref = types.ModuleType(MODULE_NAME)
ref.__file__ = str(FROZEN)
ref.__package__ = None
sys.modules[MODULE_NAME] = ref
exec(compile(patched, str(FROZEN), "exec"), ref.__dict__)

if __name__ == "__main__":
    raise SystemExit(ref.main())
