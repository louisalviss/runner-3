#!/usr/bin/env python3
from __future__ import annotations
import csv, io, json, zipfile, importlib.util, sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
import requests

ROOT=Path(__file__).resolve().parents[1]
EXACT=ROOT/'wave-rider-verify'/'reference_verify_v2513_exact.py'
spec=importlib.util.spec_from_file_location('wrexact',EXACT); wr=importlib.util.module_from_spec(spec); sys.modules[spec.name]=wr; spec.loader.exec_module(wr)
base=wr.base
SYMBOL='TRXUSDT'; TF=5; S3='https://data.binance.vision/data/futures/um'
ENGINE_START=date(2024,12,1); FETCH_END=date(2026,8,17)

def month_iter(a,b):
 y,m=a.year,a.month
 while (y,m)<=(b.year,b.month):
  yield y,m; m+=1
  if m==13: y+=1; m=1

def parse_zip(content):
 bars=[]; prices=[]
 with zipfile.ZipFile(io.BytesIO(content)) as z: text=z.read(z.namelist()[0]).decode()
 for row in csv.reader(io.StringIO(text)):
  if not row or not row[0].isdigit(): continue
  bars.append(base.Bar(int(row[0]),int(row[6]),*map(float,row[1:5]))); prices.extend(row[1:5])
 return bars,prices

def fetch():
 s=requests.Session(); bars=[]; prices=[]
 for y,m in month_iter(ENGINE_START,date(2026,7,31)):
  ym=f'{y:04d}-{m:02d}'; u=f'{S3}/monthly/klines/{SYMBOL}/{TF}m/{SYMBOL}-{TF}m-{ym}.zip'; r=s.get(u,timeout=45)
  if r.status_code==404: continue
  r.raise_for_status(); b,p=parse_zip(r.content); bars+=b; prices+=p
 d=date(2026,8,1)
 while d<=FETCH_END:
  ds=d.isoformat(); u=f'{S3}/daily/klines/{SYMBOL}/{TF}m/{SYMBOL}-{TF}m-{ds}.zip'; r=s.get(u,timeout=45)
  if r.status_code!=404:
   r.raise_for_status(); b,p=parse_zip(r.content); bars+=b; prices+=p
  d+=timedelta(days=1)
 ded={x.ot:x for x in bars}; bars=[ded[k] for k in sorted(ded)]
 return bars,base.infer_tick(prices)

def ms_vn(y,m,d,hh=0,mm=0):
 # VN UTC+7 -> UTC
 return int(datetime(y,m,d,hh,mm,tzinfo=timezone(timedelta(hours=7))).timestamp()*1000)

def pivot_variant(mode):
 def f(v,left,right,high=True):
  raw=[None]*len(v)
  for conf in range(left+right,len(v)):
   c=conf-right; center=v[c]; L=v[c-left:c]; R=v[c+1:c+right+1]
   if high:
    if mode=='unique': ok=all(x<center for x in L+R)
    elif mode=='allow_all': ok=all(x<=center for x in L+R)
    elif mode=='right_strict': ok=all(x<=center for x in L) and all(x<center for x in R)
    elif mode=='left_strict': ok=all(x<center for x in L) and all(x<=center for x in R)
   else:
    if mode=='unique': ok=all(x>center for x in L+R)
    elif mode=='allow_all': ok=all(x>=center for x in L+R)
    elif mode=='right_strict': ok=all(x>=center for x in L) and all(x>center for x in R)
    elif mode=='left_strict': ok=all(x>center for x in L) and all(x>=center for x in R)
   if ok: raw[conf]=center
  return [None]+raw[:-1],0
 return f

def main():
 bars,tick=fetch(); orig=base.pivots
 windows={
  '28Jul_00_to_12':(ms_vn(2026,7,28,0),ms_vn(2026,7,28,12)),
  '28Jul_to_29Jul':(ms_vn(2026,7,28),ms_vn(2026,7,29)),
  '28Jul_to_01Aug':(ms_vn(2026,7,28),ms_vn(2026,8,1)),
  '28Jul_to_06Aug':(ms_vn(2026,7,28),ms_vn(2026,8,6)),
  '28Jul_to_16Aug':(ms_vn(2026,7,28),ms_vn(2026,8,16)),
 }
 out={}
 for mode in ['unique','allow_all','right_strict','left_strict']:
  base.pivots=pivot_variant(mode); out[mode]={}
  for name,(a,b) in windows.items():
   tr,s=wr.run_window_exact(TF,bars,tick,a,b,engine_start_ms=int(datetime(2024,12,1,tzinfo=timezone.utc).timestamp()*1000))
   out[mode][name]={'trades':s['trades'],'total_r':round(s['total_r'],6),'first_signals':[t.signal_time for t in tr[:5]]}
 base.pivots=orig
 print(json.dumps(out,indent=2)); Path('trx_pivot_mode_sweep.json').write_text(json.dumps(out,indent=2))

if __name__=='__main__': main()
