import csv,io,json,math,os,sys,time,types,zipfile
from collections import defaultdict
from datetime import datetime,timezone
from pathlib import Path
import requests

TF=int(os.environ.get('TF_MIN','3'))
SHARD=int(os.environ.get('SHARD','0'))
SHARDS=int(os.environ.get('SHARDS','8'))
BASE=Path(os.environ.get('BASE_DIR','/tmp/base'))
OUT=Path(os.environ.get('OUT_DIR','/tmp/out')); OUT.mkdir(parents=True,exist_ok=True)
if TF not in (3,10): raise SystemExit('TF_MIN must be 3 or 10')

# Frozen WR v2.5.15 reference + parity patches used by canonical 5m rebuild.
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

# Exact same current-TV crypto universe used for clean comparison.
tv=json.load(open(BASE/'tv_tick_map.json'))
base_summary=json.load(open(BASE/'summary.json'))
base_syms={x['symbol'] for x in base_summary}
tradfi={'BZUSDT','CLUSDT','DRAMUSDT','EWYUSDT','INTCUSDT','KORUUSDT','MRVLUSDT','MSTRUSDT','MUUSDT','SAMSUNGUSDT','SKHYNIXUSDT','SKHYUSDT','SNDKUSDT','SNXXUSDT','SOXLUSDT','SOXSUSDT','SPCXUSDT','XAGUSDT'}
universe=sorted((base_syms & set(tv))-tradfi)
if len(universe)!=654: raise RuntimeError(f'universe drift: expected 654 got {len(universe)}')
symbols=[s for i,s in enumerate(universe) if i%SHARDS==SHARD]

STATE=int(datetime(2024,12,1,tzinfo=timezone.utc).timestamp()*1000)
START=int(datetime(2025,1,1,tzinfo=timezone.utc).timestamp()*1000)
END=int(datetime(2026,8,15,tzinfo=timezone.utc).timestamp()*1000)
RUN_END=int(datetime(2026,8,18,tzinfo=timezone.utc).timestamp()*1000)
months=[(2024,12)]+[(2025,m) for m in range(1,13)]+[(2026,m) for m in range(1,8)]
chart_ms=TF*60_000
source_tf=3 if TF==3 else 5
sess=requests.Session(); sess.headers['User-Agent']=f'runner3-wr2515-phase1-{TF}m/1.0'

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
    out=[]
    if not data:return out
    with zipfile.ZipFile(io.BytesIO(data)) as z: text=z.read(z.namelist()[0]).decode()
    for row in csv.reader(io.StringIO(text)):
        if row and row[0].isdigit(): out.append(Bar(int(row[0]),int(row[6]),*map(float,row[1:5])))
    return out

