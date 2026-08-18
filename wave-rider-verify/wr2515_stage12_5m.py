#!/usr/bin/env python3
from __future__ import annotations
import csv, io, json, math, os, sys, time, types, zipfile
from bisect import bisect_left, bisect_right
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo
import requests

# Frozen research track: v2.5.15 semantics, 5m only.
# Stage1 thresholds are copied from canonical Stage 1 Watchlist and Trade Flow.
# Stage2 thresholds are copied from frozen Stage2 suitability memo; only timeframe changes 3m -> 5m.
START = datetime(2025,1,1,tzinfo=timezone.utc)
END_EXCL = datetime(2026,8,15,tzinfo=timezone.utc)
STATE = datetime(2024,12,1,tzinfo=timezone.utc)
START_MS=int(START.timestamp()*1000); END_MS=int(END_EXCL.timestamp()*1000); STATE_MS=int(STATE.timestamp()*1000)
TF=5; TF_MS=300_000
TP_R=2.3; RISK_PCT=1.0; INIT=100000.0
S1_QV24=100_000_000.0; S1_AVG10=200_000_000.0; S1_VOL7=0.06; S1_ADR14=0.05
S2_LOOKBACK_MS=14*86400_000; S2_MIN_SETUPS=5; S2_TOPN=5
VN=ZoneInfo('Asia/Ho_Chi_Minh'); NY=ZoneInfo('America/New_York')
SHARD=int(os.getenv('SHARD','0')); SHARDS=int(os.getenv('SHARDS','1'))
BASE_DIR=Path(os.getenv('BASE_DIR','/tmp/base')); OUT=Path(os.getenv('OUT_DIR','/tmp/stage12'))
OUT.mkdir(parents=True,exist_ok=True)

# Load exact reference engine and patch only the already-verified Pine parity semantics.
def load_ref():
    p=Path(os.getenv('REFERENCE_VERIFY','/tmp/reference_verify.py'))
    src=p.read_text().replace('sra<=SIGNAL_RANGE_MAX','sra<SIGNAL_RANGE_MAX')
    old="""        if v[c]==ext:\n            if sum(x==ext for x in w)==1: base[conf]=v[c]\n            else: ties+=1\n"""
    new="""        if v[c]==ext:\n            if all(x!=ext for x in v[c+1:c+right+1]): base[conf]=v[c]\n            else: ties+=1\n"""
    if src.count(old)!=1: raise RuntimeError('pivot patch anchor missing')
    src=src.replace(old,new,1)
    m=types.ModuleType('wr2515ref');m.__file__='reference_verify.py';sys.modules[m.__name__]=m
    exec(compile(src,m.__file__,'exec'),m.__dict__)
    return m
REF=load_ref(); Bar=REF.Bar; Plan=REF.Plan; calc_ind=REF.calc_ind; next_bracket=REF.next_bracket; session_flags=REF.session_flags

sess=requests.Session();sess.headers['User-Agent']='runner3-wr2515-stage12/1.0'
months=[(2024,12)]+[(2025,m) for m in range(1,13)]+[(2026,m) for m in range(1,8)]

def getzip(url):
    for k in range(3):
        try:
            r=sess.get(url,timeout=45)
            if r.status_code==404:return None
            r.raise_for_status();return r.content
        except Exception:
            if k==2: raise
            time.sleep(.5*(k+1))

def decode(data):
    out=[]
    if not data:return out
    with zipfile.ZipFile(io.BytesIO(data)) as z: txt=z.read(z.namelist()[0]).decode()
    for row in csv.reader(io.StringIO(txt)):
        if not row or not row[0].isdigit(): continue
        # open_time, open, high, low, close, base_volume, close_time, quote_volume
        try: out.append((int(row[0]),float(row[1]),float(row[2]),float(row[3]),float(row[4]),float(row[5]),int(row[6]),float(row[7])))
        except Exception: continue
    return out

def load(sym):
    raw=[]
    for y,m in months:
        fn=f'{sym}-5m-{y:04d}-{m:02d}.zip';u=f'https://data.binance.vision/data/futures/um/monthly/klines/{sym}/5m/{fn}'
        try: raw += decode(getzip(u))
        except Exception as e: print('FETCH_ERR',sym,fn,repr(e),flush=True)
    for d in range(1,16):
        fn=f'{sym}-5m-2026-08-{d:02d}.zip';u=f'https://data.binance.vision/data/futures/um/daily/klines/{sym}/5m/{fn}'
        try: raw += decode(getzip(u))
        except Exception as e: print('FETCH_ERR',sym,fn,repr(e),flush=True)
    ded={r[0]:r for r in raw}; rows=[ded[k] for k in sorted(ded) if STATE_MS<=k<END_MS]
    return rows

