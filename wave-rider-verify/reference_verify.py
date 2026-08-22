#!/usr/bin/env python3
from __future__ import annotations
import csv, io, json, math, os, time, zipfile
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
import requests

# Canonical WR 2.5.13 Python reference.
# Consolidated 2026-08-23 from frozen verifier 8192984... with the parity-proven
# Pine ta.pivothigh/ta.pivotlow RIGHTMOST-TIE semantics embedded directly.
# Do not monkeypatch pivot semantics downstream.

SYMBOL=os.getenv('WR_SYMBOL','SOLUSDT')
START=os.getenv('WR_START','2026-07-27')
END=os.getenv('WR_END','2026-08-14')
WARMUP_DAYS=3
TFS=(3,5,10)
OUT=Path('wave-rider-verify/output')
LEFT=10; RIGHT=10; EMA_LEN=21; EMA_SMOOTH=2; REGIME=12
ANGLE_PERIOD=4; ATR_ANGLE=10; ANGLE_LEVEL=5.0
CHOP_LEN=14; CHOP_MAX=50.0; SIGNAL_ATR=14; SIGNAL_RANGE_MAX=1.5
TP_R=2.3; RISK_PCT=1.0; INIT=100000.0
SESSION_GUARD=True; NO_ENTRY_MIN=40; EXIT_MIN=15

@dataclass
class Bar:
    ot:int; ct:int; o:float; h:float; l:float; c:float
@dataclass
class Plan:
    d:int; e:float; s:float; t:float; risk:float; qty:float; sig_i:int; sig_t:int; sig_h:float; sig_l:float
@dataclass
class Trade:
    tf:int; side:str; signal_time:str; entry_time:str; exit_time:str
    signal_high:float; signal_low:float; entry:float; stop:float; target:float
    exit_price:float; exit_reason:str; canon_r:float; risk_cash:float; qty:float; ambiguous:bool

def iso(ms): return datetime.fromtimestamp(ms/1000,tz=timezone.utc).isoformat().replace('+00:00','Z')
def day_iter(a,b):
    d=a
    while d.date()<=b.date(): yield d.date(); d+=timedelta(days=1)

def infer_tick(vals):
    md=max((len(x.split('.',1)[1]) if '.' in x else 0 for x in vals),default=3)
    sc=10**md; u=sorted(set(int(round(float(x)*sc)) for x in vals))
    g=0
    for a,b in zip(u,u[1:]):
        if b>a:
            g=math.gcd(g,b-a)
            if g==1: break
    return (g/sc) if g else 10**(-md)

def fetch_1m():
    a=datetime.fromisoformat(START).replace(tzinfo=timezone.utc)-timedelta(days=WARMUP_DAYS)
    b=datetime.fromisoformat(END).replace(tzinfo=timezone.utc)
    sess=requests.Session(); sess.headers['User-Agent']='runner-3-wr-verify/1.0'
    bars=[]; prices=[]; missing=[]
    for d in day_iter(a,b):
        ds=d.isoformat(); url=f'https://data.binance.vision/data/futures/um/daily/klines/{SYMBOL}/1m/{SYMBOL}-1m-{ds}.zip'
        ok=False
        for k in range(3):
            try:
                r=sess.get(url,timeout=40)
                if r.status_code==404: break
                r.raise_for_status()
                with zipfile.ZipFile(io.BytesIO(r.content)) as z:
                    text=z.read(z.namelist()[0]).decode()
                for row in csv.reader(io.StringIO(text)):
                    if not row or not row[0].isdigit(): continue
                    bars.append(Bar(int(row[0]),int(row[6]),*map(float,row[1:5])))
                    prices.extend(row[1:5])
                ok=True; break
            except Exception:
                time.sleep(1+k)
        if not ok: missing.append(ds)
    ded={x.ot:x for x in bars}; bars=[ded[k] for k in sorted(ded)]
    if not bars: raise RuntimeError('no 1m candles fetched')
    return bars,infer_tick(prices),missing

def agg(src,m):
    ms=m*60000; out=[]; key=None; g=[]
    def emit(g):
        if len(g)!=m: return None
        if any(g[j+1].ot-g[j].ot!=60000 for j in range(len(g)-1)): return None
        return Bar(g[0].ot,g[-1].ct,g[0].o,max(x.h for x in g),min(x.l for x in g),g[-1].c)
    for x in src:
        k=x.ot//ms
        if key is None: key=k
        if k!=key:
            y=emit(g)
            if y: out.append(y)
            g=[]; key=k
        g.append(x)
    y=emit(g)
    if y: out.append(y)
    return out

