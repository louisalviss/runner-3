#!/usr/bin/env bash
set -euo pipefail
cp ops/tradingview/reference_verify_v2515_tmp.py /tmp/reference_verify_v2.5.15.py
export WR_SYMBOL=TRXUSDT WR_TF=5 WR_QTY_STEP=1 WR_STATE_START='2026-07-28T00:00:00+07:00' WR_REPORT_START='2026-08-10T00:00:00+07:00' WR_REPORT_END='2026-08-16T00:00:00+07:00'
mkdir -p /tmp/pyproof
python3 - <<'PY' | tee /tmp/python-summary.txt
import importlib.util,sys,json,math
from datetime import datetime
spec=importlib.util.spec_from_file_location('wrdiag','/tmp/reference_verify_v2.5.15.py'); m=importlib.util.module_from_spec(spec);sys.modules[spec.name]=m;spec.loader.exec_module(m)
one,tick,missing=m.fetch_1m(); bars=m.agg(one,5)
state_ms=int(datetime.fromisoformat(m.STATE_START).timestamp()*1000); bars=[x for x in bars if x.ot>=state_ms]; ind,_,_=m.calc_ind(bars)
start_trace=int(datetime.fromisoformat('2026-08-12T00:00:00+00:00').timestamp()*1000)
end_trace=int(datetime.fromisoformat('2026-08-15T00:00:00+00:00').timestamp()*1000)
target_lo=int(datetime.fromisoformat('2026-08-14T19:00:00+00:00').timestamp()*1000); target_hi=int(datetime.fromisoformat('2026-08-14T19:35:00+00:00').timestamp()*1000)
eq=m.INIT; pending=active=None; entry_t=None; events=[]
def ev(kind,i,**kw):
    x=bars[i]
    rec=dict(kind=kind,ot=m.iso(x.ot),ct=m.iso(x.ct),**kw); events.append(rec)
    if x.ct>=start_trace: print('EVENT',json.dumps(rec,sort_keys=True))
def close(i,reason,px):
    global active,entry_t,eq
    cr=m.TP_R if reason=='TP' else (-1.0 if reason=='SL' else ((px-active.e)*(1 if active.d==1 else -1)*active.qty/active.risk))
    ev('EXIT',i,reason=reason,side='LONG' if active.d==1 else 'SHORT',signal=m.iso(active.sig_t),entry=m.iso(entry_t),px=px,r=cr)
    eq+=cr*active.risk; active=None;entry_t=None
for i,x in enumerate(bars):
    closed=False
    if active is not None:
        r,px=m.next_bracket(active,x,None)
        if r: close(i,r,px);closed=True
    if active is None and pending is not None and i==pending.sig_i+1 and not closed:
        fill=(pending.d==1 and x.h>=pending.e) or (pending.d==-1 and x.l<=pending.e)
        if fill:
            active=pending;pending=None;entry_t=x.ot;ev('FILL',i,side='LONG' if active.d==1 else 'SHORT',signal=m.iso(active.sig_t),entry_px=active.e,stop=active.s,target=active.t)
            r,px=m.next_bracket(active,x,active.e)
            if r: close(i,r,px);closed=True
    allowed,sexit=m.session_flags(x.ct,5*60000)
    if active is not None and not closed:
        z=ind[i]; le=active.d==1 and x.c<z['ema'] and not z['ha'] and not z['ema_up']; se=active.d==-1 and x.c>z['ema'] and not z['hb'] and bool(z['ema_up'])
        if sexit: close(i,'SESSION',x.c);closed=True
        elif le or se: close(i,'EMA',x.c);closed=True
    if pending is not None and i>=pending.sig_i+1 and active is None:
        ev('PENDING_EXPIRE',i,side='LONG' if pending.d==1 else 'SHORT',signal=m.iso(pending.sig_t));pending=None
    z=ind[i]; lr=z['ha'] and x.c>z['ema'] and z['ag'] and z['chop_ok'] and z['res'] is not None; sr=z['hb'] and x.c<z['ema'] and z['ar'] and z['chop_ok'] and z['sup'] is not None
    nl=allowed and z['sra_ok'] and x.c>x.o and lr and x.c>z['res'] and x.l<=z['res']; ns=allowed and z['sra_ok'] and x.c<x.o and sr and x.c<z['sup'] and x.h>=z['sup']
    if target_lo<=x.ct<=target_hi:
        print('TARGETSTATE',json.dumps(dict(ct=m.iso(x.ct),nl=nl,ns=ns,closed=closed,active=None if active is None else dict(side='L' if active.d==1 else 'S',signal=m.iso(active.sig_t),e=active.e,s=active.s,t=active.t),pending=None if pending is None else dict(side='L' if pending.d==1 else 'S',signal=m.iso(pending.sig_t),e=pending.e)),sort_keys=True))
    if active is None and pending is None and not closed and (nl or ns):
        if nl: d=1;e=x.h+tick;s=x.l-tick;t=e+m.TP_R*(e-s)
        else: d=-1;e=x.l-tick;s=x.h+tick;t=e-m.TP_R*(s-e)
        raw=(eq*m.RISK_PCT/100)/abs(e-s);q=math.floor(raw/m.QTY_STEP)*m.QTY_STEP;risk=abs(e-s)*q
        if q>0 and risk>0:
            pending=m.Plan(d,e,s,t,risk,q,i,x.ct,x.h,x.l);ev('SIGNAL',i,side='LONG' if d==1 else 'SHORT',e=e,s=s,t=t)
open('/tmp/pyproof/W2_TRX_state_events.json','w').write(json.dumps(events,indent=2))
PY
