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
SLOTS = [5, 8, 10, 12, 15, 20, 25, 30, 35, 40, 45, 50, 56]


def parse_dt(v):
    if v is None:
        return None
    s = str(v).strip()
    if not s:
        return None
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
    return (pos / neg) if neg > 0 else None


def infer_return_field(rows, target_pf, target_mean_bps):
    keys = sorted(set().union(*(r.keys() for r in rows[:200])))
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
        if raw_pf is None or raw_mean == 0:
            continue
        lname = key.lower()
        name_rank = 0
        if "actual" in lname: name_rank -= 3
        if "bps" in lname: name_rank -= 3
        if "return" in lname or "ret" in lname: name_rank -= 2
        if "pnl" in lname or "profit" in lname: name_rank -= 2
        if "mid" in lname: name_rank += 3
        if "spread" in lname or "price" in lname: name_rank += 5
        # Try common units. PF is scale-invariant; mean pins the unit.
        best = None
        for scale in [1.0, 100.0, 10000.0, 0.01, 0.0001]:
            mean_bps = raw_mean * scale
            score = abs(raw_pf - target_pf) * 10.0 + abs(mean_bps - target_mean_bps) / max(1.0, abs(target_mean_bps)) + name_rank
            if best is None or score < best[0]:
                best = (score, scale, mean_bps)
        candidates.append((best[0], key, best[1], raw_pf, best[2]))
    if not candidates:
        raise RuntimeError(f"could not infer signed return field; keys={keys}")
    candidates.sort()
    score, key, scale, got_pf, got_mean = candidates[0]
    if abs(got_pf - target_pf) > 0.02 or abs(got_mean - target_mean_bps) > 1.0:
        raise RuntimeError(f"return inference failed canonical validation: best={candidates[:5]}")
    return key, scale, candidates[:5]


def max_realized_dd(accepted, slots):
    by_exit = defaultdict(float)
    for t in accepted:
        by_exit[t["exit"]] += t["bps"] / 10000.0 / slots
    equity = 1.0
    peak = 1.0
    max_dd = 0.0
    for ts in sorted(by_exit):
        equity += by_exit[ts]
        peak = max(peak, equity)
        dd = (equity / peak - 1.0) if peak > 0 else 0.0
        max_dd = min(max_dd, dd)
    return 100.0 * max_dd, equity


def utilization(accepted, slots):
    events = defaultdict(lambda: {"exit": 0, "entry": 0})
    for t in accepted:
        events[t["entry"]]["entry"] += 1
        events[t["exit"]]["exit"] += 1
    active = 0
    prev = None
    weighted = 0.0
    span = 0.0
    peak = 0
    for ts in sorted(events):
        if prev is not None:
            sec = (ts - prev).total_seconds()
            weighted += active * sec
            span += sec
        active = max(0, active - events[ts]["exit"])
        active += events[ts]["entry"]
        peak = max(peak, active)
        prev = ts
    avg_open = weighted / span if span > 0 else 0.0
    return avg_open, 100.0 * avg_open / slots if slots else 0.0, peak


