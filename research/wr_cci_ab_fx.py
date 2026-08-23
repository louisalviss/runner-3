#!/usr/bin/env python3
import csv, json, math, os
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path

LEFT=10; RIGHT=10; EMA_LEN=21; EMA_SMOOTH=2; REGIME=12
ANGLE_PERIOD=4; ATR_ANGLE=10; ANGLE_LEVEL=5.0
CHOP_LEN=14; CHOP_MAX=50.0; SIGNAL_ATR=14; SIGNAL_RANGE_MAX=1.5
CCI_LEN=27; CCI_LOOKBACK=18; CCI_LEVEL=100.0; TP_R=2.3
SYMBOLS=('EURUSD','GBPUSD','USDJPY','AUDUSD','USDCAD','USDCHF','NZDUSD')
COST_PIPS={'EURUSD':1.0,'GBPUSD':1.2,'USDJPY':1.0,'AUDUSD':1.0,'USDCAD':1.2,'USDCHF':1.2,'NZDUSD':1.4}
DATA=Path(os.getenv('WRFX_DATA_DIR','/tmp/wrfx_data'))
OUT=Path('evidence/wr-cci-ab'); OUT.mkdir(parents=True,exist_ok=True)
MODES=('BASE_LONG','CCI_LONG_EXACT','BASE_BOTH','CCI_SYMMETRIC')

@dataclass
class Bar: ot:int; ct:int; o:float; h:float; l:float; c:float
@dataclass
class Plan: d:int; e:float; s:float; t:float; sig_i:int; sig_t:int
@dataclass
class Trade:
    symbol:str; tf:int; mode:str; side:str; signal_time:int; entry_time:int; exit_time:int
    entry:float; stop:float; target:float; exit_price:float; reason:str; gross_r:float; net_r:float; cost_r:float

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
        else:
            p=(p*(n-1)+x)/n; out[i]=p
    return out

def roll(v,n,fn):
    out=[None]*len(v)
    for i in range(n-1,len(v)): out[i]=fn(v[i-n+1:i+1])
    return out

def pivots(v,left,right,high=True):
    base=[None]*len(v)
    for conf in range(left+right,len(v)):
        c=conf-right; w=v[c-left:c+right+1]; ext=max(w) if high else min(w)
        if v[c]==ext and all(x!=ext for x in v[c+1:c+right+1]): base[conf]=v[c]
    return [None]+base[:-1]

def cci_series(b,n=CCI_LEN):
    tp=[(x.h+x.l+x.c)/3.0 for x in b]
    out=[None]*len(tp)
    for i in range(n-1,len(tp)):
        w=tp[i-n+1:i+1]; ma=sum(w)/n; md=sum(abs(x-ma) for x in w)/n
        out[i]=0.0 if md==0 else (tp[i]-ma)/(0.015*md)
    return out

