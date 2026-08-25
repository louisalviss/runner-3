#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import statistics
import tempfile
from pathlib import Path

import private_backtest_worker_v2 as core


def pf(vals):
    pos = sum(x for x in vals if x > 0)
    neg = -sum(x for x in vals if x < 0)
    return (pos / neg) if neg > 0 else None


def metrics(vals):
    vals = list(vals)
    return {
        "trades": len(vals),
        "pf": pf(vals),
        "mean_bps": statistics.fmean(vals) if vals else None,
        "median_bps": statistics.median(vals) if vals else None,
        "win_rate_pct": 100.0 * sum(x > 0 for x in vals) / len(vals) if vals else None,
        "sum_bps": sum(vals),
    }


def qtile(vals, q):
    s = sorted(vals)
    if not s:
        return None
    if len(s) == 1:
        return s[0]
    x = (len(s) - 1) * q
    lo = int(math.floor(x)); hi = int(math.ceil(x))
    if lo == hi:
        return s[lo]
    return s[lo] * (hi - x) + s[hi] * (x - lo)


def infer_signed_field(rows, target_pf, target_mean_bps, prefer_tokens, avoid_tokens=()):
    keys = sorted(set().union(*(r.keys() for r in rows[:300])))
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
        raw_pf = pf(vals)
        raw_mean = statistics.fmean(vals)
        if raw_pf is None:
            continue
        lname = key.lower()
        name_rank = 0.0
        for t in prefer_tokens:
            if t in lname:
                name_rank -= 4.0
        for t in avoid_tokens:
            if t in lname:
                name_rank += 5.0
        if "bps" in lname: name_rank -= 2.0
        if "return" in lname or "ret" in lname: name_rank -= 1.5
        if "pnl" in lname or "profit" in lname: name_rank -= 1.0
        if "spread" in lname or "price" in lname: name_rank += 6.0
        for scale in [1.0, 100.0, 10000.0, 0.01, 0.0001]:
            mean_bps = raw_mean * scale
            score = abs(raw_pf - target_pf) * 12.0 + abs(mean_bps - target_mean_bps) / max(1.0, abs(target_mean_bps)) + name_rank
            candidates.append((score, key, scale, raw_pf, mean_bps))
    if not candidates:
        raise RuntimeError(f"could not infer signed return field; keys={keys}")
    candidates.sort()
    best = candidates[0]
    if abs(best[3] - target_pf) > 0.02 or abs(best[4] - target_mean_bps) > 1.0:
        raise RuntimeError(f"return inference failed: best={candidates[:8]}")
    return best[1], best[2], candidates[:8]


def find_bucket(report, names):
    primary = report.get("primary", {})
    for n in names:
        b = primary.get(n)
        if isinstance(b, dict) and "PF" in b and "mean_bps" in b:
            return b
    for k, v in primary.items():
        lk = str(k).lower()
        if isinstance(v, dict) and "PF" in v and "mean_bps" in v and any(n in lk for n in names):
            return v
    raise RuntimeError(f"could not find report bucket among {names}; primary keys={list(primary.keys())}")