def checkpoint_rows():
    # The session date is the VN date after applying the canonical 06:00 rollover.
    out=[]
    d=date(2024,12,31)
    while d<=date(2026,8,15):
        cp=datetime(d.year,d.month,d.day,15,30,tzinfo=VN)
        ms=int(cp.timestamp()*1000)
        if START_MS<=ms<END_MS: out.append((ms,(cp-timedelta(hours=6)).date().isoformat(),'VN1530'))
        d+=timedelta(days=1)
    d=date(2024,12,31)
    while d<=date(2026,8,15):
        for hh,mm,label in [(10,0,'ET1000'),(12,45,'ET1245'),(15,45,'ET1545')]:
            cp=datetime(d.year,d.month,d.day,hh,mm,tzinfo=NY)
            ms=int(cp.timestamp()*1000)
            if START_MS<=ms<END_MS:
                cpvn=cp.astimezone(VN); out.append((ms,(cpvn-timedelta(hours=6)).date().isoformat(),label))
        d+=timedelta(days=1)
    # exact time de-dup and chronological order
    return sorted({x[0]:x for x in out}.values(),key=lambda x:x[0])
CHECKPOINTS=checkpoint_rows(); CP_MS=[x[0] for x in CHECKPOINTS]

def daily_metrics(rows, cp):
    # Only completed 5m bars available strictly before checkpoint are used.
    cts=[r[6] for r in rows]; j=bisect_left(cts,cp)
    if j<=0:return None
    cut=rows[:j]
    # Exact rolling 24h quote volume from kline quote-volume field.
    lo=cp-86400_000
    ots=[r[0] for r in cut]; a=bisect_left(ots,lo)
    qv24=sum(r[7] for r in cut[a:])
    days={}
    for r in cut:
        day=datetime.fromtimestamp(r[0]/1000,tz=timezone.utc).date().isoformat()
        x=days.get(day)
        if x is None: days[day]=[r[1],r[2],r[3],r[4],r[5]]
        else:
            x[1]=max(x[1],r[2]);x[2]=min(x[2],r[3]);x[3]=r[4];x[4]+=r[5]
    ds=[days[k] for k in sorted(days)]
    if len(ds)<14:return None
    last14=ds[-14:]; last10=ds[-10:]; last7=ds[-7:]
    avg10=sum(x[3]*x[4] for x in last10)/10.0
    vol7=sum((x[1]-x[2])/abs(x[2]) for x in last7 if x[2]!=0)/7.0
    cur=last14[-1][3]
    adr14=((sum(x[1] for x in last14)/14.0)-(sum(x[2] for x in last14)/14.0))/abs(cur) if cur else None
    if adr14 is None:return None
    return qv24,avg10,vol7,adr14