def calc_ind(b):
    c=[x.c for x in b]; h=[x.h for x in b]; l=[x.l for x in b]; e=ema(c,EMA_LEN); tr=[]
    for i,x in enumerate(b): tr.append(x.h-x.l if i==0 else max(x.h-x.l,abs(x.h-b[i-1].c),abs(x.l-b[i-1].c)))
    a10=rma(tr,ATR_ANGLE); a14=rma(tr,SIGNAL_ATR); tsum=roll(tr,CHOP_LEN,sum); rh=roll(h,CHOP_LEN,max); rl=roll(l,CHOP_LEN,min)
    ph=pivots(h,LEFT,RIGHT,True); pl=pivots(l,LEFT,RIGHT,False); cci=cci_series(b)
    res=sup=None; above=below=0; angles=[None]*len(b); out=[]
    for i,x in enumerate(b):
        if ph[i] is not None and ph[i]!=res: res=ph[i]
        if pl[i] is not None and pl[i]!=sup: sup=pl[i]
        above=above+1 if x.c>e[i] else 0; below=below+1 if x.c<e[i] else 0
        eu=None if i<EMA_SMOOTH else e[i]>=e[i-EMA_SMOOTH]; an=None
        if i>=ANGLE_PERIOD and a10[i] not in (None,0): an=math.degrees(math.atan((e[i]-e[i-ANGLE_PERIOD])/a10[i]/ANGLE_PERIOD))
        angles[i]=an; outside=an is not None and (an>ANGLE_LEVEL or an<-ANGLE_LEVEL)
        ag=i>0 and an is not None and angles[i-1] is not None and an>angles[i-1] and outside
        ar=i>0 and an is not None and angles[i-1] is not None and an<angles[i-1] and outside
        ch=None
        if tsum[i] is not None and rh[i] is not None and rh[i]>rl[i] and tsum[i]>0: ch=100*math.log10(tsum[i]/(rh[i]-rl[i]))/math.log10(CHOP_LEN)
        sra=None if a14[i] in (None,0) else (x.h-x.l)/a14[i]
        cwin=[z for z in cci[max(0,i-CCI_LOOKBACK+1):i+1] if z is not None]
        cci_long=len(cwin)==CCI_LOOKBACK and min(cwin)<-CCI_LEVEL
        cci_short=len(cwin)==CCI_LOOKBACK and max(cwin)>CCI_LEVEL
        out.append(dict(ema=e[i],ema_up=eu,ha=above>=REGIME,hb=below>=REGIME,ag=ag,ar=ar,
                        chop_ok=ch is not None and ch<CHOP_MAX,sra_ok=sra is not None and sra<=SIGNAL_RANGE_MAX,
                        res=res,sup=sup,cci=cci[i],cci_long=cci_long,cci_short=cci_short))
    return out

def path4(x): return [x.o,x.h,x.l,x.c] if abs(x.o-x.h)<abs(x.o-x.l) else [x.o,x.l,x.h,x.c]
def cross(a,z,p): return min(a,z)<=p<=max(a,z)

def bracket(plan,x,start_at=None):
    pts=path4(x); active=start_at is None; cur=pts[0]
    if active:
        if plan.d==1 and x.o<=plan.s: return 'SL',x.o
        if plan.d==1 and x.o>=plan.t: return 'TP',x.o
        if plan.d==-1 and x.o>=plan.s: return 'SL',x.o
        if plan.d==-1 and x.o<=plan.t: return 'TP',x.o
    for z in pts[1:]:
        pos=cur
        while True:
            if not active:
                enter=(plan.d==1 and pos<=plan.e<=z) or (plan.d==-1 and pos>=plan.e>=z)
                if not enter: break
                pos=plan.e; active=True; continue
            cand=[]
            if cross(pos,z,plan.s) and abs(plan.s-pos)>1e-12: cand.append((abs(plan.s-pos),'SL',plan.s))
            if cross(pos,z,plan.t) and abs(plan.t-pos)>1e-12: cand.append((abs(plan.t-pos),'TP',plan.t))
            if not cand: break
            _,r,p=min(cand); return r,p
        cur=z
    return None,None

def read_m5(symbol):
    f=DATA/f'{symbol}_M5.csv'; bars=[]
    with f.open(newline='') as fh:
        r=csv.DictReader(fh)
        for row in r:
            ts=int(float(row['timestamp'])); bars.append(Bar(ts,ts+5*60000-1,float(row['open']),float(row['high']),float(row['low']),float(row['close'])))
    bars.sort(key=lambda x:x.ot); return bars

def agg10(src):
    out=[]; g=[]; key=None
    for x in src:
        k=x.ot//600000
        if key is None: key=k
        if k!=key:
            if len(g)==2 and g[1].ot-g[0].ot==300000: out.append(Bar(g[0].ot,g[-1].ct,g[0].o,max(y.h for y in g),min(y.l for y in g),g[-1].c))
            g=[]; key=k
        g.append(x)
    if len(g)==2 and g[1].ot-g[0].ot==300000: out.append(Bar(g[0].ot,g[-1].ct,g[0].o,max(y.h for y in g),min(y.l for y in g),g[-1].c))
    return out

