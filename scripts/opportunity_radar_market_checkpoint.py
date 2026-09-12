#!/usr/bin/env python3
"""Persist the live Opportunity Radar MARKET_PRICING packet checkpoint to Runner3 Core.

The Google Sheet remains the live decision-layer authority. This helper stores only
machine runtime state for the public Runner3 pricing lane: persisted session,
packet identity, signal count and run metadata.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data" / "opportunity-radar"
HEALTH_PATH = DATA_DIR / "market-health.json"
SIGNALS_PATH = DATA_DIR / "market-signals.json"
PREFILTER_PATH = DATA_DIR / "market-prefilter.json"

PROJECT = "opportunity-radar-v2"
SCOPE = "market-pricing"
SOURCE = "opportunity-radar-market-v2"
PREFILTER_SOURCE = "data/opportunity-radar/market-prefilter.json"
D1_CHECKPOINT_BINDING = {"project": PROJECT, "scope": SCOPE, "source": SOURCE}

sys.path.insert(0, str(ROOT / ".github" / "scripts"))
from runner3_core import get_checkpoint, report_status, save_checkpoint  # noqa: E402


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError(f"{path.name} must contain a JSON object")
    return value


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sha256_json(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def validate_packet(health: dict[str, Any], packet: dict[str, Any], prefilter: dict[str, Any]) -> list[str]:
    if health.get("status") != "COMPLETE" or health.get("complete") is not True:
        raise RuntimeError("market-health is not COMPLETE")
    if packet.get("complete") is not True:
        raise RuntimeError("market-signals packet is not complete")

    health_session = health.get("source_session_date")
    packet_session = packet.get("source_session_date")
    if not health_session or health_session != packet_session:
        raise RuntimeError(
            f"source_session_date mismatch: health={health_session!r} packet={packet_session!r}"
        )

    signals = packet.get("signals")
    if not isinstance(signals, list):
        raise RuntimeError("market-signals.signals must be a list")

    ids: list[str] = []
    for row in signals:
        if not isinstance(row, dict) or not row.get("intake_id"):
            raise RuntimeError("every market signal must have intake_id")
        ids.append(str(row["intake_id"]))

    if len(ids) != len(set(ids)):
        raise RuntimeError("duplicate intake_id inside current market packet")

    health_count = int(health.get("signal_count") or 0)
    if health_count != len(ids):
        raise RuntimeError(f"signal_count mismatch: health={health_count} packet={len(ids)}")

    if prefilter.get("schema") != "opportunity-radar-market-prefilter-v1":
        raise RuntimeError("market-prefilter schema invalid")
    if prefilter.get("complete") is not True or prefilter.get("status") != "COMPLETE":
        raise RuntimeError("market-prefilter is not COMPLETE")
    if prefilter.get("source_session_date") != health_session:
        raise RuntimeError("market-prefilter source_session_date mismatch")
    records = prefilter.get("records")
    if not isinstance(records, list):
        raise RuntimeError("market-prefilter.records must be a list")
    if int(prefilter.get("universe_count") or -1) != len(records):
        raise RuntimeError("market-prefilter universe_count mismatch")
    if int(health.get("prefilter_count") or -1) != len(records):
        raise RuntimeError("market-health prefilter_count mismatch")

    actual_prefilter_sha256 = sha256_file(PREFILTER_PATH)
    if health.get("prefilter_sha256") != actual_prefilter_sha256:
        raise RuntimeError("market-health prefilter_sha256 mismatch")
    if health.get("prefilter_source") != PREFILTER_SOURCE:
        raise RuntimeError("market-health prefilter_source mismatch")
    built_utc = health.get("prefilter_built_utc")
    try:
        built_dt = datetime.fromisoformat(str(built_utc).replace("Z", "+00:00"))
    except Exception as exc:
        raise RuntimeError("market-health prefilter_built_utc invalid") from exc
    if built_dt.utcoffset() != timezone.utc.utcoffset(built_dt):
        raise RuntimeError("market-health prefilter_built_utc must be UTC")

    binding = health.get("d1_checkpoint_binding")
    if binding != D1_CHECKPOINT_BINDING:
        raise RuntimeError("market-health D1 checkpoint binding mismatch")
    if health.get("checkpoint_project") != PROJECT:
        raise RuntimeError("market-health checkpoint_project mismatch")
    if health.get("checkpoint_scope") != SCOPE:
        raise RuntimeError("market-health checkpoint_scope mismatch")
    if health.get("checkpoint_source") != SOURCE:
        raise RuntimeError("market-health checkpoint_source mismatch")

    return sorted(ids)


def run_meta(name: str, fallback: str) -> str | None:
    return os.environ.get(name) or os.environ.get(fallback)


def main() -> None:
    health = load_json(HEALTH_PATH)
    packet = load_json(SIGNALS_PATH)
    prefilter = load_json(PREFILTER_PATH)
    intake_ids = validate_packet(health, packet, prefilter)

    session = str(health["source_session_date"])
    intake_ids_sha256 = sha256_json(intake_ids)
    signals_sha256 = sha256_file(SIGNALS_PATH)
    health_sha256 = sha256_file(HEALTH_PATH)
    prefilter_sha256 = sha256_file(PREFILTER_PATH)
    prefilter_count = len(prefilter.get("records") or [])
    run_id = run_meta("RADAR_RUN_ID", "GITHUB_RUN_ID")
    run_attempt = run_meta("RADAR_RUN_ATTEMPT", "GITHUB_RUN_ATTEMPT")
    trigger_sha = run_meta("RADAR_TRIGGER_SHA", "GITHUB_SHA")
    workflow = run_meta("RADAR_WORKFLOW", "GITHUB_WORKFLOW") or "Runner3 Opportunity Radar Market V2"

    previous = get_checkpoint(PROJECT, SCOPE)
    previous_position = previous.get("position") if isinstance(previous, dict) else None
    same_session = bool(
        isinstance(previous_position, dict)
        and previous_position.get("source_session_date") == session
    )
    same_identity = bool(
        same_session
        and previous_position.get("intake_ids_sha256") == intake_ids_sha256
    )

    position = {
        "phase": "persisted",
        "lane": "MARKET_PRICING",
        "source_session_date": session,
        "generated_at": health.get("generated_at"),
        "signal_count": len(intake_ids),
        "intake_ids_sha256": intake_ids_sha256,
        "signals_sha256": signals_sha256,
        "health_sha256": health_sha256,
        "prefilter_sha256": prefilter_sha256,
        "prefilter_count": prefilter_count,
        "prefilter_schema": prefilter.get("schema"),
        "scanner_version": prefilter.get("scanner_version"),
        "run_id": run_id,
        "run_attempt": run_attempt,
        "trigger_sha": trigger_sha,
    }

    checkpoint = save_checkpoint(
        PROJECT,
        SOURCE,
        scope=SCOPE,
        status="success",
        position=position,
        last_error=None,
    )

    state = report_status(
        SOURCE,
        "success",
        run_id=run_id,
        detail={
            "workflow": workflow,
            "phase": "persisted",
            "lane": "MARKET_PRICING",
            "source_session_date": session,
            "signal_count": len(intake_ids),
            "prefilter_count": prefilter_count,
            "prefilter_sha256": prefilter_sha256,
            "checkpoint_project": PROJECT,
            "checkpoint_scope": SCOPE,
        },
    )

    print(
        json.dumps(
            {
                "ok": True,
                "project": PROJECT,
                "scope": SCOPE,
                "source": SOURCE,
                "source_session_date": session,
                "signal_count": len(intake_ids),
                "prefilter_count": prefilter_count,
                "prefilter_sha256": prefilter_sha256,
                "same_session_as_previous": same_session,
                "same_packet_identity_as_previous": same_identity,
                "checkpoint": checkpoint,
                "state": state,
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