def simulate(trades, slots):
    # Preregistered rule: exit at timestamp frees slots first. New entries are
    # processed by timestamp, then ticker A->Z, then original row order.
    by_entry = defaultdict(list)
    for t in trades:
        by_entry[t["entry"]].append(t)
    active = []  # min-heap of (exit_ts, seq)
    accepted = []
    skipped = []
    seq = 0
    for ts in sorted(by_entry):
        while active and active[0][0] <= ts:
            heapq.heappop(active)
        group = sorted(by_entry[ts], key=lambda x: (x["symbol"], x["idx"]))
        free = max(0, slots - len(active))
        take = group[:free]
        drop = group[free:]
        for t in take:
            seq += 1
            heapq.heappush(active, (t["exit"], seq))
            accepted.append(t)
        skipped.extend(drop)

    av = [t["bps"] for t in accepted]
    sv = [t["bps"] for t in skipped]
    avg_open, util_pct, peak = utilization(accepted, slots)
    dd_pct, ending_equity = max_realized_dd(accepted, slots)
    simple_return_pct = 100.0 * sum(x / 10000.0 / slots for x in av)
    return {
        "slots": slots,
        "position_notional_pct_initial_capital": 100.0 / slots,
        "accepted_trades": len(accepted),
        "skipped_trades": len(skipped),
        "retained_trade_pct": 100.0 * len(accepted) / len(trades),
        "accepted_pf": pf(av),
        "accepted_mean_bps": statistics.fmean(av) if av else None,
        "accepted_sum_bps": sum(av),
        "skipped_pf": pf(sv) if sv else None,
        "skipped_mean_bps": statistics.fmean(sv) if sv else None,
        "simple_return_on_initial_capital_pct": simple_return_pct,
        "realized_equity_ending_multiple": ending_equity,
        "realized_equity_max_drawdown_pct": dd_pct,
        "avg_open_positions": avg_open,
        "avg_gross_capital_utilization_pct": util_pct,
        "peak_open_positions": peak,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", default="private-backtest")
    ap.add_argument("--scope", required=True)
    args = ap.parse_args()

    work = Path(tempfile.mkdtemp(prefix="bt-capacity-"))
    tp = work / "trades.jsonl"
    rp = work / "report.json"
    core.download_artifact(args.project, args.scope, "final/trades.jsonl", tp)
    core.download_artifact(args.project, args.scope, "final/report.json", rp)
    report = json.loads(rp.read_text(encoding="utf-8"))
    primary_symbols = {str(s).upper() for s in report.get("primary_symbols", [])}
    target_pf = float(report["primary"]["actual"]["PF"])
    target_mean = float(report["primary"]["actual"]["mean_bps"])

    raw_all = [json.loads(x) for x in tp.read_text(encoding="utf-8").splitlines() if x.strip()]
    sample = raw_all[0]
    ek = pick_key(sample, ENTRY_KEYS); xk = pick_key(sample, EXIT_KEYS); sk = pick_key(sample, SYMBOL_KEYS)
    if not ek or not xk or not sk:
        raise RuntimeError(f"could not infer core trade fields; keys={sorted(sample.keys())}")
    raw = [r for r in raw_all if str(r.get(sk, "")).upper() in primary_symbols]
    if len(raw) != 4023:
        raise RuntimeError(f"primary trade count mismatch: {len(raw)} != 4023")

    rk, scale, candidates = infer_return_field(raw, target_pf, target_mean)
    trades = []
    for i, r in enumerate(raw):
        et, xt = parse_dt(r.get(ek)), parse_dt(r.get(xk))
        sym = str(r.get(sk, "")).upper()
        if et is None or xt is None or xt <= et:
            raise RuntimeError(f"invalid timestamps at row {i}")
        trades.append({"idx": i, "entry": et, "exit": xt, "symbol": sym, "bps": float(r[rk]) * scale})

    baseline_vals = [t["bps"] for t in trades]
    baseline = {
        "trade_count": len(trades),
        "pf": pf(baseline_vals),
        "mean_bps": statistics.fmean(baseline_vals),
        "sum_bps": sum(baseline_vals),
    }
    if abs(baseline["pf"] - target_pf) > 1e-8 or abs(baseline["mean_bps"] - target_mean) > 1e-6:
        raise RuntimeError(f"baseline return field does not reproduce canonical report: {baseline} target_pf={target_pf} target_mean={target_mean}")

    rows = [simulate(trades, s) for s in SLOTS]
    result = {
        "schema": 1,
        "scope": args.scope,
        "universe": "primary_63",
        "preregistered_rule": {
            "capital": "fixed initial capital; each accepted trade uses exactly 1/N initial capital where N=slot cap",
            "exit_priority": "exits at timestamp free slots before entries at same timestamp",
            "simultaneous_entry_tiebreak": "ticker ascending A->Z, then original row order",
            "outcome_dependent_selection": False,
            "drawdown_note": "realized-equity drawdown from closed-trade P&L only; not intratrade mark-to-market drawdown",
        },
        "fields": {"entry": ek, "exit": xk, "symbol": sk, "return_field": rk, "return_to_bps_scale": scale},
        "return_field_validation_top5": [
            {"field": c[1], "scale": c[2], "pf": c[3], "mean_bps": c[4], "score": c[0]} for c in candidates
        ],
        "baseline": baseline,
        "slot_results": rows,
    }
    out = work / "capital-capacity-v1.json"
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    core.upload_artifact(args.project, args.scope, "research/capital-capacity-v1.json", out, "application/json; charset=utf-8")
    core.put_json(
        "/checkpoints/super-rsi/capital-capacity-v1",
        {
            "source": core.SOURCE,
            "status": "success",
            "position": {
                "phase": "complete", "scope": args.scope, "universe": "primary_63",
                "rule": "fixed-1/N-initial-capital__exit-first__same-time-ticker-asc",
                "artifact_project": args.project, "artifact_scope": args.scope,
                "artifact_name": "research/capital-capacity-v1.json",
            },
            "dropbox_path": None, "last_error": None,
        },
    )
    compact = {
        "scope": args.scope, "return_field": rk, "return_scale": scale,
        "baseline": baseline,
        "slots": rows,
    }
    print(json.dumps(compact, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
