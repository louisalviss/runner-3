#!/usr/bin/env python3
from __future__ import annotations

import argparse
import bisect
import json
import tarfile
import tempfile
from collections import Counter
from datetime import datetime
from pathlib import Path

import private_backtest_worker_v2 as core
import private_backtest_us60_survivorship_audit as surv

PROJECT = "private-backtest"


def ts(value: str) -> datetime:
    x = str(value).strip().replace("Z", "+00:00")
    return datetime.fromisoformat(x)


def point_in_time_membership(rows):
    dates = [d for d, _ in rows]
    sets = [s for _, s in rows]

    def at(when: datetime):
        i = bisect.bisect_right(dates, when.date()) - 1
        return sets[i] if i >= 0 else set()

    return at


def load_available_trade_rows(c: dict, work: Path):
    stage_path = work / "stage.json"
    core.download_artifact(PROJECT, c["scope"], "research/survivorship-audit-stage.json", stage_path)
    stage = json.loads(stage_path.read_text(encoding="utf-8"))
    controls = [str(x).upper() for x in stage["control_symbols_preregistered"]]

    symbols_root = work / "symbols"
    symbols_root.mkdir(exist_ok=True)
    missing_shards = []
    for sid in range(int(c["shards"])):
        ar = work / f"shard-{sid:02d}.tar.gz"
        try:
            core.download_artifact(PROJECT, c["scope"], f"shards/shard-{sid:02d}.tar.gz", ar)
        except Exception:
            missing_shards.append(sid)
            continue
        with tarfile.open(ar, "r:gz") as tf:
            tf.extractall(work)

    control_rows = []
    successful_controls = []
    for sym in controls:
        sd = symbols_root / sym
        sp = sd / f"summary-{sym}.json"
        if not sp.exists():
            continue
        try:
            sm = json.loads(sp.read_text(encoding="utf-8"))
        except Exception:
            continue
        if sm.get("status") != "OK":
            continue
        rows = surv.read_trade_rows(sd)
        for r in rows:
            r = dict(r)
            r["_source_group"] = "historical_removal_control"
            control_rows.append(r)
        successful_controls.append(sym)

    report_p = work / "canonical-report.json"
    trades_p = work / "canonical-trades.jsonl"
    core.download_artifact(PROJECT, c["source_scope"], "final/report.json", report_p)
    core.download_artifact(PROJECT, c["source_scope"], "final/trades.jsonl", trades_p)
    report = json.loads(report_p.read_text(encoding="utf-8"))
    primary = {str(x).upper() for x in report.get("primary_symbols", [])}
    canonical_rows = []
    for line in trades_p.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        if str(r.get("symbol", "")).upper() not in primary:
            continue
        if r.get("actual_return_bps") is None:
            continue
        r["_source_group"] = "canonical_current_universe"
        canonical_rows.append(r)
    if len(canonical_rows) != 4023:
        raise RuntimeError(f"canonical trade mismatch: {len(canonical_rows)} != 4023")

    return stage, canonical_rows, control_rows, successful_controls, missing_shards


def metric_rows(rows):
    vals = [float(r["actual_return_bps"]) for r in rows]
    return surv.metrics(vals)


def filter_pit_proxy(rows, history_rows, aliases):
    member_at = point_in_time_membership(history_rows)
    kept, removed = [], []
    reason_counts = Counter()
    for r in rows:
        sym = surv.norm_symbol(str(r.get("symbol", "")), aliases)
        when_raw = r.get("signal_entry") or r.get("entry_time")
        if not when_raw:
            removed.append(r)
            reason_counts["missing_signal_time"] += 1
            continue
        when = ts(when_raw)
        if sym in member_at(when):
            rr = dict(r)
            rr["symbol"] = sym
            rr["_pit_signal_date"] = when.date().isoformat()
            kept.append(rr)
        else:
            removed.append(r)
            reason_counts["not_member_at_signal_time"] += 1
    return kept, removed, dict(reason_counts)


def standard_drawdown_from_exits(accepted, slots):
    ordered = sorted(accepted, key=lambda r: (ts(r["exit_time"]), str(r.get("symbol", ""))))
    equity = 1.0
    peak = 1.0
    worst = 0.0
    for r in ordered:
        equity += (float(r["actual_return_bps"]) / 10000.0) / slots
        peak = max(peak, equity)
        if peak > 0:
            worst = min(worst, equity / peak - 1.0)
    return worst * 100.0, equity


