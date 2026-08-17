#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import math
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

REPORT_START=int(os.environ.get('REPORT_START_MS','1785110400000'))
REPORT_END=int(os.environ.get('REPORT_END_MS','1786924800000'))
SYMBOLS=('BNBUSDT','TRXUSDT')


def parse_parts(line:str)->dict[str,str]:
    out={}
    for part in line.strip().split('|')[1:]:
        if '=' in part:
            k,v=part.split('=',1); out[k]=v
    return out


def read_tv(sym:str):
    lines=Path(f'/tmp/tv-accounting-{sym}.txt').read_text().splitlines()
    meta=parse_parts(next(x for x in lines if x.startswith('WRMETA|')))
    rows=[]
    for line in lines:
        if not line.startswith('WRP#'): continue
        d=parse_parts(line); d['native_n']=int(line.split('|',1)[0][4:]); rows.append(d)
    rows.sort(key=lambda x:int(float(x['entryMs'])))
    return meta,rows


def load_parity(sym:str, first_ms:int, last_ms:int):
    os.environ['WR_SYMBOL']=sym
    os.environ['WR_START']=datetime.fromtimestamp(first_ms/1000,tz=timezone.utc).date().isoformat()
    os.environ['WR_END']=datetime.fromtimestamp(last_ms/1000,tz=timezone.utc).date().isoformat()
    name=f'wr_parity_{sym}'
    spec=importlib.util.spec_from_file_location(name,'wave-rider-verify/reference_verify_parity.py')
    mod=importlib.util.module_from_spec(spec); sys.modules[name]=mod; spec.loader.exec_module(mod)
    return mod.ref


