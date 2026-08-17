#!/usr/bin/env python3
from pathlib import Path
p=Path('wave-rider-verify/reference_verify.py')
s=p.read_text()

old="from datetime import datetime, timedelta, timezone\nfrom pathlib import Path\nimport requests\n"
new="from datetime import datetime, timedelta, timezone\nfrom zoneinfo import ZoneInfo\nfrom pathlib import Path\nimport requests\n"
assert old in s; s=s.replace(old,new,1)

anchor="SESSION_GUARD=True; NO_ENTRY_MIN=40; EXIT_MIN=15\n"
insert="""SESSION_GUARD=True; NO_ENTRY_MIN=40; EXIT_MIN=15
USE_NEWS=os.getenv('WR_USE_NEWS','1').lower() not in ('0','false','no','off')
NEWS_EXIT_MIN=int(os.getenv('WR_NEWS_EXIT_MIN','15'))
NEWS_RESUME_MIN=int(os.getenv('WR_NEWS_RESUME_MIN','15'))
_NY=ZoneInfo('America/New_York')
NEWS_TIMES=[
    int(datetime(2025,11,20,8,30,tzinfo=_NY).timestamp()*1000),
    int(datetime(2025,12,10,14,0,tzinfo=_NY).timestamp()*1000),
    int(datetime(2025,12,16,8,30,tzinfo=_NY).timestamp()*1000),
    int(datetime(2025,12,18,8,30,tzinfo=_NY).timestamp()*1000),
]

def canonical_time_close(bar,chart_ms): return bar.ot+chart_ms

def news_locked_at(t):
    if not USE_NEWS: return False
    before=NEWS_EXIT_MIN*60000; after=NEWS_RESUME_MIN*60000
    return any(t>=e-before and t<e+after for e in NEWS_TIMES)

def news_exit_at_bar_close(tc,chart_ms):
    if not USE_NEWS: return False
    for e in NEWS_TIMES:
        cutoff=e-NEWS_EXIT_MIN*60000
        if (tc<cutoff and tc+chart_ms>=cutoff) or (tc>=cutoff and tc<e): return True
    return False
"""
assert anchor in s; s=s.replace(anchor,insert,1)

old="diag=dict(signals=0,pending_expired=0,pending_filled=0,ambiguous=0,tp=0,sl=0,ema=0,session=0,pivot_high_ties=pht,pivot_low_ties=plt)"
new="diag=dict(signals=0,pending_expired=0,pending_filled=0,ambiguous=0,tp=0,sl=0,ema=0,news=0,session=0,pivot_high_ties=pht,pivot_low_ties=plt)"
assert old in s; s=s.replace(old,new,1)

old="""        allowed,sexit=session_flags(x.ct,chart_ms)
        if active is not None and not closed:
            z=ind[i]
            le=active.d==1 and x.c<z['ema'] and not z['ha'] and not z['ema_up']
            se=active.d==-1 and x.c>z['ema'] and not z['hb'] and bool(z['ema_up'])
            if sexit: diag['session']+=1; closed=close_trade(i,'SESSION',x.c)
            elif le or se: diag['ema']+=1; closed=close_trade(i,'EMA',x.c)
        if pending is not None and i>=pending.sig_i+1 and active is None:
            pending=None; diag['pending_expired']+=1
        if x.ct<execution_start_ms or x.ct>=end_ms: continue
"""
new="""        tc=canonical_time_close(x,chart_ms)
        allowed,sexit=session_flags(tc,chart_ms)
        nexit=news_exit_at_bar_close(tc,chart_ms)
        if active is not None and not closed:
            z=ind[i]
            le=active.d==1 and x.c<z['ema'] and not z['ha'] and not z['ema_up']
            se=active.d==-1 and x.c>z['ema'] and not z['hb'] and bool(z['ema_up'])
            if sexit: diag['session']+=1; closed=close_trade(i,'SESSION',x.c)
            elif nexit: diag['news']+=1; closed=close_trade(i,'NEWS',x.c)
            elif le or se: diag['ema']+=1; closed=close_trade(i,'EMA',x.c)
        if pending is not None and i>=pending.sig_i+1 and active is None:
            pending=None; diag['pending_expired']+=1
        if tc<execution_start_ms or tc>=end_ms: continue
"""
assert old in s; s=s.replace(old,new,1)

old="""            nl=allowed and z['sra_ok'] and x.c>x.o and lr and x.c>z['res'] and x.l<=z['res']
            ns=allowed and z['sra_ok'] and x.c<x.o and sr and x.c<z['sup'] and x.h>=z['sup']
"""
new="""            news_ok=not news_locked_at(tc) and not news_locked_at(tc+chart_ms)
            nl=allowed and news_ok and z['sra_ok'] and x.c>x.o and lr and x.c>z['res'] and x.l<=z['res']
            ns=allowed and news_ok and z['sra_ok'] and x.c<x.o and sr and x.c<z['sup'] and x.h>=z['sup']
"""
assert old in s; s=s.replace(old,new,1)

old="pending=Plan(d,e,s,t,risk,q,i,x.ct,x.h,x.l); diag['signals']+=1"
new="pending=Plan(d,e,s,t,risk,q,i,tc,x.h,x.l); diag['signals']+=1"
assert old in s; s=s.replace(old,new,1)

old="exits={k:sum(t.exit_reason==k for t in trades) for k in ('TP','SL','AMBIG->SL','EMA','SESSION')}"
new="exits={k:sum(t.exit_reason==k for t in trades) for k in ('TP','SL','AMBIG->SL','EMA','NEWS','SESSION')}"
assert old in s; s=s.replace(old,new,1)

old="bars=sum(start_ms<=x.ct<end_ms for x in bars)"
new="bars=sum(start_ms<=canonical_time_close(x,chart_ms)<end_ms for x in bars)"
assert old in s; s=s.replace(old,new,1)

old="en=int((datetime.fromisoformat(END).replace(tzinfo=timezone.utc)+timedelta(days=1)).timestamp()*1000)-1"
new="en=int((datetime.fromisoformat(END).replace(tzinfo=timezone.utc)+timedelta(days=1)).timestamp()*1000)"
assert old in s; s=s.replace(old,new,1)

old="'No external news calendar implementation yet'"
new="'Embedded late-2025 NEWS sample copied from canonical Pine; extend calendar before research outside that sample'"
assert old in s; s=s.replace(old,new,1)

p.write_text(s)
print('TIME_NEWS_PATCH_OK')
