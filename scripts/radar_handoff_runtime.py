#!/usr/bin/env python3
"""Existing Global/Opportunity Radar handoff's guarded VPS runtime.

Uses EXISTING GitHub event ledger + EXISTING Dropbox checkpoint only.
No scheduler, no additional database, no user notification, no trade.
Source -> handoff -> economic triage are audited separately from delivery.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import sys
import urllib.request
from datetime import timezone
from datetime import datetime
from zoneinfo import ZoneInfo

from radar_bidirectional_handoff import eligible_global_events, review_global_events, project_checkpoint, reverse_price_requests

LEDGER_URL = (
    "https://api.github.com/repos/louisalviss/runner-3/contents/"
    "ops/global-viral-radar/event-notification-ledger.json"
)
CHECKPOINT = (
    "/Apps/remotely-save/AI/01_Canonical/Finance/07_Trading/"
    "Opportunity Radar/Recall-Evidence-20261111.json"
)
SCHEMA = "cross-radar-live-e2e-audit-v1"


def source_ledger_fetch(url=LEDGER_URL):
    """Fetch the current default-branch GitHub Contents blob, not a stale raw CDN response."""
    if url != LEDGER_URL:
        raise ValueError("LEDGER_SOURCE_URL_NOT_CANONICAL")
    req = urllib.request.Request(
        url, headers={
            "User-Agent": "Runner3-CrossRadar/1.0",
            "Accept": "application/vnd.github+json",
            "Cache-Control": "no-cache",
        })
    with urllib.request.urlopen(req, timeout=25) as r:
        wrapped = r.read(7_000_001)
    if len(wrapped) > 7_000_000:
        raise ValueError("LEDGER_API_RESPONSE_TOO_LARGE")
    payload = json.loads(wrapped)
    if (not isinstance(payload, dict) or payload.get("type") != "file"
            or payload.get("encoding") != "base64"
            or not isinstance(payload.get("content"), str)):
        raise ValueError("LEDGER_GITHUB_CONTENTS_INVALID")
    raw = base64.b64decode("".join(payload["content"].split()), validate=True)
    if len(raw) > 5_000_000:
        raise ValueError("LEDGER_TOO_LARGE")
    git_blob_sha = hashlib.sha1(
        b"blob " + str(len(raw)).encode("ascii") + bytes([0]) + raw
    ).hexdigest()
    if git_blob_sha != payload.get("sha"):
        raise ValueError("LEDGER_GITHUB_BLOB_SHA_MISMATCH")
    data = json.loads(raw)
    if not isinstance(data, dict) or not isinstance(data.get("entries"), dict):
        raise ValueError("LEDGER_SCHEMA_INVALID")
    return data, hashlib.sha256(raw).hexdigest()


PRICE_REPO = "louisalviss/runner-3"
PRICE_API = "https://api.github.com/repos/" + PRICE_REPO + "/commits/main"
PRICE_SOURCE_FILES = {
    "health": "data/opportunity-radar/market-health.json",
    "prefilter": "data/opportunity-radar/market-prefilter.json",
    "events": "data/opportunity-radar/market-move-events.jsonl",
}
REVERSE_DAILY_NEW_LIMIT = 8
REVERSE_PENDING_CAP = 40


def _read_https_capped(url, cap):
    if not url.startswith("https://"):
        raise ValueError("NON_HTTPS_SOURCE")
    req = urllib.request.Request(url, headers={
        "User-Agent": "Runner3-CrossRadar/1.0", "Accept": "application/json,text/plain"
    })
    with urllib.request.urlopen(req, timeout=45) as response:
        raw = response.read(cap + 1)
    if len(raw) > cap:
        raise ValueError("SOURCE_SIZE_BOUND_EXCEEDED")
    return raw


def pinned_reverse_price_source_fetch():
    """Use same immutable GitHub commit for market health, prefilter, and event log.

    This is a read of the EXISTING market scanner, not a new scan of equities.
    Called exclusively on the Opportunity owner path (--sync-reverse).
    """
    commit = json.loads(_read_https_capped(PRICE_API, 500_000)).get("sha", "")
    if len(commit) != 40 or not all(c in "0123456789abcdef" for c in commit):
        raise ValueError("GITHUB_PRICE_COMMIT_SHA_INVALID")
    base = ("https://raw.githubusercontent.com/" + PRICE_REPO + "/" + commit + "/")
    blobs = {key: _read_https_capped(base + path, 30_000_000 if key == "events" else 18_000_000)
             for key, path in PRICE_SOURCE_FILES.items()}
    health = json.loads(blobs["health"])
    prefilter = json.loads(blobs["prefilter"])
    session = health.get("source_session_date")
    if not (health.get("status") == "COMPLETE" and health.get("complete") is True
            and session and session == health.get("expected_latest_completed_us_session")
            and float(health.get("fresh_history_coverage") or 0) >= 0.8
            and prefilter.get("status") == "COMPLETE" and prefilter.get("complete") is True
            and prefilter.get("source_session_date") == session):
        raise ValueError("MARKET_PRICE_SOURCE_NOT_COMPLETE_OR_MATCHED")
    if hashlib.sha256(blobs["prefilter"]).hexdigest() != health.get("prefilter_sha256"):
        raise ValueError("PRICE_PREFILTER_SHA_MISMATCH")
    if len(prefilter.get("records") or []) != health.get("prefilter_count"):
        raise ValueError("PRICE_PREFILTER_COUNT_MISMATCH")
    time = datetime.fromisoformat(str(health.get("generated_at", "")).replace("Z", "+00:00"))
    if time.tzinfo is None:
        raise ValueError("PRICE_PACKET_NAIVE_GENERATED_AT")
    age = (datetime.now(timezone.utc) - time.astimezone(timezone.utc)).total_seconds()
    if age < -300 or age > 6 * 86400:
        raise ValueError("PRICE_PACKET_STALE_OR_FUTURE")
    events = [json.loads(line) for line in blobs["events"].splitlines() if line.strip()]
    return health, prefilter, events, commit


from radar_queue_lifecycle import (bounded_reverse_projection_v2,
                                   bounded_research_worklist,
                                   screen_full_inventory_cheap_v1,
                                   apply_signed_research_closeouts_v1)


def bounded_reverse_projection(checkpoint, health, prefilter, raw_events,
                               source_commit, observed_at_vn):
    """Backward-compatible entrypoint for bounded, persistent queue v2."""
    return bounded_reverse_projection_v2(checkpoint, health, prefilter, raw_events,
                                         source_commit, observed_at_vn)


def _source_only_history(previous):
    rows = previous.get("source_only_event_statuses") or []
    if not isinstance(rows, list):
        raise ValueError("SOURCE_ONLY_HISTORY_INVALID")
    out = {}
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get("source_group_id"), str):
            raise ValueError("SOURCE_ONLY_RECORD_INVALID")
        k = row["source_group_id"]
        if k in out:
            raise ValueError("SOURCE_ONLY_DUPLICATE_ID")
        out[k] = dict(row)
    return out


def _source_only_disposition(row, review, observed_at_vn):
    """Consume explicit existing-owner evidence, never infer terminal from age."""
    if not isinstance(review, dict) or review.get("material_update_key") != row.get("material_update_key"):
        return None
    proof = review.get("source_only_disposition")
    if not isinstance(proof, dict):
        return None
    if (proof.get("source_group_id") != row.get("source_group_id") or
            proof.get("material_update_key") != row.get("material_update_key") or
            proof.get("decision") not in ("WAIT_NEW_EVIDENCE", "TERMINAL") or
            proof.get("signal_state") != "NOT_AUTHORIZED" or
            proof.get("owner") != "Opportunity Radar V3"):
        return None
    for name in ("reason", "reopen_condition"):
        if not isinstance(proof.get(name), str) or not proof[name].strip():
            return None
    urls = proof.get("evidence_urls")
    if not isinstance(urls, list) or not urls or not all(isinstance(x, str) and x.startswith("https://") for x in urls):
        return None
    try:
        from radar_bidirectional_handoff import parse_time
        t = parse_time(proof.get("reviewed_at"))
        if t > parse_time(observed_at_vn) or t < parse_time(row["first_ingested_at_vn"]):
            return None
    except (ValueError, TypeError, KeyError):
        return None
    return dict(proof)


def audit_projection(ledger, original, observed_at_vn, ledger_sha256):
    """Merge only newly verified events and one bounded evidence audit.

    The audit is the same record on every run. Avoid writing when nothing
    changed. The only place capable of recording a user delivery receipt
    remains the actual existing notification provider.
    """
    old_state = original.get("cross_radar_handoff") or {}
    reviews = old_state.get("global_event_linkage_reviews_v1") or {}
    prior_audit = old_state.get("runtime_e2e_audit_v1") or {}
    history = _source_only_history(prior_audit)
    for row in history.values():
        row.setdefault("lifecycle_state", "PENDING")
        row.setdefault("first_ingested_at_vn", observed_at_vn)
    pending_ids = {k for k,r in history.items() if r["lifecycle_state"] == "PENDING"}
    verified, fresh_source_only = review_global_events(ledger, as_of=observed_at_vn, reviews=reviews, retained_source_ids=pending_ids)
    for row in fresh_source_only:
        k = row["source_group_id"]
        if k not in history:
            history[k] = {**row, "first_ingested_at_vn": observed_at_vn, "lifecycle_state": "PENDING"}
        elif history[k]["lifecycle_state"] == "PENDING":
            old = history[k]
            if row.get("source_verified") is True and old.get("source_verified") is not True:
                old["verified_source_evidence"] = row
    for row in history.values():
        if row["lifecycle_state"] == "PENDING":
            proof = _source_only_disposition(row, reviews.get(row.get("source_event_key")), observed_at_vn)
            if proof:
                row["lifecycle_state"] = proof["decision"]
                row["disposition_proof"] = proof
    closed = {k for k,r in history.items() if r["lifecycle_state"] in ("WAIT_NEW_EVIDENCE", "TERMINAL")}
    verified = [r for r in verified if r["event_id"] not in closed or r["event_id"] in (old_state.get("global_to_opportunity") or {})]
    # Price requests are already stored by the existing Opportunity owner.
    # DO NOT enqueue another daily set of 30 while causal backlog remains.
    projected, stats = project_checkpoint(original, verified, [], observed_at_vn=observed_at_vn)
    state = projected["cross_radar_handoff"]
    existing = state["global_to_opportunity"]
    for k,row in history.items():
        if k in existing and row["lifecycle_state"] == "PENDING":
            row["lifecycle_state"] = "LINKED"
            row["linked_event_id"] = k
    source_only = sorted(history.values(), key=lambda r:r["source_group_id"])
    pending_source_only = [r for r in source_only if r["lifecycle_state"] == "PENDING"]
    exposure_map = dict(prior_audit.get("verified_security_exposures_by_event") or {})
    exposure_map.update({x["event_id"]:x["affected_securities"] for x in verified if x.get("affected_securities")})
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
        "source_only_event_statuses": source_only,
        "source_only_events": len(pending_source_only),
        "source_only_history_count": len(source_only),
        "source_only_lifecycle_counts": {s:sum(r["lifecycle_state"]==s for r in source_only) for s in ("PENDING","WAIT_NEW_EVIDENCE","TERMINAL","LINKED")},
        "verified_security_exposures_by_event": exposure_map,
    }
    # Deny FULL PASS until all sides (including real notification receipts)
    # independently pass.
    audit["end_to_end_status"] = (
        "FULL_PASS" if (
            records and not pending_source_only and all(x["research_triage_done"] and
                            x["underwrite_certified"] and
                            x["user_delivery_confirmed"] for x in records)
        ) else "RESEARCH_HANDOFF_PARTIAL__DELIVERY_OR_UNDERWRITE_OPEN"
    )
    changed = (stats["forward_added"] > 0 or state.get("runtime_e2e_audit_v1") != audit)
    state["runtime_e2e_audit_v1"] = audit
    return projected, stats, audit, changed



# Historical source-backed identity baseline restored Nov17; all subsequent
# writer paths must retain each known old event before accepting a CAS.
IMMUTABLE_PRICE_EVENT_FLOOR = 295


def _price_event_ids(checkpoint):
    state = checkpoint.get("cross_radar_handoff") or {}
    cases = state.get("opportunity_to_global") or {}
    deferred = (state.get("reverse_queue_v2") or {}).get("deferred") or []
    if not isinstance(cases, dict) or not isinstance(deferred, list):
        raise ValueError("REVERSE_INVENTORY_SCHEMA_INVALID")
    ids = list(cases)
    for row in deferred:
        if not isinstance(row, dict) or not isinstance(row.get("event_id"), str):
            raise ValueError("REVERSE_DEFERRED_ID_INVALID")
        ids.append(row["event_id"])
    if len(ids) != len(set(ids)):
        raise ValueError("REVERSE_DUPLICATE_IMMUTABLE_ID")
    return set(ids)


def assert_price_event_identity_nonloss(previous, projected):
    original_ids = _price_event_ids(previous)
    if len(original_ids) < IMMUTABLE_PRICE_EVENT_FLOOR:
        raise ValueError("REVERSE_HISTORICAL_295_ID_BASELINE_MISSING")
    new_ids = _price_event_ids(projected)
    if not original_ids.issubset(new_ids):
        raise ValueError("REVERSE_HISTORICAL_ID_LOSS")
    return len(original_ids), len(new_ids)


def run_live(*, sync_reverse=False):
    try:
        from vps_dropbox import DropboxService
    except ImportError as e:
        raise RuntimeError("APPROVED_DROPBOX_SERVICE_NOT_IN_PYTHONPATH") from e
    svc = DropboxService()  # env loaded by caller: only /etc/vps-control/dropbox.env
    ledger, sha = source_ledger_fetch()
    price_sources = pinned_reverse_price_source_fetch() if sync_reverse else None
    observed = datetime.now(ZoneInfo("Asia/Ho_Chi_Minh")).isoformat(timespec="seconds")
    with svc.path_lock(CHECKPOINT):
        current, metadata = svc.download_text(CHECKPOINT)
        source = json.loads(current)
        original_checkpoint = source
        source, signed_closeouts = (apply_signed_research_closeouts_v1(source)
                                    if price_sources is not None else (source, 0))
        reverse_stats = {"reverse_added": 0, "changed": False, "already_accepted": False,
                         "source_session": None, "capacity_skipped": 0}
        if price_sources is not None:
            source, reverse_stats = bounded_reverse_projection(
                source, *price_sources, observed_at_vn=observed)
        projected, stats, audit, changed = audit_projection(ledger, source, observed, sha)
        changed = changed or reverse_stats["changed"] or signed_closeouts > 0
        cheap_screen = None
        if price_sources is not None:
            cheap_screen = screen_full_inventory_cheap_v1(
                projected, price_sources[0], price_sources[1])
            # Same bounded owner worklist; keep a durable source-catalyst
            # bridge in the existing cheap-screen snapshot for next owner
            # execution. No new writer, state machine, BUY or quota.
            due_plan = bounded_research_worklist(projected, cheap_screen=cheap_screen)
            cheap_screen["source_catalyst_bridge_v1"] = {
                "source_only_catalyst_due": due_plan["source_only_catalyst_due"],
                "source_only_catalyst_selected": due_plan["source_only_catalyst_selected"],
                "source_only_catalyst_deferred": due_plan["source_only_catalyst_deferred"],
                "selected_worklist": due_plan["worklist"],
                "newest_deferred_price_only_watch":
                    due_plan["newest_deferred_price_only_watch"],
                "candidate_write_authorized": False,
                "full_underwrite_or_entry_proven": False,
            }
            state = projected["cross_radar_handoff"]
            if state.get("full_inventory_cheap_screen_v1") != cheap_screen:
                state["full_inventory_cheap_screen_v1"] = cheap_screen
                changed = True
        # Validate both inherited 295 identities and any new admissions
        # before any production writer or report can advance.
        assert_price_event_identity_nonloss(original_checkpoint, projected)
        if changed:
            serialized = json.dumps(projected, ensure_ascii=False, separators=(",", ":")) + "\n"
            result = svc.upload_text(CHECKPOINT, serialized, expected_rev=metadata["rev"])
            check, checkmeta = svc.download_text(CHECKPOINT)
            if check != serialized or checkmeta.get("rev") != result.get("rev"):
                raise RuntimeError("DROPBOX_CAS_READBACK_FAILED")
            assert_price_event_identity_nonloss(original_checkpoint, json.loads(check))
            # Exact byte and revision checks above remain mandatory.
            # This second parse verifies the immutable ID union after CAS.

            written = True
            rev = result["rev"]
        else:
            # A no-op replay still confirms that the original checkpoint was read.
            written = False
            rev = metadata["rev"]
    research_plan = (bounded_research_worklist(projected, cheap_screen=cheap_screen)
                     if sync_reverse else None)
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
        "reverse_added_this_run": reverse_stats["reverse_added"],
        "reverse_price_source_session": reverse_stats["source_session"],
        "reverse_price_source_already_accepted": reverse_stats["already_accepted"],
        "reverse_eligible_capacity_skipped": reverse_stats["capacity_skipped"],
        "reverse_active_pending": reverse_stats.get("active_pending"),
        "reverse_terminal_count": reverse_stats.get("terminal_count"),
        "reverse_deferred_count": reverse_stats.get("deferred_count"),
        "reverse_daily_budget_used": reverse_stats.get("daily_used"),
        "research_worklist": research_plan,
        "cheap_inventory_screen": ({
            "classified_ids": cheap_screen["all_immutable_event_ids"],
            "unique_symbols": cheap_screen["unique_symbols"],
            "active": cheap_screen["active"],
            "deferred": cheap_screen["deferred"],
            "terminal": cheap_screen["terminal"],
            "source_investigation_selected_n":
                cheap_screen["source_investigation_selected_n"],
            "deep_underwrite_selected_n":
                cheap_screen["deep_underwrite_selected_n"],
            "automatic_terminal_added": signed_closeouts,
            "trade_authorized": False,
            "source_catalyst_bridge": cheap_screen["source_catalyst_bridge_v1"],
        } if cheap_screen else None),
        "no_trade": True,
    }
    print(json.dumps(out, ensure_ascii=False))
    return 0


def quick_source_plan(health, events, tickers, filings, previous=(), limit=12):
    """Pure source-locator projection. Source coverage is not economic review."""
    from collections import defaultdict
    import re
    session = health["source_session_date"]
    sha = health["prefilter_sha256"]
    if not health.get("complete") or health.get("status") != "COMPLETE":
        raise ValueError("QUICK_MARKET_SOURCE_UNVERIFIED")
    if type(limit) is not int or not 0 <= limit <= 24:
        raise ValueError("QUICK_SOURCE_BUDGET_INVALID")
    raw = {}
    for e in events:
        if e.get("source_session_date") != session or e.get("source_prefilter_sha256") != sha:
            continue
        i = e["event_id"]
        row = {k:e[k] for k in ("event_id","symbol","predicate")}
        if i in raw and raw[i] != row:
            raise ValueError("QUICK_RAW_EVENT_CONFLICT")
        raw[i] = row
    symbols = {e["symbol"] for e in raw.values()}
    by_symbol, by_cik = defaultdict(set), defaultdict(set)
    for x in tickers["data"]:
        d = dict(zip(tickers["fields"], x))
        if not d.get("ticker") or not d.get("cik"):
            continue
        cik = str(d["cik"]).lstrip("0")
        by_symbol[d["ticker"]].add(cik)
        by_cik[cik].add(d["ticker"])
    mapped = {x:next(iter(by_symbol[x])) for x in symbols if len(by_symbol[x]) == 1}
    anomaly_ciks = set(mapped.values())
    docs = {}
    for f in filings:
        cik = str(f["cik"]).lstrip("0")
        name = f["filename"]
        date = str(f["filing_date"])
        if (cik not in by_cik or date > session or f["form"] not in
                {"8-K","8-K/A","6-K","10-K","10-Q","20-F","40-F"} or
                not re.fullmatch(r"edgar/data/[0-9]+/[0-9-]+\.txt",name)):
            continue
        associated = sorted(x for x in symbols if mapped.get(x) == cik)
        row = {"cik":cik,"form":f["form"],"filing_date":date,"filename":name,
               "anomaly_symbols":associated,"listed_security_candidates":sorted(by_cik[cik]),
               "lane":"PRICE_DISCOVERY" if cik in anomaly_ciks else "INDEPENDENT_ISSUER_DISCOVERY",
               "security_exposure_verified":False}
        if name in docs and docs[name] != row:
            raise ValueError("QUICK_FILING_ID_CONFLICT")
        docs[name] = row
    seen = set(previous)
    groups = [[],[]]
    for d in sorted(docs.values(),key=lambda x:(x["filing_date"],x["form"] in {"8-K","6-K"},x["filename"]),reverse=True):
        if d["filename"] not in seen:
            groups[0 if d["lane"] == "PRICE_DISCOVERY" else 1].append(d)
    selected = []
    # Balance discovery sources, not engine/BUY quotas; do not exhaust one lane
    # while entirely starving the other. All unselected locators remain visible.
    while len(selected) < limit and any(groups):
        for g in groups:
            if g and len(selected) < limit:
                selected.append(g.pop(0))
    matched = {sym for d in docs.values() for sym in d["anomaly_symbols"]}
    return {"raw_observations":list(raw.values()),"mapped":mapped,"unmapped":sorted(symbols-set(mapped)),
            "locators":list(docs.values()),"selected":selected,
            "counts":{"raw_events":len(raw),"symbols":len(symbols),"mapped":len(mapped),
                      "anomaly_symbols_with_index_match":len(matched),
                      "independent_issuer_locators":sum(d["lane"]=="INDEPENDENT_ISSUER_DISCOVERY" for d in docs.values()),
                      "locators":len(docs),"selected":len(selected),"reused_locator_count":len(set(docs)&seen)},
            "economic_review_completed":0,"trade_authorized":False}


def quick_source_extract(raw):
    """Bounded machine-extracted evidence, not semantic or valuation certification."""
    import re
    from bs4 import BeautifulSoup
    body = raw.decode("latin-1")
    stamp = re.search(r"<ACCEPTANCE-DATETIME>(\d{14})",body)
    docs = []
    terms = re.compile(r"(?i)\b(revenues?|net sales|operating (?:profit|income)|gross margin|cash flow|guidance|outlook|backlog|dividend|repurchase|merger|purchase price|capacity|orders?|warrants?|debt|dilution|redemption|capital expenditure|financing|liquidation|preferred|distribution)\b")
    for part in re.findall(r"<DOCUMENT>(.*?)</DOCUMENT>",body,re.S|re.I):
        typ = re.search(r"<TYPE>([^\r\n<]+)",part,re.I)
        typ = typ.group(1).strip().upper() if typ else ""
        if not (typ in {"8-K","8-K/A","6-K","10-K","10-Q","20-F","40-F"} or typ.startswith(("EX-99","EX-2."))):
            continue
        content = re.split(r"<TEXT>",part,maxsplit=1,flags=re.I)[-1]
        text = re.sub(r"\s+"," ",BeautifulSoup(content,"html.parser").get_text(" ",strip=True))
        chunks = []
        last = -1000
        for hit in terms.finditer(text):
            i = hit.start()
            if i-last < 350:
                continue
            chunks.append(text[max(0,i-100):i+320])
            last = i
            if len(chunks) == 12:
                break
        docs.append({"type":typ,"text_chars":len(text),"opening":text[:3500] if typ in {"8-K","8-K/A","6-K"} else text[:900],"economic_passages":chunks})
        if len(docs) == 5:
            break
    return {"sha256":hashlib.sha256(raw).hexdigest(),"bytes":len(raw),
            "acceptance_raw_et":stamp.group(1) if stamp else None,"documents":docs,
            "status":"SOURCE_EXTRACT_READY_NOT_ECONOMIC_REVIEW" if docs else "SOURCE_EXTRACT_UNKNOWN"}


def run_quick_sources():
    """Existing owner's optional source-preparation step. No market intake or trades."""
    import subprocess
    from concurrent.futures import ThreadPoolExecutor
    from datetime import date,timedelta
    from historical_scan.sec_index import user_agent_from_contact,parse_master
    from vps_dropbox import DropboxService
    health,prefilter,events,commit = pinned_reverse_price_source_fetch()
    session = health["source_session_date"]
    sha = health["prefilter_sha256"]
    svc = DropboxService()
    original,meta = svc.download_text(CHECKPOINT)
    state = json.loads(original)["cross_radar_handoff"]
    q = state["reverse_queue_v2"]
    if q.get("latest_completed_price_session") != session or q.get("latest_prefilter_sha256") != sha:
        raise ValueError("QUICK_SOURCE_PACKET_NOT_ACCEPTED")
    key = "opportunity_first_quick_sources_" + session.replace("-","") + "_v1"
    old = state.get(key) or {}
    if old and old.get("market_sha") != sha:
        raise ValueError("QUICK_SOURCE_SAME_SESSION_SHA_CONFLICT")
    cached = old.get("documents") or {}
    prior = set(cached)
    reused_sources = {}
    # Across sessions, retain references to successful unchanged submissions.
    # Do not download the same accession again merely because the price changed.
    for k,v in state.items():
        if not k.startswith("opportunity_first_quick_sources_") or k == key or not isinstance(v,dict):
            continue
        for name,doc in (v.get("documents") or {}).items():
            if doc.get("status") == "SOURCE_EXTRACT_READY_NOT_ECONOMIC_REVIEW" and doc.get("sha256"):
                prior.add(name)
                reused_sources[name] = {"checkpoint_key":k,"sha256":doc["sha256"]}
    # Reuse actual earlier semantic receipts when the exact SEC submission
    # was read and hashed; an unresolved cover-only receipt is not completion.
    for k,v in state.items():
        if not k.startswith("orv3_opportunity_first_current_source_pilot_") or not isinstance(v,dict):
            continue
        for r in v.get("source_results",[]):
            url = r.get("source_url","")
            if r.get("sha256") and r.get("source_semantics_reviewed") is True and url.startswith("https://www.sec.gov/Archives/"):
                name = url.removeprefix("https://www.sec.gov/Archives/")
                prior.add(name)
                reused_sources[name] = {"checkpoint_key":k,"sha256":r["sha256"],"semantic_receipt":True}
    status = json.loads(subprocess.check_output(["bw","status"],stderr=subprocess.DEVNULL))
    ua = user_agent_from_contact(status.get("userEmail"))
    def fetch(url,cap=20_000_000):
        try:
            req = urllib.request.Request(url,headers={"User-Agent":ua,"Accept":"*/*"})
            with urllib.request.urlopen(req,timeout=12) as f:
                data = f.read(cap+1)
            if len(data)>cap:
                raise ValueError("SEC_SOURCE_TOO_LARGE")
            return data,None
        except Exception as e:
            return None,type(e).__name__+":"+str(getattr(e,"code",""))
    # Use observed market sessions, not an arbitrary weekday/holiday guess.
    days = sorted({e["source_session_date"] for e in events if e.get("source_session_date") and e["source_session_date"]<=session})[-4:]
    urls = ["https://www.sec.gov/files/company_tickers_exchange.json"]
    for day in days:
        d=date.fromisoformat(day)
        urls.append(f"https://www.sec.gov/Archives/edgar/daily-index/{d.year}/QTR{(d.month-1)//3+1}/master.{d:%Y%m%d}.idx")
    with ThreadPoolExecutor(max_workers=3) as pool:
        sources = list(pool.map(fetch,urls))
    if sources[0][0] is None:
        raise RuntimeError("QUICK_TICKER_SOURCE_UNAVAILABLE:"+str(sources[0][1]))
    filings = []
    for data,err in sources[1:]:
        if data is not None:
            filings.extend(parse_master(data.decode("latin-1")))
    plan = quick_source_plan(health,events,json.loads(sources[0][0]),filings,prior)
    def extract(row):
        url="https://www.sec.gov/Archives/"+row["filename"]
        raw,err=fetch(url,12_000_000)
        if raw is None:
            return {"locator":row,"source_url":url,"status":"SOURCE_UNAVAILABLE","error":err}
        try:
            return dict(quick_source_extract(raw),locator=row,source_url=url)
        except Exception as e:
            return {"locator":row,"source_url":url,"status":"SOURCE_EXTRACT_UNKNOWN","error":type(e).__name__}
    with ThreadPoolExecutor(max_workers=4) as pool:
        results=list(pool.map(extract,plan["selected"]))
    # Keep successful extracts and exact failures visible. Failures are not
    # repeatedly retried to fill batches; a new source/session may qualify.
    merged=dict(cached)
    for row in results:
        merged[row["locator"]["filename"]]=row
    source_errors={url:err for url,(_,err) in zip(urls,sources) if err}
    payload={"market_session":session,"market_sha":sha,"market_commit":commit,
             "source_hashes":{url:hashlib.sha256(b).hexdigest() for url,(b,err) in zip(urls,sources) if b},
             "source_errors":source_errors,"plan":plan,"documents":merged,
             "reused_sources":{x["filename"]:reused_sources[x["filename"]] for x in plan["locators"] if x["filename"] in reused_sources},
             "status":"SOURCE_PREPARATION_PARTIAL" if source_errors else "SOURCE_PREPARATION_ONLY",
             "economic_review_completed":0,"full_underwrites":0,"trade_authorized":False}
    with svc.path_lock(CHECKPOINT):
        current,metadata=svc.download_text(CHECKPOINT)
        if metadata["rev"]!=meta["rev"]:
            raise RuntimeError("QUICK_SOURCE_CONCURRENT_CHECKPOINT_CHANGED")
        j=json.loads(current)
        j["cross_radar_handoff"][key]=payload
        assert_price_event_identity_nonloss(json.loads(current),j)
        serialized=json.dumps(j,ensure_ascii=False,separators=(",",":"))+"\n"
        if serialized!=current:
            receipt=svc.upload_text(CHECKPOINT,serialized,expected_rev=metadata["rev"])
            check,checkmeta=svc.download_text(CHECKPOINT)
            if check!=serialized or checkmeta["rev"]!=receipt["rev"]:
                raise RuntimeError("QUICK_SOURCE_CAS_READBACK_FAILED")
        else:
            checkmeta=metadata
    print(json.dumps({"status":payload["status"],"market_session":session,"checkpoint_rev":checkmeta["rev"],
                      "counts":plan["counts"],"source_errors":source_errors,
                      "new_extracted":sum(r["status"]=="SOURCE_EXTRACT_READY_NOT_ECONOMIC_REVIEW" for r in results),
                      "new_failed_or_unknown":sum(r["status"]!="SOURCE_EXTRACT_READY_NOT_ECONOMIC_REVIEW" for r in results),
                      "economic_review_completed":0,"trade_authorized":False},ensure_ascii=False))
    return 0


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--live", action="store_true", help="run existing source+checkpoint synchronization")
    p.add_argument("--sync-reverse", action="store_true",
                   help="Opportunity owner only: bounded latest-session price reverse intake")
    p.add_argument("--quick-sources", action="store_true", help="prepare bounded primary-source extracts for the existing owner")
    args = p.parse_args()
    if args.quick_sources:
        if not args.live or args.sync_reverse:
            p.error("--quick-sources requires --live without --sync-reverse")
        return run_quick_sources()
    if not args.live:
        p.error("--live required (offline regression via unittest)")
    return run_live(sync_reverse=args.sync_reverse)


if __name__ == "__main__":
    sys.exit(main())
