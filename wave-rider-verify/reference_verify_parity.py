#!/usr/bin/env python3
"""Wave Rider external parity engine under incremental TradingView repair.

The historical reference file remains untouched. This loader verifies its frozen
Git blob, applies only semantics proven against canonical Pine / native
TradingView evidence, then executes the patched module in memory.

Verified repairs as of 2026-08-18:
1. Pine pivot ties: equal extremes on the older/left side are allowed; an equal
   extreme on the newer/right side disqualifies the candidate pivot.
2. Pending stop-entry touch: compare market and order prices in integer tick
   space so binary float representation cannot turn an exact touch into a miss.
3. Broker bracket tick semantics: keep Pine's raw planned target for Canon
   accounting/ambiguity tests, but quantize the executable TP to the broker tick
   grid (LONG ceil, SHORT floor) and evaluate bracket touches in tick space.
4. Contract sizing: match Pine f_riskQty with syminfo.mincontract and
   syminfo.pointvalue. Effective TradingView metadata is verified for the current
   golden symbols: BNBUSDT mincontract=0.01, pointvalue=1; TRXUSDT
   mincontract=1, pointvalue=1. Exact raw Strategy Tester quantities match 14/14
   trades for each symbol.

Current 5m golden block through 2026-08-16:
- BNBUSDT: 14/14 entry/exit timestamps and prices; quantity 14/14; +10.92R.
- TRXUSDT: 14/14 entry/exit timestamps and prices; quantity 14/14; +12.40R.

Report-window execution semantics are repaired separately below; unknown symbols
without verified contract metadata retain the historical 1-contract fallback and
must not be called parity-verified until their metadata is checked.
"""
from __future__ import annotations

import hashlib
import math
import os
import sys
import types
from pathlib import Path

FROZEN = Path(__file__).with_name("reference_verify.py")
EXPECTED_GIT_BLOB = "2ba5f66d33e2e483a4c669c95f3b97778c80fcd0"
MODULE_NAME = "wave_rider_frozen_reference_parity"

# Effective TradingView/Pine symbol metadata proven from the canonical sizing
# formula + exact native Strategy Tester rowData.quantity values.
VERIFIED_CONTRACT_META = {
    "BNBUSDT": (0.01, 1.0),
    "TRXUSDT": (1.0, 1.0),
}

raw = FROZEN.read_bytes()
git_blob = hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()
if git_blob != EXPECTED_GIT_BLOB:
    raise RuntimeError(f"frozen reference drift: {git_blob} != {EXPECTED_GIT_BLOB}")

src = raw.decode("utf-8")

PIVOT_OLD = """        if v[c]==ext:\n            if sum(x==ext for x in w)==1: base[conf]=v[c]\n            else: ties+=1\n"""
PIVOT_NEW = """        if v[c]==ext:\n            # TradingView/Pine parity: ties on the older/left side are allowed;\n            # an equal extreme on the newer/right side rejects this candidate.\n            if all(x!=ext for x in v[c+1:c+right+1]): base[conf]=v[c]\n            else: ties+=1\n"""
FILL_OLD = """            fill=(pending.d==1 and x.h>=pending.e) or (pending.d==-1 and x.l<=pending.e)\n"""
FILL_NEW = """            # TradingView/Pine parity: exact tick touches must fill.\n            fill=(pending.d==1 and round(x.h/tick)>=round(pending.e/tick)) or (pending.d==-1 and round(x.l/tick)<=round(pending.e/tick))\n"""
PLAN_OLD = """                if nl: d=1; e=x.h+tick; s=x.l-tick; t=e+TP_R*(e-s)\n                else: d=-1; e=x.l-tick; s=x.h+tick; t=e-TP_R*(s-e)\n                raw=(eq*RISK_PCT/100)/abs(e-s); q=math.floor(raw); risk=abs(e-s)*q\n"""
PLAN_NEW = """                if nl:\n                    d=1; ei=round(x.h/tick)+1; si=round(x.l/tick)-1\n                    e=ei*tick; s=si*tick; t=e+TP_R*(e-s)\n                else:\n                    d=-1; ei=round(x.l/tick)-1; si=round(x.h/tick)+1\n                    e=ei*tick; s=si*tick; t=e-TP_R*(s-e)\n                risk_per_unit=abs(e-s)*_WR_PARITY_POINTVALUE\n                raw=(eq*RISK_PCT/100)/risk_per_unit if risk_per_unit>0 else 0.0\n                q=math.floor(raw/_WR_PARITY_QTY_STEP)*_WR_PARITY_QTY_STEP\n                risk=abs(e-s)*q*_WR_PARITY_POINTVALUE\n"""
EMA_R_OLD = """        cr=TP_R if reason=='TP' else (-1.0 if reason in ('SL','AMBIG->SL') else ((px-active.e)*(1 if active.d==1 else -1)*active.qty/active.risk))\n"""
EMA_R_NEW = """        cr=TP_R if reason=='TP' else (-1.0 if reason in ('SL','AMBIG->SL') else ((px-active.e)*(1 if active.d==1 else -1)*active.qty*_WR_PARITY_POINTVALUE/active.risk))\n"""

