#!/usr/bin/env python3
"""Wave Rider v2.5.13 external parity engine.

The historical reference file remains untouched. This wrapper verifies its frozen
Git blob and applies only semantics proven against canonical Pine / native
TradingView evidence.

Verified repairs as of 2026-08-18:
1. Pine pivot ties: equal extremes on the older/left side are allowed; an equal
   extreme on the newer/right side disqualifies the candidate pivot.
2. Exact stop-entry touches are compared in integer tick space.
3. Pine's raw planned TP is retained for Canon accounting/ambiguity; the native
   executable TP is quantized to the broker tick grid (LONG ceil, SHORT floor),
   and bracket touches are evaluated in tick space.
4. Position sizing matches Pine f_riskQty using syminfo.mincontract and
   syminfo.pointvalue. Verified metadata: BNBUSDT 0.01 / 1; TRXUSDT 1 / 1.
5. Window semantics match canonical Pine: WR_START/WR_END are REPORT ONLY,
   membership is SIGNAL CANDLE time_close, and out-of-window trades continue to
   execute and affect canonical equity/sizing. WR_DATA_START/WR_DATA_END define
   the execution dataset and default to the report dates for backward-compatible
   single-window runs.
6. Binance kline close timestamps are normalized from close-1ms to Pine
   time_close by adding 1ms. Strategy Tester trade exit timestamps are emitted at
   the execution bar timestamp, matching native List of Trades rows.

Current verified 5m golden block through 2026-08-16:
- BNBUSDT: 14/14 entry/exit execution fields, quantity 14/14, +10.92R.
- TRXUSDT: 14/14 entry/exit execution fields, quantity 14/14, +12.40R.

Embedded-news behavior and unknown-symbol contract metadata remain outside the
current BNB/TRX 2026 golden block and must be verified before broader historical
research is re-enabled.
"""
from __future__ import annotations

import hashlib
import math
import os
import sys
import types
from datetime import datetime, timedelta, timezone
from pathlib import Path

FROZEN = Path(__file__).with_name("reference_verify.py")
EXPECTED_GIT_BLOB = "2ba5f66d33e2e483a4c669c95f3b97778c80fcd0"
MODULE_NAME = "wave_rider_frozen_reference_parity"

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

if src.count(PIVOT_OLD) != 1:
    raise RuntimeError(f"pivot patch anchor count={src.count(PIVOT_OLD)}")
patched = src.replace(PIVOT_OLD, PIVOT_NEW, 1)

# Native broker-emulator bracket helper. Plan.t remains the raw Pine target;
# only the executable limit is quantized to the symbol tick grid.
a = patched.index("def next_bracket(")
b = patched.index("\ndef run(", a)
BRACKET_NEW = '''def next_bracket(plan,x,start_at=None,tick=None):\n    if tick is None or tick<=0: raise ValueError("tick required")\n    qi=lambda v: round(v/tick)\n    raw_ti=plan.t/tick\n    nearest_ti=round(raw_ti)\n    if math.isclose(raw_ti,nearest_ti,rel_tol=0.0,abs_tol=1e-7):\n        target_i=nearest_ti\n    else:\n        target_i=math.ceil(raw_ti) if plan.d==1 else math.floor(raw_ti)\n    tx=target_i*tick\n    def tcross(a,z,p): return min(qi(a),qi(z))<=qi(p)<=max(qi(a),qi(z))\n    pts=path(x); active=start_at is None; cur=pts[0]\n    if active:\n        if plan.d==1 and qi(x.o)<=qi(plan.s): return 'SL',x.o\n        if plan.d==1 and qi(x.o)>=qi(tx): return 'TP',x.o\n        if plan.d==-1 and qi(x.o)>=qi(plan.s): return 'SL',x.o\n        if plan.d==-1 and qi(x.o)<=qi(tx): return 'TP',x.o\n    for z in pts[1:]:\n        pos=cur\n        while True:\n            if not active:\n                enter=(plan.d==1 and qi(pos)<qi(plan.e)<=qi(z)) or (plan.d==-1 and qi(pos)>qi(plan.e)>=qi(z))\n                if not enter: break\n                pos=plan.e; active=True; continue\n            cand=[]\n            if tcross(pos,z,plan.s) and qi(plan.s)!=qi(pos): cand.append((abs(qi(plan.s)-qi(pos)),'SL',plan.s))\n            if tcross(pos,z,tx) and qi(tx)!=qi(pos): cand.append((abs(qi(tx)-qi(pos)),'TP',tx))\n            if not cand: break\n            _,r,p=min(cand); return r,p\n        cur=z\n    return None,None\n'''
patched = patched[:a] + BRACKET_NEW + patched[b:]

