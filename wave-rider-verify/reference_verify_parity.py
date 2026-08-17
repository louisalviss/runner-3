#!/usr/bin/env python3
"""Wave Rider external parity engine under incremental TradingView repair.

The historical reference file remains untouched. This loader verifies its frozen
Git blob, applies only semantics proven by isolated probes, then executes the
patched module in memory.

Verified repairs as of 2026-08-17:
1. Pine pivot ties: equal extremes on the older/left side are allowed; an equal
   extreme on the newer/right side disqualifies the candidate pivot.
2. Pending stop-entry touch: compare market and order prices in integer tick
   space so binary float representation cannot turn an exact touch into a miss.
3. Broker bracket tick semantics: build entry/stop in tick indices, round TP in
   the profit direction (LONG ceil, SHORT floor), and evaluate bracket path
   touches in tick space.

Current 5m native-field regression through 2026-08-16:
- BNBUSDT: 14/14 entry timestamps/prices and exit bar timestamps/prices
- TRXUSDT: 14/14 entry timestamps/prices and exit bar timestamps/prices

This is NOT a declaration of full trade-ledger parity. Exact size/PnL, Canon R,
report-window, news and remaining lifecycle/accounting semantics still require
separate regression.
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
FILL_NEW = """            # TradingView/Pine parity: exact tick touches must fill.\n            fill=(pending.d==1 and round(x.h/tick)>=round(pending.e/tick)) or (pending.d==-1 and round(x.l/tick)<=round(pending.e/tick))\n"""
PLAN_OLD = """                if nl: d=1; e=x.h+tick; s=x.l-tick; t=e+TP_R*(e-s)\n                else: d=-1; e=x.l-tick; s=x.h+tick; t=e-TP_R*(s-e)\n"""
PLAN_NEW = """                if nl:\n                    d=1\n                    ei=round(x.h/tick)+1; si=round(x.l/tick)-1\n                    ti=math.ceil(ei+TP_R*(ei-si)-1e-12)\n                    e=ei*tick; s=si*tick; t=ti*tick\n                else:\n                    d=-1\n                    ei=round(x.l/tick)-1; si=round(x.h/tick)+1\n                    ti=math.floor(ei-TP_R*(si-ei)+1e-12)\n                    e=ei*tick; s=si*tick; t=ti*tick\n"""

for name, old in (("pivot", PIVOT_OLD), ("fill", FILL_OLD), ("plan", PLAN_OLD)):
    if src.count(old) != 1:
        raise RuntimeError(f"{name} patch anchor count={src.count(old)}")

patched = src.replace(PIVOT_OLD, PIVOT_NEW, 1).replace(FILL_OLD, FILL_NEW, 1).replace(PLAN_OLD, PLAN_NEW, 1)

# Replace only the historical broker-emulator bracket helper. The rest of the
# frozen lifecycle/accounting code remains byte-for-byte inherited.
a = patched.index("def next_bracket(")
b = patched.index("\ndef run(", a)
BRACKET_NEW = '''def next_bracket(plan,x,start_at=None,tick=None):\n    if tick is None or tick<=0: raise ValueError("tick required")\n    qi=lambda v: round(v/tick)\n    def tcross(a,z,p): return min(qi(a),qi(z))<=qi(p)<=max(qi(a),qi(z))\n    pts=path(x); active=start_at is None; cur=pts[0]\n    if active:\n        if plan.d==1 and qi(x.o)<=qi(plan.s): return 'SL',x.o\n        if plan.d==1 and qi(x.o)>=qi(plan.t): return 'TP',x.o\n        if plan.d==-1 and qi(x.o)>=qi(plan.s): return 'SL',x.o\n        if plan.d==-1 and qi(x.o)<=qi(plan.t): return 'TP',x.o\n    for z in pts[1:]:\n        pos=cur\n        while True:\n            if not active:\n                enter=(plan.d==1 and qi(pos)<qi(plan.e)<=qi(z)) or (plan.d==-1 and qi(pos)>qi(plan.e)>=qi(z))\n                if not enter: break\n                pos=plan.e; active=True; continue\n            cand=[]\n            if tcross(pos,z,plan.s) and qi(plan.s)!=qi(pos): cand.append((abs(qi(plan.s)-qi(pos)),'SL',plan.s))\n            if tcross(pos,z,plan.t) and qi(plan.t)!=qi(pos): cand.append((abs(qi(plan.t)-qi(pos)),'TP',plan.t))\n            if not cand: break\n            _,r,p=min(cand); return r,p\n        cur=z\n    return None,None\n'''
patched = patched[:a] + BRACKET_NEW + patched[b:]
patched = patched.replace("next_bracket(active,x,None)", "next_bracket(active,x,None,tick)")
patched = patched.replace("next_bracket(active,x,active.e)", "next_bracket(active,x,active.e,tick)")

ref = types.ModuleType(MODULE_NAME)
ref.__file__ = str(FROZEN)
ref.__package__ = None
sys.modules[MODULE_NAME] = ref
exec(compile(patched, str(FROZEN), "exec"), ref.__dict__)

if __name__ == "__main__":
    raise SystemExit(ref.main())
