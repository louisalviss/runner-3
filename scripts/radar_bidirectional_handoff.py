#!/usr/bin/env python3
"""Read-only, deterministic Global Viral <-> Opportunity Radar event handoff.

Inputs are EXISTING verified ledgers and the existing Dropbox research checkpoint.
No network, no state writes, no scanner, no scheduling and no trading authority.
Consumers must CAS-write only the returned projection into the same checkpoint,
then independently verify exact readback before claiming a handoff persisted.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import math
import re
from datetime import datetime, timezone, timedelta
from pathlib import Path

SCHEMA = "global-opportunity-handoff-v1"
# Issuer identity aliases are deliberately narrow. Add symbols only after
# validating the issuer's security identity, never by loose substring matching.
VERIFIED_ALIASES = {
    "NVIDIA CORPORATION": "NVDA",
}
VALID_SYMBOL = re.compile(r"^[A-Z][A-Z0-9.-]{0,11}$")


def parse_time(value):
    if not isinstance(value, str) or not value:
        raise ValueError("MISSING_EVENT_TIME")
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        raise ValueError("NAIVE_EVENT_TIME")
    return dt.astimezone(timezone.utc)


def key_hash(*parts):
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:24]


def symbol_for_event(event):
    raw = event.get("symbol") or event.get("ticker") or event.get("affected_ticker")
    if raw and VALID_SYMBOL.fullmatch(str(raw)):
        return str(raw)
    entity = str(event.get("primary_entity") or "").upper()
    for name, symbol in VERIFIED_ALIASES.items():
        if entity.startswith(name) and (len(entity) == len(name) or not entity[len(name)].isalnum()):
            return symbol
    return None


def eligible_global_events(ledger, *, as_of, max_age_days=14):
    """Route only independently source-backed issuer events, never X claims alone.

    Delivery confirmation is independent of economic intake; lack of notification
    receipt cannot suppress a verified event, nor does precommit prove delivery.
    """
    if not isinstance(ledger, dict) or not isinstance(ledger.get("entries"), dict):
        raise ValueError("GLOBAL_LEDGER_INVALID")
    now = parse_time(as_of)
    out = []
    for source_key, event in ledger["entries"].items():
        if not isinstance(event, dict):
            continue
        symbol = symbol_for_event(event)
        material_key = event.get("material_update_key")
        source = event.get("last_verified_source_url")
        stamp = event.get("source_event_time_vn")
        if not (symbol and material_key and source and stamp):
            continue
        if not str(source).startswith("https://"):
            continue
        try:
            t = parse_time(stamp)
        except (ValueError, TypeError):
            continue
        age = now - t
        if age < -timedelta(minutes=10) or age > timedelta(days=max_age_days):
            continue
        event_id = "G2O|" + key_hash(source_key, str(material_key))
        out.append({
            "event_id": event_id,
            "direction": "GLOBAL_TO_OPPORTUNITY",
            "source_event_key": source_key,
            "material_update_key": material_key,
            "symbol": symbol,
            "source_event_time_vn": stamp,
            "primary_source_url": source,
            "headline": event.get("label") or event.get("named_event") or "",
            "verified_source": True,
            "global_notification_delivery": event.get("delivery_status") or "UNKNOWN",
            "intake_state": "PENDING_ECONOMIC_REVIEW",
            "signal_state": "NOT_AUTHORIZED",
        })
    return sorted(out, key=lambda x: (x["source_event_time_vn"], x["event_id"]))


def reverse_price_requests(price_events, health, *, max_out=30):
    """Only the latest COMPLETE, immutable price session enters reverse triage."""
    if (health.get("status") != "COMPLETE" or health.get("complete") is not True
            or not health.get("source_session_date") or not health.get("prefilter_sha256")):
        raise ValueError("MARKET_PACKET_NOT_VERIFIED_COMPLETE")
    session = health["source_session_date"]
    by_symbol = {}
    for r in price_events:
        if not isinstance(r, dict) or r.get("source_session_date") != session:
            continue
        symbol = r.get("symbol")
        if not symbol or not VALID_SYMBOL.fullmatch(str(symbol)):
            continue
        if r.get("corporate_action_suspected") is True:
            continue
        predicate = r.get("predicate")
        if predicate not in ("1D_SHOCK", "5D_SHOCK", "1D_PUMP", "5D_PUMP"):
            continue
        ret = r.get("adjusted_return_1d_pct_first_seen") if predicate.startswith("1D") else r.get("adjusted_return_5d_pct_first_seen")
        try:
            ret = float(ret)
        except (ValueError, TypeError):
            continue
        if not math.isfinite(ret) or not ((predicate.endswith("SHOCK") and ret <= (-7 if predicate.startswith("1D") else -15)) or (predicate.endswith("PUMP") and ret >= (7 if predicate.startswith("1D") else 15))):
            continue
        original_id = r.get("event_id")
        if original_id != f"{session}|{symbol}|{predicate}":
            continue
        if r.get("source_prefilter_sha256") != health.get("prefilter_sha256"):
            continue
        score = abs(ret) / (7 if predicate.startswith("1D") else 15)
        old = by_symbol.get(symbol)
        if old and old[0] >= score:
            continue
        by_symbol[symbol] = (score, {
            "event_id": "O2G|" + key_hash(original_id, health["prefilter_sha256"]),
            "direction": "OPPORTUNITY_TO_GLOBAL",
            "price_event_id": original_id,
            "source_session_date": session,
            "source_prefilter_sha256": health["prefilter_sha256"],
            "symbol": symbol,
            "price_predicate": predicate,
            "adjusted_return_pct": round(ret, 4),
            "intake_state": "PENDING_CAUSAL_NEWS_VERIFICATION",
            "causal_statement": "NO_CAUSAL_CLAIM",
            "signal_state": "NOT_AUTHORIZED",
        })
    return [v for _, v in sorted(by_symbol.values(), key=lambda p: (-p[0], p[1]["symbol"]))[:max_out]]


def project_checkpoint(checkpoint, forward, reverse, *, observed_at_vn):
    """Idempotent merge. Never mark review completed, notified or trade-ready."""
    parse_time(observed_at_vn)
    if not isinstance(checkpoint, dict):
        raise ValueError("CHECKPOINT_INVALID")
    clone = dict(checkpoint)
    state = dict(clone.get("cross_radar_handoff") or {})
    if state.get("schema") not in (None, SCHEMA):
        raise ValueError("UNKNOWN_HANDOFF_SCHEMA")
    fwd = dict(state.get("global_to_opportunity") or {})
    rev = dict(state.get("opportunity_to_global") or {})
    incoming = {"forward_added": 0, "reverse_added": 0}
    for record in forward:
        event_id = record["event_id"]
        if event_id not in fwd:
            fwd[event_id] = {**record, "first_ingested_at_vn": observed_at_vn}
            incoming["forward_added"] += 1
        elif fwd[event_id].get("material_update_key") != record["material_update_key"]:
            raise ValueError("EVENT_ID_CONFLICT")
    for record in reverse:
        event_id = record["event_id"]
        if event_id not in rev:
            rev[event_id] = {**record, "first_ingested_at_vn": observed_at_vn}
            incoming["reverse_added"] += 1
        elif rev[event_id].get("price_event_id") != record["price_event_id"]:
            raise ValueError("PRICE_ID_CONFLICT")
    state.update({"schema": SCHEMA, "global_to_opportunity": fwd, "opportunity_to_global": rev})
    clone["cross_radar_handoff"] = state
    return clone, incoming


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--global-ledger", type=Path, required=True)
    p.add_argument("--price-events-jsonl", type=Path, required=True)
    p.add_argument("--market-health", type=Path, required=True)
    p.add_argument("--checkpoint", type=Path, required=True)
    p.add_argument("--as-of-vn", required=True)
    p.add_argument("--out", type=Path, required=True)
    args = p.parse_args()
    read = lambda path: json.loads(path.read_text(encoding="utf-8"))
    with args.price_events_jsonl.open(encoding="utf-8") as f:
        price_rows = [json.loads(line) for line in f if line.strip()]
    forward = eligible_global_events(read(args.global_ledger), as_of=args.as_of_vn)
    reverse = reverse_price_requests(price_rows, read(args.market_health))
    projected, stats = project_checkpoint(read(args.checkpoint), forward, reverse, observed_at_vn=args.as_of_vn)
    args.out.write_text(json.dumps(projected, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    print(json.dumps({"schema": SCHEMA, **stats, "forward_input": len(forward), "reverse_input": len(reverse),
                      "checkpoint_write": "NOT_ATTEMPTED__CAS_AND_READBACK_REQUIRED",
                      "no_trade": True}))


if __name__ == "__main__":
    main()
