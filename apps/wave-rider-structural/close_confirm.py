#!/usr/bin/env python3
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo
import math

@dataclass
class Position:
    d:int; e:float; s:float; t:float; risk:float; qty:float
    sig_i:int; sig_t:int; sig_h:float; sig_l:float; report:bool
    trigger:float|None=None; confirm_t:int|None=None; entry_t:int|None=None


def _trade_sig(rows):
    return [(int(x['signal']), int(x['exit']), x['side'], round(float(x['R']),10), x['reason'], round(float(x['e']),10), round(float(x['s']),10), round(float(x['t']),10)) for x in rows]


def assert_canonical_parity(base, ref, bars, info, history_start, report_start, report_end, anchor='start', use_session=True):
    old_start, old_end = base.START, base.END
    base.START, base.END = report_start, report_end
    try:
        want,_ = base.run_case(ref,bars,info,history_start,anchor=anchor,use_session=use_session)
        got,_ = run_case(base,ref,bars,info,history_start,report_start,report_end,variant='canonical',anchor=anchor,use_session=use_session)
    finally:
        base.START, base.END = old_start, old_end
    if _trade_sig(want) != _trade_sig(got):
        raise AssertionError(f'canonical parity mismatch want={len(want)} got={len(got)}')
    return len(want)


def run_case(base, ref, bars, info, history_start, report_start, report_end, *, variant='canonical', anchor='start', use_session=True, eligible_signal=None, disable_news=False):
    if variant not in ('canonical','close_confirmed'):
        raise ValueError(variant)
    bars=[b for b in bars if b.ot>=int(history_start.timestamp()*1000)]
    if len(bars)<100:return [],{'error':'too_few_bars'}
    ind,_,_=ref.calc_ind(bars); tick=base.tv_tick(info,[x.c for x in bars]); sc=base.SessionClock(info,anchor)
    start_ms=int(report_start.timestamp()*1000); end_ms=int(report_end.timestamp()*1000)
    eq=100000.; pending=None; active=None; trades=[]
    exit_counts={k:0 for k in ('TP','SL','EMA','SESSION','AMBIG->SL','NEWS')}
    counters={'signals':0,'eligible_signals':0,'confirm_pass':0,'confirm_fail':0,'entry_session_skip':0,'entry_news_skip':0,'entry_invalid_stop':0}
    ny=ZoneInfo('America/New_York')
    news=[datetime(2025,11,20,8,30,tzinfo=ny),datetime(2025,12,10,14,0,tzinfo=ny),datetime(2025,12,16,8,30,tzinfo=ny),datetime(2025,12,18,8,30,tzinfo=ny)]
    news=[int(x.timestamp()*1000) for x in news]
    def news_locked(t): return False if disable_news else any(e-15*60000 <= t < e+15*60000 for e in news)
    def news_exit(tc): return False if disable_news else any((tc<e-15*60000 and tc+base.TF_MS>=e-15*60000) or (tc>=e-15*60000 and tc<e) for e in news)
    def sess_flags(b):
        if not use_session:return True,False
        market,rdc=sc.state(b)
        if not market or rdc is None:return False,False
        tc=b.ct; ne=rdc-40*60000; ex=rdc-15*60000
        noentry=tc<=rdc and (tc>=ne or tc+base.TF_MS>=ne)
        lastbar=tc>=rdc or tc+base.TF_MS>rdc
        sexit=(tc<ex and tc+base.TF_MS>=ex) or (tc>=ex and tc<=rdc) or lastbar
        return not noentry,sexit
    def entry_open_allowed(b):
        if not use_session:return True
        market,rdc=sc.state(b)
        if not market or rdc is None:return False
        return b.ot < rdc-40*60000
    def close(i,reason,px):
        nonlocal active,eq
        p=active; b=bars[i]
        both=(reason in ('TP','SL') and b.h>=max(p.s,p.t) and b.l<=min(p.s,p.t))
        if both:reason='AMBIG->SL'
        cr=2.3 if reason=='TP' else (-1.0 if reason in ('SL','AMBIG->SL') else ((px-p.e)*(1 if p.d==1 else -1)/abs(p.e-p.s) if abs(p.e-p.s)>0 else 0.0))
        eq += cr*p.risk
        if p.report:
            trades.append({'signal':p.sig_t,'exit':b.ct,'side':'L' if p.d==1 else 'S','R':cr,'reason':reason,'e':p.e,'s':p.s,'t':p.t,
                           'trigger':p.trigger,'confirm':p.confirm_t,'entry_time':p.entry_t,'variant':variant})
        exit_counts[reason]=exit_counts.get(reason,0)+1; active=None

    for i,b in enumerate(bars):
        closed=False
        if active is not None:
            r,px=ref.next_bracket(active,b,None)
            if r:close(i,r,px);closed=True

        if active is None and pending is not None and not closed:
            if variant=='canonical':
                if i==pending.sig_i+1:
                    fill=(pending.d==1 and round(b.h/tick)>=round(pending.e/tick)) or (pending.d==-1 and round(b.l/tick)<=round(pending.e/tick))
                    if fill:
                        active=pending; pending=None; active.entry_t=b.ot
                        gap=(active.d==1 and round(b.o/tick)>=round(active.e/tick)) or (active.d==-1 and round(b.o/tick)<=round(active.e/tick))
                        r,px=ref.next_bracket(active,b,None if gap else active.e)
                        if r:close(i,r,px);closed=True
            else:
                if pending.get('stage')=='confirm' and i==pending['sig_i']+1:
                    passed=(pending['d']==1 and b.c>pending['trigger']) or (pending['d']==-1 and b.c<pending['trigger'])
                    if passed:
                        counters['confirm_pass']+=1
                        pending['stage']='entry'; pending['entry_i']=i+1; pending['confirm_t']=b.ct
                    else:
                        counters['confirm_fail']+=1; pending=None
                elif pending.get('stage')=='entry' and i==pending['entry_i']:
                    entry_allowed=entry_open_allowed(b)
                    if not entry_allowed:
                        counters['entry_session_skip']+=1; pending=None
                    elif news_locked(b.ot):
                        counters['entry_news_skip']+=1; pending=None
                    else:
                        e=float(b.o); s=float(pending['s']); d=int(pending['d'])
                        dist=(e-s) if d==1 else (s-e)
                        if dist<=0:
                            counters['entry_invalid_stop']+=1; pending=None
                        else:
                            t=e+2.3*dist if d==1 else e-2.3*dist
                            q=math.floor((max(eq,0)*0.01)/dist); risk=dist*q
                            if q>0 and risk>0:
                                active=Position(d,e,s,t,risk,q,pending['sig_i'],pending['sig_t'],pending['sig_h'],pending['sig_l'],pending['report'],pending['trigger'],pending['confirm_t'],b.ot)
                            pending=None
                            if active is not None:
                                r,px=ref.next_bracket(active,b,None)
                                if r:close(i,r,px);closed=True

        allowed,sexit=sess_flags(b)
        if active is not None and not closed:
            z=ind[i]; le=active.d==1 and b.c<z['ema'] and not z['ha'] and not z['ema_up']; se=active.d==-1 and b.c>z['ema'] and not z['hb'] and bool(z['ema_up'])
            if sexit:close(i,'SESSION',b.c);closed=True
            elif news_exit(b.ct):close(i,'NEWS',b.c);closed=True
            elif le or se:close(i,'EMA',b.c);closed=True

        if pending is not None and active is None:
            if variant=='canonical' and i>=pending.sig_i+1: pending=None
            elif variant=='close_confirmed':
                if pending.get('stage')=='confirm' and i>pending['sig_i']+1: pending=None
                elif pending.get('stage')=='entry' and i>pending.get('entry_i',10**18): pending=None

        if active is None and pending is None and not closed:
            z=ind[i]; lr=z['ha'] and b.c>z['ema'] and z['ag'] and z['chop_ok'] and z['res'] is not None; sr=z['hb'] and b.c<z['ema'] and z['ar'] and z['chop_ok'] and z['sup'] is not None
            safe=not news_locked(b.ct) and not news_locked(b.ct+base.TF_MS)
            nl=allowed and safe and z['sra_ok'] and b.c>b.o and lr and b.c>z['res'] and b.l<=z['res']
            ns=allowed and safe and z['sra_ok'] and b.c<b.o and sr and b.c<z['sup'] and b.h>=z['sup']
            if nl or ns:
                counters['signals']+=1
                if eligible_signal is not None and not bool(eligible_signal(int(b.ct))):
                    continue
                counters['eligible_signals']+=1
                if nl:d=1;trigger=b.h+tick;s=b.l-tick
                else:d=-1;trigger=b.l-tick;s=b.h+tick
                report=start_ms<=b.ct<end_ms
                if variant=='canonical':
                    e=trigger;dist=abs(e-s);t=e+2.3*(e-s) if d==1 else e-2.3*(s-e);q=math.floor((max(eq,0)*0.01)/dist);risk=dist*q
                    if q>0 and risk>0: pending=Position(d,e,s,t,risk,q,i,b.ct,b.h,b.l,report,trigger,None,None)
                else:
                    pending={'stage':'confirm','d':d,'trigger':float(trigger),'s':float(s),'sig_i':i,'sig_t':int(b.ct),'sig_h':float(b.h),'sig_l':float(b.l),'report':report}

    return trades,{'n':len(trades),'R':sum(x['R'] for x in trades),'tick':tick,'session':sc.raw,'timezone':str(sc.tz),'exits':exit_counts,'bars':len(bars),'variant':variant,'counters':counters}
