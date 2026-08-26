#!/usr/bin/env python3
from __future__ import annotations
import json, statistics, tempfile
from pathlib import Path
import private_backtest_worker_v2 as core

PROJECT = "private-backtest"
SOURCE_SCOPE = "bt-20260825-0455z-v3c"
FUTURE_ADDITIONS = ["CSGP", "MRVL", "PANW", "PLTR", "WDAY"]


def pf(vals):
    gp = sum(x for x in vals if x > 0)
    gl = -sum(x for x in vals if x < 0)
    return gp / gl if gl > 0 else (999.0 if gp > 0 else None)


def met(vals):
    return {
        "n": len(vals),
        "pf": pf(vals),
        "mean_bps": statistics.fmean(vals) if vals else None,
        "median_bps": statistics.median(vals) if vals else None,
        "win_rate_pct": 100.0 * sum(x > 0 for x in vals) / len(vals) if vals else None,
        "sum_bps": sum(vals),
    }


def main():
    work = Path(tempfile.mkdtemp(prefix="us60-future-membership-"))
    rp, tp = work / "report.json", work / "trades.jsonl"
    core.download_artifact(PROJECT, SOURCE_SCOPE, "final/report.json", rp)
    core.download_artifact(PROJECT, SOURCE_SCOPE, "final/trades.jsonl", tp)
    report = json.loads(rp.read_text(encoding="utf-8"))
    primary = {str(x).upper() for x in report.get("primary_symbols", [])}
    rows = []
    for line in tp.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        s = str(r.get("symbol", "")).upper()
        if s in primary and r.get("actual_return_bps") is not None:
            rows.append((s, float(r["actual_return_bps"])))
    if len(rows) != 4023:
        raise RuntimeError(f"canonical primary trade mismatch {len(rows)} != 4023")
    base = [v for _, v in rows]
    future = [v for s, v in rows if s in FUTURE_ADDITIONS]
    ex = [v for s, v in rows if s not in FUTURE_ADDITIONS]
    by = {}
    for s in FUTURE_ADDITIONS:
        vals = [v for ss, v in rows if ss == s]
        by[s] = met(vals)
    result = {
        "schema": 1,
        "source_scope": SOURCE_SCOPE,
        "diagnostic_status": "POST_STAGE_DESCRIPTIVE_NOT_PREREGISTERED",
        "reason": "Historical membership audit discovered five canonical symbols that were end-snapshot S&P500 members but not start-snapshot members.",
        "future_additions": FUTURE_ADDITIONS,
        "baseline": met(base),
        "future_additions_only": met(future),
        "excluding_future_additions": met(ex),
        "by_symbol": by,
        "interpretation_guardrails": {
            "not_a_preregistered_pass_fail_test": True,
            "not_parameter_selection": True,
            "does_not_change_strategy": True,
            "does_not_prove_original_universe_was_sp500_based": True
        }
    }
    out = work / "future-membership-diagnostic-v1.json"
    out.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    core.upload_artifact(PROJECT, "bt-super-rsi-us60-survivorship-audit-v1", "research/future-membership-diagnostic-v1.json", out, "application/json; charset=utf-8")
    core.put_json("/checkpoints/super-rsi/us60-future-membership-diagnostic-v1", {
        "source": core.SOURCE,
        "status": "complete",
        "position": {"phase": "post_stage_descriptive", "source_scope": SOURCE_SCOPE, "future_additions": FUTURE_ADDITIONS, "baseline_pf": result["baseline"]["pf"], "excluding_future_additions_pf": result["excluding_future_additions"]["pf"]},
        "dropbox_path": None,
        "last_error": None
    })
    print(json.dumps(result, indent=2))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
