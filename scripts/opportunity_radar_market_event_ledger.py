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
ALLOWED = frozenset({"1D_PUMP", "5D_PUMP", "1D_SHOCK", "5D_SHOCK"})
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
        triggers = row.get("shadow_triggers") or []
        if not isinstance(triggers, list) or len(triggers) != len(set(triggers)):
            raise ValueError("INVALID_OR_DUPLICATE_PRICE_TRIGGER")
        if any(t not in ALLOWED for t in triggers):
            raise ValueError("UNKNOWN_PRICE_TRIGGER")
        for trigger in triggers:
            change = finite_or_none(row.get("ret_1d_pct") if trigger.startswith("1D_") else row.get("ret_5d_pct"))
            if change is None or not (
                (trigger.endswith("_PUMP") and change >= (7 if trigger.startswith("1D_") else 15))
                or (trigger.endswith("_SHOCK") and change <= (-7 if trigger.startswith("1D_") else -15))
            ):
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
    if output != old:
        tmp = LEDGER_PATH.with_suffix(".jsonl.tmp")
        tmp.write_text(output, encoding="utf-8")
        tmp.replace(LEDGER_PATH)
    print(json.dumps({
        "status": "RAW_MOVE_LEDGER_APPEND_ONLY", "session": health["source_session_date"],
        "raw_1d_5d_predicates": stats["source_events"],
        "new_events": stats["new"], "cumulative_events": stats["total"],
        "baseline_selection_unchanged": True, "d1_unchanged": True,
    }))


if __name__ == "__main__":
    main()
