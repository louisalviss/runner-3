#!/usr/bin/env python3
from __future__ import annotations
import json, os, sys
from datetime import datetime, timezone
from pathlib import Path
import pandas as pd

HELPER=Path(os.getenv("WR_HELPER_DIR","/tmp/wr-helper")); sys.path.insert(0,str(HELPER))
import wr_dukascopy_expanded_matrix as exp
SRC=Path(os.getenv("WR_SOURCE_ROOT","/tmp/source"))
OUT=Path(os.getenv("WR_OUT","/tmp/out")); OUT.mkdir(parents=True,exist_ok=True)
TF_MIN=10; EMA_LEN=200; COSTS=(0.0,0.25,0.5,1.0,2.0); SOURCE_RUN=32507430808

def parse_side(t):
    s=str(t.get("side","")).strip().upper()
    if s in ("L","LONG"): return "LONG"
    if s in ("S","SHORT"): return "SHORT"
    raise ValueError(f"unknown side={s!r}")

def read_all_trades():
    out=[]
    for p in sorted(SRC.rglob(f"trades-*-{TF_MIN}m.jsonl")):
        if p.name==f"trades-US500-{TF_MIN}m.jsonl": continue
        for ln in p.read_text().splitlines():
            if not ln.strip(): continue
            t=json.loads(ln); parse_side(t); out.append(t)
    if not out: raise RuntimeError("no 10m stock trades found")
    return out

def load_us500_close():
    df,manifest,instrument=exp.load_mid("US500",TF_MIN)
    if df is None or df.empty: raise RuntimeError("no US500 midpoint data")
    s=df["close"].copy().dropna().sort_index()
    if s.index.tz is None: s.index=s.index.tz_localize("UTC")
    else: s.index=s.index.tz_convert("UTC")
    return s

def signal_feature_ts(t):
    return pd.Timestamp(int(t["signal"]),unit="ms",tz="UTC")-pd.Timedelta(minutes=TF_MIN)

def build_regime(close):
    ema=close.ewm(span=EMA_LEN,adjust=False,min_periods=EMA_LEN).mean()
    slope=ema.diff()
    state=pd.Series("NEUTRAL",index=close.index,dtype="object")
    state[(close>ema)&(slope>0)]="BULL"
    state[(close<ema)&(slope<0)]="BEAR"
    return pd.DataFrame({"close":close,"ema200":ema,"ema_slope":slope,"state":state})

def allowed(side,state):
    return (side=="LONG" and state=="BULL") or (side=="SHORT" and state=="BEAR")

def cost_r(t,bps):
    d=abs(float(t["e"])-float(t["s"]))
    return 0.0 if d<=0 else (float(t["e"])/d)*(bps/10000.0)

def metrics(trades,bps=0.0):
    xs=[float(t["R"])-cost_r(t,bps) for t in trades]
    if not xs: return {"n":0,"R":0.0,"avg_R":None,"PF":None,"win_rate":None,"max_DD_R":0.0}
    gp=sum(max(x,0.0) for x in xs); gl=sum(max(-x,0.0) for x in xs)
    eq=peak=0.0; mdd=0.0
    for x in xs:
        eq+=x; peak=max(peak,eq); mdd=min(mdd,eq-peak)
    return {"n":len(xs),"R":sum(xs),"avg_R":sum(xs)/len(xs),"PF":gp/gl if gl else None,
            "win_rate":100.0*sum(x>0 for x in xs)/len(xs),"max_DD_R":mdd}

def pack(trades):
    return {f"{bps:g}bps":metrics(trades,bps) for bps in COSTS}

def year_of(t):
    return datetime.fromtimestamp(int(t["signal"])/1000,tz=timezone.utc).year

def symbol_of(t):
    return str(t.get("symbol","")).upper()

def split_side(trades,side):
    return [t for t in trades if parse_side(t)==side]

def evaluate_group(base,kept):
    return {"base":pack(base),"filtered":pack(kept),
            "delta":{f"{bps:g}bps_R":metrics(kept,bps)["R"]-metrics(base,bps)["R"] for bps in COSTS},
            "retention_pct":100.0*len(kept)/len(base) if base else None}

