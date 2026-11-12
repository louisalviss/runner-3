#!/usr/bin/env python3
"""Existing Global/Opportunity Radar handoff's guarded VPS runtime.

Uses EXISTING GitHub event ledger + EXISTING Dropbox checkpoint only.
No scheduler, no additional database, no user notification, no trade.
Source -> handoff -> economic triage are audited separately from delivery.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import urllib.request
from datetime import datetime
from zoneinfo import ZoneInfo

from radar_bidirectional_handoff import eligible_global_events, project_checkpoint

LEDGER_URL = (
    "https://raw.githubusercontent.com/louisalviss/runner-3/main/"
    "ops/global-viral-radar/event-notification-ledger.json"
)
CHECKPOINT = (
    "/Apps/remotely-save/AI/01_Canonical/Finance/07_Trading/"
    "Opportunity Radar/Recall-Evidence-20261111.json"
)
SCHEMA = "cross-radar-live-e2e-audit-v1"


def source_ledger_fetch(url=LEDGER_URL):
    if url != LEDGER_URL:
        raise ValueError("LEDGER_SOURCE_URL_NOT_CANONICAL")
    req = urllib.request.Request(url, headers={"User-Agent": "Runner3-CrossRadar/1.0"})
    with urllib.request.urlopen(req, timeout=25) as r:
        raw = r.read(5_000_001)
    if len(raw) > 5_000_000:
        raise ValueError("LEDGER_TOO_LARGE")
    data = json.loads(raw)
    if not isinstance(data, dict) or not isinstance(data.get("entries"), dict):
        raise ValueError("LEDGER_SCHEMA_INVALID")
    return data, hashlib.sha256(raw).hexdigest()


def audit_projection(ledger, original, observed_at_vn, ledger_sha256):
    """Merge only newly verified events and one bounded evidence audit.

    The audit is the same record on every run. Avoid writing when nothing
    changed. The only place capable of recording a user delivery receipt
    remains the actual existing notification provider.
    """
    verified = eligible_global_events(ledger, as_of=observed_at_vn)
    # Price requests are already stored by the existing Opportunity owner.
    # DO NOT enqueue another daily set of 30 while causal backlog remains.
    projected, stats = project_checkpoint(original, verified, [], observed_at_vn=observed_at_vn)
    state = projected["cross_radar_handoff"]
    existing = state["global_to_opportunity"]
    by_key = {}
    for e in verified:
        k = e["event_id"]
        if k not in existing or existing[k].get("source_event_key") != e["source_event_key"]:
            raise ValueError("FORWARD_EVENT_KEY_CONFLICT")
        record = existing[k]
        source_record = ledger["entries"][e["source_event_key"]]
        stage_reviewed = bool(record.get("fast_catalyst_triage_at_vn") or
                              record.get("review_level") or
                              record.get("numeric_sensitivity_20261113"))
        stage_full_underwrite = record.get("full_numeric_deep_underwrite_certified") is True
        delivery = source_record.get("delivery_status") or "UNKNOWN"
        receipt = source_record.get("actual_delivery_receipt_id")
        # No inferred success from notification_precommitted or notified_at.
        delivered = bool(receipt) and delivery == "actual_delivery_confirmed"
        by_key[k] = {
            "source_key": e["source_event_key"],
            "symbol": e["symbol"],
            "event_time_vn": e["source_event_time_vn"],
            "source_verified": True,
            "handoff_persisted": True,
            "research_triage_done": stage_reviewed,
            "underwrite_certified": stage_full_underwrite,
            "intake_state": record.get("intake_state", "PENDING"),
            "user_delivery_confirmed": delivered,
            "delivery_state_recorded": delivery,
        }
    records = sorted(by_key.values(), key=lambda x: (x["event_time_vn"], x["source_key"]))
    audit = {
        "schema": SCHEMA,
        "source_ledger_sha256": ledger_sha256,
        "source_events_verified": len(verified),
        "handoff_events_matched": len(records),
        "research_triage_completed": sum(x["research_triage_done"] for x in records),
        "underwrites_certified": sum(x["underwrite_certified"] for x in records),
        "actual_deliveries_receipt_confirmed": sum(x["user_delivery_confirmed"] for x in records),
        "reverse_price_requests_total": len(state.get("opportunity_to_global", {})),
        "reverse_source_screened": sum(bool(x.get("primary_source_triage_20261113"))
                                      for x in state.get("opportunity_to_global", {}).values()),
        "reverse_causal_certified": sum(x.get("intake_state") == "CAUSAL_VERIFIED"
                                      for x in state.get("opportunity_to_global", {}).values()),
        "no_new_trades": True,
        "event_statuses": records,
    }
    # Deny FULL PASS until all sides (including real notification receipts)
    # independently pass.
    audit["end_to_end_status"] = (
        "FULL_PASS" if (
            records and all(x["research_triage_done"] and
                            x["underwrite_certified"] and
                            x["user_delivery_confirmed"] for x in records)
        ) else "RESEARCH_HANDOFF_PARTIAL__DELIVERY_OR_UNDERWRITE_OPEN"
    )
    changed = (stats["forward_added"] > 0 or state.get("runtime_e2e_audit_v1") != audit)
    state["runtime_e2e_audit_v1"] = audit
    return projected, stats, audit, changed


def run_live():
    try:
        from vps_dropbox import DropboxService
    except ImportError as e:
        raise RuntimeError("APPROVED_DROPBOX_SERVICE_NOT_IN_PYTHONPATH") from e
    svc = DropboxService()  # env loaded by caller: only /etc/vps-control/dropbox.env
    ledger, sha = source_ledger_fetch()
    observed = datetime.now(ZoneInfo("Asia/Ho_Chi_Minh")).isoformat(timespec="seconds")
    with svc.path_lock(CHECKPOINT):
        current, metadata = svc.download_text(CHECKPOINT)
        source = json.loads(current)
        projected, stats, audit, changed = audit_projection(ledger, source, observed, sha)
        if changed:
            serialized = json.dumps(projected, ensure_ascii=False, separators=(",", ":")) + "\n"
            result = svc.upload_text(CHECKPOINT, serialized, expected_rev=metadata["rev"])
            check, checkmeta = svc.download_text(CHECKPOINT)
            if check != serialized or checkmeta.get("rev") != result.get("rev"):
                raise RuntimeError("DROPBOX_CAS_READBACK_FAILED")
            written = True
            rev = result["rev"]
        else:
            # A no-op replay still confirms that the original checkpoint was read.
            written = False
            rev = metadata["rev"]
    out = {
        "schema": SCHEMA,
        "status": audit["end_to_end_status"],
        "checkpoint": CHECKPOINT,
        "checkpoint_rev": rev,
        "checkpoint_cas_readback": "PASS" if written else "NO_CHANGE_VERIFIED",
        "new_forward_events": stats["forward_added"],
        "forward_verified": audit["source_events_verified"],
        "handoff_research_triaged": audit["research_triage_completed"],
        "reverse_source_screened": audit["reverse_source_screened"],
        "reverse_requests_total": audit["reverse_price_requests_total"],
        "delivery_receipt_confirmed": audit["actual_deliveries_receipt_confirmed"],
        "underwrites_certified": audit["underwrites_certified"],
        "no_trade": True,
    }
    print(json.dumps(out, ensure_ascii=False))
    return 0


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--live", action="store_true", help="run existing source+checkpoint synchronization")
    args = p.parse_args()
    if not args.live:
        p.error("--live required (offline regression via unittest)")
    return run_live()


if __name__ == "__main__":
    sys.exit(main())
