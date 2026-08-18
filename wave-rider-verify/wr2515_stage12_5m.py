#!/usr/bin/env python3
from __future__ import annotations
import csv, io, json, math, os, sys, time, types, zipfile
from bisect import bisect_left
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo
import requests

# Frozen research track: Wave Rider v2.5.15 verified Pine semantics, 5m only.
# Stage1 thresholds/schedule come from canonical Stage 1 Watchlist and Trade Flow.
# Stage2 thresholds remain frozen: 14 calendar days, >=5 prior setups, lowest P90 Required-X, Top 5.
START=datetime(2025,1,1,tzinfo=timezone.utc)
END_EXCL=datetime(2026,8,15,tzinfo=timezone.utc)
STATE=datetime(2024,12,1,tzinfo=timezone.utc)
START_MS=int(START.timestamp()*1000); END_MS=int(END_EXCL.timestamp()*1000); STATE_MS=int(STATE.timestamp()*1000)
TF_MS=300_000
TP_R=2.3; RISK_PCT=1.0; INIT=100000.0
S1_QV24=100_000_000.0; S1_AVG10=200_000_000.0; S1_VOL7=0.06; S1_ADR14=0.05
S2_LOOKBACK_MS=14*86400_000
VN=ZoneInfo('Asia/Ho_Chi_Minh'); NY=ZoneInfo('America/New_York')
SHARD=int(os.getenv('SHARD','0')); SHARDS=int(os.getenv('SHARDS','1'))
BASE_DIR=Path(os.getenv('BASE_DIR','/tmp/base')); OUT=Path(os.getenv('OUT_DIR','/tmp/stage12')); OUT.mkdir(parents=True,exist_ok=True)


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
sess=requests.Session();sess.headers['User-Agent']='runner3-wr2515-stage12/2.0'
MONTHS=[(2024,12)]+[(2025,m) for m in range(1,13)]+[(2026,m) for m in range(1,8)]


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
        if not row or not row[0].isdigit():continue
        try:
            # ot,o,h,l,c,base_volume,ct,quote_volume
            out.append((int(row[0]),float(row[1]),float(row[2]),float(row[3]),float(row[4]),float(row[5]),int(row[6]),float(row[7])))
        except Exception:continue
    return out


def load(sym):
    raw=[]
    for y,m in MONTHS:
        fn=f'{sym}-5m-{y:04d}-{m:02d}.zip';u=f'https://data.binance.vision/data/futures/um/monthly/klines/{sym}/5m/{fn}'
        try:raw+=decode(getzip(u))
        except Exception as e:print('FETCH_ERR',sym,fn,repr(e),flush=True)
    for d in range(1,16):
        fn=f'{sym}-5m-2026-08-{d:02d}.zip';u=f'https://data.binance.vision/data/futures/um/daily/klines/{sym}/5m/{fn}'
        try:raw+=decode(getzip(u))
        except Exception as e:print('FETCH_ERR',sym,fn,repr(e),flush=True)
    ded={r[0]:r for r in raw}
    return [ded[k] for k in sorted(ded) if STATE_MS<=k<END_MS]


def checkpoint_rows():
    out=[]
    # Daily Crypto refresh: 15:30 VN, seven days/week.
    d=date(2024,12,31)
    while d<=date(2026,8,15):
        cp=datetime(d.year,d.month,d.day,15,30,tzinfo=VN);ms=int(cp.timestamp()*1000)
        if START_MS<=ms<END_MS:out.append((ms,(cp-timedelta(hours=6)).date().isoformat(),'VN1530'))
        d+=timedelta(days=1)
    # US-session checkpoints are weekdays only; America/New_York handles DST.
    d=date(2024,12,31)
    while d<=date(2026,8,15):
        if d.weekday()<5:
            for hh,mm,label in ((10,0,'ET1000'),(12,45,'ET1245'),(15,45,'ET1545')):
                cp=datetime(d.year,d.month,d.day,hh,mm,tzinfo=NY);ms=int(cp.timestamp()*1000)
                if START_MS<=ms<END_MS:
                    v=cp.astimezone(VN);out.append((ms,(v-timedelta(hours=6)).date().isoformat(),label))
        d+=timedelta(days=1)
    return sorted({x[0]:x for x in out}.values(),key=lambda x:x[0])

CHECKPOINTS=checkpoint_rows()