def tick(symbol): return 0.001 if symbol.endswith('JPY') else 0.00001
def pip(symbol): return 0.01 if symbol.endswith('JPY') else 0.0001

def allow_signal(mode,d,z):
    if mode=='BASE_LONG': return d==1
    if mode=='CCI_LONG_EXACT': return d==1 and z['cci_long']
    if mode=='BASE_BOTH': return True
    if mode=='CCI_SYMMETRIC': return z['cci_long'] if d==1 else z['cci_short']
    return False

def close_trade(symbol,tf,mode,plan,entry_t,exit_t,exit_price,reason,gross_r):
    risk=abs(plan.e-plan.s); cr=COST_PIPS[symbol]*pip(symbol)/risk
    return Trade(symbol,tf,mode,'LONG' if plan.d==1 else 'SHORT',plan.sig_t,entry_t,exit_t,plan.e,plan.s,plan.t,exit_price,reason,gross_r,gross_r-cr,cr)

def run_stateful(symbol,tf,bars,mode):
    ind=calc_ind(bars); tk=tick(symbol); pending=active=None; entry_t=None; trades=[]
    for i,x in enumerate(bars):
        closed=False
        if active is not None:
            r,px=bracket(active,x)
            if r:
                both=x.h>=max(active.s,active.t) and x.l<=min(active.s,active.t)
                if both: r='SL'; px=active.s
                gr=TP_R if r=='TP' else -1.0
                trades.append(close_trade(symbol,tf,mode,active,entry_t,x.ct,px,r,gr)); active=None; entry_t=None; closed=True
        if active is None and pending is not None and i==pending.sig_i+1 and not closed:
            fill=(pending.d==1 and x.h>=pending.e) or (pending.d==-1 and x.l<=pending.e)
            if fill:
                active=pending; pending=None; entry_t=x.ot
                r,px=bracket(active,x,active.e)
                if r:
                    both=x.h>=max(active.s,active.t) and x.l<=min(active.s,active.t)
                    if both: r='SL'; px=active.s
                    gr=TP_R if r=='TP' else -1.0
                    trades.append(close_trade(symbol,tf,mode,active,entry_t,x.ct,px,r,gr)); active=None; entry_t=None; closed=True
        if active is not None and not closed:
            z=ind[i]; le=active.d==1 and x.c<z['ema'] and not z['ha'] and not z['ema_up']; se=active.d==-1 and x.c>z['ema'] and not z['hb'] and bool(z['ema_up'])
            if le or se:
                risk=abs(active.e-active.s); gr=(x.c-active.e)*(1 if active.d==1 else -1)/risk
                trades.append(close_trade(symbol,tf,mode,active,entry_t,x.ct,x.c,'EMA',gr)); active=None; entry_t=None; closed=True
        if pending is not None and i>=pending.sig_i+1 and active is None: pending=None
        if active is None and pending is None and not closed:
            z=ind[i]; lr=z['ha'] and x.c>z['ema'] and z['ag'] and z['chop_ok'] and z['res'] is not None; sr=z['hb'] and x.c<z['ema'] and z['ar'] and z['chop_ok'] and z['sup'] is not None
            nl=z['sra_ok'] and x.c<x.o and lr and x.c>z['res'] and x.l<=z['res']; ns=z['sra_ok'] and x.c>x.o and sr and x.c<z['sup'] and x.h>=z['sup']
            if nl or ns:
                d=1 if nl else -1
                if allow_signal(mode,d,z):
                    if d==1: e=x.h+tk; s=x.l-tk; t=e+TP_R*(e-s)
                    else: e=x.l-tk; s=x.h+tk; t=e-TP_R*(s-e)
                    pending=Plan(d,e,s,t,i,x.ct)
    return trades

