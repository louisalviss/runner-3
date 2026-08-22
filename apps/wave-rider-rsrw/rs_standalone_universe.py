#!/usr/bin/env python3
from __future__ import annotations

import importlib.util, json, math, os, sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

CANON_DIR = Path(os.getenv("WR_CANON_DIR", "/tmp/wr-canonical"))
OUT = Path(os.getenv("WR_RS_STANDALONE_OUT", "/tmp/wr-rs-standalone"))
LENGTHS = [int(x) for x in os.getenv("WR_RS_LENGTHS", "10,21,50").split(",") if x.strip()]
SHARD = int(os.getenv("WR_RS_SHARD", "0")); SHARDS = int(os.getenv("WR_RS_SHARDS", "8"))
BENCH = "BTCUSDT"; ATR_LEN = 14; TP_R = 2.3; MAX_HOLD = 288


def load_canon():
    p = CANON_DIR / "wr_canonical_crypto_5m.py"
    spec = importlib.util.spec_from_file_location("wr_canon", p)
    m = importlib.util.module_from_spec(spec); sys.modules[spec.name] = m; spec.loader.exec_module(m); return m


def ema_states(asset, btc, length):
    bm = {b.ot:b.c for b in btc}; a = 2.0/(length+1.0); prev=None
    out={}
    for b in asset:
        bc=bm.get(b.ot)
        if bc in (None,0): continue
        ratio=b.c/bc; cur=ratio if prev is None else a*ratio+(1-a)*prev
        out[b.ot]={"ratio":ratio,"ema":cur,"long":prev is not None and ratio>cur and cur>prev,"short":prev is not None and ratio<cur and cur<prev}
        prev=cur
    return out


def atr14(bars):
    out={}; prev_c=None; vals=[]
    for b in bars:
        tr=(b.h-b.l) if prev_c is None else max(b.h-b.l,abs(b.h-prev_c),abs(b.l-prev_c))
        vals.append(tr)
        if len(vals)>ATR_LEN: vals.pop(0)
        if len(vals)==ATR_LEN: out[b.ot]=sum(vals)/ATR_LEN
        prev_c=b.c
    return out


def signal_transitions(bars, st, start_ms, end_ms):
    sig=[]; pl=ps=False
    for i,b in enumerate(bars[:-1]):
        if not(start_ms <= b.ct < end_ms):
            z=st.get(b.ot,{}); pl=bool(z.get("long")); ps=bool(z.get("short")); continue
        z=st.get(b.ot,{}) ; l=bool(z.get("long")); s=bool(z.get("short"))
        if l and not pl: sig.append((i,"L"))
        if s and not ps: sig.append((i,"S"))
        pl,ps=l,s
    return sig


def run_fixed_r(bars, st, length, start_ms, end_ms):
    atr=atr14(bars); trades=[]; busy_until=-1
    for i,side in signal_transitions(bars,st,start_ms,end_ms):
        if i < busy_until or i+1>=len(bars): continue
        sb=bars[i]; nb=bars[i+1]; av=atr.get(sb.ot)
        if not av or av<=0: continue
        e=nb.o; risk=av
        sl=e-risk if side=="L" else e+risk; tp=e+TP_R*risk if side=="L" else e-TP_R*risk
        exit_i=min(len(bars)-1,i+1+MAX_HOLD); r=None; reason="TIME"
        for j in range(i+1,exit_i+1):
            b=bars[j]
            if side=="L":
                hit_s=b.l<=sl; hit_t=b.h>=tp
            else:
                hit_s=b.h>=sl; hit_t=b.l<=tp
            if hit_s and hit_t: r=-1.0; reason="BOTH_SL_FIRST"; exit_i=j; break
            if hit_s: r=-1.0; reason="SL"; exit_i=j; break
            if hit_t: r=TP_R; reason="TP"; exit_i=j; break
        if r is None:
            x=bars[exit_i].c; r=((x-e)/risk) if side=="L" else ((e-x)/risk)
        trades.append({"signal":sb.ct,"entry_ts":nb.ot,"exit_ts":bars[exit_i].ct,"side":side,"e":e,"s":sl,"R":r,"reason":reason,"length":length})
        busy_until=exit_i+1
    return trades


def run_native(bars, st, length, start_ms, end_ms):
    trades=[]; pos=None
    for i,b in enumerate(bars[:-1]):
        z=st.get(b.ot,{})
        if pos is not None:
            side,ei,e=pos
            invalid = (side=="L" and not z.get("long",False)) or (side=="S" and not z.get("short",False))
            if invalid:
                x=bars[i+1].o
                ret=(x/e-1.0) if side=="L" else (e/x-1.0)
                trades.append({"signal":bars[ei-1].ct if ei>0 else bars[ei].ot,"entry_ts":bars[ei].ot,"exit_ts":bars[i+1].ot,"side":side,"ret":ret,"length":length})
                pos=None
        if pos is None and start_ms <= b.ct < end_ms:
            pz=st.get(bars[i-1].ot,{}) if i>0 else {}
            if z.get("long",False) and not pz.get("long",False): pos=("L",i+1,bars[i+1].o)
            elif z.get("short",False) and not pz.get("short",False): pos=("S",i+1,bars[i+1].o)
    return trades