ref = types.ModuleType(MODULE_NAME)
ref.__file__ = str(FROZEN)
ref.__package__ = None
sys.modules[MODULE_NAME] = ref
exec(compile(patched, str(FROZEN), "exec"), ref.__dict__)


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


def _day_start_ms(s: str) -> int:
    return int(datetime.fromisoformat(s).replace(tzinfo=timezone.utc).timestamp()*1000)


def _day_end_exclusive_ms(s: str) -> int:
    return int((datetime.fromisoformat(s).replace(tzinfo=timezone.utc)+timedelta(days=1)).timestamp()*1000)


_step,_pv,_verified = _resolve_contract_meta(ref.SYMBOL)
ref._WR_PARITY_QTY_STEP = _step
ref._WR_PARITY_POINTVALUE = _pv
ref._WR_PARITY_CONTRACT_META_VERIFIED = _verified

# Separate the execution dataset from the report window. The original fetcher is
# reused, but temporarily receives DATA dates so its warmup + Binance retrieval
# behavior stays frozen.
_DATA_START = os.getenv("WR_DATA_START", ref.START)
_DATA_END = os.getenv("WR_DATA_END", ref.END)
_DATA_START_MS = _day_start_ms(_DATA_START)
_DATA_END_EXCL_MS = _day_end_exclusive_ms(_DATA_END)
_orig_fetch_1m = ref.fetch_1m


def _parity_fetch_1m():
    old_start,old_end=ref.START,ref.END
    ref.START,ref.END=_DATA_START,_DATA_END
    try:
        return _orig_fetch_1m()
    finally:
        ref.START,ref.END=old_start,old_end


ref.fetch_1m = _parity_fetch_1m