def aggregate_10m(bars):
    g=defaultdict(list)
    for b in bars:g[(b.ot//600_000)*600_000].append(b)
    out=[]
    for ot in sorted(g):
        xs=sorted(g[ot],key=lambda x:x.ot)
        # 10m TradingView-style bucket. One child is allowed only at listing boundary.
        o=xs[0].o; h=max(x.h for x in xs); l=min(x.l for x in xs); c=xs[-1].c
        out.append(Bar(ot,ot+600_000-1,o,h,l,c))
    return out

def load(sym):
    b=[]
    for y,m in months:
        fn=f'{sym}-{source_tf}m-{y:04d}-{m:02d}.zip'
        u=f'https://data.binance.vision/data/futures/um/monthly/klines/{sym}/{source_tf}m/{fn}'
        try:b.extend(readzip(getzip(u)))
        except Exception as e:print('FETCH_ERR',sym,fn,repr(e),flush=True)
    for d in range(1,19):
        fn=f'{sym}-{source_tf}m-2026-08-{d:02d}.zip'
        u=f'https://data.binance.vision/data/futures/um/daily/klines/{sym}/{source_tf}m/{fn}'
        try:b.extend(readzip(getzip(u)))
        except Exception as e:print('FETCH_ERR',sym,fn,repr(e),flush=True)
    ded={x.ot:x for x in b}; bars=[ded[k] for k in sorted(ded) if STATE<=k<RUN_END]
    if TF==10: bars=aggregate_10m(bars)
    return bars

def bt(sym,tick,bars):
    if len(bars)<500:return None,[]
    ind,_,_=calc(bars); eq=INIT; pending=active=None; trades=[]
    def close(i,reason,px):
        nonlocal active,eq
        p=active
        both=bars[i].h>=max(p.s,p.t) and bars[i].l<=min(p.s,p.t) and reason in ('TP','SL')
        if both:reason='AMBIG->SL'
        cr=TP if reason=='TP' else (-1.0 if reason in ('SL','AMBIG->SL') else ((px-p.e)*(1 if p.d==1 else -1)*p.qty/p.risk))
        eq+=cr*p.risk
        if START<=p.sig_t<END:
            sp=abs(p.e-p.s)/p.e*100
            trades.append({'symbol':sym,'tf':TF,'signal_time':p.sig_t,'side':'LONG' if p.d==1 else 'SHORT','entry':p.e,'stop':p.s,'target':p.t,'exit_time':bars[i].ct,'exit_reason':reason,'R':cr,'stop_pct':sp,'required_x':1/sp if sp>0 else None})
        active=None; return True
    for i,x in enumerate(bars):
        closed=False
        if active is not None:
            r,px=nextb(active,x,None)
            if r:closed=close(i,r,px)
        if active is None and pending is not None and i==pending.sig_i+1 and not closed:
            fill=(pending.d==1 and round(x.h/tick)>=round(pending.e/tick)) or (pending.d==-1 and round(x.l/tick)<=round(pending.e/tick))
            if fill:
                gap=(pending.d==1 and round(x.o/tick)>=round(pending.e/tick)) or (pending.d==-1 and round(x.o/tick)<=round(pending.e/tick))
                active=pending; pending=None; r,px=nextb(active,x,None if gap else active.e)
                if r:closed=close(i,r,px)
        allowed,sexit=sf(x.ct+1,chart_ms)
        if active is not None and not closed:
            z=ind[i]; le=active.d==1 and x.c<z['ema'] and not z['ha'] and not z['ema_up']; se=active.d==-1 and x.c>z['ema'] and not z['hb'] and bool(z['ema_up'])
            if sexit:closed=close(i,'SESSION',x.c)
            elif le or se:closed=close(i,'EMA',x.c)
        if pending is not None and i>=pending.sig_i+1 and active is None:pending=None
        if active is None and pending is None and not closed:
            z=ind[i]; lr=z['ha'] and x.c>z['ema'] and z['ag'] and z['chop_ok'] and z['res'] is not None; sr=z['hb'] and x.c<z['ema'] and z['ar'] and z['chop_ok'] and z['sup'] is not None
            nl=allowed and z['sra_ok'] and x.c>x.o and lr and x.c>z['res'] and x.l<=z['res']; sh=allowed and z['sra_ok'] and x.c<x.o and sr and x.c<z['sup'] and x.h>=z['sup']
            if nl or sh:
                if nl:d=1;e=x.h+tick;s=x.l-tick;t=e+TP*(e-s)
                else:d=-1;e=x.l-tick;s=x.h+tick;t=e-TP*(s-e)
                q=math.floor((eq*RP/100)/abs(e-s)); risk=abs(e-s)*q
                if q>0 and risk>0:pending=Plan(d,e,s,t,risk,q,i,x.ct,x.h,x.l)
    rs=[a['R'] for a in trades]; n=len(rs); gp=sum(max(r,0) for r in rs); gl=sum(max(-r,0) for r in rs)
    row={'symbol':sym,'tf':TF,'bars':len(bars),'tick':tick,'n':n,'total_r':sum(rs),'avg_r':sum(rs)/n if n else None,'win_rate':100*sum(r>0 for r in rs)/n if n else None,'pf':gp/gl if gl else None}
    for bps in (4,6,8,10):row[f'net_r_{bps}bps']=sum(a['R']-(a['entry']/abs(a['entry']-a['stop']))*bps/10000 for a in trades)
    return row,trades

sums=[]; trs=[]; errs=[]
for j,sym in enumerate(symbols,1):
    try:
        bars=load(sym); tick=float(tv[sym]['tick']); row,t=bt(sym,tick,bars)
        if row:sums.append(row); trs.extend(t)
        print(f'[{TF}m shard {SHARD}] {j}/{len(symbols)} {sym} bars={len(bars)} trades={0 if row is None else row["n"]}',flush=True)
    except Exception as e:
        errs.append({'symbol':sym,'error':repr(e)}); print('ERROR',sym,repr(e),flush=True)
json.dump(sums,open(OUT/f'summary-{SHARD}.json','w'))
json.dump(errs,open(OUT/f'errors-{SHARD}.json','w'),indent=2)
json.dump({'tf':TF,'shard':SHARD,'universe_total':len(universe),'symbols_shard':len(symbols),'completed':len(sums),'trades':len(trs),'errors':len(errs)},open(OUT/f'meta-{SHARD}.json','w'),indent=2)
with open(OUT/f'trades-{SHARD}.jsonl','w') as f:
    for a in trs:f.write(json.dumps(a,separators=(',',':'))+'\n')