for name, old in (("pivot", PIVOT_OLD), ("fill", FILL_OLD), ("plan+sizing", PLAN_OLD), ("managed-R pointvalue", EMA_R_OLD)):
    if src.count(old) != 1:
        raise RuntimeError(f"{name} patch anchor count={src.count(old)}")

patched = (
    src.replace(PIVOT_OLD, PIVOT_NEW, 1)
       .replace(FILL_OLD, FILL_NEW, 1)
       .replace(PLAN_OLD, PLAN_NEW, 1)
       .replace(EMA_R_OLD, EMA_R_NEW, 1)
)

# Replace only the historical broker-emulator bracket helper. Plan.t remains the
# raw Pine target. strategy.exit's effective executable TP is quantized here.
a = patched.index("def next_bracket(")
b = patched.index("\ndef run(", a)
BRACKET_NEW = '''def next_bracket(plan,x,start_at=None,tick=None):\n    if tick is None or tick<=0: raise ValueError("tick required")\n    qi=lambda v: round(v/tick)\n    tx=(math.ceil(plan.t/tick-1e-12)*tick) if plan.d==1 else (math.floor(plan.t/tick+1e-12)*tick)\n    def tcross(a,z,p): return min(qi(a),qi(z))<=qi(p)<=max(qi(a),qi(z))\n    pts=path(x); active=start_at is None; cur=pts[0]\n    if active:\n        if plan.d==1 and qi(x.o)<=qi(plan.s): return 'SL',x.o\n        if plan.d==1 and qi(x.o)>=qi(tx): return 'TP',x.o\n        if plan.d==-1 and qi(x.o)>=qi(plan.s): return 'SL',x.o\n        if plan.d==-1 and qi(x.o)<=qi(tx): return 'TP',x.o\n    for z in pts[1:]:\n        pos=cur\n        while True:\n            if not active:\n                enter=(plan.d==1 and qi(pos)<qi(plan.e)<=qi(z)) or (plan.d==-1 and qi(pos)>qi(plan.e)>=qi(z))\n                if not enter: break\n                pos=plan.e; active=True; continue\n            cand=[]\n            if tcross(pos,z,plan.s) and qi(plan.s)!=qi(pos): cand.append((abs(qi(plan.s)-qi(pos)),'SL',plan.s))\n            if tcross(pos,z,tx) and qi(tx)!=qi(pos): cand.append((abs(qi(tx)-qi(pos)),'TP',tx))\n            if not cand: break\n            _,r,p=min(cand); return r,p\n        cur=z\n    return None,None\n'''
patched = patched[:a] + BRACKET_NEW + patched[b:]
patched = patched.replace("next_bracket(active,x,None)", "next_bracket(active,x,None,tick)")
patched = patched.replace("next_bracket(active,x,active.e)", "next_bracket(active,x,active.e,tick)")

ref = types.ModuleType(MODULE_NAME)
ref.__file__ = str(FROZEN)
ref.__package__ = None
sys.modules[MODULE_NAME] = ref
exec(compile(patched, str(FROZEN), "exec"), ref.__dict__)

# Resolve exact contract metadata only after the frozen module has read WR_SYMBOL.
# Explicit env values allow a future symbol to be tested without editing this file.
def _resolve_contract_meta(symbol: str) -> tuple[float, float, bool]:
    env_step = os.getenv("WR_MINCONTRACT")
    env_pv = os.getenv("WR_POINTVALUE")
    if env_step is not None or env_pv is not None:
        if env_step is None or env_pv is None:
            raise RuntimeError("set WR_MINCONTRACT and WR_POINTVALUE together")
        step=float(env_step); pv=float(env_pv)
        if step<=0 or pv<=0: raise RuntimeError("contract metadata must be > 0")
        return step,pv,True
    if symbol in VERIFIED_CONTRACT_META:
        step,pv=VERIFIED_CONTRACT_META[symbol]
        return step,pv,True
    return 1.0,1.0,False

_step,_pv,_verified = _resolve_contract_meta(ref.SYMBOL)
ref._WR_PARITY_QTY_STEP = _step
ref._WR_PARITY_POINTVALUE = _pv
ref._WR_PARITY_CONTRACT_META_VERIFIED = _verified

if __name__ == "__main__":
    raise SystemExit(ref.main())
