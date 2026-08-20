#!/usr/bin/env python3
import csv, io, json, math, os, time, zipfile
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
import requests

GROUP=int(os.environ.get('GROUP','0')); GROUPS=int(os.environ.get('GROUPS','6'))
BASE=Path(os.environ.get('BASE_DIR','/tmp/base')); OUT=Path(os.environ.get('OUT_DIR','/tmp/out')); OUT.mkdir(parents=True,exist_ok=True)
SYMBOLS=['BTCUSDT','ETHUSDT','SOLUSDT','XRPUSDT','BNBUSDT','DOGEUSDT','ADAUSDT','AVAXUSDT','LINKUSDT','DOTUSDT','BCHUSDT','LTCUSDT','TRXUSDT','AAVEUSDT','NEARUSDT','SUIUSDT','WIFUSDT','1000PEPEUSDT']
symbols=[s for i,s in enumerate(SYMBOLS) if i%GROUPS==GROUP]
TFS=(5,10); TPS=(1.5,2.0,2.3,3.0); BPS=(4,6,8,10,12)
STATE=int(datetime(2023,12,1,tzinfo=timezone.utc).timestamp()*1000)
START=int(datetime(2024,1,1,tzinfo=timezone.utc).timestamp()*1000)
END=int(datetime(2026,8,15,tzinfo=timezone.utc).timestamp()*1000)
months=[(2023,12)]+[(2024,m) for m in range(1,13)]+[(2025,m) for m in range(1,13)]+[(2026,m) for m in range(1,8)]

class Bar:
    def __init__(self,ot,ct,o,h,l,c): self.ot=int(ot); self.ct=int(ct); self.o=o; self.h=h; self.l=l; self.c=c

sess=requests.Session(); sess.headers['User-Agent']=f'runner3-wr-nextgen-{GROUP}/1.0'
def getzip(url):
    for k in range(4):
        try:
            r=sess.get(url,timeout=60)
            if r.status_code==404:return None
            r.raise_for_status(); return r.content
        except Exception:
            if k==3: raise
            time.sleep(.7*(k+1))
def readzip(data):
    if not data:return []
    out=[]
    with zipfile.ZipFile(io.BytesIO(data)) as z: text=z.read(z.namelist()[0]).decode()
    for row in csv.reader(io.StringIO(text)):
        if row and row[0].isdigit(): out.append(Bar(row[0],row[6],*map(float,row[1:5])))
    return out
def load5(sym):
    b=[]
    for y,m in months:
        fn=f'{sym}-5m-{y:04d}-{m:02d}.zip'; u=f'https://data.binance.vision/data/futures/um/monthly/klines/{sym}/5m/{fn}'
        try:b.extend(readzip(getzip(u)))
        except Exception as e: print('FETCH_ERR',sym,fn,repr(e),flush=True)
    for d in range(1,15):
        fn=f'{sym}-5m-2026-08-{d:02d}.zip'; u=f'https://data.binance.vision/data/futures/um/daily/klines/{sym}/5m/{fn}'
        try:b.extend(readzip(getzip(u)))
        except Exception as e: print('FETCH_ERR',sym,fn,repr(e),flush=True)
    ded={x.ot:x for x in b}; return [ded[k] for k in sorted(ded) if STATE<=k<END]