def sum_fixed(canon,sym,length,tr):
    rs=[t["R"] for t in tr]; n=len(rs); gp=sum(max(x,0) for x in rs); gl=sum(max(-x,0) for x in rs)
    net6=sum(t["R"]-canon.trade_cost_r(t,6) for t in tr)
    return {"symbol":sym,"mode":"FIXED_R","ema_length":length,"n":n,"total_r":sum(rs),"avg_r":sum(rs)/n if n else None,"win_rate":100*sum(x>0 for x in rs)/n if n else None,"pf":gp/gl if gl else None,"net_r_6bps":net6}


def sum_native(sym,length,tr):
    rr=[t["ret"] for t in tr]; n=len(rr); gross=sum(rr); cost=0.0006*n
    return {"symbol":sym,"mode":"NATIVE","ema_length":length,"n":n,"sum_return":gross,"avg_return":gross/n if n else None,"win_rate":100*sum(x>0 for x in rr)/n if n else None,"net_sum_return_6bps":gross-cost}


def shard():
    OUT.mkdir(parents=True,exist_ok=True); c=load_canon(); base,ref=c.load_modules(); http=c.sess()
    btc,_=c.load_symbol(http,ref,BENCH); universe=[s for s in c.list_symbols(http) if s!=BENCH]; mine=[s for i,s in enumerate(universe) if i%SHARDS==SHARD]
    rows=[]; errors=[]; skips=[]; trades=[]
    sm=int(c.REPORT_START.timestamp()*1000); em=int(c.REPORT_END.timestamp()*1000)
    for k,sym in enumerate(mine,1):
        print(f"[{SHARD}] {k}/{len(mine)} {sym}",flush=True)
        try:
            bars,tick=c.load_symbol(http,ref,sym)
            if len(bars)<1000 or not tick: skips.append({"symbol":sym,"reason":"insufficient_data"}); continue
            for L in LENGTHS:
                st=ema_states(bars,btc,L)
                fr=run_fixed_r(bars,st,L,sm,em); nr=run_native(bars,st,L,sm,em)
                rows += [sum_fixed(c,sym,L,fr),sum_native(sym,L,nr)]
                trades += [{"symbol":sym,"mode":"FIXED_R",**x} for x in fr]
                trades += [{"symbol":sym,"mode":"NATIVE",**x} for x in nr]
        except Exception as e:
            errors.append({"symbol":sym,"error":repr(e)}); print("ERROR",sym,repr(e),flush=True)
    p={"status":"COMPLETE" if not errors else "PARTIAL","shard":SHARD,"shards":SHARDS,"universe":len(universe),"symbols":len(mine),"rows":rows,"errors":errors,"skips":skips,"spec":{"benchmark":BENCH,"ema_lengths":LENGTHS,"state":"ratio>EMA + EMA slope up for long; symmetric short","fixed_r":"entry next-bar open; ATR14 1R stop; TP 2.3R; max hold 288 bars; same-bar SL+TP => SL first","native":"entry next-bar open on state transition; exit next-bar open when state invalid"}}
    (OUT/f"result-{SHARD}.json").write_text(json.dumps(p,indent=2)+"\n")
    with (OUT/f"trades-{SHARD}.jsonl").open("w") as f:
        for x in trades: f.write(json.dumps(x,separators=(",",":"))+"\n")


def merge():
    root=Path(os.getenv("WR_RS_MERGE_ROOT","/tmp/all")); final=Path(os.getenv("WR_RS_FINAL_OUT","/tmp/final")); final.mkdir(parents=True,exist_ok=True)
    payloads=[]; rows=[]; errors=[]; skips=[]
    for p in root.rglob("result-*.json"):
        x=json.loads(p.read_text()); payloads.append(x); rows+=x.get("rows",[]); errors+=x.get("errors",[]); skips+=x.get("skips",[])
    agg={}
    for mode in ("FIXED_R","NATIVE"):
      for L in LENGTHS:
        xs=[r for r in rows if r["mode"]==mode and r["ema_length"]==L]
        n=sum(r["n"] for r in xs)
        if mode=="FIXED_R":
          total=sum(r["total_r"] for r in xs); net=sum(r["net_r_6bps"] for r in xs)
          agg[f"{mode}_EMA{L}"]={"symbols":len(xs),"n":n,"total_r":total,"avg_r":total/n if n else None,"net_r_6bps":net}
        else:
          total=sum(r["sum_return"] for r in xs); net=sum(r["net_sum_return_6bps"] for r in xs)
          agg[f"{mode}_EMA{L}"]={"symbols":len(xs),"n":n,"sum_return":total,"avg_return":total/n if n else None,"net_sum_return_6bps":net}
    report={"status":"COMPLETE" if len(payloads)==SHARDS and not errors else "PARTIAL","shards_found":len(payloads),"rows":len(rows),"aggregate":agg,"errors":errors,"skips":skips,"spec":payloads[0].get("spec") if payloads else {}}
    (final/"report.json").write_text(json.dumps(report,indent=2)+"\n"); (final/"per-symbol.json").write_text(json.dumps(rows,indent=2)+"\n")
    print(json.dumps(report,indent=2),flush=True)

if __name__=="__main__":
    (merge if len(sys.argv)>1 and sys.argv[1]=="merge" else shard)()