def run_external(sym:str, meta:dict[str,str]):
    first=int(float(meta['firstMs'])); last=int(float(meta['lastMs']))
    tick=float(meta['mintick']); minc=float(meta['mincontract']); pv=float(meta['pointvalue'])
    r=load_parity(sym,first,last)
    one,_,missing=r.fetch_1m()
    one=[x for x in one if x.ot>=first and x.ot<last]
    bars=r.agg(one,5)
    ind,_,_=r.calc_ind(bars)

    class Plan:
        __slots__=('d','e','s','t','tx','risk','qty','sig_i','sig_t','sig_h','sig_l')
        def __init__(self,d,e,s,t,tx,risk,qty,sig_i,sig_t,sig_h,sig_l):
            self.d=d; self.e=e; self.s=s; self.t=t; self.tx=tx; self.risk=risk; self.qty=qty
            self.sig_i=sig_i; self.sig_t=sig_t; self.sig_h=sig_h; self.sig_l=sig_l

    def qi(v): return round(v/tick)
    def tcross(a,z,p): return min(qi(a),qi(z))<=qi(p)<=max(qi(a),qi(z))
    def bracket(plan,x,start_at=None):
        pts=r.path(x); active_path=start_at is None; cur=pts[0]
        if active_path:
            if plan.d==1 and qi(x.o)<=qi(plan.s): return 'SL',x.o
            if plan.d==1 and qi(x.o)>=qi(plan.tx): return 'TP',x.o
            if plan.d==-1 and qi(x.o)>=qi(plan.s): return 'SL',x.o
            if plan.d==-1 and qi(x.o)<=qi(plan.tx): return 'TP',x.o
        for z in pts[1:]:
            pos=cur
            while True:
                if not active_path:
                    enter=(plan.d==1 and qi(pos)<qi(plan.e)<=qi(z)) or (plan.d==-1 and qi(pos)>qi(plan.e)>=qi(z))
                    if not enter: break
                    pos=plan.e; active_path=True; continue
                cand=[]
                if tcross(pos,z,plan.s) and qi(plan.s)!=qi(pos): cand.append((abs(qi(plan.s)-qi(pos)),'SL',plan.s))
                if tcross(pos,z,plan.tx) and qi(plan.tx)!=qi(pos): cand.append((abs(qi(plan.tx)-qi(pos)),'TP',plan.tx))
                if not cand: break
                _,why,px=min(cand); return why,px
            cur=z
        return None,None

    eq=r.INIT; peak=r.INIT; pending=None; active=None; entry_ms=None
    report_rows=[]; all_rows=[]; canon_trades=0

    def close_trade(i,why,px):
        nonlocal eq,peak,active,entry_ms,canon_trades
        x=bars[i]
        both=why in ('TP','SL') and x.h>=max(active.s,active.t) and x.l<=min(active.s,active.t)
        if both:
            canon_r=-1.0; exit_class='AMBIG→SL'
        elif why=='TP':
            canon_r=r.TP_R; exit_class='TP'
        elif why=='SL':
            canon_r=-1.0; exit_class='SL'
        else:
            canon_r=(px-active.e)*(1 if active.d==1 else -1)*active.qty*pv/active.risk
            exit_class=why
        eq_before=eq
        eq += canon_r*active.risk
        peak=max(peak,eq); canon_trades+=1
        row=dict(
            entryMs=entry_ms, exitMs=x.ot, qty=active.qty, risk=active.risk,
            planE=active.e, planS=active.s, planT=active.t, actualX=px,
            canonR=canon_r, exit=exit_class, report=REPORT_START<=active.sig_t<REPORT_END,
            eqBefore=eq_before, both=both, signalMs=active.sig_t,
        )
        all_rows.append(row)
        if row['report']: report_rows.append(row)
        active=None; entry_ms=None
        return True

    for i,x in enumerate(bars):
        if x.ot<first or x.ct>last: continue
        closed=False
        if active is not None:
            why,px=bracket(active,x,None)
            if why: closed=close_trade(i,why,px)
        if active is None and pending is not None and i==pending.sig_i+1 and not closed:
            fill=(pending.d==1 and qi(x.h)>=qi(pending.e)) or (pending.d==-1 and qi(x.l)<=qi(pending.e))
            if fill:
                active=pending; pending=None; entry_ms=x.ot
                why,px=bracket(active,x,active.e)
                if why: closed=close_trade(i,why,px)
        allowed,session_exit=r.session_flags(x.ct,5*60000)
        if active is not None and not closed:
            z=ind[i]
            long_ema=active.d==1 and x.c<z['ema'] and not z['ha'] and not z['ema_up']
            short_ema=active.d==-1 and x.c>z['ema'] and not z['hb'] and bool(z['ema_up'])
            if session_exit: closed=close_trade(i,'SESSION',x.c)
            elif long_ema or short_ema: closed=close_trade(i,'EMA',x.c)
        if pending is not None and i>=pending.sig_i+1 and active is None:
            pending=None
        if active is None and pending is None and not closed:
            z=ind[i]
            lr=z['ha'] and x.c>z['ema'] and z['ag'] and z['chop_ok'] and z['res'] is not None
            sr=z['hb'] and x.c<z['ema'] and z['ar'] and z['chop_ok'] and z['sup'] is not None
            nl=allowed and z['sra_ok'] and x.c>x.o and lr and x.c>z['res'] and x.l<=z['res']
            ns=allowed and z['sra_ok'] and x.c<x.o and sr and x.c<z['sup'] and x.h>=z['sup']
            if nl or ns:
                if nl:
                    d=1; e=x.h+tick; s=x.l-tick; raw_t=e+r.TP_R*(e-s)
                    exec_t=math.ceil(raw_t/tick-1e-12)*tick
                else:
                    d=-1; e=x.l-tick; s=x.h+tick; raw_t=e-r.TP_R*(s-e)
                    exec_t=math.floor(raw_t/tick+1e-12)*tick
                risk_budget=max(eq,0.0)*r.RISK_PCT/100.0
                risk_per_unit=abs(e-s)*pv
                raw_qty=risk_budget/risk_per_unit if risk_per_unit>0 else 0.0
                qty=math.floor(raw_qty/minc)*minc if minc>0 else math.floor(raw_qty)
                risk=abs(e-s)*qty*pv
                if qty>0 and risk>0:
                    pending=Plan(d,e,s,raw_t,exec_t,risk,qty,i,x.ct,x.h,x.l)

    return dict(first=first,last=last,missing=missing,report_rows=report_rows,all_rows=all_rows,
                finalEq=eq,canonTrades=canon_trades,tick=tick,mincontract=minc,pointvalue=pv)


