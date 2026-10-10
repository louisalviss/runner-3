#!/usr/bin/env python3
"""Read-only bidirectional discovery-recall audit; never a signal or trading writer.

Inputs are the same immutable scanner packet. Shadow thresholds/quotas are
hypotheses, not promoted settings. This script does not call the network.
"""
from __future__ import annotations

import hashlib
import json
import math
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "opportunity-radar"
OUT = DATA / "market-recall-shadow.json"
SHADOW = {
    "one_day_pump_pct": 7.0,
    "five_day_pump_pct": 15.0,
    "one_day_shock_pct": -7.0,
    "five_day_shock_pct": -15.0,
    "one_day_early_pct": 3.0,
    "early_volume_ratio": 2.0,
    "sector_relative_5d_pct": -10.0,
    "selection_quotas": {"PUMP": 28, "SHOCK": 28, "SECTOR": 16, "EARLY": 8},
}


def number(value: Any) -> float | None:
    try:
        result = float(value)
        return result if math.isfinite(result) else None
    except (TypeError, ValueError):
        return None


def is_corporate_action(rec: dict) -> bool:
    return bool(
        rec.get("corporate_action_suspected")
        or rec.get("corporate_action_unverified")
    )


def shadow_triggers(rec: dict) -> list[str]:
    if is_corporate_action(rec):
        return []
    one, five = number(rec.get("ret_1d_pct")), number(rec.get("ret_5d_pct"))
    result = []
    if one is not None and one >= SHADOW["one_day_pump_pct"]:
        result.append("1D_PUMP")
    if five is not None and five >= SHADOW["five_day_pump_pct"]:
        result.append("5D_PUMP")
    if one is not None and one <= SHADOW["one_day_shock_pct"]:
        result.append("1D_SHOCK")
    if five is not None and five <= SHADOW["five_day_shock_pct"]:
        result.append("5D_SHOCK")
    return result


def shadow_group(rec: dict, triggers: list[str]) -> str | None:
    # One symbol gets at most one shadow ranking slot. Current-session move
    # determines direction when a reversal satisfies opposite 5D threshold.
    one = number(rec.get("ret_1d_pct"))
    if any(t.endswith("_PUMP") for t in triggers) and any(
        t.endswith("_SHOCK") for t in triggers
    ):
        return "PUMP" if one is not None and one >= 0 else "SHOCK"
    if any(t.endswith("_PUMP") for t in triggers):
        return "PUMP"
    if any(t.endswith("_SHOCK") for t in triggers):
        return "SHOCK"
    rel = number(rec.get("sector_relative_5d_pct"))
    if rel is not None and rel <= SHADOW["sector_relative_5d_pct"]:
        return "SECTOR"
    volume = number(rec.get("volume_ratio"))
    if (
        one is not None
        and abs(one) >= SHADOW["one_day_early_pct"]
        and volume is not None
        and volume >= SHADOW["early_volume_ratio"]
    ):
        return "EARLY"
    return None


def priority(rec: dict, group: str) -> tuple[float, float, float, str]:
    one = abs(number(rec.get("ret_1d_pct")) or 0)
    five = abs(number(rec.get("ret_5d_pct")) or 0)
    vr = number(rec.get("volume_ratio")) or 0
    adv = number(rec.get("avg_dollar_volume_20d")) or 0
    # Comparable direction-aware severity, then volume/liquidity evidence.
    severity = max(one / 7.0, five / 15.0)
    if group == "SECTOR":
        severity = abs(number(rec.get("sector_relative_5d_pct")) or 0) / 10.0
    return (severity, min(vr, 10), math.log10(max(adv, 1)), str(rec["symbol"]))


def classify_baseline(rec: dict, selected: bool) -> str:
    state = rec.get("discovery_state")
    if selected:
        return "EMITTED_" + str(state or "UNCLASSIFIED")
    if is_corporate_action(rec):
        return "CORPORATE_ACTION_SUPPRESSED"
    if state == "RAW_ANOMALY":
        return "RANK_CAP_RAW"
    if state == "EARLY_WATCH":
        return "RANK_CAP_EARLY"
    one = number(rec.get("ret_1d_pct"))
    volume = number(rec.get("volume_ratio"))
    if one is not None and abs(one) >= 3.0 and (
        volume is None or volume < 2.0
    ):
        return "BELOW_EARLY_VOLUME"
    return "BELOW_BASELINE_DISCOVERY_RULE"


