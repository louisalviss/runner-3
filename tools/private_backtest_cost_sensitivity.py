#!/usr/bin/env python3
from __future__ import annotations

import argparse
import heapq
import json
import math
import statistics
import tempfile
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import private_backtest_worker_v2 as core

ENTRY_KEYS = ["entry_time", "entry_ts", "entry_at", "entry_datetime", "entry_dt", "entry_timestamp", "entry_time_utc", "entry"]
EXIT_KEYS = ["exit_time", "exit_ts", "exit_at", "exit_datetime", "exit_dt", "exit_timestamp", "exit_time_utc", "exit"]
SYMBOL_KEYS = ["symbol", "ticker", "instrument"]
CAPACITY_SLOTS = [40, 45, 50]
SPREAD_MULTIPLIERS = [1.0, 1.25, 1.5, 2.0, 3.0]
EXTRA_ROUNDTRIP_BPS = [0.0, 2.0, 5.0, 10.0, 20.0, 30.0, 40.0, 50.0, 60.0]
SCENARIOS = [
    {"name": "baseline_actual", "spread_multiplier": 1.0, "commission_bps_per_side": 0.0, "slippage_bps_per_side": 0.0},
    {"name": "light", "spread_multiplier": 1.0, "commission_bps_per_side": 0.5, "slippage_bps_per_side": 1.0},
    {"name": "normal", "spread_multiplier": 1.0, "commission_bps_per_side": 1.0, "slippage_bps_per_side": 2.5},
    {"name": "heavy", "spread_multiplier": 1.25, "commission_bps_per_side": 1.0, "slippage_bps_per_side": 5.0},
    {"name": "severe", "spread_multiplier": 1.5, "commission_bps_per_side": 2.0, "slippage_bps_per_side": 10.0},
    {"name": "spread_2x_only", "spread_multiplier": 2.0, "commission_bps_per_side": 0.0, "slippage_bps_per_side": 0.0},
]


def parse_dt(v):
    s = str(v).strip()
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def pick_key(row, candidates):
    for k in candidates:
        if k in row and row[k] not in (None, ""):
            return k
    return None


def pf(vals):
    pos = sum(x for x in vals if x > 0)
    neg = -sum(x for x in vals if x < 0)
    return pos / neg if neg > 0 else None


def percentile(vals, q):
    xs = sorted(vals)
    if not xs:
        return None
    if len(xs) == 1:
        return xs[0]
    pos = (len(xs) - 1) * q
    lo = int(math.floor(pos)); hi = int(math.ceil(pos))
    if lo == hi:
        return xs[lo]
    return xs[lo] * (hi - pos) + xs[hi] * (pos - lo)


def candidate_fields(rows, target_pf, target_mean_bps, prefer):
    keys = sorted(set().union(*(r.keys() for r in rows[:250])))
    candidates = []
    for key in keys:
        vals = []
        for r in rows:
            try:
                x = float(r.get(key))
            except (TypeError, ValueError):
                continue
            if math.isfinite(x):
                vals.append(x)
        if len(vals) < max(100, int(len(rows) * 0.95)) or not any(x > 0 for x in vals) or not any(x < 0 for x in vals):
            continue
        raw_pf = pf(vals); raw_mean = statistics.fmean(vals)
        if raw_pf is None or raw_mean == 0:
            continue
        lname = key.lower(); name_rank = 0.0
        if "bps" in lname: name_rank -= 3
        if "return" in lname or "ret" in lname: name_rank -= 2
        if prefer == "actual":
            if "actual" in lname: name_rank -= 5
            if "mid" in lname: name_rank += 6
        else:
            if "mid" in lname: name_rank -= 5
            if "actual" in lname: name_rank += 6
        if "spread" in lname or "price" in lname: name_rank += 5
        for scale in [1.0, 100.0, 10000.0, 0.01, 0.0001]:
            mean_bps = raw_mean * scale
            score = abs(raw_pf - target_pf) * 15.0 + abs(mean_bps - target_mean_bps) / max(1.0, abs(target_mean_bps)) + name_rank
            candidates.append((score, key, scale, raw_pf, mean_bps))
    candidates.sort()
    if not candidates:
        raise RuntimeError(f"could not infer {prefer} return field")
    best = candidates[0]
    if abs(best[3] - target_pf) > 0.02 or abs(best[4] - target_mean_bps) > 1.0:
        raise RuntimeError(f"{prefer} return inference failed: {candidates[:8]}")
    return best, candidates[:8]


def find_mid_stats(primary):
    options = []
    for k, v in primary.items():
        if not isinstance(v, dict) or "PF" not in v or "mean_bps" not in v:
            continue
        if k == "actual":
            continue
        rank = 0 if "mid" in k.lower() else 10
        options.append((rank, k, v))
    if not options:
        raise RuntimeError(f"midpoint stats not found in primary keys={list(primary.keys())}")
    options.sort(key=lambda x: (x[0], x[1]))
    return options[0][1], options[0][2]


