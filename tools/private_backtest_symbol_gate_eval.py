#!/usr/bin/env python3
from __future__ import annotations
import argparse, json, statistics, tempfile
from collections import defaultdict
from pathlib import Path
import private_backtest_worker_v2 as core

PROJECT = "private-backtest"
SYMBOL_KEYS = ("symbol","ticker","instrument")
ENTRY_KEYS = ("entry_time","entry_ts","entry_at","entry_datetime","entry_dt","entry_timestamp","entry_time_utc","entry")

def metric(vals):
    gp=sum(v for v in vals if v>0); gl=-sum(v for v in vals if v<0)
    pf=gp/gl if gl>0 else (999.0 if gp>0 else None)
    return {"n":len(vals),"pf":pf,"mean_bps":statistics.fmean(vals) if vals else None,
            "median_bps":statistics.median(vals) if vals else None,
            "win_rate_pct":100*sum(v>0 for v in vals)/len(vals) if vals else None}

def getv(r, keys):
    for k in keys:
        if r.get(k) not in (None,""): return r[k]
    return None

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--config",required=True); ap.add_argument("--family",required=True); a=ap.parse_args()
    cfg=json.loads(Path(a.config).read_text()); fam=cfg["families"][a.family]; scope=fam["scope"]; sg=cfg["symbol_gates"]
    work=Path(tempfile.mkdtemp(prefix=f"symgate-{a.family}-")); tp=work/"trades.jsonl"
    core.download_artifact(PROJECT,scope,"final/trades.jsonl",tp)
    groups=defaultdict(list)
    for line in tp.read_text(encoding="utf-8").splitlines():
        if not line.strip(): continue
        r=json.loads(line); sym=getv(r,SYMBOL_KEYS); et=getv(r,ENTRY_KEYS)
        if sym is None or et is None or r.get("actual_return_bps") is None: continue
        groups[str(sym).upper()].append((str(et),float(r["actual_return_bps"])))
    stress_cost=float(cfg["gates"]["stress_extra_rt_bps"]); holdout=cfg["holdout_start"]; rows=[]; eligible=[]
    for sym in sorted(groups):
        x=groups[sym]; allv=[v for _,v in x]; pre=[v for t,v in x if t<holdout]; ho=[v for t,v in x if t>=holdout]; st=[v-stress_cost for v in allv]
        m=metric(allv); pm=metric(pre); hm=metric(ho); sm=metric(st)
        flags={
          "trades":m["n"]>=int(sg["trades_min"]), "pre_trades":pm["n"]>=int(sg["pre_trades_min"]), "holdout_trades":hm["n"]>=int(sg["holdout_trades_min"]),
          "actual_pf":m["pf"] is not None and m["pf"]>=float(sg["actual_pf_min"]), "actual_mean":m["mean_bps"] is not None and m["mean_bps"]>=float(sg["actual_mean_bps_min"]),
          "pre_pf":pm["pf"] is not None and pm["pf"]>=float(sg["pre_holdout_pf_min"]), "holdout_pf":hm["pf"] is not None and hm["pf"]>=float(sg["holdout_pf_min"]),
          "holdout_mean_positive":hm["mean_bps"] is not None and hm["mean_bps"]>0, "stress_pf":sm["pf"] is not None and sm["pf"]>=float(sg["stress_pf_min"]),
          "stress_mean_positive":sm["mean_bps"] is not None and sm["mean_bps"]>0}
        ok=all(flags.values()); rows.append({"symbol":sym,"eligible":ok,"base":m,"pre_holdout":pm,"holdout":hm,"stress":sm,"flags":flags})
        if ok: eligible.append(sym)
    result={"schema":1,"family":a.family,"scope":scope,"holdout_start":holdout,"stress_extra_rt_bps":stress_cost,"symbol_gates":sg,
            "eligible_count":len(eligible),"eligible_symbols":eligible,"symbols_evaluated":len(rows),"symbols":rows,
            "discipline":{"strategy_parameters":"UNCHANGED","direction":"LONG_ONLY","gate_preregistered_before_expanded_outcomes":True}}
    rp=work/"symbol-gate-evaluation-v1.json"; rp.write_text(json.dumps(result,indent=2)+"\n",encoding="utf-8")
    core.upload_artifact(PROJECT,scope,"research/symbol-gate-evaluation-v1.json",rp,"application/json; charset=utf-8")
    core.put_json(f"/checkpoints/super-rsi/cross-asset-30m-{a.family}-symbol-gates-v1", {"source":core.SOURCE,"status":"complete","position":{"phase":"symbol_gate_evaluated","scope":scope,"eligible_count":len(eligible),"eligible_symbols":eligible,"artifact_project":PROJECT,"artifact_scope":scope,"artifact_name":"research/symbol-gate-evaluation-v1.json"},"dropbox_path":None,"last_error":None})
    print(json.dumps({"family":a.family,"eligible_count":len(eligible),"eligible_symbols":eligible,"symbols_evaluated":len(rows)},indent=2)); return 0

if __name__=="__main__": raise SystemExit(main())
