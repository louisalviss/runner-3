#!/usr/bin/env python3
"""Append-only, complete-session price-event register, separate from the top-80.

Each (NYSE source session, symbol, 1D/5D Pump/Shock predicate) gets one
immutable first-observed event. This is a *discovery ledger*, not a buy signal,
candidate, replay fill, or authority D1 writer. It never scrapes new data.
"""
from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "opportunity-radar"
SHADOW_PATH = DATA / "market-recall-shadow.json"
HEALTH_PATH = DATA / "market-health.json"
LEDGER_PATH = DATA / "market-move-events.jsonl"
ALLOWED = frozenset({"1D_PUMP", "5D_PUMP", "1D_SHOCK", "5D_SHOCK", "INTRADAY_HIGH_PUMP", "INTRADAY_LOW_SHOCK"})
SCHEMA = "market-pricing-append-only-raw-move-event-v1"


def finite_or_none(value: Any) -> float | None:
    try:
        n = float(value)
        return n if math.isfinite(n) else None
    except (ValueError, TypeError):
        return None


def source_events(shadow: dict, health: dict, captured_at: str) -> list[dict]:
    session = health.get("source_session_date")
    if (
        not session
        or health.get("status") != "COMPLETE"
        or health.get("complete") is not True
        or shadow.get("status") != "SHADOW_AUDIT_ONLY"
        or shadow.get("source_session_date") != session
        or shadow.get("selection_unchanged") is not True
    ):
        raise ValueError("SOURCE_NOT_VERIFIED_COMPLETE_OR_SESSION_MISMATCH")
    records = shadow.get("records") or []
    if len(records) != health.get("prefilter_count"):
        raise ValueError("SHADOW_PREFILTER_COUNT_MISMATCH")

    ids: set[str] = set()
    seen_symbols: set[str] = set()
    out: list[dict] = []
    for row in records:
        if row.get("source_session_date") != session:
            raise ValueError("PER_SYMBOL_SESSION_MISMATCH")
        symbol = str(row.get("symbol") or "")
        if not symbol or any(c not in "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789.-" for c in symbol):
            raise ValueError("INVALID_SYMBOL")
        if symbol in seen_symbols:
            raise ValueError("DUPLICATE_SOURCE_PRICE_EVENT")
        seen_symbols.add(symbol)
        daily_triggers = row.get("shadow_triggers") or []
        intraday_triggers = row.get("shadow_intraday_triggers") or []
        if not isinstance(daily_triggers, list) or not isinstance(intraday_triggers, list):
            raise ValueError("INVALID_PRICE_TRIGGER_FORMAT")
        triggers = daily_triggers + intraday_triggers
        if len(triggers) != len(set(triggers)):
            raise ValueError("INVALID_OR_DUPLICATE_PRICE_TRIGGER")
        if any(t not in ALLOWED for t in triggers):
            raise ValueError("UNKNOWN_PRICE_TRIGGER")
        if intraday_triggers and row.get("intraday_extremes_verified") is not True:
            raise ValueError("INTRADAY_OHLC_NOT_VERIFIED")
        if any(t.startswith("INTRADAY_") for t in daily_triggers):
            raise ValueError("MISCLASSIFIED_INTRADAY_TRIGGER")
        if any(not t.startswith("INTRADAY_") for t in intraday_triggers):
            raise ValueError("MISCLASSIFIED_CLOSE_TRIGGER")
        for trigger in triggers:
            if trigger == "INTRADAY_HIGH_PUMP":
                change = finite_or_none(row.get("intraday_high_vs_prior_adjusted_close_pct"))
                valid = change is not None and change >= 7
            elif trigger == "INTRADAY_LOW_SHOCK":
                change = finite_or_none(row.get("intraday_low_vs_prior_adjusted_close_pct"))
                valid = change is not None and change <= -7
            else:
                change = finite_or_none(row.get("ret_1d_pct") if trigger.startswith("1D_") else row.get("ret_5d_pct"))
                valid = change is not None and (
                    (trigger.endswith("_PUMP") and change >= (7 if trigger.startswith("1D_") else 15))
                    or (trigger.endswith("_SHOCK") and change <= (-7 if trigger.startswith("1D_") else -15))
                )
            if not valid:
                raise ValueError("PRICE_TRIGGER_INCONSISTENT_WITH_ADJUSTED_MOVE")
            event_id = f"{session}|{symbol}|{trigger}"
            if event_id in ids:
                raise ValueError("DUPLICATE_SOURCE_PRICE_EVENT")
            ids.add(event_id)
            out.append({
                "schema": SCHEMA,
                "event_id": event_id,
                "source_session_date": session,
                "symbol": symbol,
                "predicate": trigger,
                "adjusted_return_1d_pct_first_seen": finite_or_none(row.get("ret_1d_pct")),
                "adjusted_return_5d_pct_first_seen": finite_or_none(row.get("ret_5d_pct")),
                "completed_daily_extreme_adjusted_return_pct_first_seen": (
                    change if trigger.startswith("INTRADAY_") else None
                ),
                "intraday_basis": (
                    "COMPLETED_DAILY_BAR_HIGH_LOW_NOT_REALTIME"
                    if trigger.startswith("INTRADAY_") else None
                ),
                "volume_ratio_first_seen": finite_or_none(row.get("volume_ratio")),
                "baseline_emitted": row.get("baseline_emitted") is True,
                "baseline_exclusion_reason": row.get("baseline_explanation"),
                "source_prefilter_sha256": health.get("prefilter_sha256"),
                "source_packet_generated_at": shadow.get("generated_at"),
                "event_first_logged_at_utc": captured_at,
                "state": "RAW_MOVE_ONLY_NOT_TRADE",
            })
    return sorted(out, key=lambda r: r["event_id"])


