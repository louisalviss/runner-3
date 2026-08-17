#!/usr/bin/env python3
from __future__ import annotations
import csv, io, math, zipfile, importlib.util, sys, json
from datetime import datetime, timezone
from pathlib import Path
import requests

ROOT=Path(__file__).resolve().parents[1]
REF=ROOT/'wave-rider-verify'/'reference_verify.py'
spec=importlib.util.spec_from_file_location('wrbase',REF); base=importlib.util.module_from_spec(spec); sys.modules[spec.name]=base; spec.loader.exec_module(base)

SYMBOL='TRXUSDT'; TF=5
URL=f'https://data.binance.vision/data/futures/um/monthly/klines/{SYMBOL}/{TF}m/{SYMBOL}-{TF}m-2026-07.zip'

def fetch():
 r=requests.get(URL,timeout=60); r.raise_for_status()
 with zipfile.ZipFile(io.BytesIO(r.content)) as z: text=z.read(z.namelist()[0]).decode()
 bars=[]
 for row in csv.reader(io.StringIO(text)):
  if not row or not row[0].isdigit(): continue
  bars.append(base.Bar(int(row[0]),int(row[6]),*map(float,row[1:5])))
 return bars

def rma(v,n):
 out=[None]*len(v); p=None; seed=[]
 for i,x in enumerate(v):
  if p is None:
   seed.append(x)
   if len(seed)==n: p=sum(seed)/n; out[i]=p
  else: p=(p*(n-1)+x)/n; out[i]=p
 return out

def ema(v,n):
 a=2/(n+1); out=[]; p=None
 for x in v:
  p=x if p is None else a*x+(1-a)*p; out.append(p)
 return out

def roll(v,n,fn):
 out=[None]*len(v)
 for i in range(n-1,len(v)): out[i]=fn(v[i-n+1:i+1])
 return out

def main():
 b=fetch(); ind,pht,plt=base.calc_ind(b)
 c=[x.c for x in b]; h=[x.h for x in b]; l=[x.l for x in b]; e=ema(c,base.EMA_LEN)
 tr=[]
 for i,x in enumerate(b): tr.append(x.h-x.l if i==0 else max(x.h-x.l,abs(x.h-b[i-1].c),abs(x.l-b[i-1].c)))
 a10=rma(tr,base.ATR_ANGLE); a14=rma(tr,base.SIGNAL_ATR); tsum=roll(tr,base.CHOP_LEN,sum); rh=roll(h,base.CHOP_LEN,max); rl=roll(l,base.CHOP_LEN,min)
 # Reconstruct current support/resistance exactly as base calc does, so raw values are visible.
 ph,_=base.pivots(h,base.LEFT,base.RIGHT,True); pl,_=base.pivots(l,base.LEFT,base.RIGHT,False)
 res=sup=None; resarr=[]; suparr=[]
 for i in range(len(b)):
  if ph[i] is not None and ph[i]!=res: res=ph[i]
  if pl[i] is not None and pl[i]!=sup: sup=pl[i]
  resarr.append(res); suparr.append(sup)

 rows=[]
 for i,x in enumerate(b):
  dt=datetime.fromtimestamp(x.ot/1000,tz=timezone.utc)
  if not (datetime(2026,7,27,17,30,tzinfo=timezone.utc) <= dt <= datetime(2026,7,27,18,30,tzinfo=timezone.utc)): continue
  an=None
  if i>=base.ANGLE_PERIOD and a10[i] not in (None,0): an=math.degrees(math.atan((e[i]-e[i-base.ANGLE_PERIOD])/a10[i]/base.ANGLE_PERIOD))
  anprev=None
  if i>0 and i-1>=base.ANGLE_PERIOD and a10[i-1] not in (None,0): anprev=math.degrees(math.atan((e[i-1]-e[i-1-base.ANGLE_PERIOD])/a10[i-1]/base.ANGLE_PERIOD))
  outside=an is not None and (an>base.ANGLE_LEVEL or an<-base.ANGLE_LEVEL)
  ar=an is not None and anprev is not None and an<anprev and outside
  ch=None
  if tsum[i] is not None and rh[i] is not None and rh[i]>rl[i] and tsum[i]>0: ch=100*math.log10(tsum[i]/(rh[i]-rl[i]))/math.log10(base.CHOP_LEN)
  sra=None if a14[i] in (None,0) else (x.h-x.l)/a14[i]
  allowed,sexit=base.session_flags(x.ct,TF*60000)
  z=ind[i]
  short_ready=z['hb'] and x.c<z['ema'] and z['ar'] and z['chop_ok'] and z['sup'] is not None
  short_signal=allowed and z['sra_ok'] and x.c<x.o and short_ready and x.c<z['sup'] and x.h>=z['sup']
  rows.append(dict(
   open_utc=dt.isoformat(), close_utc=datetime.fromtimestamp(x.ct/1000,tz=timezone.utc).isoformat(),
   open_vn=(dt.replace(tzinfo=timezone.utc).timestamp()+7*3600),
   o=x.o,h=x.h,l=x.l,c=x.c,ema=e[i],support=suparr[i],resistance=resarr[i],
   hb=z['hb'], below_ema=x.c<z['ema'], angle=an, angle_prev=anprev, angle_red=ar,
   chop=ch,chop_ok=z['chop_ok'],signal_range_atr=sra,range_ok=z['sra_ok'],
   bearish=x.c<x.o, close_below_support=(z['sup'] is not None and x.c<z['sup']), retest=(z['sup'] is not None and x.h>=z['sup']),
   session_allowed=allowed, session_exit=sexit, short_ready=short_ready, SHORT_SIGNAL=short_signal,
   ph_shifted=ph[i],pl_shifted=pl[i]
  ))
 print(json.dumps({'pivot_high_ties':pht,'pivot_low_ties':plt,'rows':rows},indent=2))
 Path('trx_0105_diag.json').write_text(json.dumps(rows,indent=2))

if __name__=='__main__': main()
