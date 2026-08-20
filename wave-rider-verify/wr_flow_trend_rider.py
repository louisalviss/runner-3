#!/usr/bin/env python3
import csv,io,json,math,os,time,zipfile
from collections import defaultdict
from datetime import datetime,timezone
from pathlib import Path
import requests

GROUP=int(os.getenv('GROUP','0')); GROUPS=int(os.getenv('GROUPS','6'))
BASE=Path(os.getenv('BASE_DIR','/tmp/base')); OUT=Path(os.getenv('OUT_DIR','/tmp/out')); OUT.mkdir(parents=True,exist_ok=True)
SYMBOLS=['BTCUSDT','ETHUSDT','SOLUSDT','XRPUSDT','BNBUSDT','DOGEUSDT','ADAUSDT','AVAXUSDT','LINKUSDT','DOTUSDT','BCHUSDT','LTCUSDT','TRXUSDT','AAVEUSDT','NEARUSDT','SUIUSDT','WIFUSDT','1000PEPEUSDT']
symbols=[s for i,s in enumerate(SYMBOLS) if i%GROUPS==GROUP]
TFS=(5,10); SETUPS=('FLOW_BREAK','FLOW_PULLBACK'); EXITS=('FIXED_2_0','FIXED_2_3','ATR_TRAIL_2_5','EMA20_EXIT','CHANNEL10_EXIT'); BPS=(4,6,8,10,12)
STATE=int(datetime(2023,12,1,tzinfo=timezone.utc).timestamp()*1000); START=int(datetime(2024,1,1,tzinfo=timezone.utc).timestamp()*1000); END=int(datetime(2026,8,15,tzinfo=timezone.utc).timestamp()*1000)
MONTHS=[(2023,12)]+[(2024,m) for m in range(1,13)]+[(2025,m) for m in range(1,13)]+[(2026,m) for m in range(1,8)]

class B:
 def __init__(self,r):
  self.ot=int(r[0]); self.o=float(r[1]); self.h=float(r[2]); self.l=float(r[3]); self.c=float(r[4]); self.ct=int(r[6]); self.qv=float(r[7]); self.tbq=float(r[10])

sess=requests.Session(); sess.headers['User-Agent']=f'runner3-flow-trend-{GROUP}/1.0'
def getzip(u):
 for k in range(4):
  try:
   r=sess.get(u,timeout=60)
   if r.status_code==404:return None
   r.raise_for_status(); return r.content
  except Exception:
   if k==3: raise
   time.sleep(.7*(k+1))
def readzip(data):
 if not data:return []
 with zipfile.ZipFile(io.BytesIO(data)) as z: text=z.read(z.namelist()[0]).decode()
 return [B(r) for r in csv.reader(io.StringIO(text)) if r and r[0].isdigit()]
def load5(sym):
 a=[]
 for y,m in MONTHS:
  fn=f'{sym}-5m-{y:04d}-{m:02d}.zip'; u=f'https://data.binance.vision/data/futures/um/monthly/klines/{sym}/5m/{fn}'
  try:a+=readzip(getzip(u))
  except Exception as e: print('FETCH_ERR',sym,fn,repr(e),flush=True)
 for d in range(1,15):
  fn=f'{sym}-5m-2026-08-{d:02d}.zip'; u=f'https://data.binance.vision/data/futures/um/daily/klines/{sym}/5m/{fn}'
  try:a+=readzip(getzip(u))
  except Exception as e: print('FETCH_ERR',sym,fn,repr(e),flush=True)
 ded={x.ot:x for x in a}; return [ded[k] for k in sorted(ded) if STATE<=k<END]
