import csv, io, json, math, os, sys, time, types, zipfile
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
import requests

SHARD=int(os.environ.get('SHARD','0'))
SHARDS=int(os.environ.get('SHARDS','8'))
TV_DIR=Path(os.environ.get('TV_DIR','/tmp/base5'))
UNIVERSE_FILE=Path(os.environ.get('UNIVERSE_FILE','/tmp/old10/universe.json'))
OUT=Path(os.environ.get('OUT_DIR','/tmp/out')); OUT.mkdir(parents=True,exist_ok=True)

ref=Path('/tmp/reference_verify.py')
src=ref.read_text().replace('sra<=SIGNAL_RANGE_MAX','sra<SIGNAL_RANGE_MAX')
old="""        if v[c]==ext:\n            if sum(x==ext for x in w)==1: base[conf]=v[c]\n            else: ties+=1\n"""
new="""        if v[c]==ext:\n            if all(x!=ext for x in v[c+1:c+right+1]): base[conf]=v[c]\n            else: ties+=1\n"""
if src.count(old)!=1: raise RuntimeError('pivot patch anchor missing')
src=src.replace(old,new,1)
mod=types.ModuleType('wrref'); mod.__file__='reference_verify.py'; sys.modules['wrref']=mod
exec(compile(src,'reference_verify.py','exec'),mod.__dict__); ns=mod.__dict__
Bar=ns['Bar']; Plan=ns['Plan']; calc=ns['calc_ind']; nextb=ns['next_bracket']; sf=ns['session_flags']
TP=ns['TP_R']; RP=ns['RISK_PCT']; INIT=ns['INIT']

tv=json.load(open(TV_DIR/'tv_tick_map.json'))
universe=sorted(set(json.load(open(UNIVERSE_FILE))))
if len(universe)!=654: raise RuntimeError(f'universe drift: expected 654 got {len(universe)}')
missing_ticks=[s for s in universe if s not in tv]
if missing_ticks: raise RuntimeError(f'missing TradingView ticks for {len(missing_ticks)} symbols: {missing_ticks[:20]}')
symbols=[s for i,s in enumerate(universe) if i%SHARDS==SHARD]

STATE=int(datetime(2024,12,1,tzinfo=timezone.utc).timestamp()*1000)
START=int(datetime(2025,1,1,tzinfo=timezone.utc).timestamp()*1000)
END=int(datetime(2026,8,15,tzinfo=timezone.utc).timestamp()*1000)
RUN_END=int(datetime(2026,8,18,tzinfo=timezone.utc).timestamp()*1000)
MONTHS=[(2024,12)]+[(2025,m) for m in range(1,13)]+[(2026,m) for m in range(1,8)]
DAYS=[(2026,8,d) for d in range(1,18)]
chart_ms=600_000
sess=requests.Session(); sess.headers['User-Agent']='runner3-wr2515-strict10m/1.0'

class IntegrityError(RuntimeError): pass

def getzip(url, label):
    last=None
    for k in range(4):
        try:
            r=sess.get(url,timeout=60)
            if r.status_code==404:return None
            r.raise_for_status(); return r.content
        except Exception as e:
            last=e
            if k<3: time.sleep(.7*(k+1))
    raise IntegrityError(f'network/archive fetch failed {label}: {last!r}')

def readzip(data,label):
    if not data:return []
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            names=z.namelist()
            if len(names)!=1: raise IntegrityError(f'{label}: expected 1 file in zip, got {len(names)}')
            text=z.read(names[0]).decode()
    except IntegrityError:
        raise
    except Exception as e:
        raise IntegrityError(f'{label}: zip parse failed: {e!r}')
    out=[]; prev=None
    for row in csv.reader(io.StringIO(text)):
        if not row or not row[0].isdigit(): continue
        if len(row)<7: raise IntegrityError(f'{label}: malformed kline row')
        b=Bar(int(row[0]),int(row[6]),*map(float,row[1:5]))
        if b.ct!=b.ot+299_999: raise IntegrityError(f'{label}: bad 5m close_time at {b.ot}: {b.ct}')
        if b.ot%300_000!=0: raise IntegrityError(f'{label}: unaligned 5m open_time {b.ot}')
        if prev is not None and b.ot<=prev: raise IntegrityError(f'{label}: non-increasing/duplicate row {b.ot}')
        prev=b.ot; out.append(b)
    if not out: raise IntegrityError(f'{label}: zip contained no kline rows')
    return out

