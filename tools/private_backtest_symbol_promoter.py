#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import statistics
import tempfile
from pathlib import Path

import private_backtest_worker_v2 as core

PROJECT = "private-backtest"


def pf(vals):
    gp = sum(v for v in vals if v > 0)
    gl = -sum(v for v in vals if v < 0)
    return gp / gl if gl > 0 else (999.0 if gp > 0 else None)


def met(vals):
    return {
        "n": len(vals),
        "pf": pf(vals),
        "mean_bps": statistics.fmean(vals) if vals else None,
        "median_bps": statistics.median(vals) if vals else None,
        "win_rate_pct": 100.0 * sum(v > 0 for v in vals) / len(vals) if vals else None,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    ap.add_argument("--family", required=True)
    args = ap.parse_args()

    cfg = json.loads(Path(args.config).read_text(encoding="utf-8"))
    fam = cfg["families"][args.family]
    scope = fam["scope"]
    sg = cfg["symbol_gates"]
    holdout_start = cfg["holdout_start"]
    stress_rt = float(cfg["gates"]["stress_extra_rt_bps"])

    work = Path(tempfile.mkdtemp(prefix=f"symbol-promoter-{args.family}-"))
    tp = work / "trades.jsonl"
    rp = work / "report.json"
    core.download_artifact(PROJECT, scope, "final/trades.jsonl", tp)
    core.download_artifact(PROJECT, scope, "final/report.json", rp)
    report = json.loads(rp.read_text(encoding="utf-8"))
    rows = [json.loads(x) for x in tp.read_text(encoding="utf-8").splitlines() if x.strip()]

    universe = list(fam["instruments"].keys())
    out = {}
    eligible = []
    for sym in universe:
        rr = [r for r in rows if str(r.get("symbol", "")).upper() == sym.upper()]
        vals = [float(r["actual_return_bps"]) for r in rr]
        pre = [float(r["actual_return_bps"]) for r in rr if str(r.get("entry_time", "")) < holdout_start]
        ho = [float(r["actual_return_bps"]) for r in rr if str(r.get("entry_time", "")) >= holdout_start]
        stress = [v - stress_rt for v in vals]
        bm, pm, hm, sm = met(vals), met(pre), met(ho), met(stress)
        flags = {
            "trades": bm["n"] >= int(sg["trades_min"]),
            "pre_trades": pm["n"] >= int(sg["pre_trades_min"]),
            "holdout_trades": hm["n"] >= int(sg["holdout_trades_min"]),
            "base_pf": bm["pf"] is not None and bm["pf"] >= float(sg["actual_pf_min"]),
            "base_mean": bm["mean_bps"] is not None and bm["mean_bps"] >= float(sg["actual_mean_bps_min"]),
            "pre_pf": pm["pf"] is not None and pm["pf"] >= float(sg["pre_holdout_pf_min"]),
            "holdout_pf": hm["pf"] is not None and hm["pf"] >= float(sg["holdout_pf_min"]),
            "holdout_mean": hm["mean_bps"] is not None and hm["mean_bps"] > 0,
            "stress_pf": sm["pf"] is not None and sm["pf"] >= float(sg["stress_pf_min"]),
            "stress_mean": sm["mean_bps"] is not None and sm["mean_bps"] > 0,
        }
        ok = all(flags.values())
        if ok:
            eligible.append(sym)
        out[sym] = {"base": bm, "pre_holdout": pm, "holdout": hm, "stress": sm, "flags": flags, "lower_tf_research_eligible": ok}

    carry_required = str(fam.get("carry_model", "none")) != "none"
    result = {
        "schema": 1,
        "family": args.family,
        "scope": scope,
        "profile": report.get("profile"),
        "holdout_start": holdout_start,
        "stress_extra_rt_bps": stress_rt,
        "symbol_gates": sg,
        "eligible_symbols": eligible,
        "eligible_count": len(eligible),
        "promotion_note": "LOWER_TF_RESEARCH_ELIGIBLE only; live promotion remains blocked by carry/financing where required" if carry_required else "LOWER_TF_RESEARCH_ELIGIBLE only; live promotion requires later shadow/paper gates",
        "symbols": out,
    }
    op = work / "symbol-promotion-30m-v1.json"
    op.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    core.upload_artifact(PROJECT, scope, "research/symbol-promotion-30m-v1.json", op, "application/json; charset=utf-8")
    core.put_json(f"/checkpoints/super-rsi/cross-asset-symbol-promotion-{args.family}-v1", {
        "source": core.SOURCE,
        "status": "complete",
        "position": {"phase": "symbol_evaluated", "scope": scope, "eligible_symbols": eligible, "artifact_project": PROJECT, "artifact_scope": scope, "artifact_name": "research/symbol-promotion-30m-v1.json"},
        "dropbox_path": None,
        "last_error": None,
    })
    print(json.dumps({"family": args.family, "eligible_count": len(eligible), "eligible_symbols": eligible}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