def ema(v,n):
    a=2/(n+1); out=[]; p=None
    for x in v:
        p=x if p is None else a*x+(1-a)*p; out.append(p)
    return out

def rma(v,n):
    out=[None]*len(v); p=None; seed=[]
    for i,x in enumerate(v):
        if p is None:
            seed.append(x)
            if len(seed)==n: p=sum(seed)/n; out[i]=p
        else: p=(p*(n-1)+x)/n; out[i]=p
    return out

def roll(v,n,fn):
    out=[None]*len(v)
    for i in range(n-1,len(v)): out[i]=fn(v[i-n+1:i+1])
    return out

def pivots(v,left,right,high=True):
    """Pine-compatible rightmost-tie pivot semantics for ta.pivothigh/low(...)[1]."""
    base=[None]*len(v); ties=0
    for conf in range(left+right,len(v)):
        c=conf-right; x=v[c]; older=v[c-left:c]; newer=v[c+1:c+right+1]
        ok=(all(x>=z for z in older) and all(x>z for z in newer)) if high else (all(x<=z for z in older) and all(x<z for z in newer))
        if ok:
            base[conf]=x
        else:
            w=v[c-left:c+right+1]; ext=max(w) if high else min(w)
            if x==ext: ties+=1
    return [None]+base[:-1],ties

def calc_ind(b):
    c=[x.c for x in b]; h=[x.h for x in b]; l=[x.l for x in b]; e=ema(c,EMA_LEN)
    tr=[]
    for i,x in enumerate(b):
        tr.append(x.h-x.l if i==0 else max(x.h-x.l,abs(x.h-b[i-1].c),abs(x.l-b[i-1].c)))
    a10=rma(tr,ATR_ANGLE); a14=rma(tr,SIGNAL_ATR)
    tsum=roll(tr,CHOP_LEN,sum); rh=roll(h,CHOP_LEN,max); rl=roll(l,CHOP_LEN,min)
    ph,pht=pivots(h,LEFT,RIGHT,True); pl,plt=pivots(l,LEFT,RIGHT,False)
    res=sup=None; above=below=0; angles=[None]*len(b); out=[]
    for i,x in enumerate(b):
        if ph[i] is not None and ph[i]!=res: res=ph[i]
        if pl[i] is not None and pl[i]!=sup: sup=pl[i]
        above=above+1 if x.c>e[i] else 0; below=below+1 if x.c<e[i] else 0
        eu=None if i<EMA_SMOOTH else e[i]>=e[i-EMA_SMOOTH]
        an=None
        if i>=ANGLE_PERIOD and a10[i] not in (None,0): an=math.degrees(math.atan((e[i]-e[i-ANGLE_PERIOD])/a10[i]/ANGLE_PERIOD))
        angles[i]=an; outside=an is not None and (an>ANGLE_LEVEL or an<-ANGLE_LEVEL)
        ag=i>0 and an is not None and angles[i-1] is not None and an>angles[i-1] and outside
        ar=i>0 and an is not None and angles[i-1] is not None and an<angles[i-1] and outside
        ch=None
        if tsum[i] is not None and rh[i] is not None and rh[i]>rl[i] and tsum[i]>0:
            ch=100*math.log10(tsum[i]/(rh[i]-rl[i]))/math.log10(CHOP_LEN)
        sra=None if a14[i] in (None,0) else (x.h-x.l)/a14[i]
        out.append(dict(ema=e[i],ema_up=eu,ha=above>=REGIME,hb=below>=REGIME,
                        ag=ag,ar=ar,chop_ok=ch is not None and ch<CHOP_MAX,
                        sra_ok=sra is not None and sra<=SIGNAL_RANGE_MAX,res=res,sup=sup))
    return out,pht,plt

def session_flags(ct,chart_ms):
    if not SESSION_GUARD: return True,False
    dt=datetime.fromtimestamp(ct/1000,tz=timezone.utc)
    midnight=datetime(dt.year,dt.month,dt.day,tzinfo=timezone.utc)
    rdc=int((midnight+(timedelta(days=0) if ct==int(midnight.timestamp()*1000) else timedelta(days=1))).timestamp()*1000)
    ne=rdc-NO_ENTRY_MIN*60000; ex=rdc-EXIT_MIN*60000
    noentry=ct<=rdc and (ct>=ne or ct+chart_ms>=ne)
    exitnow=(ct<ex and ct+chart_ms>=ex) or (ct>=ex and ct<=rdc)
    return not noentry,exitnow