def period_specs(sym):
    for y,m in MONTHS:
        fn=f'{sym}-5m-{y:04d}-{m:02d}.zip'
        yield ('month',f'{y:04d}-{m:02d}',f'https://data.binance.vision/data/futures/um/monthly/klines/{sym}/5m/{fn}')
    for y,m,d in DAYS:
        fn=f'{sym}-5m-{y:04d}-{m:02d}-{d:02d}.zip'
        yield ('day',f'{y:04d}-{m:02d}-{d:02d}',f'https://data.binance.vision/data/futures/um/daily/klines/{sym}/5m/{fn}')

def load_strict(sym):
    bars=[]; started=False; first_period=None; leading_404=[]; periods_ok=[]
    for kind,label,url in period_specs(sym):
        data=getzip(url,f'{sym} {kind} {label}')
        if data is None:
            if not started:
                leading_404.append(label); continue
            raise IntegrityError(f'{sym}: missing archive period after listing/start: {kind} {label}')
        rows=readzip(data,f'{sym} {kind} {label}')
        if not started: started=True; first_period=label
        bars.extend(rows); periods_ok.append(label)
    if not started: raise IntegrityError(f'{sym}: no archives found in requested window')
    seen={}
    for b in bars:
        if b.ot in seen: raise IntegrityError(f'{sym}: duplicate 5m timestamp across archives: {b.ot}')
        seen[b.ot]=b
    bars=[seen[k] for k in sorted(seen) if STATE<=k<RUN_END]
    if len(bars)<500: raise IntegrityError(f'{sym}: too few 5m bars after clipping: {len(bars)}')
    gaps=[]
    for a,b in zip(bars,bars[1:]):
        if b.ot-a.ot!=300_000:
            gaps.append((a.ot,b.ot,b.ot-a.ot))
            if len(gaps)>=5: break
    if gaps: raise IntegrityError(f'{sym}: 5m continuity gap(s): {gaps}')
    groups=defaultdict(list)
    for b in bars: groups[(b.ot//600_000)*600_000].append(b)
    out=[]; leading_partial=0; emitted=False
    for ot in sorted(groups):
        xs=sorted(groups[ot],key=lambda x:x.ot); expected=[ot,ot+300_000]; got=[x.ot for x in xs]
        if got!=expected:
            if not emitted and len(xs)==1 and got[0] in expected:
                leading_partial+=1; continue
            raise IntegrityError(f'{sym}: incomplete/invalid 10m bucket {ot}: got={got} expected={expected}')
        out.append(Bar(ot,ot+599_999,xs[0].o,max(x.h for x in xs),min(x.l for x in xs),xs[-1].c)); emitted=True
    if len(out)<250: raise IntegrityError(f'{sym}: too few strict 10m bars: {len(out)}')
    return out,{'first_period':first_period,'leading_404_periods':leading_404,'periods_ok':len(periods_ok),'bars_5m':len(bars),'bars_10m':len(out),'leading_partial_10m':leading_partial}

def bt(sym,tick,bars):
    ind,_,_=calc(bars); eq=INIT; pending=active=None; trades=[]
    def close(i,reason,px):
        nonlocal active,eq
        p=active; both=bars[i].h>=max(p.s,p.t) and bars[i].l<=min(p.s,p.t) and reason in ('TP','SL')
        if both: reason='AMBIG->SL'
        cr=TP if reason=='TP' else (-1.0 if reason in ('SL','AMBIG->SL') else ((px-p.e)*(1 if p.d==1 else -1)*p.qty/p.risk))
        eq+=cr*p.risk
        if START<=p.sig_t<END:
            sp=abs(p.e-p.s)/p.e*100
            trades.append({'symbol':sym,'tf':10,'signal_time':p.sig_t,'side':'LONG' if p.d==1 else 'SHORT','entry':p.e,'stop':p.s,'target':p.t,'exit_time':bars[i].ct,'exit_reason':reason,'R':cr,'stop_pct':sp,'required_x':1/sp if sp>0 else None})
        active=None; return True
    for i,x in enumerate(bars):
        closed=False
        if active is not None:
            r,px=nextb(active,x,None)
            if r: closed=close(i,r,px)
        if active is None and pending is not None and i==pending.sig_i+1 and not closed:
            fill=(pending.d==1 and round(x.h/tick)>=round(pending.e/tick)) or (pending.d==-1 and round(x.l/tick)<=round(pending.e/tick))
            if fill:
                gap=(pending.d==1 and round(x.o/tick)>=round(pending.e/tick)) or (pending.d==-1 and round(x.o/tick)<=round(pending.e/tick))
                active=pending; pending=None; r,px=nextb(active,x,None if gap else active.e)
                if r: closed=close(i,r,px)
        allowed,sexit=sf(x.ct+1,chart_ms)
        if active is not None and not closed:
            z=ind[i]; le=active.d==1 and x.c<z['ema'] and not z['ha'] and not z['ema_up']; se=active.d==-1 and x.c>z['ema'] and not z['hb'] and bool(z['ema_up'])
            if sexit: closed=close(i,'SESSION',x.c)
            elif le or se: closed=close(i,'EMA',x.c)
        if pending is not None and i>=pending.sig_i+1 and active is None: pending=None
        if active is None and pending is None and not closed:
            z=ind[i]; lr=z['ha'] and x.c>z['ema'] and z['ag'] and z['chop_ok'] and z['res'] is not None; sr=z['hb'] and x.c<z['ema'] and z['ar'] and z['chop_ok'] and z['sup'] is not None
            nl=allowed and z['sra_ok'] and x.c>x.o and lr and x.c>z['res'] and x.l<=z['res']; sh=allowed and z['sra_ok'] and x.c<x.o and sr and x.c<z['sup'] and x.h>=z['sup']
            if nl or sh:
                if nl: d=1; e=x.h+tick; s=x.l-tick; t=e+TP*(e-s)
                else: d=-1; e=x.l-tick; s=x.h+tick; t=e-TP*(s-e)
                q=math.floor((eq*RP/100)/abs(e-s)); risk=abs(e-s)*q
                if q>0 and risk>0: pending=Plan(d,e,s,t,risk,q,i,x.ct,x.h,x.l)
    rs=[a['R'] for a in trades]; n=len(rs); gp=sum(max(r,0) for r in rs); gl=sum(max(-r,0) for r in rs)
    row={'symbol':sym,'tf':10,'bars':len(bars),'tick':tick,'n':n,'total_r':sum(rs),'avg_r':sum(rs)/n if n else None,'win_rate':100*sum(r>0 for r in rs)/n if n else None,'pf':gp/gl if gl else None}
    for bps in (4,6,8,10): row[f'net_r_{bps}bps']=sum(a['R']-(a['entry']/abs(a['entry']-a['stop']))*bps/10000 for a in trades)
    return row,trades

summaries=[]; trades=[]; failures=[]; integrity=[]
for j,sym in enumerate(symbols,1):
    try:
        bars,diag=load_strict(sym); tick=float(tv[sym]['tick']); row,t=bt(sym,tick,bars)
        summaries.append(row); trades.extend(t); integrity.append({'symbol':sym,**diag})
        print(f'[strict10 shard {SHARD}] {j}/{len(symbols)} {sym} 5m={diag["bars_5m"]} 10m={diag["bars_10m"]} trades={row["n"]}',flush=True)
    except Exception as e:
        failures.append({'symbol':sym,'error':repr(e)}); print('INTEGRITY_FAIL',sym,repr(e),flush=True)
json.dump(summaries,open(OUT/f'summary-{SHARD}.json','w')); json.dump(failures,open(OUT/f'failures-{SHARD}.json','w'),indent=2); json.dump(integrity,open(OUT/f'integrity-{SHARD}.json','w'),indent=2)
json.dump({'shard':SHARD,'symbols_shard':len(symbols),'completed':len(summaries),'failed':len(failures),'trades':len(trades)},open(OUT/f'meta-{SHARD}.json','w'),indent=2)
with open(OUT/f'trades-{SHARD}.jsonl','w') as f:
    for a in trades:f.write(json.dumps(a,separators=(',',':'))+'\n')
