#!/usr/bin/env python3
import csv, io, json, math, os, time, zipfile, types, sys
from dataclasses import dataclass
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
import requests

GROUP=int(os.environ.get("GROUP","0"))
GROUPS=int(os.environ.get("GROUPS","6"))
BASE=Path(os.environ.get("BASE_DIR","/tmp/base"))
OUT=Path(os.environ.get("OUT_DIR","/tmp/out")); OUT.mkdir(parents=True,exist_ok=True)

SYMBOLS=[
 "BTCUSDT","ETHUSDT","SOLUSDT","XRPUSDT","BNBUSDT","DOGEUSDT",
 "ADAUSDT","AVAXUSDT","LINKUSDT","DOTUSDT","BCHUSDT","LTCUSDT",
 "TRXUSDT","AAVEUSDT","NEARUSDT","SUIUSDT","WIFUSDT","1000PEPEUSDT"
]
symbols=[s for i,s in enumerate(SYMBOLS) if i%GROUPS==GROUP]
TFS=(5,10)

STATE=int(datetime(2024,12,1,tzinfo=timezone.utc).timestamp()*1000)
START=int(datetime(2025,1,1,tzinfo=timezone.utc).timestamp()*1000)
END=int(datetime(2026,8,15,tzinfo=timezone.utc).timestamp()*1000)
months=[(2024,12)]+[(2025,m) for m in range(1,13)]+[(2026,m) for m in range(1,8)]
BPS=(4,6,8,10,12)

ref=Path("/tmp/reference_verify.py")
mod=types.ModuleType("wrref"); mod.__file__="reference_verify.py"; sys.modules["wrref"]=mod
exec(compile(ref.read_text(),"reference_verify.py","exec"),mod.__dict__)
Bar=mod.Bar
calc_ind=mod.calc_ind
nextb=mod.next_bracket
sf=mod.session_flags

ANGLE_LEVEL=5.0

@dataclass
class P:
    d:int; e:float; s:float; t:float; sig_i:int; sig_t:int; hi:float; lo:float

VARIANTS=[
 {"name":"BASE","tp":2.3},
 {"name":"TP_1_5","tp":1.5},
 {"name":"TP_2_0","tp":2.0},
 {"name":"TP_3_0","tp":3.0},
 {"name":"NO_REGIME12","tp":2.3,"regime":"none"},
 {"name":"EMA21_50_STACK","tp":2.3,"regime":"ema_stack"},
 {"name":"NO_ANGLE","tp":2.3,"angle":"none"},
 {"name":"ANGLE_SIGN_ONLY","tp":2.3,"angle":"sign"},
 {"name":"ADX_DMI","tp":2.3,"angle":"adx"},
 {"name":"NO_CHOP","tp":2.3,"chop":"none"},
 {"name":"ER20","tp":2.3,"chop":"er"},
 {"name":"DONCHIAN20","tp":2.3,"breakout":"donchian"},
 {"name":"SIGNAL_STRENGTH","tp":2.3,"candle_strength":True},
 {"name":"NO_EMA_EXIT","tp":2.3,"no_ema_exit":True},
 {"name":"CLOSE_CONFIRM","tp":2.3,"entry":"close_confirm"},
]

sess=requests.Session()
sess.headers["User-Agent"]=f"runner3-wr-modular-trend-{GROUP}/1.0"

def getzip(url):
    for k in range(4):
        try:
            r=sess.get(url,timeout=60)
            if r.status_code==404: return None
            r.raise_for_status(); return r.content
        except Exception:
            if k==3: raise
            time.sleep(.6*(k+1))

def readzip(data):
    out=[]
    if not data:return out
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        text=z.read(z.namelist()[0]).decode()
    for row in csv.reader(io.StringIO(text)):
        if row and row[0].isdigit():
            out.append(Bar(int(row[0]),int(row[6]),*map(float,row[1:5])))
    return out

def load5(sym):
    b=[]
    for y,m in months:
        fn=f"{sym}-5m-{y:04d}-{m:02d}.zip"
        u=f"https://data.binance.vision/data/futures/um/monthly/klines/{sym}/5m/{fn}"
        try:b.extend(readzip(getzip(u)))
        except Exception as e: print("FETCH_ERR",sym,fn,repr(e),flush=True)
    for d in range(1,15):
        fn=f"{sym}-5m-2026-08-{d:02d}.zip"
        u=f"https://data.binance.vision/data/futures/um/daily/klines/{sym}/5m/{fn}"
        try:b.extend(readzip(getzip(u)))
        except Exception as e: print("FETCH_ERR",sym,fn,repr(e),flush=True)
    ded={x.ot:x for x in b}
    return [ded[k] for k in sorted(ded) if STATE<=k<END]