def path(x):
    return [x.o,x.h,x.l,x.c] if abs(x.o-x.h)<abs(x.o-x.l) else [x.o,x.l,x.h,x.c]
def cross(a,z,p): return min(a,z)<=p<=max(a,z)

def next_bracket(plan,x,start_at=None):
    pts=path(x); active=start_at is None; cur=pts[0]
    if active:
        if plan.d==1 and x.o<=plan.s: return 'SL',x.o
        if plan.d==1 and x.o>=plan.t: return 'TP',x.o
        if plan.d==-1 and x.o>=plan.s: return 'SL',x.o
        if plan.d==-1 and x.o<=plan.t: return 'TP',x.o
    for z in pts[1:]:
        pos=cur
        while True:
            if not active:
                enter=(plan.d==1 and pos<plan.e<=z) or (plan.d==-1 and pos>plan.e>=z)
                if not enter: break
                pos=plan.e; active=True; continue
            cand=[]
            if cross(pos,z,plan.s) and abs(plan.s-pos)>1e-12: cand.append((abs(plan.s-pos),'SL',plan.s))
            if cross(pos,z,plan.t) and abs(plan.t-pos)>1e-12: cand.append((abs(plan.t-pos),'TP',plan.t))
            if not cand: break
            _,r,p=min(cand); return r,p
        cur=z
    return None,None

def run(tf,bars,tick,start_ms,end_ms):
    ind,pht,plt=calc_ind(bars); chart_ms=tf*60000; eq=INIT; peak=INIT
    pending=active=None; entry_t=None; trades=[]
    diag=dict(signals=0,pending_expired=0,pending_filled=0,ambiguous=0,tp=0,sl=0,ema=0,session=0,pivot_high_ties=pht,pivot_low_ties=plt)
    cur_ls=max_ls=0; maxdd=0.0
    def close_trade(i,reason,px):
        nonlocal active,entry_t,eq,peak,maxdd,cur_ls,max_ls
        both=active is not None and bars[i].h>=max(active.s,active.t) and bars[i].l<=min(active.s,active.t) and reason in ('TP','SL')
        if both: reason='AMBIG->SL'; diag['ambiguous']+=1
        cr=TP_R if reason=='TP' else (-1.0 if reason in ('SL','AMBIG->SL') else ((px-active.e)*(1 if active.d==1 else -1)*active.qty/active.risk))
        cash=cr*active.risk; eq+=cash; peak=max(peak,eq); maxdd=max(maxdd,100*(peak-eq)/peak)
        if cash<0: cur_ls+=1; max_ls=max(max_ls,cur_ls)
        else: cur_ls=0
        if start_ms<=bars[i].ct<=end_ms:
            trades.append(Trade(tf,'LONG' if active.d==1 else 'SHORT',iso(active.sig_t),iso(entry_t),iso(bars[i].ct),active.sig_h,active.sig_l,active.e,active.s,active.t,px,reason,cr,active.risk,active.qty,both))
        active=None; entry_t=None
        return True
    for i,x in enumerate(bars):
        if x.ct>end_ms: break
        closed=False
        if active is not None:
            r,px=next_bracket(active,x,None)
            if r:
                diag['tp' if r=='TP' else 'sl']+=1; closed=close_trade(i,r,px)
        if active is None and pending is not None and i==pending.sig_i+1 and not closed:
            fill=(pending.d==1 and x.h>=pending.e) or (pending.d==-1 and x.l<=pending.e)
            if fill:
                active=pending; pending=None; entry_t=x.ot; diag['pending_filled']+=1
                r,px=next_bracket(active,x,active.e)
                if r:
                    diag['tp' if r=='TP' else 'sl']+=1; closed=close_trade(i,r,px)
        allowed,sexit=session_flags(x.ct,chart_ms)
        if active is not None and not closed:
            z=ind[i]
            le=active.d==1 and x.c<z['ema'] and not z['ha'] and not z['ema_up']
            se=active.d==-1 and x.c>z['ema'] and not z['hb'] and bool(z['ema_up'])
            if sexit: diag['session']+=1; closed=close_trade(i,'SESSION',x.c)
            elif le or se: diag['ema']+=1; closed=close_trade(i,'EMA',x.c)
        if pending is not None and i>=pending.sig_i+1 and active is None:
            pending=None; diag['pending_expired']+=1
        if x.ct<start_ms or x.ct>end_ms: continue
        if active is None and pending is None and not closed:
            z=ind[i]
            lr=z['ha'] and x.c>z['ema'] and z['ag'] and z['chop_ok'] and z['res'] is not None
            sr=z['hb'] and x.c<z['ema'] and z['ar'] and z['chop_ok'] and z['sup'] is not None
            nl=allowed and z['sra_ok'] and x.c>x.o and lr and x.c>z['res'] and x.l<=z['res']
            ns=allowed and z['sra_ok'] and x.c<x.o and sr and x.c<z['sup'] and x.h>=z['sup']
            if nl or ns:
                if nl: d=1; e=x.h+tick; s=x.l-tick; t=e+TP_R*(e-s)
                else: d=-1; e=x.l-tick; s=x.h+tick; t=e-TP_R*(s-e)
                raw=(eq*RISK_PCT/100)/abs(e-s); q=math.floor(raw); risk=abs(e-s)*q
                if q>0 and risk>0:
                    pending=Plan(d,e,s,t,risk,q,i,x.ct,x.h,x.l); diag['signals']+=1
    wins=sum(t.canon_r>0 for t in trades); losses=sum(t.canon_r<0 for t in trades); even=len(trades)-wins-losses
    total=sum(t.canon_r for t in trades); gp=sum(max(t.canon_r*t.risk_cash,0) for t in trades); gl=sum(max(-t.canon_r*t.risk_cash,0) for t in trades)
    exits={k:sum(t.exit_reason==k for t in trades) for k in ('TP','SL','AMBIG->SL','EMA','SESSION')}
    return trades,dict(symbol=SYMBOL,tf=tf,bars=sum(start_ms<=x.ct<=end_ms for x in bars),trades=len(trades),wins=wins,losses=losses,even=even,
        win_rate=(100*wins/len(trades) if trades else None),total_r=total,avg_r=(total/len(trades) if trades else None),profit_factor=(gp/gl if gl else None),
        max_dd_pct=maxdd,max_losing_streak=max_ls,exit_counts=exits,outcome_invariant=len(trades)==wins+losses+even,exit_invariant=len(trades)==sum(exits.values()),diagnostics=diag)

