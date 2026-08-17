#!/usr/bin/env python3
from __future__ import annotations
import csv, io, importlib.util, os, sys, time, zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
import requests

spec=importlib.util.spec_from_file_location('wrp','wave-rider-verify/reference_verify_parity.py')
m=importlib.util.module_from_spec(spec); sys.modules[spec.name]=m; spec.loader.exec_module(m)
r=m.ref
r.TFS=(5,)

def month_iter(a: datetime, b: datetime):
    y,mn=a.year,a.month
    while (y,mn) <= (b.year,b.month):
        yield y,mn
        mn += 1
        if mn==13: y+=1; mn=1

def parse_zip_bytes(content: bytes, lo_ms: int, hi_ms: int, bars, prices):
    with zipfile.ZipFile(io.BytesIO(content)) as z:
        text=z.read(z.namelist()[0]).decode()
    for row in csv.reader(io.StringIO(text)):
        if not row or not row[0].isdigit():
            continue
        ot=int(row[0])
        if ot < lo_ms or ot > hi_ms:
            continue
        bars.append(r.Bar(ot,int(row[6]),*map(float,row[1:5])))
        prices.extend(row[1:5])

def get_with_retry(sess, url, tries=3):
    last=None
    for k in range(tries):
        try:
            resp=sess.get(url,timeout=60)
            if resp.status_code==404:
                return None
            resp.raise_for_status()
            return resp.content
        except Exception as e:
            last=e; time.sleep(1+k)
    if last: raise last

def fetch_monthly_mix():
    sym=r.SYMBOL
    start=datetime.fromisoformat(m._DATA_START).replace(tzinfo=timezone.utc)-timedelta(days=r.WARMUP_DAYS)
    end=datetime.fromisoformat(m._DATA_END).replace(tzinfo=timezone.utc)+timedelta(days=1)-timedelta(milliseconds=1)
    lo_ms=int(start.timestamp()*1000); hi_ms=int(end.timestamp()*1000)
    sess=requests.Session(); sess.headers['User-Agent']='runner-3-wr-monthly/1.0'
    bars=[]; prices=[]; missing=[]
    for y,mo in month_iter(start,end):
        first=datetime(y,mo,1,tzinfo=timezone.utc)
        if mo==12: nextm=datetime(y+1,1,1,tzinfo=timezone.utc)
        else: nextm=datetime(y,mo+1,1,tzinfo=timezone.utc)
        month_last=nextm-timedelta(milliseconds=1)
        # Use monthly archives only for fully covered months. Partial edge months use daily archives.
        full = start <= first and end >= month_last
        if full:
            url=f'https://data.binance.vision/data/futures/um/monthly/klines/{sym}/1m/{sym}-1m-{y:04d}-{mo:02d}.zip'
            content=get_with_retry(sess,url)
            if content is not None:
                parse_zip_bytes(content,lo_ms,hi_ms,bars,prices)
                continue
        d=max(start,first)
        de=min(end,month_last)
        cur=datetime(d.year,d.month,d.day,tzinfo=timezone.utc)
        last_day=datetime(de.year,de.month,de.day,tzinfo=timezone.utc)
        while cur<=last_day:
            ds=cur.date().isoformat()
            url=f'https://data.binance.vision/data/futures/um/daily/klines/{sym}/1m/{sym}-1m-{ds}.zip'
            content=get_with_retry(sess,url)
            if content is None:
                missing.append(ds)
            else:
                parse_zip_bytes(content,lo_ms,hi_ms,bars,prices)
            cur += timedelta(days=1)
    ded={x.ot:x for x in bars}; bars=[ded[k] for k in sorted(ded)]
    if not bars: raise RuntimeError('no Binance candles fetched')
    return bars,r.infer_tick(prices),missing

r.fetch_1m=fetch_monthly_mix
raise SystemExit(r.main())