def audit(health: dict, prefilter: dict, signals: dict) -> dict:
    session = health.get("source_session_date")
    if (
        health.get("status") != "COMPLETE"
        or health.get("complete") is not True
        or not session
        or prefilter.get("source_session_date") != session
        or signals.get("source_session_date") != session
        or prefilter.get("complete") is not True
        or signals.get("complete") is not True
    ):
        raise ValueError("SOURCE_NOT_COMPLETE_OR_SESSION_MISMATCH")

    records = prefilter.get("records") or []
    source_signals = signals.get("signals") or []
    if len(records) != health.get("prefilter_count"):
        raise ValueError("PREFILTER_COUNT_MISMATCH")
    if len(source_signals) != health.get("signal_count"):
        raise ValueError("SOURCE_SIGNAL_COUNT_MISMATCH")
    if any(r.get("last_date") != session for r in records):
        raise ValueError("SYMBOL_SOURCE_SESSION_MISMATCH")
    if any((s.get("source") or {}).get("last_date") != session for s in source_signals):
        raise ValueError("SIGNAL_SOURCE_SESSION_MISMATCH")

    selected = [str(s.get("affected_assets") or "") for s in source_signals]
    if len(selected) != len(set(selected)):
        raise ValueError("DUPLICATE_SOURCE_SIGNAL")
    symbols = [str(r.get("symbol") or "") for r in records]
    if len(symbols) != len(set(symbols)):
        raise ValueError("DUPLICATE_PREFILTER_SYMBOL")
    if not set(selected).issubset(set(symbols)):
        raise ValueError("SOURCE_SIGNAL_NOT_IN_PREFILTER")

    selected_set = set(selected)
    groups: dict[str, list[dict]] = {name: [] for name in SHADOW["selection_quotas"]}
    rows: list[dict] = []
    baseline_counts: Counter = Counter()
    hit_counts: Counter = Counter()
    emitted_hit_counts: Counter = Counter()

    for rec in records:
        symbol = str(rec["symbol"])
        emitted = symbol in selected_set
        triggers = shadow_triggers(rec)
        group = shadow_group(rec, triggers)
        status = classify_baseline(rec, emitted)
        baseline_counts[status] += 1
        row = {
            "symbol": symbol,
            "source_session_date": session,
            "ret_1d_pct": number(rec.get("ret_1d_pct")),
            "ret_5d_pct": number(rec.get("ret_5d_pct")),
            "volume_ratio": number(rec.get("volume_ratio")),
            "raw_priority": number(rec.get("raw_priority")),
            "baseline_emitted": emitted,
            "baseline_discovery_state": rec.get("discovery_state"),
            "baseline_explanation": status,
            "shadow_triggers": triggers,
            "shadow_group": group,
            "shadow_selection": "NOT_SELECTED",
        }
        rows.append(row)
        for hit in triggers:
            hit_counts[hit] += 1
            if emitted:
                emitted_hit_counts[hit] += 1
        if group:
            groups[group].append((priority(rec, group), row))

    for name, candidates in groups.items():
        candidates.sort(key=lambda pair: pair[0], reverse=True)
        quota = SHADOW["selection_quotas"][name]
        for rank, (_, row) in enumerate(candidates, 1):
            row["shadow_rank"] = rank
            row["shadow_selection"] = "SELECTED" if rank <= quota else "SHADOW_QUOTA"
    shadow_selected = {r["symbol"] for r in rows if r["shadow_selection"] == "SELECTED"}
    status_counts = Counter(r["shadow_selection"] for r in rows)
    source_stats = signals.get("stats") or {}
    audit_rows_count = len(rows)
    return {
        "schema": "opportunity-radar-market-recall-shadow-v1",
        "status": "SHADOW_AUDIT_ONLY",
        "source_session_date": session,
        "generated_at": health.get("generated_at"),
        "scanner_version": health.get("scanner_version"),
        "selection_unchanged": True,
        "trading_gates_unchanged": True,
        "no_promotion_or_backdating": True,
        "model": SHADOW,
        "universe_funnel": {
            "listed_total": source_stats.get("listed_securities"),
            "common_like": source_stats.get("common_like_universe"),
            "snapshot_rows": source_stats.get("snapshot_rows"),
            "history_requested": health.get("history_requested"),
            "history_returned": health.get("history_returned"),
            "fresh_audited": audit_rows_count,
            "upstream_symbol_exclusion_reason_coverage": "COUNTS_ONLY_NOT_PER_SYMBOL",
            "universe_truncation_note": "No claims about symbols outside this fresh prefilter; upstream exclusions remain a separate audit gap.",
        },
        "counts": {
            "baseline_emitted": len(selected_set),
            "baseline_reason": dict(sorted(baseline_counts.items())),
            "qualified_price_moves": dict(sorted(hit_counts.items())),
            "baseline_emitted_price_moves": dict(sorted(emitted_hit_counts.items())),
            "shadow_group_eligible": {k: len(v) for k, v in groups.items()},
            "shadow_selection": dict(sorted(status_counts.items())),
            "shadow_selected_total": len(shadow_selected),
            "new_shadow_symbols_not_in_baseline": len(shadow_selected - selected_set),
            "baseline_symbols_not_in_shadow": len(selected_set - shadow_selected),
        },
        "scope_warning": (
            "Discovery recall only: 1D/5D price magnitude is a screening proxy. "
            "It cannot prove event value, alpha, viability, BUY/SHORT eligibility, "
            "or causality. No backdated point-in-time discovery."
        ),
        "records": rows,
    }


def main() -> None:
    health = json.loads((DATA / "market-health.json").read_text())
    # Do not reuse an older full-universe prefilter when the new market lane
    # degraded. Persist only a bounded failure status, not false audit results.
    if health.get("status") != "COMPLETE" or health.get("complete") is not True:
        OUT.write_text(json.dumps({
            "schema": "opportunity-radar-market-recall-shadow-v1",
            "status": "SOURCE_DEGRADED_NOT_EVALUATED",
            "source_session_date": health.get("source_session_date"),
            "generated_at": health.get("generated_at"),
            "reason_code": health.get("reason_code"),
            "records": [],
            "trading_gates_unchanged": True,
        }, indent=2) + "\\n", encoding="utf-8")
        print("Recall shadow withheld: MARKET_PRICING not COMPLETE")
        return
    prefilter_path = DATA / "market-prefilter.json"
    prefilter_bytes = prefilter_path.read_bytes()
    if hashlib.sha256(prefilter_bytes).hexdigest() != health.get("prefilter_sha256"):
        raise ValueError("PREFILTER_SHA256_MISMATCH")
    prefilter = json.loads(prefilter_bytes)
    signals = json.loads((DATA / "market-signals.json").read_text())
    result = audit(health, prefilter, signals)
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": result["status"], "session": result["source_session_date"],
        "funnel": result["universe_funnel"], "counts": result["counts"],
        "output": str(OUT),
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