def main():
    OUT.mkdir(parents=True,exist_ok=True)
    one,tick,missing=fetch_1m(); sm=[]
    st=int(datetime.fromisoformat(START).replace(tzinfo=timezone.utc).timestamp()*1000)
    en=int((datetime.fromisoformat(END).replace(tzinfo=timezone.utc)+timedelta(days=1)).timestamp()*1000)-1
    for tf in TFS:
        tr,s=run(tf,agg(one,tf),tick,st,en); sm.append(s)
        p=OUT/f'{SYMBOL}_{tf}m_trades.csv'
        with p.open('w',newline='') as f:
            fields=list(Trade.__dataclass_fields__); w=csv.DictWriter(f,fieldnames=fields); w.writeheader()
            for x in tr: w.writerow(asdict(x))
        (OUT/f'{SYMBOL}_{tf}m_summary.json').write_text(json.dumps(s,indent=2))
    master=dict(strategy='Wave Rider 2.5.13 independent reference',source='Binance USD-M 1m public daily klines',symbol=SYMBOL,start=START,end=END,tick=tick,missing=missing,summaries=sm,
        caveats=['Same 1m source resampled to all timeframes','UTC Binance session-close model','TradingView OHLC path heuristic; Canon both-touch bar forced to -1R','Pine rightmost-tie pivot semantics embedded directly'])
    (OUT/'master.json').write_text(json.dumps(master,indent=2))
    print(json.dumps(master,indent=2))
    print('\nTF Trades WR PF AvgR TotalR MaxDD MaxLS Invariants')
    for s in sm:
        print(f"{s['tf']:>2}m {s['trades']:>5} {(s['win_rate'] or 0):>5.1f} {(s['profit_factor'] or 0):>5.2f} {(s['avg_r'] or 0):>+6.3f} {s['total_r']:>+7.2f} {s['max_dd_pct']:>5.2f}% {s['max_losing_streak']:>5} {s['outcome_invariant']}/{s['exit_invariant']}")
if __name__=='__main__': main()