def _parity_run(tf,bars,tick,start_ms,end_ms):
    """Execute the full DATA stream, then slice closed Canon trades by signal close."""
    ind,pht,plt=ref.calc_ind(bars)
    chart_ms=tf*60000
    eq=ref.INIT; peak=ref.INIT
    pending=active=None; entry_t=None; trades=[]
    diag=dict(signals=0,pending_expired=0,pending_filled=0,ambiguous=0,tp=0,sl=0,ema=0,session=0,
              pivot_high_ties=pht,pivot_low_ties=plt)

    prod_cur_ls=prod_max_ls=0; prod_maxdd=0.0
    window_eq=None; window_peak=None; window_maxdd=0.0
    window_cur_ls=window_max_ls=0

    def close_trade(i,reason,px):
        nonlocal active,entry_t,eq,peak,prod_maxdd,prod_cur_ls,prod_max_ls
        nonlocal window_eq,window_peak,window_maxdd,window_cur_ls,window_max_ls
        both=(active is not None and bars[i].h>=max(active.s,active.t) and bars[i].l<=min(active.s,active.t)
              and reason in ('TP','SL'))
        if both:
            reason='AMBIG->SL'; diag['ambiguous']+=1
        if reason=='TP':
            cr=ref.TP_R
        elif reason in ('SL','AMBIG->SL'):
            cr=-1.0
        else:
            managed=(px-active.e)*(1 if active.d==1 else -1)*active.qty*_pv
            cr=managed/active.risk
        cash=cr*active.risk
        eq_before=eq
        eq+=cash; peak=max(peak,eq); prod_maxdd=max(prod_maxdd,100*(peak-eq)/peak)
        if cash<0:
            prod_cur_ls+=1; prod_max_ls=max(prod_max_ls,prod_cur_ls)
        else:
            prod_cur_ls=0

        report_eligible=start_ms<=active.sig_t<=end_ms
        if report_eligible:
            if window_eq is None:
                window_eq=eq_before; window_peak=eq_before
            window_eq+=cash; window_peak=max(window_peak,window_eq)
            window_maxdd=max(window_maxdd,100*(window_peak-window_eq)/window_peak if window_peak else 0.0)
            if cash<0:
                window_cur_ls+=1; window_max_ls=max(window_max_ls,window_cur_ls)
            else:
                window_cur_ls=0
            trades.append(ref.Trade(
                tf,'LONG' if active.d==1 else 'SHORT',ref.iso(active.sig_t),ref.iso(entry_t),ref.iso(bars[i].ot),
                active.sig_h,active.sig_l,active.e,active.s,active.t,px,reason,cr,active.risk,active.qty,both
            ))
        active=None; entry_t=None
        return True

    for i,x in enumerate(bars):
        if x.ot>=_DATA_END_EXCL_MS:
            break
        closed=False

        if active is not None:
            why,px=ref.next_bracket(active,x,None,tick)
            if why:
                diag['tp' if why=='TP' else 'sl']+=1
                closed=close_trade(i,why,px)

        if active is None and pending is not None and i==pending.sig_i+1 and not closed:
            fill=(pending.d==1 and round(x.h/tick)>=round(pending.e/tick)) or \
                 (pending.d==-1 and round(x.l/tick)<=round(pending.e/tick))
            if fill:
                active=pending; pending=None; entry_t=x.ot; diag['pending_filled']+=1
                why,px=ref.next_bracket(active,x,active.e,tick)
                if why:
                    diag['tp' if why=='TP' else 'sl']+=1
                    closed=close_trade(i,why,px)

        tc=x.ct+1
        allowed,sexit=ref.session_flags(tc,chart_ms)
        if active is not None and not closed:
            z=ind[i]
            le=active.d==1 and x.c<z['ema'] and not z['ha'] and not z['ema_up']
            se=active.d==-1 and x.c>z['ema'] and not z['hb'] and bool(z['ema_up'])
            if sexit:
                diag['session']+=1; closed=close_trade(i,'SESSION',x.c)
            elif le or se:
                diag['ema']+=1; closed=close_trade(i,'EMA',x.c)

        if pending is not None and i>=pending.sig_i+1 and active is None:
            pending=None; diag['pending_expired']+=1

        if x.ot<_DATA_START_MS:
            continue

        if active is None and pending is None and not closed:
            z=ind[i]
            lr=z['ha'] and x.c>z['ema'] and z['ag'] and z['chop_ok'] and z['res'] is not None
            sr=z['hb'] and x.c<z['ema'] and z['ar'] and z['chop_ok'] and z['sup'] is not None
            nl=allowed and z['sra_ok'] and x.c>x.o and lr and x.c>z['res'] and x.l<=z['res']
            ns=allowed and z['sra_ok'] and x.c<x.o and sr and x.c<z['sup'] and x.h>=z['sup']
            if nl or ns:
                if nl:
                    d=1; ei=round(x.h/tick)+1; si=round(x.l/tick)-1
                    e=ei*tick; s=si*tick; t=e+ref.TP_R*(e-s)
                else:
                    d=-1; ei=round(x.l/tick)-1; si=round(x.h/tick)+1
                    e=ei*tick; s=si*tick; t=e-ref.TP_R*(s-e)
                risk_per_unit=abs(e-s)*_pv
                risk_budget=max(eq,0.0)*ref.RISK_PCT/100.0
                raw_qty=risk_budget/risk_per_unit if risk_per_unit>0 else 0.0
                qty=math.floor(raw_qty/_step)*_step
                risk=abs(e-s)*qty*_pv
                if qty>0 and risk>0:
                    pending=ref.Plan(d,e,s,t,risk,qty,i,tc,x.h,x.l)
                    diag['signals']+=1

    wins=sum(t.canon_r>0 for t in trades); losses=sum(t.canon_r<0 for t in trades); even=len(trades)-wins-losses
    total=sum(t.canon_r for t in trades)
    gp=sum(max(t.canon_r*t.risk_cash,0) for t in trades)
    gl=sum(max(-t.canon_r*t.risk_cash,0) for t in trades)
    exits={k:sum(t.exit_reason==k for t in trades) for k in ('TP','SL','AMBIG->SL','EMA','SESSION')}
    report_bars=sum(start_ms<=x.ct+1<=end_ms for x in bars)
    return trades,dict(
        symbol=ref.SYMBOL,tf=tf,bars=report_bars,trades=len(trades),wins=wins,losses=losses,even=even,
        win_rate=(100*wins/len(trades) if trades else None),total_r=total,avg_r=(total/len(trades) if trades else None),
        profit_factor=(gp/gl if gl else None),max_dd_pct=window_maxdd,max_losing_streak=window_max_ls,
        exit_counts=exits,outcome_invariant=len(trades)==wins+losses+even,exit_invariant=len(trades)==sum(exits.values()),
        diagnostics=diag,production_final_equity=eq,window_final_equity=window_eq,
        data_start=_DATA_START,data_end=_DATA_END,contract_meta_verified=_verified,
        mincontract=_step,pointvalue=_pv
    )


ref.run = _parity_run

if __name__ == "__main__":
    raise SystemExit(ref.main())