def year_of(ms): return datetime.fromtimestamp(ms/1000,timezone.utc).year

def metrics(trades):
    vals=[t.net_r for t in trades]; wins=[v for v in vals if v>0]; losses=[v for v in vals if v<0]
    eq=0.0; peak=0.0; maxdd=0.0
    for t in sorted(trades,key=lambda x:(x.exit_time,x.symbol)):
        eq+=t.net_r; peak=max(peak,eq); maxdd=max(maxdd,peak-eq)
    pf=(sum(wins)/abs(sum(losses))) if losses else (999.0 if wins else None)
    return {'n':len(vals),'net_r':round(sum(vals),3),'net_exp':round(sum(vals)/len(vals),4) if vals else None,
            'gross_r':round(sum(t.gross_r for t in trades),3),'win_rate':round(len(wins)/len(vals),4) if vals else None,
            'pf':round(pf,4) if pf is not None else None,'max_dd_r':round(maxdd,3),
            'avg_cost_r':round(sum(t.cost_r for t in trades)/len(vals),4) if vals else None}

def main():
    all_trades=[]; coverage={}
    for symbol in SYMBOLS:
        b5=read_m5(symbol); coverage[symbol]={'m5':len(b5),'first':b5[0].ot if b5 else None,'last':b5[-1].ot if b5 else None}
        for tf,bars in ((5,b5),(10,agg10(b5))):
            for mode in MODES:
                ts=run_stateful(symbol,tf,bars,mode); all_trades.extend(ts)
                print('DONE',symbol,tf,mode,len(ts))
    summary={'method':{'canonical_engine':'ported from wave-rider-scanner research/wr_fx_backtest.py','tp_r':TP_R,'cci':{'period':CCI_LEN,'lookback':CCI_LOOKBACK,'long':'min < -100','short_symmetric':'max > +100'},'cost_pips_roundtrip':COST_PIPS,'same_bar_both':'SL conservative'},'coverage':coverage,'aggregate':{},'by_year':{},'by_symbol':{}}
    for tf in (5,10):
        summary['aggregate'][str(tf)]={}
        summary['by_year'][str(tf)]={}
        summary['by_symbol'][str(tf)]={}
        for mode in MODES:
            g=[t for t in all_trades if t.tf==tf and t.mode==mode]
            summary['aggregate'][str(tf)][mode]=metrics(g)
            summary['by_year'][str(tf)][mode]={str(y):metrics([t for t in g if year_of(t.signal_time)==y]) for y in (2022,2023,2024,2025,2026)}
            summary['by_symbol'][str(tf)][mode]={s:metrics([t for t in g if t.symbol==s]) for s in SYMBOLS}
    def delta(tf,a,b):
        A=summary['aggregate'][str(tf)][a]; B=summary['aggregate'][str(tf)][b]
        return {'trade_retention':round(B['n']/A['n'],4) if A['n'] else None,'delta_net_r':round(B['net_r']-A['net_r'],3),'delta_exp':round((B['net_exp'] or 0)-(A['net_exp'] or 0),4),'delta_pf':round((B['pf'] or 0)-(A['pf'] or 0),4),'delta_max_dd_r':round(B['max_dd_r']-A['max_dd_r'],3)}
    summary['comparisons']={str(tf):{'exact_long':delta(tf,'BASE_LONG','CCI_LONG_EXACT'),'symmetric':delta(tf,'BASE_BOTH','CCI_SYMMETRIC')} for tf in (5,10)}
    (OUT/'summary.json').write_text(json.dumps(summary,indent=2))
    with (OUT/'trades.csv').open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=asdict(all_trades[0]).keys()); w.writeheader(); w.writerows(asdict(t) for t in all_trades)
    print('WR_CCI_AB_RESULT',json.dumps(summary['comparisons']))
    print(json.dumps(summary['aggregate']['10'],indent=2))

if __name__=='__main__': main()