def append_unseen(original: str, new_events: list[dict]) -> tuple[str, dict]:
    prior: set[str] = set()
    existing_count = 0
    for line in original.splitlines():
        if not line.strip():
            continue
        old = json.loads(line)
        key = old.get("event_id")
        if old.get("schema") != SCHEMA or not key or key in prior:
            raise ValueError("EXISTING_EVENT_LEDGER_CORRUPT_OR_DUPLICATED")
        prior.add(key)
        existing_count += 1
    seen: set[str] = set()
    additions: list[dict] = []
    for event in new_events:
        key = event["event_id"]
        if key in seen:
            raise ValueError("DUPLICATE_NEW_EVENT")
        seen.add(key)
        if key not in prior:
            additions.append(event)

    if not additions:
        return original, {"existing": existing_count, "new": 0, "total": existing_count, "source_events": len(new_events)}
    newline = "" if not original or original.endswith("\n") else "\n"
    rendered = original + newline + "".join(json.dumps(x, ensure_ascii=False, separators=(",", ":"), allow_nan=False) + "\n" for x in additions)
    return rendered, {
        "existing": existing_count,
        "new": len(additions),
        "total": existing_count + len(additions),
        "source_events": len(new_events),
    }


def rolling_severe_backlog(raw_text: str, source_session: str, max_sessions: int = 10) -> dict:
    """Diagnostics only: aggregate severe historical price events by ticker.

    Ticker grouping is not economic-event deduplication or an investment decision.
    """
    if max_sessions < 1:
        raise ValueError("INVALID_ROLLING_WINDOW")
    events = [json.loads(line) for line in raw_text.splitlines() if line.strip()]
    dates = sorted({x["source_session_date"] for x in events if x["source_session_date"] <= source_session})
    selected_dates = dates[-max_sessions:]
    grouped = {}
    severe_rows = 0
    for event in events:
        if event.get("schema") != SCHEMA or event["source_session_date"] > source_session:
            raise ValueError("INVALID_ROLLING_SOURCE")
        if event["source_session_date"] not in selected_dates:
            continue
        predicate = event.get("predicate")
        field = ("adjusted_return_1d_pct_first_seen" if predicate == "1D_SHOCK"
                 else "adjusted_return_5d_pct_first_seen" if predicate == "5D_SHOCK" else None)
        change = finite_or_none(event.get(field)) if field else None
        if change is None or change > -15.0:
            continue
        severe_rows += 1
        symbol = event["symbol"]
        item = grouped.setdefault(symbol, {
            "symbol": symbol, "sessions": [], "worst_severe_return_pct": change,
            "outside_top80_seen": False, "raw_predicate_count": 0,
            "triage": "PENDING_ECONOMIC_CAUSAL_RECONCILIATION", "actionable": False,
        })
        if event["source_session_date"] not in item["sessions"]:
            item["sessions"].append(event["source_session_date"])
        item["worst_severe_return_pct"] = min(item["worst_severe_return_pct"], change)
        item["outside_top80_seen"] |= event.get("baseline_emitted") is not True
        item["raw_predicate_count"] += 1
    queue = sorted(grouped.values(), key=lambda x: (x["worst_severe_return_pct"], x["symbol"]))
    for row in queue:
        row["sessions"].sort()
    return {
        "status": "RESEARCH_ONLY_PENDING_RECONCILIATION",
        "source_session_date": source_session,
        "observed_sessions": selected_dates,
        "coverage": "OBSERVED_LEDGER_SESSIONS_ONLY_NOT_ALL_LISTINGS",
        "severe_predicate_rows": severe_rows,
        "severe_unique_symbols": len(queue),
        "ever_outside_top80": sum(x["outside_top80_seen"] for x in queue),
        "multi_session_symbols": sum(len(x["sessions"]) > 1 for x in queue),
        "no_automatic_signals_or_trades": True, "queue": queue,
    }


def main() -> None:
    health = json.loads(HEALTH_PATH.read_text())
    if health.get("status") != "COMPLETE" or health.get("complete") is not True:
        print("RAW_MOVE_LEDGER_SKIPPED: SOURCE_NOT_COMPLETE; no append")
        return
    shadow = json.loads(SHADOW_PATH.read_text())
    timestamp = datetime.now(timezone.utc).isoformat()
    events = source_events(shadow, health, timestamp)
    old = LEDGER_PATH.read_text(encoding="utf-8") if LEDGER_PATH.exists() else ""
    output, stats = append_unseen(old, events)
    rolling = rolling_severe_backlog(output, health["source_session_date"])
    shadow["rolling_severe_backlog"] = rolling
    shadow_tmp = SHADOW_PATH.with_suffix(".json.tmp")
    shadow_tmp.write_text(json.dumps(shadow, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    shadow_tmp.replace(SHADOW_PATH)
    if output != old:
        tmp = LEDGER_PATH.with_suffix(".jsonl.tmp")
        tmp.write_text(output, encoding="utf-8")
        tmp.replace(LEDGER_PATH)
    print(json.dumps({
        "status": "RAW_MOVE_LEDGER_APPEND_ONLY", "session": health["source_session_date"],
        "raw_1d_5d_predicates": stats["source_events"],
        "new_events": stats["new"], "cumulative_events": stats["total"],
        "baseline_selection_unchanged": True, "d1_unchanged": True,
        "rolling_severe_symbols": rolling["severe_unique_symbols"],
    }))


if __name__ == "__main__":
    main()