def agg10(b):
    g=defaultdict(list)
    for x in b:g[(x.ot//600000)*600000].append(x)
    out=[]
    for ot in sorted(g):
        xs=sorted(g[ot],key=lambda z:z.ot)
        if not xs:continue
        out.append(Bar(ot,ot+599999,xs[0].o,max(z.h for z in xs),min(z.l for z in xs),xs[-1].c))
    return out

def ema(v,n):
    a=2/(n+1); p=None; out=[]
    for x in v: p=x if p is None else a*x+(1-a)*p; out.append(p)
    return out
def rma(v,n):
    out=[None]*len(v); seed=[]; p=None
    for i,x in enumerate(v):
        if p is None:
            seed.append(x)
            if len(seed)==n: p=sum(seed)/n; out[i]=p
        else: p=(p*(n-1)+x)/n; out[i]=p
    return out

def ind(b):
    n=len(b); c=[x.c for x in b]; h=[x.h for x in b]; l=[x.l for x in b]
    e8=ema(c,8); e20=ema(c,20); e21=ema(c,21); e50=ema(c,50)
    tr=[]; pdm=[]; mdm=[]
    for i,x in enumerate(b):
        if i==0: tr.append(x.h-x.l); pdm.append(0.0); mdm.append(0.0)
        else:
            up=x.h-b[i-1].h; dn=b[i-1].l-x.l
            pdm.append(up if up>dn and up>0 else 0.0); mdm.append(dn if dn>up and dn>0 else 0.0)
            tr.append(max(x.h-x.l,abs(x.h-b[i-1].c),abs(x.l-b[i-1].c)))
    atr14=rma(tr,14); atr5=rma(tr,5); atr20=rma(tr,20); p14=rma(pdm,14); m14=rma(mdm,14)
    pdi=[None]*n; mdi=[None]*n; dx=[0.0]*n
    for i in range(n):
        if atr14[i] not in (None,0) and p14[i] is not None:
            pdi[i]=100*p14[i]/atr14[i]; mdi[i]=100*m14[i]/atr14[i]; den=pdi[i]+mdi[i]; dx[i]=0 if den==0 else 100*abs(pdi[i]-mdi[i])/den
    adx=rma(dx,14)
    er=[None]*n
    for i in range(20,n):
        den=sum(abs(c[j]-c[j-1]) for j in range(i-19,i+1)); er[i]=0 if den==0 else abs(c[i]-c[i-20])/den
    hh10=[None]*n; ll10=[None]*n; hh20=[None]*n; ll20=[None]*n
    for i in range(20,n):
        hh10[i]=max(h[i-10:i]); ll10[i]=min(l[i-10:i]); hh20[i]=max(h[i-20:i]); ll20[i]=min(l[i-20:i])
    return dict(e8=e8,e20=e20,e21=e21,e50=e50,atr14=atr14,atr5=atr5,atr20=atr20,pdi=pdi,mdi=mdi,adx=adx,er=er,hh10=hh10,ll10=ll10,hh20=hh20,ll20=ll20)

def candle_strength(x,long):
    r=x.h-x.l
    if r<=0:return False
    body=abs(x.c-x.o)/r; clv=(x.c-x.l)/r
    return body>=0.45 and (clv>=0.70 if long else clv<=0.30)

def setup(name,i,b,z):
    if i<55:return None
    x=b[i]; prev=b[i-1]
    long_trend=z['e20'][i]>z['e50'][i] and z['e50'][i]>z['e50'][i-5]
    short_trend=z['e20'][i]<z['e50'][i] and z['e50'][i]<z['e50'][i-5]
    ad=z['adx'][i]; p=z['pdi'][i]; m=z['mdi'][i]
    long_adx=ad is not None and p is not None and m is not None and ad>=20 and p>m
    short_adx=ad is not None and p is not None and m is not None and ad>=20 and m>p
    if name=='BREAKOUT_ADX':
        if long_trend and long_adx and z['hh20'][i] is not None and x.c>z['hh20'][i] and candle_strength(x,True): return (1,x.l)
        if short_trend and short_adx and z['ll20'][i] is not None and x.c<z['ll20'][i] and candle_strength(x,False): return (-1,x.h)
    elif name=='PULLBACK_RECLAIM':
        if long_trend and long_adx and x.l<=z['e20'][i] and x.c>z['e20'][i] and x.c>prev.h and candle_strength(x,True): return (1,min(x.l,prev.l))
        if short_trend and short_adx and x.h>=z['e20'][i] and x.c<z['e20'][i] and x.c<prev.l and candle_strength(x,False): return (-1,max(x.h,prev.h))
    elif name=='FAST_STACK_ER':
        er=z['er'][i]
        if er is not None and er>=0.30 and z['e8'][i]>z['e21'][i]>z['e50'][i] and z['hh10'][i] is not None and x.c>z['hh10'][i] and candle_strength(x,True): return (1,x.l)
        if er is not None and er>=0.30 and z['e8'][i]<z['e21'][i]<z['e50'][i] and z['ll10'][i] is not None and x.c<z['ll10'][i] and candle_strength(x,False): return (-1,x.h)
    elif name=='COMPRESSION_BREAK':
        a5=z['atr5'][i]; a20=z['atr20'][i]
        compressed=a5 is not None and a20 not in (None,0) and a5/a20<=0.80
        if compressed and long_trend and z['hh10'][i] is not None and x.c>z['hh10'][i] and candle_strength(x,True): return (1,x.l)
        if compressed and short_trend and z['ll10'][i] is not None and x.c<z['ll10'][i] and candle_strength(x,False): return (-1,x.h)
    return None

ARCHS=('BREAKOUT_ADX','PULLBACK_RECLAIM','FAST_STACK_ER','COMPRESSION_BREAK')

def run(sym,tf,b,tick,arch,tp):
    z=ind(b); pending=None; active=None; trades=[]
    for i,x in enumerate(b):
        if x.ot>=END:break
        if active:
            d,e,s,t,sigt=active
            sl=(x.l<=s if d==1 else x.h>=s); hit=(x.h>=t if d==1 else x.l<=t)
            if sl or hit:
                rr=-1.0 if sl else tp
                trades.append({'symbol':sym,'tf':tf,'arch':arch,'tp':tp,'signal_time':sigt,'side':'LONG' if d==1 else 'SHORT','entry':e,'stop':s,'exit_time':x.ct,'R':rr})
                active=None
                continue
        if pending and i==pending[0]+1 and active is None:
            _,d,trig,st,sigt=pending
            confirm=(x.c>trig if d==1 else x.c<trig)
            if confirm:
                e=x.c
                if (d==1 and e>st) or (d==-1 and e<st):
                    t=e+tp*(e-st) if d==1 else e-tp*(st-e); active=(d,e,st,t,sigt)
            pending=None
        if pending and i>pending[0]+1: pending=None
        if active is None and pending is None and x.ct>=START:
            s=setup(arch,i,b,z)
            if s:
                d,st=s; trig=x.h+tick if d==1 else x.l-tick
                if abs(trig-st)/trig>=0.0015: pending=(i,d,trig,st,x.ct)
    for r in trades:
        for bps in BPS:r[f'net{bps}']=r['R']-(r['entry']/abs(r['entry']-r['stop']))*bps/10000
    return trades

def main():
    tickmap=json.load(open(BASE/'tv_tick_map.json')); out=[]; errs=[]
    for sym in symbols:
        try:
            b5=load5(sym); tick=float(tickmap[sym]['tick'])
            for tf in TFS:
                b=b5 if tf==5 else agg10(b5)
                for arch in ARCHS:
                    for tp in TPS: out.extend(run(sym,tf,b,tick,arch,tp))
            print('DONE',sym,len(out),flush=True)
        except Exception as e: errs.append({'symbol':sym,'error':repr(e)}); print('ERR',sym,repr(e),flush=True)
    with open(OUT/f'trades-{GROUP}.jsonl','w') as f:
        for r in out:f.write(json.dumps(r,separators=(',',':'))+'\n')
    json.dump(errs,open(OUT/f'errors-{GROUP}.json','w'),indent=2)
if __name__=='__main__':main()