def agg10(a):
 g=defaultdict(list)
 for x in a:g[(x.ot//600000)*600000].append(x)
 out=[]
 for ot in sorted(g):
  xs=sorted(g[ot],key=lambda z:z.ot)
  if not xs:continue
  r=['0']*11; r[0]=ot; r[1]=xs[0].o; r[2]=max(z.h for z in xs); r[3]=min(z.l for z in xs); r[4]=xs[-1].c; r[6]=ot+599999; r[7]=sum(z.qv for z in xs); r[10]=sum(z.tbq for z in xs)
  out.append(B(r))
 return out

def ema(v,n):
 a=2/(n+1); p=None; out=[]
 for x in v:p=x if p is None else a*x+(1-a)*p; out.append(p)
 return out
def rma(v,n):
 out=[None]*len(v); p=None; seed=[]
 for i,x in enumerate(v):
  if p is None:
   seed.append(x)
   if len(seed)==n:p=sum(seed)/n; out[i]=p
  else:p=(p*(n-1)+x)/n; out[i]=p
 return out

def indicators(b,tf):
 n=len(b); c=[x.c for x in b]; e20=ema(c,20); e50=ema(c,50); tr=[]
 for i,x in enumerate(b):tr.append(x.h-x.l if i==0 else max(x.h-x.l,abs(x.h-b[i-1].c),abs(x.l-b[i-1].c)))
 atr=rma(tr,14); look=max(1,30//tf); qlook=max(look,60//tf); qbase=max(qlook+1,180//tf)
 hh10=[None]*n; ll10=[None]*n; ret30=[None]*n; rvol=[None]*n; taker=[None]*n
 for i in range(max(50,qbase),n):
  hh10[i]=max(x.h for x in b[i-10:i]); ll10[i]=min(x.l for x in b[i-10:i]); ret30[i]=c[i]/c[i-look]-1
  recent=sum(x.qv for x in b[i-qlook+1:i+1]); prior=[x.qv for x in b[i-qbase:i-qlook+1]]; denom=(sum(prior)/len(prior))*qlook if prior else 0; rvol[i]=recent/denom if denom>0 else None
  q=sum(x.qv for x in b[i-look+1:i+1]); tb=sum(x.tbq for x in b[i-look+1:i+1]); taker[i]=tb/q if q>0 else None
 return dict(e20=e20,e50=e50,atr=atr,hh10=hh10,ll10=ll10,ret30=ret30,rvol=rvol,taker=taker)

def strength(x,long):
 r=x.h-x.l
 if r<=0:return False
 body=abs(x.c-x.o)/r; clv=(x.c-x.l)/r
 return body>=.35 and (clv>=.65 if long else clv<=.35)

def align_btc(b,btc,btcz):
 mp={x.ot:i for i,x in enumerate(btc)}; out=[None]*len(b)
 for i,x in enumerate(b):
  j=mp.get(x.ot)
  if j is not None:out[i]=btcz['ret30'][j]
 return out

def signal(setup,i,b,z,btcret,sym):
 if i<60:return None
 x=b[i]; rv=z['rvol'][i]; tk=z['taker'][i]; rr=z['ret30'][i]; br=btcret[i]
 if None in (rv,tk,rr,br):return None
 longtrend=z['e20'][i]>z['e50'][i] and z['e50'][i]>z['e50'][i-5]
 shorttrend=z['e20'][i]<z['e50'][i] and z['e50'][i]<z['e50'][i-5]
 rel=rr-br if sym!='BTCUSDT' else rr
 flowL=rv>=1.30 and tk>=.55 and rel>0; flowS=rv>=1.30 and tk<=.45 and rel<0
 if setup=='FLOW_BREAK':
  if longtrend and flowL and x.c>z['hh10'][i] and strength(x,1):return (1,x.l)
  if shorttrend and flowS and x.c<z['ll10'][i] and strength(x,0):return (-1,x.h)
 else:
  p=b[i-1]
  if longtrend and flowL and x.l<=z['e20'][i] and x.c>z['e20'][i] and x.c>p.h and strength(x,1):return (1,min(x.l,p.l))
  if shorttrend and flowS and x.h>=z['e20'][i] and x.c<z['e20'][i] and x.c<p.l and strength(x,0):return (-1,max(x.h,p.h))
 return None

def run(sym,tf,b,tick,btc,btcz,setup,exitmode):
 z=indicators(b,tf); btcret=align_btc(b,btc,btcz); pending=None; active=None; out=[]
 for i,x in enumerate(b):
  if x.ot>=END:break
  if active:
   d,e,st,sigt,peak,trough=active; hit=(x.l<=st if d==1 else x.h>=st); reason=None; px=None
   if hit: reason='SL/TRAIL'; px=st
   if not reason and exitmode.startswith('FIXED'):
    tp=2.0 if exitmode=='FIXED_2_0' else 2.3; tgt=e+tp*(e-st) if d==1 else e-tp*(st-e); h=(x.h>=tgt if d==1 else x.l<=tgt)
    if h: reason='TP'; px=tgt
   if not reason and exitmode=='EMA20_EXIT':
    if (d==1 and x.c<z['e20'][i]) or (d==-1 and x.c>z['e20'][i]):reason='EMA20'; px=x.c
   if not reason and exitmode=='CHANNEL10_EXIT' and i>=10:
    chlo=min(y.l for y in b[i-10:i]); chhi=max(y.h for y in b[i-10:i])
    if (d==1 and x.c<chlo) or (d==-1 and x.c>chhi):reason='CHANNEL'; px=x.c
   if reason:
    rr=(px-e)*(1 if d==1 else -1)/abs(e-(active[2] if reason!='SL/TRAIL' else active[2]))
    # normalize to ORIGINAL structural risk stored separately below
    orig=active[7]; rr=(px-e)*(1 if d==1 else -1)/orig
    out.append({'symbol':sym,'tf':tf,'setup':setup,'exit':exitmode,'signal_time':sigt,'side':'LONG' if d==1 else 'SHORT','entry':e,'stop0':e-orig if d==1 else e+orig,'exit_time':x.ct,'R':rr,'exit_reason':reason})
    active=None; continue
   peak=max(peak,x.h); trough=min(trough,x.l)
   if exitmode=='ATR_TRAIL_2_5' and z['atr'][i] is not None:
    ns=peak-2.5*z['atr'][i] if d==1 else trough+2.5*z['atr'][i]; st=max(st,ns) if d==1 else min(st,ns)
   active=(d,e,st,sigt,peak,trough,active[6],active[7])
  if pending and i==pending[0]+1 and active is None:
   _,d,trig,s0,sigt=pending; ok=(x.c>trig if d==1 else x.c<trig)
   if ok:
    e=x.c; orig=abs(e-s0)
    if orig/e>=.0015:active=(d,e,s0,sigt,x.h,x.l,i,orig)
   pending=None
  if pending and i>pending[0]+1:pending=None
  if active is None and pending is None and x.ct>=START:
   s=signal(setup,i,b,z,btcret,sym)
   if s:
    d,s0=s; trig=x.h+tick if d==1 else x.l-tick; pending=(i,d,trig,s0,x.ct)
 for r in out:
  for bps in BPS:r[f'net{bps}']=r['R']-(r['entry']/abs(r['entry']-r['stop0']))*bps/10000
 return out

def main():
 tickmap=json.load(open(BASE/'tv_tick_map.json')); btc5=load5('BTCUSDT'); allout=[]; errs=[]
 btc_by_tf={5:btc5,10:agg10(btc5)}; btcz={tf:indicators(btc_by_tf[tf],tf) for tf in TFS}
 for sym in symbols:
  try:
   b5=btc5 if sym=='BTCUSDT' else load5(sym); tick=float(tickmap[sym]['tick'])
   for tf in TFS:
    b=b5 if tf==5 else agg10(b5)
    for s in SETUPS:
     for e in EXITS:allout+=run(sym,tf,b,tick,btc_by_tf[tf],btcz[tf],s,e)
   print('DONE',sym,len(allout),flush=True)
  except Exception as e:errs.append({'symbol':sym,'error':repr(e)}); print('ERR',sym,repr(e),flush=True)
 with open(OUT/f'trades-{GROUP}.jsonl','w') as f:
  for r in allout:f.write(json.dumps(r,separators=(',',':'))+'\n')
 json.dump(errs,open(OUT/f'errors-{GROUP}.json','w'),indent=2)
if __name__=='__main__':main()