def run_symbol(sym,tick,rows):
    if len(rows)<1000:return [],[],{'symbol':sym,'bars':len(rows),'reason':'insufficient_bars'}
    bars=[Bar(r[0],r[6],r[1],r[2],r[3],r[4]) for r in rows]
    ind,_,_=calc_ind(bars); eq=INIT; pending=active=None; setups=[]
    # Setup ledger follows actual strategy state: only a signal capable of creating a pending order counts.
    def close(i,reason,px):
        nonlocal active,eq
        p=active; both=bars[i].h>=max(p.s,p.t) and bars[i].l<=min(p.s,p.t) and reason in ('TP','SL')
        if both:reason='AMBIG->SL'
        cr=TP_R if reason=='TP' else (-1.0 if reason in ('SL','AMBIG->SL') else ((px-p.e)*(1 if p.d==1 else -1)*p.qty/p.risk))
        eq+=cr*p.risk;active=None;return True
    for i,x in enumerate(bars):
        closed=False
        if active is not None:
            r,px=next_bracket(active,x,None)
            if r:closed=close(i,r,px)
        if active is None and pending is not None and i==pending.sig_i+1 and not closed:
            fill=(pending.d==1 and round(x.h/tick)>=round(pending.e/tick)) or (pending.d==-1 and round(x.l/tick)<=round(pending.e/tick))
            if fill:
                gap=(pending.d==1 and round(x.o/tick)>=round(pending.e/tick)) or (pending.d==-1 and round(x.o/tick)<=round(pending.e/tick))
                active=pending;pending=None;r,px=next_bracket(active,x,None if gap else active.e)
                if r:closed=close(i,r,px)
        allowed,sexit=session_flags(x.ct+1,TF_MS)
        if active is not None and not closed:
            z=ind[i];le=active.d==1 and x.c<z['ema'] and not z['ha'] and not z['ema_up'];se=active.d==-1 and x.c>z['ema'] and not z['hb'] and bool(z['ema_up'])
            if sexit:closed=close(i,'SESSION',x.c)
            elif le or se:closed=close(i,'EMA',x.c)
        if pending is not None and i>=pending.sig_i+1 and active is None:pending=None
        if x.ct<START_MS or x.ct>=END_MS:continue
        if active is None and pending is None and not closed:
            z=ind[i];lr=z['ha'] and x.c>z['ema'] and z['ag'] and z['chop_ok'] and z['res'] is not None;sr=z['hb'] and x.c<z['ema'] and z['ar'] and z['chop_ok'] and z['sup'] is not None
            nl=allowed and z['sra_ok'] and x.c>x.o and lr and x.c>z['res'] and x.l<=z['res'];sh=allowed and z['sra_ok'] and x.c<x.o and sr and x.c<z['sup'] and x.h>=z['sup']
            if nl or sh:
                if nl:d=1;e=x.h+tick;s=x.l-tick;t=e+TP_R*(e-s)
                else:d=-1;e=x.l-tick;s=x.h+tick;t=e-TP_R*(s-e)
                raw=(eq*RISK_PCT/100)/abs(e-s);q=math.floor(raw);risk=abs(e-s)*q
                if q>0 and risk>0:
                    pending=Plan(d,e,s,t,risk,q,i,x.ct,x.h,x.l)
                    stop_pct=abs(e-s)/abs(e)*100 if e else None
                    if stop_pct and stop_pct>0:
                        setups.append({'symbol':sym,'signal_time':x.ct,'stop_pct':stop_pct,'required_x':1.0/stop_pct})
    passes=[]
    for cp,session_date,label in CHECKPOINTS:
        m=daily_metrics(rows,cp)
        if m is None:continue
        qv24,avg10,vol7,adr14=m
        if qv24>=S1_QV24 and avg10>=S1_AVG10 and vol7>S1_VOL7 and adr14>=S1_ADR14:
            passes.append({'symbol':sym,'checkpoint':cp,'session_date':session_date,'mode':label,'qv24':qv24,'avg10':avg10,'vol7':vol7,'adr14':adr14})
    return setups,passes,{'symbol':sym,'bars':len(rows),'setups':len(setups),'passes':len(passes)}

def main_shard():
    tv=json.load(open(BASE_DIR/'tv_tick_map.json')); summary=json.load(open(BASE_DIR/'summary.json'))
    have={x['symbol'] for x in summary}; symbols=sorted(set(tv)&have); symbols=[s for i,s in enumerate(symbols) if i%SHARDS==SHARD]
    setups=[];passes=[];meta=[];errs=[]
    print('SHARD',SHARD,'SYMBOLS',len(symbols),flush=True)
    for i,sym in enumerate(symbols,1):
        try:
            rows=load(sym);a,b,m=run_symbol(sym,float(tv[sym]['tick']),rows);setups+=a;passes+=b;meta.append(m)
            print(f'[{SHARD}] {i}/{len(symbols)} {sym} bars={len(rows)} setups={len(a)} s1pass={len(b)}',flush=True)
        except Exception as e:
            errs.append({'symbol':sym,'error':repr(e)});print('ERROR',sym,repr(e),flush=True)
    (OUT/f'setups-{SHARD}.json').write_text(json.dumps(setups))
    (OUT/f'passes-{SHARD}.json').write_text(json.dumps(passes))
    (OUT/f'meta-{SHARD}.json').write_text(json.dumps(meta,indent=2))
    (OUT/f'errors-{SHARD}.json').write_text(json.dumps(errs,indent=2))
    print(json.dumps({'shard':SHARD,'symbols':len(symbols),'setups':len(setups),'stage1_pass_rows':len(passes),'errors':len(errs)}))

if __name__=='__main__':main_shard()