def select_capacity(trades, slots):
    by_entry = defaultdict(list)
    for t in trades:
        by_entry[t["entry"]].append(t)
    active = []
    accepted = []
    seq = 0
    for ts in sorted(by_entry):
        while active and active[0][0] <= ts:
            heapq.heappop(active)
        group = sorted(by_entry[ts], key=lambda x: (x["symbol"], x["idx"]))
        free = max(0, slots - len(active))
        for t in group[:free]:
            seq += 1
            heapq.heappush(active, (t["exit"], seq))
            accepted.append(t)
    return accepted


def stress_bps(t, spread_multiplier=1.0, extra_roundtrip_bps=0.0):
    return t["actual_bps"] - (spread_multiplier - 1.0) * t["spread_drag_bps"] - extra_roundtrip_bps


def metrics(trades, *, slots=None, spread_multiplier=1.0, extra_roundtrip_bps=0.0):
    vals = [stress_bps(t, spread_multiplier, extra_roundtrip_bps) for t in trades]
    out = {
        "trades": len(vals),
        "pf": pf(vals),
        "mean_bps": statistics.fmean(vals) if vals else None,
        "sum_bps": sum(vals),
        "win_pct": 100.0 * sum(1 for x in vals if x > 0) / len(vals) if vals else None,
    }
    if slots:
        out["simple_return_on_initial_capital_pct"] = 100.0 * sum(x / 10000.0 / slots for x in vals)
    return out


def pf1_cost_budget(trades):
    lo, hi = 0.0, 500.0
    if pf([t["actual_bps"] - hi for t in trades]) and pf([t["actual_bps"] - hi for t in trades]) > 1.0:
        hi = 2000.0
    for _ in range(70):
        mid = (lo + hi) / 2.0
        cur = pf([t["actual_bps"] - mid for t in trades])
        if cur is not None and cur > 1.0:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2.0


