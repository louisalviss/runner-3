#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import statistics
import tempfile
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

import private_backtest_worker_v2 as core

ENTRY_KEYS = ["entry_time", "entry_ts", "entry_at", "entry_datetime", "entry_dt", "entry_timestamp", "entry_time_utc", "entry"]
EXIT_KEYS = ["exit_time", "exit_ts", "exit_at", "exit_datetime", "exit_dt", "exit_timestamp", "exit_time_utc", "exit"]
SYMBOL_KEYS = ["symbol", "ticker", "instrument"]


def parse_dt(v):
    if v is None:
        return None
    s = str(v).strip()
    if not s:
        return None
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def pick_key(row, candidates):
    for k in candidates:
        if k in row and row[k] not in (None, ""):
            return k
    return None


def qtile(values, q):
    if not values:
        return None
    xs = sorted(values)
    if len(xs) == 1:
        return xs[0]
    pos = (len(xs) - 1) * q
    lo, hi = math.floor(pos), math.ceil(pos)
    if lo == hi:
        return xs[lo]
    return xs[lo] * (hi - pos) + xs[hi] * (pos - lo)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", default="private-backtest")
    ap.add_argument("--scope", required=True)
    args = ap.parse_args()

    work = Path(tempfile.mkdtemp(prefix="bt-overlap-primary-"))
    trades_path = work / "trades.jsonl"
    report_path = work / "report.json"
    core.download_artifact(args.project, args.scope, "final/trades.jsonl", trades_path)
    core.download_artifact(args.project, args.scope, "final/report.json", report_path)

    report = json.loads(report_path.read_text(encoding="utf-8"))
    primary_symbols = {str(s).upper() for s in report.get("primary_symbols", [])}
    expected_n = int(report.get("primary", {}).get("actual", {}).get("n", 0))
    if not primary_symbols:
        raise RuntimeError("report.primary_symbols missing")

    raw = [json.loads(line) for line in trades_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if not raw:
        raise RuntimeError("no trades found")
    sample = raw[0]
    entry_key = pick_key(sample, ENTRY_KEYS)
    exit_key = pick_key(sample, EXIT_KEYS)
    symbol_key = pick_key(sample, SYMBOL_KEYS)
    if not entry_key or not exit_key or not symbol_key:
        raise RuntimeError(f"could not infer required fields; keys={sorted(sample.keys())}")

    filtered = []
    for r in raw:
        sym = str(r.get(symbol_key, "")).upper()
        if sym not in primary_symbols:
            continue
        et, xt = parse_dt(r.get(entry_key)), parse_dt(r.get(exit_key))
        if et is None or xt is None or xt <= et:
            raise RuntimeError(f"invalid timestamps for {sym}")
        filtered.append((et, xt, sym))

    if len(filtered) != expected_n:
        raise RuntimeError(f"primary trade count mismatch: filtered={len(filtered)} report={expected_n}")

    events = defaultdict(lambda: {"entry": 0, "exit": 0})
    bursts = Counter()
    durations_h = []
    for et, xt, _ in filtered:
        events[et]["entry"] += 1
        events[xt]["exit"] += 1
        bursts[et] += 1
        durations_h.append((xt - et).total_seconds() / 3600)

    active = 0
    peak = 0
    prev = None
    time_at_level = Counter()
    preexisting = []
    postentry = []
    for t in sorted(events):
        if prev is not None:
            time_at_level[active] += (t - prev).total_seconds()
        row = events[t]
        active = max(0, active - row["exit"])
        before = active
        if row["entry"]:
            preexisting.extend([before] * row["entry"])
        active += row["entry"]
        if row["entry"]:
            postentry.extend([active] * row["entry"])
        peak = max(peak, active)
        prev = t

    total_span = sum(time_at_level.values())
    active_span = sum(sec for level, sec in time_at_level.items() if level > 0)
    avg_open = sum(level * sec for level, sec in time_at_level.items()) / total_span
    avg_open_active = sum(level * sec for level, sec in time_at_level.items() if level > 0) / active_span

    slots = [1, 2, 3, 5, 8, 10, 12, 15, 20, 25, 30, 35, 40, 45, 50, 55, 60]
    entry_pressure = {}
    time_exceed = {}
    n = len(filtered)
    for k in slots:
        pressured = sum(x >= k for x in preexisting)
        entry_pressure[str(k)] = {
            "signals_arriving_with_all_slots_already_occupied": pressured,
            "pct_entries": 100.0 * pressured / n,
        }
        sec = sum(v for level, v in time_at_level.items() if level > k)
        time_exceed[str(k)] = 100.0 * sec / total_span

    burst_vals = list(bursts.values())
    top_bursts = sorted(
        ({"timestamp": t.isoformat(), "entries": c} for t, c in bursts.items()),
        key=lambda x: (-x["entries"], x["timestamp"]),
    )[:20]

    result = {
        "schema": 2,
        "scope": args.scope,
        "universe": "primary_63",
        "primary_symbol_count": len(primary_symbols),
        "trade_count": n,
        "all_trade_count_in_artifact": len(raw),
        "fields": {"entry": entry_key, "exit": exit_key, "symbol": symbol_key},
        "range": {"first_entry": min(x[0] for x in filtered).isoformat(), "last_exit": max(x[1] for x in filtered).isoformat()},
        "holding_hours": {
            "mean": statistics.fmean(durations_h),
            "median": statistics.median(durations_h),
            "p90": qtile(durations_h, .90),
            "p95": qtile(durations_h, .95),
            "p99": qtile(durations_h, .99),
            "max": max(durations_h),
        },
        "concurrency": {
            "peak_open_positions": peak,
            "time_weighted_avg_open": avg_open,
            "avg_open_when_any_position_open": avg_open_active,
            "preexisting_open_at_entry_mean": statistics.fmean(preexisting),
            "preexisting_open_at_entry_median": statistics.median(preexisting),
            "preexisting_open_at_entry_p90": qtile(preexisting, .90),
            "preexisting_open_at_entry_p95": qtile(preexisting, .95),
            "preexisting_open_at_entry_p99": qtile(preexisting, .99),
            "postentry_open_p95": qtile(postentry, .95),
            "postentry_open_p99": qtile(postentry, .99),
        },
        "entry_bursts": {
            "unique_entry_timestamps": len(bursts),
            "mean_entries_per_timestamp": statistics.fmean(burst_vals),
            "median": statistics.median(burst_vals),
            "p95": qtile(burst_vals, .95),
            "p99": qtile(burst_vals, .99),
            "max": max(burst_vals),
            "top20": top_bursts,
        },
        "capacity_pressure_by_slots": entry_pressure,
        "time_pct_open_positions_above_slots": time_exceed,
        "note": "Capacity pressure is descriptive only. No trade-selection/tie-break rule is applied in this phase."
    }

    out = work / "portfolio-overlap-primary63.json"
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    core.upload_artifact(args.project, args.scope, "research/portfolio-overlap-primary63.json", out, "application/json; charset=utf-8")
    core.put_json(
        "/checkpoints/super-rsi/portfolio-overlap-concurrency-v1",
        {
            "source": core.SOURCE,
            "status": "success",
            "position": {
                "phase": "complete",
                "scope": args.scope,
                "universe": "primary_63",
                "trade_count": n,
                "peak_open_positions": peak,
                "time_weighted_avg_open": avg_open,
                "entry_preexisting_open_p95": qtile(preexisting, .95),
                "entry_preexisting_open_p99": qtile(preexisting, .99),
                "max_simultaneous_entries": max(burst_vals),
                "artifact_project": args.project,
                "artifact_scope": args.scope,
                "artifact_name": "research/portfolio-overlap-primary63.json"
            },
            "dropbox_path": None,
            "last_error": None
        }
    )

    compact = {
        "scope": args.scope,
        "universe": "primary_63",
        "trades": n,
        "all_artifact_trades": len(raw),
        "peak": peak,
        "avg_open": avg_open,
        "active_avg_open": avg_open_active,
        "entry_open_p90": qtile(preexisting, .90),
        "entry_open_p95": qtile(preexisting, .95),
        "entry_open_p99": qtile(preexisting, .99),
        "max_entry_burst": max(burst_vals),
        "capacity_pressure": entry_pressure,
        "time_above": time_exceed,
        "holding_hours": result["holding_hours"]
    }
    print(json.dumps(compact, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
