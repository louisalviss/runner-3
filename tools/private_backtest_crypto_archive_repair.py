#!/usr/bin/env python3
from __future__ import annotations
import argparse, hashlib, io, json, tempfile, urllib.error, urllib.request, zipfile
from pathlib import Path
import private_backtest_worker_v2 as core

PROJECT='private-backtest'

def helper_text(venue:str, half_spread_bps:float)->str:
    root='spot' if venue=='spot' else 'futures/um'
    return f'''from __future__ import annotations
import csv, io, urllib.error, urllib.request, zipfile
import pandas as pd
BID=0; ASK=1; ROOT={root!r}; HALF={float(half_spread_bps)!r}; BASE="https://data.binance.vision/data/"+ROOT

def resolve_symbol(symbol):
    s=str(symbol).strip().upper()
    return s if s in ("BTCUSDT","ETHUSDT") else None

def pick_const(names):
    for n in names:
        if "BID" in n: return BID
        if "ASK" in n or "OFFER" in n: return ASK
    raise AttributeError(names)

def month_chunks(start,end):
    cur=pd.Timestamp(start); stop=pd.Timestamp(end)
    cur=cur.tz_localize("UTC") if cur.tzinfo is None else cur.tz_convert("UTC")
    stop=stop.tz_localize("UTC") if stop.tzinfo is None else stop.tz_convert("UTC")
    while cur<stop:
        if cur.month==12: nxt=pd.Timestamp(year=cur.year+1,month=1,day=1,tz="UTC")
        else: nxt=pd.Timestamp(year=cur.year,month=cur.month+1,day=1,tz="UTC")
        yield cur,min(nxt,stop); cur=nxt

def _get_zip(url):
    req=urllib.request.Request(url,headers={{"User-Agent":"runner3-super-rsi-public-archive/1"}})
    with urllib.request.urlopen(req,timeout=90) as r: raw=r.read()
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        names=[n for n in z.namelist() if n.lower().endswith('.csv')]
        if not names: raise ValueError("archive has no csv")
        return z.read(names[0]).decode('utf-8')

def _rows_from_csv(text):
    out=[]
    for row in csv.reader(io.StringIO(text)):
        if not row or not str(row[0]).lstrip('-').isdigit(): continue
        try: out.append((int(row[0]),float(row[1]),float(row[2]),float(row[3]),float(row[4])))
        except Exception: continue
    return out

def _monthly_url(symbol,interval,t):
    ym=t.strftime('%Y-%m'); name=f"{{symbol}}-{{interval}}-{{ym}}.zip"
    return f"{{BASE}}/monthly/klines/{{symbol}}/{{interval}}/{{name}}"

def _daily_url(symbol,interval,t):
    ymd=t.strftime('%Y-%m-%d'); name=f"{{symbol}}-{{interval}}-{{ymd}}.zip"
    return f"{{BASE}}/daily/klines/{{symbol}}/{{interval}}/{{name}}"

def _load_rows(symbol,interval,start,end):
    try:
        return _rows_from_csv(_get_zip(_monthly_url(symbol,interval,start)))
    except urllib.error.HTTPError as e:
        if e.code not in (404,403): raise
    rows=[]; d=start.normalize(); stop=end.normalize()
    if end>stop: stop=stop+pd.Timedelta(days=1)
    while d<stop:
        try: rows.extend(_rows_from_csv(_get_zip(_daily_url(symbol,interval,d))))
        except urllib.error.HTTPError as e:
            if e.code!=404: raise
        d+=pd.Timedelta(days=1)
    return rows

def _ts(v):
    unit='us' if abs(int(v))>=100_000_000_000_000 else 'ms'
    return pd.to_datetime(int(v),unit=unit,utc=True)

def fetch_side(instrument,offer_side,start,end,source_minutes):
    start=pd.Timestamp(start); end=pd.Timestamp(end)
    start=start.tz_localize('UTC') if start.tzinfo is None else start.tz_convert('UTC')
    end=end.tz_localize('UTC') if end.tzinfo is None else end.tz_convert('UTC')
    interval=f"{{int(source_minutes)}}m"; raw=_load_rows(instrument,interval,start,end)
    rows=[]
    for ts,o,h,l,c in raw:
        t=_ts(ts)
        if start<=t<end: rows.append((t,o,h,l,c))
    if not rows: return pd.DataFrame(columns=['open','high','low','close'])
    idx=pd.DatetimeIndex([x[0] for x in rows])
    out=pd.DataFrame({{'open':[x[1] for x in rows],'high':[x[2] for x in rows],'low':[x[3] for x in rows],'close':[x[4] for x in rows]}},index=idx)
    mult=1.0+(HALF/10000.0 if offer_side==ASK else -HALF/10000.0)
    out=out*mult
    return out[~out.index.duplicated(keep='last')].sort_index()
'''

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--scope',required=True); ap.add_argument('--venue',choices=['spot','perp'],required=True); ap.add_argument('--half-spread-bps',type=float,required=True); a=ap.parse_args()
    work=Path(tempfile.mkdtemp(prefix='crypto-archive-repair-')); mp=work/'manifest.json'
    core.download_artifact(PROJECT,a.scope,'manifest.json',mp); m=json.loads(mp.read_text(encoding='utf-8'))
    hp=work/'exp.py'; hp.write_text(helper_text(a.venue,a.half_spread_bps),encoding='utf-8')
    sha=core.sha256_file(hp); core.upload_artifact(PROJECT,a.scope,'package/exp.py',hp,'text/x-python; charset=utf-8')
    m['files']['helper']={'name':'package/exp.py','sha256':sha}; m['data_transport']='Binance Public Data archive data.binance.vision daily/monthly'; m['transport_repair']='restaged after REST API HTTP 451; profile/gates unchanged'
    mp.write_text(json.dumps(m,ensure_ascii=False,indent=2)+'\n',encoding='utf-8'); core.upload_artifact(PROJECT,a.scope,'manifest.json',mp,'application/json; charset=utf-8')
    print(json.dumps({'scope':a.scope,'venue':a.venue,'helper_sha256':sha,'transport':m['data_transport']}))
if __name__=='__main__': main()