def tail_scenario(trades, quantile, multiplier):
    threshold = percentile([t["spread_drag_bps"] for t in trades], quantile)
    vals = []
    affected = 0
    for t in trades:
        drag = t["spread_drag_bps"]
        extra = (multiplier - 1.0) * drag if drag >= threshold else 0.0
        if extra > 0:
            affected += 1
        vals.append(t["actual_bps"] - extra)
    return {
        "tail_quantile": quantile,
        "tail_threshold_spread_drag_bps": threshold,
        "tail_multiplier": multiplier,
        "affected_trades": affected,
        "pf": pf(vals),
        "mean_bps": statistics.fmean(vals),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", default="private-backtest")
    ap.add_argument("--scope", required=True)
    args = ap.parse_args()

    work = Path(tempfile.mkdtemp(prefix="bt-cost-"))
    tp, rp = work / "trades.jsonl", work / "report.json"
    core.download_artifact(args.project, args.scope, "final/trades.jsonl", tp)
    core.download_artifact(args.project, args.scope, "final/report.json", rp)
    report = json.loads(rp.read_text(encoding="utf-8"))
    primary = report["primary"]
    primary_symbols = {str(s).upper() for s in report.get("primary_symbols", [])}
    actual_target = primary["actual"]
    mid_name, mid_target = find_mid_stats(primary)

    raw_all = [json.loads(x) for x in tp.read_text(encoding="utf-8").splitlines() if x.strip()]
    sample = raw_all[0]
    ek, xk, sk = pick_key(sample, ENTRY_KEYS), pick_key(sample, EXIT_KEYS), pick_key(sample, SYMBOL_KEYS)
    if not ek or not xk or not sk:
        raise RuntimeError(f"could not infer trade keys: {sorted(sample.keys())}")
    raw = [r for r in raw_all if str(r.get(sk, "")).upper() in primary_symbols]
    if len(raw) != 4023:
        raise RuntimeError(f"primary trade count mismatch: {len(raw)}")

    abest, acands = candidate_fields(raw, float(actual_target["PF"]), float(actual_target["mean_bps"]), "actual")
    mbest, mcands = candidate_fields(raw, float(mid_target["PF"]), float(mid_target["mean_bps"]), "mid")
    _, ak, ascale, apf, amean = abest
    _, mk, mscale, mpf, mmean = mbest
    if ak == mk:
        raise RuntimeError(f"actual and midpoint inferred to same field: {ak}")

    trades = []
    for i, r in enumerate(raw):
        et, xt = parse_dt(r[ek]), parse_dt(r[xk])
        actual_bps = float(r[ak]) * ascale
        mid_bps = float(r[mk]) * mscale
        drag = mid_bps - actual_bps
        trades.append({
            "idx": i, "entry": et, "exit": xt, "symbol": str(r[sk]).upper(),
            "actual_bps": actual_bps, "mid_bps": mid_bps, "spread_drag_bps": drag,
        })

    actual_vals = [t["actual_bps"] for t in trades]
    mid_vals = [t["mid_bps"] for t in trades]
    if abs(pf(actual_vals) - float(actual_target["PF"])) > 1e-8 or abs(statistics.fmean(actual_vals) - float(actual_target["mean_bps"])) > 1e-6:
        raise RuntimeError("actual field failed exact canonical reproduction")
    if abs(pf(mid_vals) - float(mid_target["PF"])) > 1e-8 or abs(statistics.fmean(mid_vals) - float(mid_target["mean_bps"])) > 1e-6:
        raise RuntimeError("midpoint field failed exact canonical reproduction")

    drags = [t["spread_drag_bps"] for t in trades]
    negative_drag = sum(1 for x in drags if x < -1e-9)
    if negative_drag > max(5, int(len(drags) * 0.01)):
        raise RuntimeError(f"unexpected negative spread drag count={negative_drag}")

    subsets = {"canonical_63": (trades, None)}
    for slots in CAPACITY_SLOTS:
        subsets[f"slots_{slots}"] = (select_capacity(trades, slots), slots)

    subset_results = {}
    for name, (rows, slots) in subsets.items():
        scenarios = []
        for s in SCENARIOS:
            extra_rt = 2.0 * (s["commission_bps_per_side"] + s["slippage_bps_per_side"])
            m = metrics(rows, slots=slots, spread_multiplier=s["spread_multiplier"], extra_roundtrip_bps=extra_rt)
            scenarios.append({**s, "extra_roundtrip_bps": extra_rt, **m})
        const_grid = []
        for c in EXTRA_ROUNDTRIP_BPS:
            const_grid.append({"extra_roundtrip_bps": c, **metrics(rows, slots=slots, extra_roundtrip_bps=c)})
        spread_grid = []
        for mult in SPREAD_MULTIPLIERS:
            spread_grid.append({"spread_multiplier": mult, **metrics(rows, slots=slots, spread_multiplier=mult)})
        subset_results[name] = {
            "slots": slots,
            "selected_trades": len(rows),
            "pf1_extra_constant_cost_budget_bps_roundtrip": pf1_cost_budget(rows),
            "mean_zero_extra_constant_cost_budget_bps_roundtrip": statistics.fmean([t["actual_bps"] for t in rows]),
            "scenarios": scenarios,
            "extra_constant_cost_grid": const_grid,
            "spread_multiplier_grid": spread_grid,
            "spread_tail_shocks": [
                tail_scenario(rows, 0.95, 2.0),
                tail_scenario(rows, 0.95, 3.0),
                tail_scenario(rows, 0.99, 2.0),
                tail_scenario(rows, 0.99, 3.0),
            ],
        }

    result = {
        "schema": 1,
        "scope": args.scope,
        "universe": "primary_63",
        "model": {
            "baseline_actual": "canonical BID/ASK execution return; observed spread already included",
            "spread_stress": "additional cost = (spread_multiplier - 1) * (midpoint_return_bps - actual_return_bps)",
            "commission_slippage": "additional constant bps per side, doubled for roundtrip",
            "capacity_rule": "same preregistered exit-first; simultaneous entries ticker A->Z; fixed slot cap",
        },
        "field_validation": {
            "actual": {"field": ak, "scale": ascale, "pf": apf, "mean_bps": amean, "target": actual_target, "top_candidates": acands},
            "midpoint": {"report_key": mid_name, "field": mk, "scale": mscale, "pf": mpf, "mean_bps": mmean, "target": mid_target, "top_candidates": mcands},
        },
        "spread_drag_bps": {
            "mean": statistics.fmean(drags), "median": statistics.median(drags),
            "p90": percentile(drags, 0.90), "p95": percentile(drags, 0.95), "p99": percentile(drags, 0.99),
            "max": max(drags), "negative_count": negative_drag,
        },
        "subsets": subset_results,
    }
    out = work / "execution-cost-sensitivity-v1.json"
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    core.upload_artifact(args.project, args.scope, "research/execution-cost-sensitivity-v1.json", out, "application/json; charset=utf-8")
    core.put_json(
        "/checkpoints/super-rsi/execution-cost-sensitivity-v1",
        {
            "source": core.SOURCE, "status": "success",
            "position": {
                "phase": "complete", "scope": args.scope, "universe": "primary_63",
                "actual_field": ak, "midpoint_field": mk,
                "spread_drag_mean_bps": statistics.fmean(drags),
                "canonical_pf1_cost_budget_bps": subset_results["canonical_63"]["pf1_extra_constant_cost_budget_bps_roundtrip"],
                "artifact_project": args.project, "artifact_scope": args.scope,
                "artifact_name": "research/execution-cost-sensitivity-v1.json",
            },
            "dropbox_path": None, "last_error": None,
        },
    )

    compact = {
        "scope": args.scope,
        "actual_field": ak,
        "midpoint_field": mk,
        "spread_drag": result["spread_drag_bps"],
        "subsets": {
            name: {
                "selected_trades": data["selected_trades"],
                "pf1_cost_budget_bps": data["pf1_extra_constant_cost_budget_bps_roundtrip"],
                "mean_zero_cost_budget_bps": data["mean_zero_extra_constant_cost_budget_bps_roundtrip"],
                "scenarios": data["scenarios"],
                "spread_grid": data["spread_multiplier_grid"],
                "tail_shocks": data["spread_tail_shocks"],
            }
            for name, data in subset_results.items()
        },
    }
    print(json.dumps(compact, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