def main():
    trades=read_all_trades(); regime=build_regime(load_us500_close())
    kept=[]; removed=[]; missing=[]; state_counts={"BULL":0,"BEAR":0,"NEUTRAL":0}; tagged=[]
    for t in trades:
        ts=signal_feature_ts(t)
        if ts not in regime.index:
            missing.append(t); continue
        row=regime.loc[ts]
        if pd.isna(row["ema200"]) or pd.isna(row["ema_slope"]):
            missing.append(t); continue
        state=str(row["state"]); state_counts[state]+=1; tagged.append((t,state))
        (kept if allowed(parse_side(t),state) else removed).append(t)
    if len(missing)>max(20,int(0.01*len(trades))):
        raise RuntimeError(f"material missing causal market-state rows: {len(missing)}/{len(trades)}")
    base=[t for t,_ in tagged]
    bl=split_side(base,"LONG"); bs=split_side(base,"SHORT")
    kl=split_side(kept,"LONG"); ks=split_side(kept,"SHORT")
    rl=split_side(removed,"LONG"); rs=split_side(removed,"SHORT")
    years={}
    for y in range(2022,2027):
        b=[t for t in base if year_of(t)==y]; k=[t for t in kept if year_of(t)==y]
        years[str(y)]={"overall":evaluate_group(b,k),
                       "long":evaluate_group(split_side(b,"LONG"),split_side(k,"LONG")),
                       "short":evaluate_group(split_side(b,"SHORT"),split_side(k,"SHORT"))}
    symbols={}; improved=worsened=unchanged=0
    for sym in sorted(set(symbol_of(t) for t in base)):
        b=[t for t in base if symbol_of(t)==sym]; k=[t for t in kept if symbol_of(t)==sym]
        d=metrics(k)["R"]-metrics(b)["R"]
        if d>1e-12: improved+=1
        elif d<-1e-12: worsened+=1
        else: unchanged+=1
        symbols[sym]={"overall":evaluate_group(b,k),
                      "long":evaluate_group(split_side(b,"LONG"),split_side(k,"LONG")),
                      "short":evaluate_group(split_side(b,"SHORT"),split_side(k,"SHORT"))}
    report={"status":"COMPLETE",
            "hypothesis":"Simple causal US500 10m EMA200 direction regime gates WR stock direction.",
            "source_wr_run":SOURCE_RUN,"source_universe":"Fusion/Nasdaq-100 available US stock cases",
            "timeframe":"10m","benchmark":"US500 midpoint",
            "regime":{"ema_length":EMA_LEN,
                      "bull":"US500 close > EMA200 and EMA200 slope > 0",
                      "bear":"US500 close < EMA200 and EMA200 slope < 0",
                      "neutral":"all other states","long_rule":"keep LONG only in BULL",
                      "short_rule":"keep SHORT only in BEAR",
                      "causal_timestamp_rule":"feature_bar = signal_timestamp - 10m; exact indexed row required",
                      "parameter_sweep":False,"state_counts_at_trade_times":state_counts},
            "research_integrity":{"note":"Hypothesis was motivated after inspecting historical Long/Short behavior, so this is fixed-rule historical confirmation, not pristine unseen-sample proof.",
                                  "future_bar_fallback":False,"missing_rows":len(missing),
                                  "base_rows_after_exact_causal_alignment":len(base)},
            "aggregate":{"overall":evaluate_group(base,kept),
                         "long":evaluate_group(bl,kl),"short":evaluate_group(bs,ks),
                         "removed_long":pack(rl),"removed_short":pack(rs),
                         "years":years,
                         "symbol_dispersion":{"symbols":len(symbols),"improved":improved,"worsened":worsened,"unchanged":unchanged}},
            "symbols":symbols}
    (OUT/"report.json").write_text(json.dumps(report,indent=2))
    print("BASE",report["aggregate"]["overall"]["base"]["0bps"])
    print("FILTERED",report["aggregate"]["overall"]["filtered"]["0bps"])
    print("LONG",report["aggregate"]["long"]["filtered"]["0bps"])
    print("SHORT",report["aggregate"]["short"]["filtered"]["0bps"])
    print("MISSING",len(missing)); print("STATE_COUNTS",state_counts)

if __name__=="__main__": main()