def threshold_cost(vals, target_pf, hi=200.0):
    # Largest constant extra round-trip bps cost whose PF remains >= target.
    if pf(vals) is None or pf(vals) < target_pf:
        return 0.0
    lo = 0.0
    for _ in range(70):
        mid = (lo + hi) / 2.0
        p = pf([x - mid for x in vals])
        if p is not None and p >= target_pf:
            lo = mid
        else:
            hi = mid
    return lo


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", default="private-backtest")
    ap.add_argument("--scope", required=True)
    args = ap.parse_args()

    work = Path(tempfile.mkdtemp(prefix="bt-friction-"))
    tp = work / "trades.jsonl"
    rp = work / "report.json"
    core.download_artifact(args.project, args.scope, "final/trades.jsonl", tp)
    core.download_artifact(args.project, args.scope, "final/report.json", rp)
    report = json.loads(rp.read_text(encoding="utf-8"))

    primary_symbols = {str(s).upper() for s in report.get("primary_symbols", [])}
    raw_all = [json.loads(x) for x in tp.read_text(encoding="utf-8").splitlines() if x.strip()]
    sample_keys = sorted(raw_all[0].keys())
    symbol_key = next((k for k in ["symbol", "ticker", "instrument"] if k in raw_all[0]), None)
    if not symbol_key:
        raise RuntimeError(f"symbol field not found; keys={sample_keys}")
    raw = [r for r in raw_all if str(r.get(symbol_key, "")).upper() in primary_symbols]
    if len(raw) != 4023:
        raise RuntimeError(f"primary trade count mismatch: {len(raw)} != 4023")

    actual_bucket = find_bucket(report, ["actual"])
    midpoint_bucket = find_bucket(report, ["midpoint", "mid"])
    actual_pf_target = float(actual_bucket["PF"])
    actual_mean_target = float(actual_bucket["mean_bps"])
    mid_pf_target = float(midpoint_bucket["PF"])
    mid_mean_target = float(midpoint_bucket["mean_bps"])

    ak, ascale, acands = infer_signed_field(raw, actual_pf_target, actual_mean_target, ["actual"], ["mid"])
    mk, mscale, mcands = infer_signed_field(raw, mid_pf_target, mid_mean_target, ["mid"], ["actual"])
    actual = [float(r[ak]) * ascale for r in raw]
    mid = [float(r[mk]) * mscale for r in raw]

    am = metrics(actual); mm = metrics(mid)
    if abs(am["pf"] - actual_pf_target) > 1e-8 or abs(am["mean_bps"] - actual_mean_target) > 1e-6:
        raise RuntimeError(f"actual baseline mismatch: {am} vs {actual_bucket}")
    if abs(mm["pf"] - mid_pf_target) > 1e-8 or abs(mm["mean_bps"] - mid_mean_target) > 1e-6:
        raise RuntimeError(f"midpoint baseline mismatch: {mm} vs {midpoint_bucket}")

    spread_drag_raw = [m - a for m, a in zip(mid, actual)]
    negative_drag = sum(x < 0 for x in spread_drag_raw)
    # Stress only increases observed spread cost; anomalous negative differences are not amplified.
    spread_drag = [max(0.0, x) for x in spread_drag_raw]
    spread_stats = {
        "mean_bps": statistics.fmean(spread_drag),
        "median_bps": statistics.median(spread_drag),
        "p90_bps": qtile(spread_drag, 0.90),
        "p95_bps": qtile(spread_drag, 0.95),
        "p99_bps": qtile(spread_drag, 0.99),
        "max_bps": max(spread_drag),
        "negative_raw_drag_trades": negative_drag,
        "negative_raw_drag_pct": 100.0 * negative_drag / len(spread_drag_raw),
        "raw_mean_mid_minus_actual_bps": statistics.fmean(spread_drag_raw),
    }

    flat_costs = [0, 2, 5, 10, 15, 20, 25, 30, 40, 50, 55, 60, 64, 65, 70, 80, 100]
    flat = []
    for c in flat_costs:
        row = {"extra_round_trip_bps": c, **metrics([x - c for x in actual])}
        flat.append(row)

    # Explicit per-side commission/slippage scenarios. Actual baseline already includes historical BID/ASK spread.
    combos = []
    for commission_side in [0.0, 0.5, 1.0, 2.0]:
        for slippage_side in [0.5, 1.0, 2.0, 3.0, 5.0, 10.0]:
            rt = 2.0 * (commission_side + slippage_side)
            combos.append({
                "commission_bps_per_side": commission_side,
                "slippage_bps_per_side": slippage_side,
                "extra_round_trip_bps": rt,
                **metrics([x - rt for x in actual]),
            })

    spread_scale = []
    for factor in [1.0, 1.25, 1.5, 2.0, 3.0]:
        vals = [a - (factor - 1.0) * d for a, d in zip(actual, spread_drag)]
        spread_scale.append({"observed_spread_cost_factor": factor, **metrics(vals)})

    tail = []
    for qname, q in [("p95", 0.95), ("p99", 0.99)]:
        threshold = qtile(spread_drag, q)
        for factor in [1.5, 2.0, 3.0, 5.0]:
            vals = []
            affected = 0
            for a, d in zip(actual, spread_drag):
                if d >= threshold:
                    vals.append(a - (factor - 1.0) * d)
                    affected += 1
                else:
                    vals.append(a)
            tail.append({
                "tail": qname,
                "tail_threshold_bps": threshold,
                "tail_spread_cost_factor": factor,
                "affected_trades": affected,
                "affected_pct": 100.0 * affected / len(actual),
                **metrics(vals),
            })

    headroom = {
        "extra_flat_rt_bps_until_pf_1_20": threshold_cost(actual, 1.20),
        "extra_flat_rt_bps_until_pf_1_10": threshold_cost(actual, 1.10),
        "extra_flat_rt_bps_until_pf_1_05": threshold_cost(actual, 1.05),
        "extra_flat_rt_bps_until_pf_1_00": threshold_cost(actual, 1.00),
        "extra_flat_rt_bps_until_mean_10": actual_mean_target - 10.0,
        "extra_flat_rt_bps_until_mean_0": actual_mean_target,
    }
    headroom["max_extra_flat_rt_bps_preserving_frozen_actual_pf1_20_and_mean10"] = min(
        headroom["extra_flat_rt_bps_until_pf_1_20"], headroom["extra_flat_rt_bps_until_mean_10"]
    )

    result = {
        "schema": 1,
        "scope": args.scope,
        "universe": "primary_63",
        "trade_count": len(actual),
        "method": {
            "baseline_actual": "canonical executable BID/ASK return; historical spread already included",
            "midpoint": "canonical midpoint return",
            "observed_spread_drag_bps": "midpoint_return_bps - actual_return_bps per trade",
            "spread_stress": "additional penalty only; max(0, midpoint-actual) is scaled, so anomalous negative drag is not turned into a benefit",
            "commission_slippage": "extra per-side cost applied symmetrically at entry and exit",
            "no_rerun": True,
        },
        "fields": {"symbol": symbol_key, "actual_return": ak, "actual_scale_to_bps": ascale, "midpoint_return": mk, "midpoint_scale_to_bps": mscale},
        "sample_trade_keys": sample_keys,
        "actual_inference_top": [{"field": x[1], "scale": x[2], "pf": x[3], "mean_bps": x[4], "score": x[0]} for x in acands],
        "midpoint_inference_top": [{"field": x[1], "scale": x[2], "pf": x[3], "mean_bps": x[4], "score": x[0]} for x in mcands],
        "baseline_actual": am,
        "baseline_midpoint": mm,
        "observed_spread_drag": spread_stats,
        "flat_extra_cost_sensitivity": flat,
        "commission_slippage_sensitivity": combos,
        "spread_scale_sensitivity": spread_scale,
        "spread_tail_sensitivity": tail,
        "headroom": headroom,
    }

    out = work / "execution-cost-sensitivity-v1.json"
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    core.upload_artifact(args.project, args.scope, "research/execution-cost-sensitivity-v1.json", out, "application/json; charset=utf-8")
    core.put_json(
        "/checkpoints/super-rsi/execution-cost-sensitivity-v1",
        {
            "source": core.SOURCE,
            "status": "success",
            "position": {
                "phase": "complete", "scope": args.scope, "universe": "primary_63",
                "artifact_project": args.project, "artifact_scope": args.scope,
                "artifact_name": "research/execution-cost-sensitivity-v1.json",
            },
            "dropbox_path": None, "last_error": None,
        },
    )
    compact = {
        "scope": args.scope,
        "fields": result["fields"],
        "baseline_actual": am,
        "baseline_midpoint": mm,
        "observed_spread_drag": spread_stats,
        "headroom": headroom,
        "flat": flat,
        "spread_scale": spread_scale,
        "spread_tail": tail,
        "selected_commission_slippage": [
            x for x in combos if (x["commission_bps_per_side"], x["slippage_bps_per_side"]) in {
                (0.0, 1.0), (0.0, 2.0), (0.0, 5.0), (0.5, 1.0), (0.5, 2.0), (0.5, 5.0), (1.0, 2.0), (1.0, 5.0)
            }
        ],
    }
    print(json.dumps(compact, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
