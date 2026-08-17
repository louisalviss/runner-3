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

def pivot_candidates(v,left,right,high=False):
 out=[]
 for conf in range(left+right,len(v)):
  c=conf-right; center=v[c]; L=v[c-left:c]; R=v[c+1:c+right+1]
  if high: anyok=all(x<=center for x in L+R)
  else: anyok=all(x>=center for x in L+R)
  if anyok:
   eq_left=[j for j,x in enumerate(L,start=c-left) if x==center]
   eq_right=[j for j,x in enumerate(R,start=c+1) if x==center]
   out.append((conf,c,center,eq_left,eq_right))
 return out

def main():
 b=fetch(); lows=[x.l for x in b]
 cand=[]
 for conf,c,level,eqL,eqR in pivot_candidates(lows,base.LEFT,base.RIGHT,False):
  # candidate is available to Pine source[1] one bar after confirmation
  available=conf+1
  if level==0.32828 and available < len(b):
   cand.append({
    'pivot_open_utc':datetime.fromtimestamp(b[c].ot/1000,tz=timezone.utc).isoformat(),
    'pivot_open_vn':datetime.fromtimestamp(b[c].ot/1000,tz=timezone.utc).astimezone(timezone.utc).timestamp()+7*3600,
    'level':level,
    'equal_left':[datetime.fromtimestamp(b[j].ot/1000,tz=timezone.utc).isoformat() for j in eqL],
    'equal_right':[datetime.fromtimestamp(b[j].ot/1000,tz=timezone.utc).isoformat() for j in eqR],
    'confirmation_open_utc':datetime.fromtimestamp(b[conf].ot/1000,tz=timezone.utc).isoformat(),
    'ph1_available_open_utc':datetime.fromtimestamp(b[available].ot/1000,tz=timezone.utc).isoformat(),
    'window':[{'t':datetime.fromtimestamp(b[j].ot/1000,tz=timezone.utc).isoformat(),'low':b[j].l,'high':b[j].h} for j in range(c-base.LEFT,c+base.RIGHT+1)]
   })
 print(json.dumps(cand[-5:],indent=2)); Path('trx_0105_diag.json').write_text(json.dumps(cand[-5:],indent=2))
if __name__=='__main__': main()