def f(v):
    try:return float(v)
    except:return None

def i(v):
    try:return int(float(v))
    except:return None

def nearly(a,b,abs_tol=1e-8,rel_tol=1e-9):
    if a is None or b is None:return False
    return abs(a-b)<=max(abs_tol,rel_tol*max(1.0,abs(a),abs(b)))


def compare_symbol(sym:str):
    meta,tv=read_tv(sym)
    ext=run_external(sym,meta)
    py=ext['report_rows']
    diffs=[]
    if len(tv)!=len(py): diffs.append(dict(field='count',tv=len(tv),py=len(py)))
    for n,(t,e) in enumerate(zip(tv,py),1):
        fields=(
            ('entryMs',i(t.get('entryMs')),e['entryMs'],0),
            ('exitMs',i(t.get('exitMs')),e['exitMs'],0),
            ('qty',f(t.get('qty')),e['qty'],1e-6),
            ('risk',f(t.get('risk')),e['risk'],1e-5),
            ('planE',f(t.get('planE')),e['planE'],1e-10),
            ('planS',f(t.get('planS')),e['planS'],1e-10),
            ('planT',f(t.get('planT')),e['planT'],1e-10),
            ('canonR',f(t.get('canonR')),e['canonR'],1e-7),
            ('eqBefore',f(t.get('eqBefore')),e['eqBefore'],1e-4),
        )
        for name,a,b,tol in fields:
            ok=(a==b) if tol==0 else nearly(a,b,tol)
            if not ok:
                diffs.append(dict(trade=n,field=name,tv=a,py=b)); break
        if diffs and diffs[-1].get('trade')==n: break
        if t.get('exit')!=e['exit']:
            diffs.append(dict(trade=n,field='exit',tv=t.get('exit'),py=e['exit'])); break
        if (t.get('both')=='1')!=bool(e['both']):
            diffs.append(dict(trade=n,field='both',tv=t.get('both'),py=e['both'])); break

    tv_total=sum(f(x.get('canonR')) or 0 for x in tv)
    py_total=sum(x['canonR'] for x in py)
    tv_window_r=f(meta.get('windowR')); tv_window_n=i(meta.get('windowTrades'))
    summary=dict(
        tv_meta=meta,
        tv_report_trades=len(tv), py_report_trades=len(py),
        tv_total_r_from_rows=tv_total, py_total_r=py_total,
        tv_window_r=tv_window_r, tv_window_trades=tv_window_n,
        external_final_eq=ext['finalEq'], external_canon_trades=ext['canonTrades'],
        first_divergence=diffs[0] if diffs else None,
    )
    summary['exact_rows']=not diffs and nearly(tv_total,py_total,1e-7)
    summary['exact_window_aggregate']=(tv_window_n==len(py) and nearly(tv_window_r,py_total,1e-7))
    summary['exact']=summary['exact_rows'] and summary['exact_window_aggregate']
    return summary


def main():
    out={}; failed=False
    for sym in SYMBOLS:
        res=compare_symbol(sym); out[sym]=res
        print(sym); print(json.dumps(res,indent=2,ensure_ascii=False))
        failed |= not res['exact']
    Path('/tmp/accounting-parity-result.json').write_text(json.dumps(out,indent=2,ensure_ascii=False)+'\n')
    return 9 if failed else 0

if __name__=='__main__':
    raise SystemExit(main())