def simulate_slots(rows, slots, start, end):
    candidates = sorted(rows, key=lambda r: (ts(r["entry_time"]), str(r.get("symbol", ""))))
    active = []  # tuples: (exit_time, symbol)
    accepted = []
    skipped = []
    peak_open = 0

    for r in candidates:
        et = ts(r["entry_time"])
        active = [x for x in active if x[0] > et]  # exits at same timestamp free slots first
        active.sort(key=lambda x: (x[0], x[1]))
        if len(active) < slots:
            accepted.append(r)
            active.append((ts(r["exit_time"]), str(r.get("symbol", ""))))
            peak_open = max(peak_open, len(active))
        else:
            skipped.append(r)

    vals = [float(r["actual_return_bps"]) for r in accepted]
    simple_return = sum(v / 10000.0 for v in vals) / slots
    realized_dd_pct, final_equity = standard_drawdown_from_exits(accepted, slots)

    total_seconds = max((end - start).total_seconds(), 1.0)
    occupied_seconds = 0.0
    for r in accepted:
        a = max(ts(r["entry_time"]), start)
        b = min(ts(r["exit_time"]), end)
        if b > a:
            occupied_seconds += (b - a).total_seconds()
    avg_util = occupied_seconds / (slots * total_seconds)

    years = total_seconds / (365.2425 * 24 * 3600)
    cagr_equiv = None
    if final_equity > 0 and years > 0:
        cagr_equiv = final_equity ** (1.0 / years) - 1.0

    yearly = Counter()
    for r in accepted:
        yearly[str(ts(r.get("signal_entry") or r["entry_time"]).year)] += 1

    max_entry = max((float(r.get("actual_entry", 0.0) or 0.0) for r in accepted), default=0.0)
    whole_share_floor_proxy = max_entry * slots if max_entry > 0 else None

    return {
        "slots": slots,
        "notional_per_position_fraction": 1.0 / slots,
        "candidates": len(rows),
        "accepted_trades": len(accepted),
        "retained_fraction": len(accepted) / len(rows) if rows else 0.0,
        "skipped_due_to_capacity": len(skipped),
        "accepted_trade_metrics": surv.metrics(vals),
        "simple_return_pct_fixed_initial_notional": simple_return * 100.0,
        "cagr_equivalent_from_final_realized_equity_pct": cagr_equiv * 100.0 if cagr_equiv is not None else None,
        "realized_exit_equity_max_drawdown_pct": realized_dd_pct,
        "mtm_drawdown": {
            "status": "NOT_AVAILABLE_FROM_TRADE_LEDGER_ONLY",
            "reason": "Intratrade mark-to-market price paths are not stored in the trade ledger; price-path replay is required."
        },
        "average_slot_utilization_fraction": avg_util,
        "peak_open_positions_after_capacity": peak_open,
        "years": years,
        "trades_per_year": len(accepted) / years if years > 0 else None,
        "accepted_trades_by_signal_year": dict(sorted(yearly.items())),
        "whole_share_equal_slot_minimum_capital_proxy_usd": whole_share_floor_proxy,
        "whole_share_proxy_note": "Conservative proxy = slots x highest historical accepted entry price; fractional-share brokers do not need this floor."
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    ap.add_argument("--slots", default="40,50,56")
    args = ap.parse_args()

    c = surv.load_json(args.config)
    work = Path(tempfile.mkdtemp(prefix="us60-pit-portfolio-"))
    stage, canonical, controls, successful_controls, missing_shards = load_available_trade_rows(c, work)

    hist_rows, hist_meta = surv.fetch_history(c)
    aliases = {surv.norm_symbol(k, {}): surv.norm_symbol(v, {}) for k, v in c.get("ticker_aliases", {}).items()}
    all_available = canonical + controls
    pit_rows, excluded_rows, exclusion_reasons = filter_pit_proxy(all_available, hist_rows, aliases)

    start = ts(c["report_start"])
    end = ts(c["end"])
    slot_values = [int(x.strip()) for x in args.slots.split(",") if x.strip()]
    sims = {str(n): simulate_slots(pit_rows, n, start, end) for n in slot_values}

    result = {
        "schema": 1,
        "scope": "bt-super-rsi-us60-pit-proxy-portfolio-v1",
        "source_survivorship_scope": c["scope"],
        "source_canonical_scope": c["source_scope"],
        "method": "S&P500_POINT_IN_TIME_MEMBERSHIP_PROXY_ON_SIGNAL_DATE_OVER_AVAILABLE_CANONICAL_PLUS_REMOVAL_CONTROL_ROWS",
        "important_limitations": [
            "This is a point-in-time S&P500 membership proxy, not proof of the original US60 selection rule.",
            "24/84 preregistered historical-removal controls were unavailable in the prior audit, so residual survivorship risk remains.",
            "The available union does not guarantee coverage of every transient constituent that entered and exited between endpoints.",
            "MTM drawdown requires intratrade price-path replay and is not inferable from entry/exit ledger alone."
        ],
        "history_parse": hist_meta,
        "canonical_rows": len(canonical),
        "available_control_rows": len(controls),
        "successful_control_symbols": len(successful_controls),
        "missing_shards": missing_shards,
        "all_available_rows": len(all_available),
        "pit_proxy_eligible_rows": len(pit_rows),
        "pit_proxy_excluded_rows": len(excluded_rows),
        "pit_proxy_exclusion_reasons": exclusion_reasons,
        "metrics_all_available_static_union": metric_rows(all_available),
        "metrics_pit_proxy_eligible": metric_rows(pit_rows),
        "portfolio": sims,
    }

    out = work / "us60-pit-proxy-portfolio-v1.json"
    out.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    core.upload_artifact(PROJECT, c["scope"], "research/us60-pit-proxy-portfolio-v1.json", out, "application/json; charset=utf-8")
    core.put_json("/checkpoints/super-rsi/us60-pit-proxy-portfolio-v1", {
        "source": core.SOURCE,
        "status": "complete",
        "position": {
            "phase": "evaluated",
            "pit_proxy_trades": len(pit_rows),
            "pit_proxy_pf": result["metrics_pit_proxy_eligible"]["pf"],
            "slot40": sims.get("40"),
        },
        "dropbox_path": None,
        "last_error": None,
    })
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