def agg10(bars):
    g=defaultdict(list)
    for b in bars:g[(b.ot//600_000)*600_000].append(b)
    out=[]
    for ot in sorted(g):
        xs=sorted(g[ot],key=lambda x:x.ot)
        if len(xs)<1:continue
        out.append(Bar(ot,ot+599_999,xs[0].o,max(x.h for x in xs),min(x.l for x in xs),xs[-1].c))
    return out

def ema(vals,n):
    a=2/(n+1); out=[]; p=None
    for x in vals:
        p=x if p is None else a*x+(1-a)*p
        out.append(p)
    return out

def rma(vals,n):
    out=[None]*len(vals); seed=[]; p=None
    for i,x in enumerate(vals):
        if p is None:
            seed.append(x)
            if len(seed)==n:
                p=sum(seed)/n; out[i]=p
        else:
            p=(p*(n-1)+x)/n; out[i]=p
    return out

def supplemental(bars, ind):
    n=len(bars)
    c=[x.c for x in bars]; h=[x.h for x in bars]; l=[x.l for x in bars]
    e21=[z["ema"] for z in ind]
    e50=ema(c,50)
    tr=[]; pdm=[]; mdm=[]
    for i,x in enumerate(bars):
        if i==0:
            tr.append(x.h-x.l); pdm.append(0.0); mdm.append(0.0)
        else:
            up=x.h-bars[i-1].h; dn=bars[i-1].l-x.l
            pdm.append(up if up>dn and up>0 else 0.0)
            mdm.append(dn if dn>up and dn>0 else 0.0)
            tr.append(max(x.h-x.l,abs(x.h-bars[i-1].c),abs(x.l-bars[i-1].c)))
    atr10=rma(tr,10)
    atr14=rma(tr,14); p14=rma(pdm,14); m14=rma(mdm,14)
    pdi=[None]*n; mdi=[None]*n; dx=[0.0]*n
    for i in range(n):
        if atr14[i] not in (None,0) and p14[i] is not None and m14[i] is not None:
            pdi[i]=100*p14[i]/atr14[i]; mdi[i]=100*m14[i]/atr14[i]
            den=pdi[i]+mdi[i]
            dx[i]=0.0 if den==0 else 100*abs(pdi[i]-mdi[i])/den
    adx=rma(dx,14)
    angle=[None]*n
    for i in range(4,n):
        if atr10[i] not in (None,0):
            angle[i]=math.degrees(math.atan((e21[i]-e21[i-4])/atr10[i]/4))
    er=[None]*n
    for i in range(20,n):
        den=sum(abs(c[j]-c[j-1]) for j in range(i-19,i+1))
        er[i]=0.0 if den==0 else abs(c[i]-c[i-20])/den
    dh=[None]*n; dl=[None]*n
    for i in range(20,n):
        dh[i]=max(h[i-20:i]); dl[i]=min(l[i-20:i])
    return dict(ema50=e50,angle=angle,adx=adx,pdi=pdi,mdi=mdi,er=er,dh=dh,dl=dl)

def variant_signal(v, i, x, z, s):
    reg=v.get("regime","base")
    if reg=="none":
        rl=rs=True
    elif reg=="ema_stack":
        rl=(x.c>z["ema"] and z["ema"]>s["ema50"][i])
        rs=(x.c<z["ema"] and z["ema"]<s["ema50"][i])
    else:
        rl=z["ha"]; rs=z["hb"]
    am=v.get("angle","base")
    if am=="none":
        al=ash=True
    elif am=="sign":
        a=s["angle"][i]
        al=a is not None and a>ANGLE_LEVEL
        ash=a is not None and a<-ANGLE_LEVEL
    elif am=="adx":
        ad=s["adx"][i]; p=s["pdi"][i]; m=s["mdi"][i]
        al=ad is not None and p is not None and m is not None and ad>=20 and p>m
        ash=ad is not None and p is not None and m is not None and ad>=20 and m>p
    else:
        al=z["ag"]; ash=z["ar"]
    cm=v.get("chop","base")
    if cm=="none":
        cl=csh=True
    elif cm=="er":
        e=s["er"][i]
        cl=csh=(e is not None and e>=0.30)
    else:
        cl=csh=z["chop_ok"]
    common_long = z["sra_ok"] and x.c>x.o and x.c>z["ema"] and rl and al and cl
    common_short= z["sra_ok"] and x.c<x.o and x.c<z["ema"] and rs and ash and csh
    if v.get("breakout")=="donchian":
        nl=common_long and s["dh"][i] is not None and x.c>s["dh"][i]
        ns=common_short and s["dl"][i] is not None and x.c<s["dl"][i]
    else:
        nl=common_long and z["res"] is not None and x.c>z["res"] and x.l<=z["res"]
        ns=common_short and z["sup"] is not None and x.c<z["sup"] and x.h>=z["sup"]
    if v.get("candle_strength"):
        rng=x.h-x.l
        if rng<=0:return False,False
        body=abs(x.c-x.o)/rng
        clv=(x.c-x.l)/rng
        nl=nl and body>=0.50 and clv>=0.75
        ns=ns and body>=0.50 and clv<=0.25
    return nl,ns

def run_variant(sym,tf,bars,tick,v):
    ind,_,_=calc_ind(bars)
    sup=supplemental(bars,ind)
    tp=float(v["tp"]); chart_ms=tf*60_000
    pending=active=None; trades=[]
    def close_trade(i, reason, px):
        nonlocal active
        p=active
        if reason=="TP": rr=tp
        elif reason in ("SL","AMBIG->SL"): rr=-1.0
        else: rr=((px-p.e)*(1 if p.d==1 else -1))/abs(p.e-p.s)
        if START<=p.sig_t<END:
            row={"symbol":sym,"tf":tf,"variant":v["name"],"signal_time":p.sig_t,
                 "side":"LONG" if p.d==1 else "SHORT","entry":p.e,"stop":p.s,
                 "exit_time":bars[i].ct,"exit_reason":reason,"R":rr}
            for bps in BPS:
                row[f"net{bps}"]=rr-(p.e/abs(p.e-p.s))*bps/10000
            trades.append(row)
        active=None
    for i,x in enumerate(bars):
        if x.ot>=END:break
        closed=False
        if active is not None:
            r,px=nextb(active,x,None)
            if r:
                if x.h>=max(active.s,active.t) and x.l<=min(active.s,active.t):
                    r,px="AMBIG->SL",active.s
                close_trade(i,r,px); closed=True
        if active is None and pending is not None and i==pending.sig_i+1 and not closed:
            if v.get("entry")=="close_confirm":
                confirm=(pending.d==1 and round(x.c/tick)>=round(pending.e/tick)) or (pending.d==-1 and round(x.c/tick)<=round(pending.e/tick))
                if confirm:
                    e=x.c; s0=pending.s
                    if (pending.d==1 and e>s0) or (pending.d==-1 and e<s0):
                        t=e+tp*(e-s0) if pending.d==1 else e-tp*(s0-e)
                        active=P(pending.d,e,s0,t,pending.sig_i,pending.sig_t,pending.hi,pending.lo)
                pending=None
            else:
                fill=(pending.d==1 and round(x.h/tick)>=round(pending.e/tick)) or (pending.d==-1 and round(x.l/tick)<=round(pending.e/tick))
                if fill:
                    gap=(pending.d==1 and round(x.o/tick)>=round(pending.e/tick)) or (pending.d==-1 and round(x.o/tick)<=round(pending.e/tick))
                    active=pending; pending=None
                    r,px=nextb(active,x,None if gap else active.e)
                    if r:
                        if x.h>=max(active.s,active.t) and x.l<=min(active.s,active.t):
                            r,px="AMBIG->SL",active.s
                        close_trade(i,r,px); closed=True
        allowed,sexit=sf(x.ct+1,chart_ms)
        if active is not None and not closed:
            if sexit:
                close_trade(i,"SESSION",x.c); closed=True
            elif not v.get("no_ema_exit"):
                z=ind[i]
                le=active.d==1 and x.c<z["ema"] and not z["ha"] and not z["ema_up"]
                se=active.d==-1 and x.c>z["ema"] and not z["hb"] and bool(z["ema_up"])
                if le or se:
                    close_trade(i,"EMA",x.c); closed=True
        if pending is not None and i>=pending.sig_i+1 and active is None:
            pending=None
        if x.ct<START:continue
        if active is None and pending is None and not closed:
            nl,ns=variant_signal(v,i,x,ind[i],sup)
            if allowed and (nl or ns):
                if nl:
                    d=1; e=x.h+tick; st=x.l-tick; t=e+tp*(e-st)
                else:
                    d=-1; e=x.l-tick; st=x.h+tick; t=e-tp*(st-e)
                if abs(e-st)>0:
                    pending=P(d,e,st,t,i,x.ct,x.h,x.l)
    return trades

def main():
    tickmap=json.load(open(BASE/"tv_tick_map.json"))
    alltr=[]; errors=[]
    for sym in symbols:
        try:
            b5=load5(sym)
            if len(b5)<500:
                errors.append({"symbol":sym,"error":"too_few_bars"}); continue
            tick=float(tickmap[sym]["tick"])
            for tf,bars in ((5,b5),(10,agg10(b5))):
                for v in VARIANTS:
                    tr=run_variant(sym,tf,bars,tick,v)
                    alltr.extend(tr)
                    print(GROUP,sym,tf,v["name"],len(tr),flush=True)
        except Exception as e:
            errors.append({"symbol":sym,"error":repr(e)})
            print("ERROR",sym,repr(e),flush=True)
    with open(OUT/f"trades-{GROUP}.jsonl","w") as f:
        for r in alltr:f.write(json.dumps(r,separators=(",",":"))+"\n")
    json.dump({"group":GROUP,"symbols":symbols,"trades":len(alltr),"errors":errors},open(OUT/f"meta-{GROUP}.json","w"),indent=2)

if __name__=="__main__":main()
