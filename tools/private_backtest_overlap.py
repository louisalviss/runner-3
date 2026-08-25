#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import os
import statistics
import tempfile
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

import private_backtest_worker_v2 as core

ENTRY_KEYS = [
    "entry_time", "entry_ts", "entry_at", "entry_datetime", "entry_dt",
    "entry_timestamp", "entry_time_utc", "entry",
]
EXIT_KEYS = [
    "exit_time", "exit_ts", "exit_at", "exit_datetime", "exit_dt",
    "exit_timestamp", "exit_time_utc", "exit",
]
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


def quantile(vals, q):
    if not vals:
        return None
    xs = sorted(vals)
    if len(xs) == 1:
        return xs[0]
    pos = (len(xs) - 1) * q
    lo = int(math.floor(pos)); hi = int(math.ceil(pos))
    if lo == hi:
        return xs[lo]
    return xs[lo] * (hi - pos) + xs[hi] * (pos - lo)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", default="private-backtest")
    ap.add_argument("--scope", required=True)
    ap.add_argument("--artifact", default="final/trades.jsonl")
    args = ap.parse_args()

    work = Path(tempfile.mkdtemp(prefix="bt-overlap-"))
    trades_path = work / "trades.jsonl"
    core.download_artifact(args.project, args.scope, args.artifact, trades_path)

    raw = []
    for line in trades_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            raw.append(json.loads(line))
    if not raw:
        raise RuntimeError("no trades found")

    sample = raw[0]
    entry_key = pick_key(sample, ENTRY_KEYS)
    exit_key = pick_key(sample, EXIT_KEYS)
    symbol_key = pick_key(sample, SYMBOL_KEYS)
    if not entry_key or not exit_key:
        raise RuntimeError(f"could not infer entry/exit fields; keys={sorted(sample.keys())}")

    trades = []
    invalid = []
    for i, r in enumerate(raw):
        et = parse_dt(r.get(entry_key)); xt = parse_dt(r.get(exit_key))
        sym = str(r.get(symbol_key, "")).upper() if symbol_key else ""
        if et is None or xt is None or xt <= et:
            invalid.append(i); continue
        trades.append((et, xt, sym))
    if invalid:
        raise RuntimeError(f"invalid trade timestamps: count={len(invalid)} sample={invalid[:10]}")

    # Sweep line. Exits at the exact same timestamp free a slot before entries.
    events = defaultdict(lambda: {"exit": 0, "entry": 0})
    entry_bursts = Counter()
    durations_h = []
    for et, xt, _ in trades:
        events[et]["entry"] += 1
        events[xt]["exit"] += 1
        entry_bursts[et] += 1
        durations_h.append((xt - et).total_seconds() / 3600.0)

    times = sorted(events)
    active = 0
    peak = 0
    active_before_entries = []
    active_after_entries = []
    entry_pressure = Counter()
    time_at_level_s = Counter()
    prev = None
    for t in times:
        if prev is not None:
            time_at_level_s[active] += (t - prev).total_seconds()
        e = events[t]
        active = max(0, active - e["exit"])
        before = active
        if e["entry"]:
            active_before_entries.extend([before] * e["entry"])
            entry_pressure[before] += e["entry"]
        active += e["entry"]
        if e["entry"]:
            active_after_entries.extend([active] * e["entry"])
        peak = max(peak, active)
        prev = t

    total_span_s = sum(time_at_level_s.values())
    weighted_avg_active = (
        sum(level * sec for level, sec in time_at_level_s.items()) / total_span_s
        if total_span_s > 0 else None
    )
    occupied_span_s = sum(sec for level, sec in time_at_level_s.items() if level > 0)
    occupied_avg_active = (
        sum(level * sec for level, sec in time_at_level_s.items() if level > 0) / occupied_span_s
        if occupied_span_s > 0 else None
    )

    # Capacity demand: fraction of ENTRY SIGNALS that arrive while N or more
    # positions are already open. This avoids arbitrary trade-selection rules.
    capacity_pressure = {}
    n = len(trades)
    for slots in [1, 2, 3, 5, 8, 10, 12, 15, 20, 25, 30]:
        pressured = sum(1 for x in active_before_entries if x >= slots)
        capacity_pressure[str(slots)] = {
            "signals_arriving_full": pressured,
            "pct_of_entries": 100.0 * pressured / n,
        }

    # Time-weighted exceedance: fraction of observed wall-clock span with active > slots.
    time_exceed = {}
    for slots in [1, 2, 3, 5, 8, 10, 12, 15, 20, 25, 30]:
        sec = sum(v for level, v in time_at_level_s.items() if level > slots)
        time_exceed[str(slots)] = 100.0 * sec / total_span_s if total_span_s else 0.0

    burst_counts = list(entry_bursts.values())
    top_bursts = sorted(
        ({"timestamp": t.isoformat(), "entries": c} for t, c in entry_bursts.items()),
        key=lambda x: (-x["entries"], x["timestamp"]),
    )[:20]

    result = {
        "schema": 1,
        "scope": args.scope,
        "artifact": args.artifact,
        "trade_count": n,
        "fields": {"entry": entry_key, "exit": exit_key, "symbol": symbol_key},
        "range": {
            "first_entry": min(t[0] for t in trades).isoformat(),
            "last_exit": max(t[1] for t in trades).isoformat(),
        },
        "duration_hours": {
            "mean": statistics.fmean(durations_h),
            "median": statistics.median(durations_h),
            "p90": quantile(durations_h, 0.90),
            "p95": quantile(durations_h, 0.95),
            "p99": quantile(durations_h, 0.99),
            "max": max(durations_h),
        },
        "concurrency": {
            "peak_open_positions": peak,
            "time_weighted_avg_open": weighted_avg_active,
            "avg_open_when_portfolio_active": occupied_avg_active,
            "entry_preexisting_open_mean": statistics.fmean(active_before_entries),
            "entry_preexisting_open_median": statistics.median(active_before_entries),
            "entry_preexisting_open_p90": quantile(active_before_entries, 0.90),
            "entry_preexisting_open_p95": quantile(active_before_entries, 0.95),
            "entry_preexisting_open_p99": quantile(active_before_entries, 0.99),
        },
        "simultaneous_entry_bursts": {
            "unique_entry_timestamps": len(entry_bursts),
            "mean_entries_per_entry_timestamp": statistics.fmean(burst_counts),
            "median": statistics.median(burst_counts),
            "p95": quantile(burst_counts, 0.95),
            "p99": quantile(burst_counts, 0.99),
            "max": max(burst_counts),
            "top20": top_bursts,
        },
        "capacity_pressure_by_slots": capacity_pressure,
        "time_pct_active_above_slots": time_exceed,
    }

    out = work / "portfolio-overlap.json"
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    core.upload_artifact(args.project, args.scope, "research/portfolio-overlap.json", out, "application/json; charset=utf-8")

    # D1 compact checkpoint, private output remains in Core/R2.
    core.put_json(
        "/checkpoints/super-rsi/portfolio-overlap-concurrency-v1",
        {
            "source": core.SOURCE,
            "status": "success",
            "position": {
                "phase": "complete",
                "scope": args.scope,
                "trade_count": n,
                "peak_open_positions": peak,
                "time_weighted_avg_open": weighted_avg_active,
                "entry_preexisting_open_p95": quantile(active_before_entries, 0.95),
                "max_simultaneous_entries": max(burst_counts),
                "artifact_project": args.project,
                "artifact_scope": args.scope,
                "artifact_name": "research/portfolio-overlap.json",
            },
            "dropbox_path": None,
            "last_error": None,
        },
    )

    # Compact aggregate only; no individual trade records are exposed in public logs.
    compact = {
        "scope": args.scope,
        "trades": n,
        "peak": peak,
        "avg_open": weighted_avg_active,
        "active_avg_open": occupied_avg_active,
        "entry_open_p95": quantile(active_before_entries, 0.95),
        "entry_open_p99": quantile(active_before_entries, 0.99),
        "max_entry_burst": max(burst_counts),
        "capacity_pressure": capacity_pressure,
        "time_above": time_exceed,
    }
    print(json.dumps(compact, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