def stage1_passes(rows,sym):
    # Deterministic historical reconstruction from completed 5m candles only.
    # qv24 is trailing 24h quote volume; daily metrics include the current partial UTC day at the checkpoint.
    ots=[r[0] for r in rows];cts=[r[6] for r in rows]
    pref=[0.0]
    for r in rows:pref.append(pref[-1]+r[7])
    full={}
    for r in rows:
        k=datetime.fromtimestamp(r[0]/1000,tz=timezone.utc).date().isoformat();x=full.get(k)
        if x is None:full[k]=[r[1],r[2],r[3],r[4],r[5]]
        else:
            x[1]=max(x[1],r[2]);x[2]=min(x[2],r[3]);x[3]=r[4];x[4]+=r[5]
    dkeys=sorted(full);passes=[]
    for cp,session_date,label in CHECKPOINTS:
        j=bisect_left(cts,cp)
        if j<=0:continue
        a=bisect_left(cts,cp-86400_000);qv24=pref[j]-pref[a]
        cur=datetime.fromtimestamp(cp/1000,tz=timezone.utc).date();key=cur.isoformat();di=bisect_left(dkeys,key)
        prev=[full[k] for k in dkeys[max(0,di-14):di]]
        day0=int(datetime(cur.year,cur.month,cur.day,tzinfo=timezone.utc).timestamp()*1000);q=bisect_left(ots,day0);rr=rows[q:j]
        if rr:
            partial=[rr[0][1],max(x[2] for x in rr),min(x[3] for x in rr),rr[-1][4],sum(x[5] for x in rr)]
            ds=(prev+[partial])[-14:]
        else:ds=prev[-14:]
        if len(ds)<14:continue
        last10=ds[-10:];last7=ds[-7:];last14=ds[-14:]
        if any(x[2]==0 for x in last7):continue
        avg10=sum(x[3]*x[4] for x in last10)/10.0
        vol7=sum((x[1]-x[2])/abs(x[2]) for x in last7)/7.0
        curclose=last14[-1][3]
        if not curclose:continue
        adr14=((sum(x[1] for x in last14)/14.0)-(sum(x[2] for x in last14)/14.0))/abs(curclose)
        if qv24>=S1_QV24 and avg10>=S1_AVG10 and vol7>S1_VOL7 and adr14>=S1_ADR14:
            passes.append({'symbol':sym,'checkpoint':cp,'session_date':session_date,'mode':label,'qv24':qv24,'avg10':avg10,'vol7':vol7,'adr14':adr14})
    return passes


def setup_ledger(sym,tick,rows):
    if len(rows)<1000:return []
    bars=[Bar(r[0],r[6],r[1],r[2],r[3],r[4]) for r in rows]
    ind,_,_=calc_ind(bars);eq=INIT;pending=active=None;setups=[]
    def close(i,reason,px):
        nonlocal active,eq
        p=active;both=bars[i].h>=max(p.s,p.t) and bars[i].l<=min(p.s,p.t) and reason in ('TP','SL')
        if both:reason='AMBIG->SL'
        cr=TP_R if reason=='TP' else (-1.0 if reason in ('SL','AMBIG->SL') else ((px-p.e)*(1 if p.d==1 else -1)*p.qty/p.risk))
        eq+=cr*p.risk;active=None;return True
    # Start at deterministic State Start; orders before Jan are real state, but only setups from Dec 18 onward are retained for Jan's 14d lookback.
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
        if active is None and pending is None and not closed:
            z=ind[i];lr=z['ha'] and x.c>z['ema'] and z['ag'] and z['chop_ok'] and z['res'] is not None;sr=z['hb'] and x.c<z['ema'] and z['ar'] and z['chop_ok'] and z['sup'] is not None
            nl=allowed and z['sra_ok'] and x.c>x.o and lr and x.c>z['res'] and x.l<=z['res'];sh=allowed and z['sra_ok'] and x.c<x.o and sr and x.c<z['sup'] and x.h>=z['sup']
            if nl or sh:
                if nl:d=1;e=x.h+tick;s=x.l-tick;t=e+TP_R*(e-s)
                else:d=-1;e=x.l-tick;s=x.h+tick;t=e-TP_R*(s-e)
                raw=(eq*RISK_PCT/100)/abs(e-s);q=math.floor(raw);risk=abs(e-s)*q
                if q>0 and risk>0:
                    pending=Plan(d,e,s,t,risk,q,i,x.ct,x.h,x.l)
                    if x.ct>=START_MS-S2_LOOKBACK_MS:
                        stop_pct=abs(e-s)/abs(e)*100 if e else None
                        if stop_pct and stop_pct>0:setups.append({'symbol':sym,'signal_time':x.ct,'stop_pct':stop_pct,'required_x':1.0/stop_pct})
    return setups


def main():
    tv=json.load(open(BASE_DIR/'tv_tick_map.json'));summary=json.load(open(BASE_DIR/'summary.json'))
    have={x['symbol'] for x in summary};symbols=sorted(set(tv)&have);symbols=[s for i,s in enumerate(symbols) if i%SHARDS==SHARD]
    setups=[];passes=[];meta=[];errs=[]
    print('SHARD',SHARD,'SYMBOLS',len(symbols),'CHECKPOINTS',len(CHECKPOINTS),flush=True)
    for i,sym in enumerate(symbols,1):
        try:
            rows=load(sym);a=setup_ledger(sym,float(tv[sym]['tick']),rows);b=stage1_passes(rows,sym) if len(rows)>=1000 else []
            setups+=a;passes+=b;meta.append({'symbol':sym,'bars':len(rows),'setups':len(a),'passes':len(b)})
            print(f'[{SHARD}] {i}/{len(symbols)} {sym} bars={len(rows)} setups={len(a)} s1pass={len(b)}',flush=True)
        except Exception as e:
            errs.append({'symbol':sym,'error':repr(e)});print('ERROR',sym,repr(e),flush=True)
    (OUT/f'setups-{SHARD}.json').write_text(json.dumps(setups))
    (OUT/f'passes-{SHARD}.json').write_text(json.dumps(passes))
    (OUT/f'meta-{SHARD}.json').write_text(json.dumps(meta,indent=2))
    (OUT/f'errors-{SHARD}.json').write_text(json.dumps(errs,indent=2))
    print(json.dumps({'shard':SHARD,'symbols':len(symbols),'checkpoints':len(CHECKPOINTS),'setups':len(setups),'stage1_pass_rows':len(passes),'errors':len(errs)}))

if __name__=='__main__':main()
