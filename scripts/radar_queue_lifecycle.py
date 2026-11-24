"""Bounded event-specific Opportunity -> Global research queue lifecycle.

Pure projection module.  Existing verified price ledger, one existing Dropbox
checkpoint, no new scheduler, database, notification or trading authority.
A documented research no-trade / waiting closeout is not certified price causality.
"""
from __future__ import annotations

import copy
import hashlib
import json
from collections import Counter
from datetime import datetime
from radar_bidirectional_handoff import parse_time, project_checkpoint, reverse_price_requests

TERMINAL_STATES = frozenset({
    "RESEARCHED_NO_TRADE", "WAITING_NEW_EVIDENCE", "REJECTED_NO_MATCHED_CATALYST",
})
DAILY_LIMIT = 8
ACTIVE_CAP = 40
FRONTIER_LIMIT = 500
LOOKBACK_LIMIT = 150
OLDER_SESSION_MIN_RESERVE = 4


def validate_research_closeout(row):
    """Never silently release capacity because a source was merely screened."""
    status = row.get("intake_state")
    if status not in TERMINAL_STATES:
        return False
    proof = row.get("research_closeout_v2")
    if not isinstance(proof, dict):
        raise ValueError("TERMINAL_RESEARCH_WITHOUT_EVIDENCE")
    if (proof.get("decision") != status or
            proof.get("signal_state") != "NOT_AUTHORIZED" or
            proof.get("new_buy_short") is not False or
            not proof.get("evidence_source_urls") or
            not isinstance(proof.get("evidence_source_urls"), list) or
            not all(isinstance(s, str) and s.startswith("https://")
                    for s in proof["evidence_source_urls"]) or
            not isinstance(proof.get("reason"), str) or
            len(proof["reason"].strip()) < 25 or
            not proof.get("reopen_condition") or
            not proof.get("reviewed_at_vn")):
        raise ValueError("TERMINAL_RESEARCH_PROOF_INVALID")
    parse_time(proof["reviewed_at_vn"])
    if row.get("signal_state") != "NOT_AUTHORIZED":
        raise ValueError("TERMINAL_TRADE_STATE_CONFLICT")
    return True


def _verified_new_material_event(symbol, reviewed, forwards):
    """Allow same issuer only when a distinct corroborated Global event exists.

    Price events are never themselves evidence of a fresh issuer catalyst.
    The linked Global event remains PENDING review, never causal certification.
    """
    same = [x for x in reviewed.values() if x.get("symbol") == symbol]
    if not same:
        return None
    linked = {x.get("linked_global_material_update_key") for x in same}
    latest_prior_session = max(str(x.get("source_session_date") or "")
                               for x in same)
    for g in sorted(forwards.values(), key=lambda x: x.get("source_event_time_vn") or "",
                    reverse=True):
        if g.get("symbol") != symbol or g.get("verified_source") is not True:
            continue
        update = g.get("material_update_key")
        url = g.get("primary_source_url")
        if not update or update in linked or not isinstance(url, str) or not url.startswith("https://"):
            continue
        try:
            source_date = datetime.fromisoformat(
                g["source_event_time_vn"].replace("Z", "+00:00")
            ).date().isoformat()
        except (ValueError, KeyError, TypeError):
            continue
        if source_date > latest_prior_session:
            return g
    return None


def _make_deferred(record, commit, validated=True):
    return {
        "event_id": record["event_id"],
        "price_event_id": record["price_event_id"],
        "source_session_date": record["source_session_date"],
        "source_prefilter_sha256": record["source_prefilter_sha256"],
        "source_commit_sha": commit,
        "symbol": record["symbol"],
        "price_predicate": record["price_predicate"],
        "adjusted_return_pct": record["adjusted_return_pct"],
        "adjustments_verified_at_intake": bool(validated),
        "signal_state": "NOT_AUTHORIZED",
    }


def _as_record(x, observed_at_vn):
    return {
        "event_id": x["event_id"],
        "price_event_id": x["price_event_id"],
        "direction": "OPPORTUNITY_TO_GLOBAL",
        "source_session_date": x["source_session_date"],
        "source_prefilter_sha256": x["source_prefilter_sha256"],
        "symbol": x["symbol"],
        "price_predicate": x["price_predicate"],
        "adjusted_return_pct": x["adjusted_return_pct"],
        "intake_state": "PENDING_CAUSAL_NEWS_VERIFICATION",
        "causal_statement": "NO_CAUSAL_CLAIM",
        "signal_state": "NOT_AUTHORIZED",
        "market_packet_commit_pin": x["source_commit_sha"],
        "source_market_status": "COMPLETE_PRICE_ONLY_NO_CAUSAL_CLAIM",
        "adjustments_verified_at_intake": True,
    }


def bounded_reverse_projection_v2(checkpoint, health, prefilter, raw_events,
                                  source_commit, observed_at_vn):
    """Refill from pinned older price frontier and newest COMPLETE session.

    Max 8 NEW cases per VN calendar day, max 40 simultaneously active. No
    additional intake on replay in the same day. Existing record facts/states
    are never overwritten. The frontier is a bounded checkpoint index into the
    immutable GitHub source event log, not a copied raw dataset.
    """
    parse_time(observed_at_vn)
    # Preserve the Asia/Ho_Chi_Minh calendar day, not UTC's previous day.
    day = datetime.fromisoformat(
        observed_at_vn.replace("Z", "+00:00")
    ).date().isoformat()
    session = health.get("source_session_date")
    if not (health.get("complete") is True and health.get("status") == "COMPLETE"
            and session and session == health.get("expected_latest_completed_us_session")
            and session == prefilter.get("source_session_date")
            and health.get("prefilter_sha256")):
        raise ValueError("REVERSE_MARKET_HEALTH_INVALID")
    if not isinstance(checkpoint, dict):
        raise ValueError("CHECKPOINT_INVALID")
    srcstate = checkpoint.get("cross_radar_handoff") or {}
    prior = srcstate.get("reverse_price_session_acceptance_v1") or {}
    if prior.get("session") == session and prior.get("prefilter_sha256") != health["prefilter_sha256"]:
        raise ValueError("SAME_SESSION_PRICE_SHA_CONFLICT")
    reviewed = srcstate.get("opportunity_to_global") or {}
    for row in reviewed.values():
        validate_research_closeout(row)
    active = sum(not validate_research_closeout(row) for row in reviewed.values())
    room = max(0, ACTIVE_CAP - active)
    known_ids = {x.get("event_id") for x in reviewed.values()}
    by_symbol = {x.get("symbol"): x for x in prefilter.get("records", [])
                 if isinstance(x, dict) and x.get("last_date") == session}
    forwards = srcstate.get("global_to_opportunity") or {}

    prior_queue = srcstate.get("reverse_queue_v2") or {}
    if prior_queue and prior_queue.get("schema") != "reverse-research-queue-v2":
        raise ValueError("UNKNOWN_REVERSE_QUEUE_SCHEMA")
    older = {}
    for x in prior_queue.get("deferred", []):
        if not isinstance(x, dict) or x.get("signal_state") != "NOT_AUTHORIZED":
            raise ValueError("DEFERRED_ROW_SCHEMA_INVALID")
        if not x.get("adjustments_verified_at_intake") or not x.get("source_commit_sha"):
            raise ValueError("DEFERRED_ROW_UNVERIFIED")
        if x["event_id"] not in known_ids:
            older[x["event_id"]] = x

    # Fixed max of 150 high-priority price events, not a second live scanner.
    latest = reverse_price_requests(raw_events, health, max_out=LOOKBACK_LIMIT)
    current = {}
    skipped_known = []
    # reverse_price_requests already rejects suspected corporate actions; the
    # exclusion still belongs in the audit, otherwise owners cannot tell a
    # safety exclusion from an empty candidate stream.
    skipped_actions = sorted({
        str(r.get("symbol")) for r in raw_events
        if isinstance(r, dict) and r.get("source_session_date") == session
        and str(r.get("predicate", "")).startswith(("1D_", "5D_"))
        and r.get("symbol") in by_symbol and (
            by_symbol[r["symbol"]].get("adjustment_verified") is not True
            or by_symbol[r["symbol"]].get("corporate_action_unverified") is not False
            or by_symbol[r["symbol"]].get("corporate_action_suspected") is not False
            or r.get("corporate_action_suspected") is True)
    })
    for record in latest:
        sym = record["symbol"]
        if record["event_id"] in known_ids:
            continue
        row = by_symbol.get(sym)
        if not row or row.get("adjustment_verified") is not True or (
                row.get("corporate_action_unverified") is not False) or (
                row.get("corporate_action_suspected") is not False):
            skipped_actions.append(sym)
            continue
        current[record["event_id"]] = _make_deferred(record, source_commit)

    # Each same-symbol continuation stays in historical research. Only a
    # separate verified material Global event can open another issuer case.
    def ready(candidate, linked_keys):
        sym = candidate["symbol"]
        if candidate["event_id"] in known_ids:
            return False
        old = [x for x in reviewed.values() if x.get("symbol") == sym]
        if not old:
            return True
        g = _verified_new_material_event(sym, reviewed, forwards)
        if g is None or g["material_update_key"] in linked_keys:
            skipped_known.append(sym)
            return False
        candidate["linked_global_event_id"] = g["event_id"]
        candidate["linked_global_material_update_key"] = g["material_update_key"]
        candidate["linked_global_primary_source_url"] = g["primary_source_url"]
        return True

    all_candidates = {}
    # Older case identities take priority over same identifiers seen again.
    for x in list(older.values()) + list(current.values()):
        all_candidates.setdefault(x["event_id"], dict(x))
    candidate_rank = {event_id: rank for rank, event_id in enumerate(all_candidates)}
    linked_keys = {x.get("linked_global_material_update_key") for x in reviewed.values()}
    valid = []
    preserved_prior_deferred = []
    for c in all_candidates.values():
        if ready(c, linked_keys):
            valid.append(c)
        elif c["event_id"] in older:
            # A known issuer may have a separately recorded historic price event.
            # It is not admissible without new material, but it must not vanish.
            preserved_prior_deferred.append(c)
    # Preserve FIFO between sessions; preserve original rank within session.
    older_valid = [c for c in valid if c["source_session_date"] < session]
    current_valid = [c for c in valid if c["source_session_date"] >= session]

    # Migrate v1's already recorded 8 Nov12 admissions into the daily budget.
    # Not every historical Nov11 research ticket should count as new intake.
    budget = prior_queue.get("daily_budget") or {}
    if budget.get("date_vn") == day:
        used = budget.get("used", 0)
    else:
        used = 0
        if not prior_queue and prior.get("session") == session:
            earlier = [x for x in reviewed.values()
                       if x.get("source_session_date") == session and
                       str(x.get("first_ingested_at_vn") or "").startswith(day)]
            if earlier:
                used = min(DAILY_LIMIT, int(prior.get("new_added") or 0))
    if type(used) is not int or not 0 <= used <= DAILY_LIMIT:
        raise ValueError("REVERSE_DAILY_BUDGET_INVALID")
    quota = min(room, max(0, DAILY_LIMIT - used))
    selected = older_valid[:min(OLDER_SESSION_MIN_RESERVE, quota)]
    selected_ids = {x["event_id"] for x in selected}
    selected.extend(current_valid[:quota - len(selected)])
    selected_ids = {x["event_id"] for x in selected}
    if len(selected) < quota:
        selected.extend(x for x in older_valid if x["event_id"] not in selected_ids)
        selected = selected[:quota]
    selected_ids = {x["event_id"] for x in selected}

    # Keep compact deferred index, never a duplicated full market archive.
    remaining = [x for x in valid if x["event_id"] not in selected_ids]
    remaining.extend(preserved_prior_deferred)
    # Deterministic backpressure: oldest session first, preserving rank.
    remaining.sort(key=lambda x: (x["source_session_date"], candidate_rank[x["event_id"]]))
    frontier = remaining[:FRONTIER_LIMIT]
    overflow = len(remaining) - len(frontier)
    projected, stats = project_checkpoint(
        checkpoint, [], [_as_record(x, observed_at_vn) for x in selected],
        observed_at_vn=observed_at_vn)
    h = projected["cross_radar_handoff"]
    for c in selected:
        rec = h["opportunity_to_global"][c["event_id"]]
        if "linked_global_event_id" in c:
            rec.update({
                "linked_global_event_id": c["linked_global_event_id"],
                "linked_global_material_update_key": c["linked_global_material_update_key"],
                "linked_global_primary_source_url": c["linked_global_primary_source_url"],
                "same_issuer_new_material_event_requires_causal_verification": True,
            })
    same_session = prior.get("session") == session
    if not same_session:
        h["reverse_price_session_acceptance_v1"] = {
            "session": session, "source_commit_sha": source_commit,
            "prefilter_sha256": health["prefilter_sha256"],
            "source_prefilter_count": len(prefilter.get("records", [])),
            "source_raw_event_count": len(raw_events),
            "source_candidates_considered": len(latest),
            "old_pending_before": active,
            "old_source_reviewed_count": sum(bool(x.get("primary_source_triage_20261113"))
                                             for x in reviewed.values()),
            "new_added": sum(c["source_session_date"] == session for c in selected),
            "new_symbols": [c["symbol"] for c in selected if c["source_session_date"] == session],
            "same_issuer_already_queued": sorted(set(skipped_known)),
            "corporate_action_or_adjustment_skipped": sorted(set(skipped_actions)),
            "new_eligible_not_admitted_due_capacity": len(frontier) + overflow,
            "no_notification_or_trade": True,
            "source_status": "PINNED_COMPLETE_NO_BUY_SHORT",
        }
    updated_queue = {
        "schema": "reverse-research-queue-v2",
        "latest_completed_price_session": session,
        "latest_source_commit_sha": source_commit,
        "latest_prefilter_sha256": health["prefilter_sha256"],
        "daily_budget": {"date_vn": day, "used": used + len(selected)},
        "max_active": ACTIVE_CAP, "max_new_per_day": DAILY_LIMIT,
        "active_count": active + len(selected),
        "terminal_case_count": len(reviewed) - active,
        "deferred": frontier,
        "deferred_count": len(frontier),
        "deferred_beyond_index_count": overflow,
        "source_note": "Compact replay index; full original immutable source market log remains on GitHub",
        "requires_new_distinct_global_material_event_for_same_symbol": True,
        "causality_certified_by_queue": False,
        "no_trade_or_alert": True,
    }
    # Do not rewrite a stable checkpoint on identical rerun. Changing date
    # with no change in work/budget must not alone create a heartbeat write.
    prev_queue = srcstate.get("reverse_queue_v2")
    if prev_queue and not selected and prev_queue.get("deferred") == frontier and (
            prev_queue.get("latest_completed_price_session") == session):
        updated_queue["daily_budget"] = prev_queue["daily_budget"]
    # Fail closed if any previously persisted deferred identity is lost during
    # the bounded projection. Earlier entries are durable historical evidence.
    projected_ids = set(h["opportunity_to_global"]) | {
        row["event_id"] for row in frontier
    }
    if set(older) - projected_ids:
        raise ValueError("REVERSE_DEFERRED_ID_LOSS")
    h["reverse_queue_v2"] = updated_queue
    changed = (stats["reverse_added"] > 0 or
               srcstate.get("reverse_queue_v2") != updated_queue or
               (not same_session))
    return (projected if changed else checkpoint), {
        "reverse_added": stats["reverse_added"],
        "changed": changed,
        "already_accepted": same_session and not selected,
        "source_session": session,
        "capacity_skipped": len(frontier) + overflow,
        "active_pending": active + len(selected),
        "terminal_count": len(reviewed) - active,
        "deferred_count": len(frontier),
        "deferred_overflow": overflow,
        "daily_used": updated_queue["daily_budget"]["used"],
    }




def screen_full_inventory_cheap_v1(checkpoint, health, prefilter, *, deep_budget=8):
    """Classify EVERY existing research event; this is not deep underwriting.

    Cheap pass: reuse the accepted market packet and saved issuer-source proofs.
    All 40 active + all deferred + all terminal event IDs are included once.
    An unverified source or a price-only move never becomes a terminal case,
    causal certification, BUY/SHORT, or automatic trade authorization.

    No network, no new scanner, no quota consumption, no closeout mutation.
    The caller persists only one same-session replacement snapshot.
    """
    if type(deep_budget) is not int or not 0 <= deep_budget <= ACTIVE_CAP:
        raise ValueError("FULL_INVENTORY_DEEP_BUDGET_INVALID")
    session = health.get("source_session_date")
    if not (health.get("complete") is True and health.get("status") == "COMPLETE"
            and session and session == health.get("expected_latest_completed_us_session")
            and session == prefilter.get("source_session_date")
            and isinstance(health.get("prefilter_sha256"), str)
            and health.get("prefilter_sha256")):
        raise ValueError("FULL_INVENTORY_PRICE_PACKET_UNVERIFIED")
    state = checkpoint.get("cross_radar_handoff") or {}
    reviewed = state.get("opportunity_to_global") or {}
    queue = state.get("reverse_queue_v2") or {}
    deferred = queue.get("deferred") or []
    if not isinstance(reviewed, dict) or not isinstance(deferred, list):
        raise ValueError("FULL_INVENTORY_SCHEMA_INVALID")
    if queue and (queue.get("latest_completed_price_session") != session or
                  queue.get("latest_prefilter_sha256") != health["prefilter_sha256"]):
        raise ValueError("FULL_INVENTORY_QUEUE_PACKET_SHA_MISMATCH")
    seen = set()
    rows = {}
    counters = Counter()
    unique_symbols = set()
    available = {}
    for quote in prefilter.get("records", []):
        if not isinstance(quote, dict) or not isinstance(quote.get("symbol"), str):
            continue
        symbol = quote["symbol"]
        if (quote.get("last_date") == session
                and quote.get("adjustment_verified") is True
                and quote.get("corporate_action_unverified") is False
                and quote.get("corporate_action_suspected") is False
                and isinstance(quote.get("price"), (int, float))
                and quote["price"] > 0):
            available[symbol] = quote
    # Source index is reused only as HISTORICAL issuer provenance. There is
    # no implicit SEC freshness, document materiality, or price causality.
    prior_index = state.get("orv3_full_507_live_sec_pit_source_delta_20261119_v1") or {}
    index_issuers = (prior_index.get("issuer_index") or {}
                     if isinstance(prior_index, dict) else {})
    source_ready = []
    source_first = []
    active = terminal = 0
    for identity in sorted(reviewed):
        rec = reviewed[identity]
        if not isinstance(rec, dict):
            raise ValueError("FULL_INVENTORY_CASE_INVALID")
        if identity in seen:
            raise ValueError("FULL_INVENTORY_DUPLICATE_ID")
        seen.add(identity)
        symbol = str(rec.get("symbol") or "")
        unique_symbols.add(symbol)
        quote_ok = symbol in available
        closed = validate_research_closeout(rec)
        if closed:
            terminal += 1
            stage = "EVIDENCE_TERMINAL_EXCLUDED"
        else:
            active += 1
            econ = rec.get("issuer_economic_event_review_20261115_v1") or {}
            econ = econ if isinstance(econ, dict) else {}
            triage = rec.get("primary_source_triage_20261113") or {}
            triage = triage if isinstance(triage, dict) else {}
            pit = rec.get("pit_primary_source_stage_20261115_v1") or {}
            pit = pit if isinstance(pit, dict) else {}
            url = (econ.get("sec_exhibit_or_full_primary_text_url")
                   or econ.get("sec_primary_issuer_filing_url")
                   or triage.get("issuer_source_url")
                   or triage.get("source_url")
                   or pit.get("primary_url"))
            valid_url = isinstance(url, str) and url.startswith("https://")
            economic_ready = (econ.get("source_verified_pit") is True
                              and econ.get("issuer_economic_mechanism_evaluated") is True
                              and valid_url)
            if economic_ready and quote_ok:
                stage = "ACTIVE_SOURCE_ECONOMIC_READY_FOR_DEEP_REVIEW"
                # Numeric review is still REQUIRED and not certified.
                source_ready.append((str(rec.get("source_session_date") or ""),
                                     symbol, identity))
            elif valid_url:
                stage = ("ACTIVE_CAUSAL_PIT_OR_MARK_REVIEW"
                         if quote_ok else "ACTIVE_NO_CURRENT_VALIDATED_PRICE")
                source_first.append((str(rec.get("source_session_date") or ""),
                                     symbol, identity))
            else:
                stage = "ACTIVE_INDEPENDENT_DATED_ISSUER_SOURCE_GAP"
                source_first.append((str(rec.get("source_session_date") or ""),
                                     symbol, identity))
        counters[stage] += 1
        rows[identity] = {"symbol": symbol, "stage": stage,
                          "price_session_validated": quote_ok}
    if queue and (queue.get("active_count") != active or
                  queue.get("terminal_case_count") != terminal):
        raise ValueError("FULL_INVENTORY_ACTIVE_TERMINAL_COUNT_MISMATCH")
    for rec in deferred:
        if not isinstance(rec, dict) or not isinstance(rec.get("event_id"), str):
            raise ValueError("FULL_INVENTORY_DEFERRED_INVALID")
        identity = rec["event_id"]
        if identity in seen:
            raise ValueError("FULL_INVENTORY_DUPLICATE_ID")
        seen.add(identity)
        symbol = str(rec.get("symbol") or "")
        unique_symbols.add(symbol)
        quote_ok = symbol in available
        # A SEC index record (even new) does NOT warrant automatically
        # promoting a deferred event into one of the 40 deep-research slots.
        stage = ("DEFERRED_PRICE_ONLY_COLD"
                 if quote_ok else "DEFERRED_PRICE_SOURCE_NOT_CURRENT")
        counters[stage] += 1
        rows[identity] = {"symbol": symbol, "stage": stage,
                          "price_session_validated": quote_ok}
    if queue and queue.get("deferred_count") != len(deferred):
        raise ValueError("FULL_INVENTORY_DEFERRED_COUNT_MISMATCH")
    source_ready.sort()
    source_first.sort()
    deep_ids = [x[2] for x in source_ready[:deep_budget]]
    # Source investigations are separate from full numeric underwriting.
    source_ids = [x[2] for x in source_first[:deep_budget]]
    ids_sha = hashlib.sha256(json.dumps(sorted(seen), separators=(",", ":")).encode()).hexdigest()
    return {
        "schema": "opportunity-cheap-complete-inventory-v1",
        "market_session": session,
        "prefilter_sha256": health["prefilter_sha256"],
        "all_immutable_event_ids": len(seen),
        "ids_sha256": ids_sha,
        "active": active, "terminal": terminal, "deferred": len(deferred),
        "unique_symbols": len(unique_symbols),
        "market_records_in_packet": len(prefilter.get("records", [])),
        "cached_sec_issuer_provenance_n": sum(
            isinstance(index_issuers.get(s), dict)
            and index_issuers[s].get("status") == "SEC_SUBMISSION_INDEX_VERIFIED"
            for s in unique_symbols),
        "sec_index_only_historical_not_fresh": True,
        "stage_counts": dict(sorted(counters.items())),
        "all_ids_stage": rows,
        "deep_underwrite_due_ids": deep_ids,
        "source_investigation_due_ids": source_ids,
        "deep_underwrite_selected_n": len(deep_ids),
        "source_investigation_selected_n": len(source_ids),
        "auto_terminal_added": 0,
        "full_numeric_certified_by_cheap_screen": 0,
        "new_buy_short_or_orders": 0,
        "source_screen_not_price_causality": True,
        "no_event_status_mutated": True,
    }



def apply_signed_research_closeouts_v1(checkpoint):
    """Apply an ALREADY recorded final research decision; invent no decisions.

    Some owners may persist a complete research_closeout_v2 proof before its
    intake_state is finalized. Only such explicit, independently attributable
    terminal decisions release an ACTIVE slot; missing source, poor score,
    stale price, or hypothetical FCF stress NEVER count as a closeout.
    """
    state = checkpoint.get("cross_radar_handoff") or {}
    reviewed = state.get("opportunity_to_global") or {}
    if not isinstance(reviewed, dict):
        raise ValueError("RESEARCH_CASE_MAP_INVALID")
    candidates = {}
    for identity, rec in reviewed.items():
        if not isinstance(rec, dict):
            raise ValueError("RESEARCH_CASE_INVALID")
        if validate_research_closeout(rec):
            continue
        proof = rec.get("research_closeout_v2")
        if not isinstance(proof, dict):
            continue
        # A dated, explicit final decision is a prerequisite. Never derive
        # terminal disposition from a financial metric or source count.
        decision = proof.get("decision")
        if decision not in TERMINAL_STATES:
            continue
        amended = copy.deepcopy(rec)
        amended["intake_state"] = decision
        if not validate_research_closeout(amended):
            raise ValueError("SIGNATURE_CLOSEOUT_REJECTED")
        candidates[identity] = amended
    if not candidates:
        return checkpoint, 0
    updated = copy.deepcopy(checkpoint)
    updated["cross_radar_handoff"]["opportunity_to_global"].update(candidates)
    return updated, len(candidates)

RESEARCH_WORKLIST_LIMIT = 8



def _due_source_catalysts(state, latest_market_session):
    """Existing FOLLOW and verified issuer handoffs stay visible when price ACTIVE=40.

    This is a read-only source-research lane, not admission to the 40 price
    tickets and never evidence of an investable price or an authorized trade.
    The original economic event timestamp remains immutable.
    """
    if not isinstance(latest_market_session, str) or len(latest_market_session) != 10:
        return []
    try:
        datetime.strptime(latest_market_session, "%Y-%m-%d")
    except ValueError:
        return []

    def valid_date(value):
        if not isinstance(value, str) or len(value) < 10:
            return None
        day = value[:10]
        try:
            datetime.strptime(day, "%Y-%m-%d")
        except ValueError:
            return None
        return day if day <= latest_market_session else None

    ranked = []
    follow = state.get("follow_catalyst_rechecks_v1") or {}
    cases = follow.get("cases") or {}
    if not isinstance(cases, dict):
        raise ValueError("FOLLOW_CATALYST_CASES_INVALID")
    for key, case in cases.items():
        if not isinstance(key, str) or not isinstance(case, dict):
            raise ValueError("FOLLOW_CATALYST_CASE_INVALID")
        if case.get("full_numeric_deep_underwrite_certified") is True:
            continue
        if case.get("research_stage") != "SOURCE_MATERIALITY_VERIFIED__NUMERIC_UNDERWRITE_DUE":
            continue
        material = case.get("material_catalyst") or {}
        original = case.get("original_follow") or {}
        if not isinstance(material, dict) or not isinstance(original, dict):
            continue
        source_day = valid_date(material.get("event_date_public"))
        original_day = valid_date(original.get("original_detected_at_vn"))
        url = material.get("primary_sec_url") or material.get("issuer_url")
        symbol = case.get("symbol")
        if (not source_day or not original_day or original_day > source_day
                or not isinstance(symbol, str) or not symbol
                or not isinstance(url, str) or not url.startswith("https://")
                or not original.get("original_intake_id")):
            continue
        task = {
            "event_id": key, "symbol": symbol, "case_type": "FOLLOW_CATALYST_RECHECK",
            "original_follow_intake_id": original["original_intake_id"],
            "material_event_date": source_day, "existing_source_url": url,
            "next_gate": "NORMALIZED_FCF_BEAR_BASE_BULL_POST_RELEASE_NET_RR",
            "source_stage": "SOURCE_MATERIALITY_VERIFIED__NUMERIC_UNDERWRITE_DUE",
            "price_source_session": (case.get("first_post_event_verified_market") or {}).get("session"),
            "price_recheck_required": True,
            "causality_certified": False, "trade_authorized_by_worklist": False,
            "candidate_write_authorized": False,
        }
        ranked.append(((0, -int(source_day.replace("-", "")), key), task))
    forwards = state.get("global_to_opportunity") or {}
    if not isinstance(forwards, dict):
        raise ValueError("GLOBAL_HANDOFF_CASES_INVALID")
    for key, record in forwards.items():
        if not isinstance(key, str) or not isinstance(record, dict):
            raise ValueError("GLOBAL_HANDOFF_CASE_INVALID")
        if record.get("verified_source") is not True:
            continue
        if record.get("full_numeric_deep_underwrite_certified") is True:
            continue
        if record.get("intake_state") in {
                "SCREENED_INCIDENT_WATCH_NO_TRADE", "RESEARCHED_NO_TRADE",
                "WAITING_NEW_EVIDENCE", "REJECTED_NO_MATCHED_CATALYST"}:
            continue
        source_day = valid_date(record.get("source_event_time_vn"))
        symbol = record.get("symbol")
        url = record.get("primary_source_url")
        material_key = record.get("material_update_key")
        if (not source_day or not isinstance(symbol, str) or not symbol
                or not isinstance(url, str) or not url.startswith("https://")
                or not isinstance(material_key, str) or not material_key):
            continue
        reviewed = bool(record.get("fast_catalyst_triage_at_vn"))
        task = {
            "event_id": key, "symbol": symbol, "case_type": "VERIFIED_MATERIAL_SOURCE_REVIEW",
            "original_follow_intake_id": None,
            "material_event_date": source_day, "material_update_key": material_key,
            "existing_source_url": url,
            "next_gate": ("CONTINUE_ISSUER_ECONOMICS_AND_POST_EVENT_VALUATION"
                          if reviewed else
                          "VERIFY_ISSUER_ECONOMICS_MATERIALITY_AND_PIT"),
            "source_stage": ("PREVIOUSLY_TRIAGED__NUMERIC_OR_CAUSAL_OPEN"
                             if reviewed else "SOURCE_ONLY_ECONOMIC_REVIEW_DUE"),
            "price_recheck_required": True,
            "causality_certified": False, "trade_authorized_by_worklist": False,
            "candidate_write_authorized": False,
        }
        # A newer truly material source phase outranks old source-only intake,
        # but never outranks the explicitly linked FOLLOW numeric review.
        ranked.append(((2 if reviewed else 1,
                        -int(source_day.replace("-", "")), key), task))
    # Consume source-only evidence and secondary exposures from the same audit.
    audit = state.get("runtime_e2e_audit_v1") or {}
    exposure_map = audit.get("verified_security_exposures_by_event") or {}
    for _, task in ranked:
        if task.get("case_type") != "VERIFIED_MATERIAL_SOURCE_REVIEW":
            continue
        rec = forwards.get(task["event_id"]) or {}
        exposures = exposure_map.get(task["event_id"]) or rec.get("affected_securities") or []
        verified = [x for x in exposures if isinstance(x, dict) and
                    x.get("verified") is True and isinstance(x.get("symbol"), str) and
                    x.get("symbol") and isinstance(x.get("exposure_url"), str) and
                    x["exposure_url"].startswith("https://")]
        task["affected_securities"] = verified
        task["review_symbols"] = sorted({task["symbol"]} | {x["symbol"] for x in verified})
        task["all_security_exposures_require_review"] = True
    seen = {task["event_id"] for _, task in ranked} | set(forwards)
    for record in audit.get("source_only_event_statuses") or []:
        if not isinstance(record, dict):
            continue
        if record.get("lifecycle_state", "PENDING") != "PENDING":
            continue
        key = record.get("source_group_id")
        day = valid_date(record.get("source_event_time_vn"))
        url = record.get("primary_source_url") or record.get("candidate_source_url")
        if (not isinstance(key, str) or not key.startswith("G2O|") or key in seen
                or record.get("symbol") is not None or not day
                or record.get("signal_state") != "NOT_AUTHORIZED"
                or record.get("intake_state") not in {"SOURCE_ONLY","SOURCE_ONLY_PENDING_VERIFICATION"}
                or not isinstance(url,str) or not url.startswith("https://")):
            continue
        seen.add(key)
        task = {"event_id": key, "symbol": None, "case_type": "GLOBAL_SOURCE_ONLY_REVIEW",
                "source_event_key": record.get("source_event_key"),
                "material_update_key": record.get("material_update_key"),
                "material_event_date": day, "existing_source_url": url,
                "source_stage": record["intake_state"],
                "next_gate": "VERIFY_PRIMARY_SOURCE_AND_CAUSAL_EXPOSURE",
                "review_symbols": [], "price_recheck_required": False,
                "causality_certified": False, "trade_authorized_by_worklist": False,
                "candidate_write_authorized": False}
        ranked.append(((3, -int(day.replace("-", "")), key), task))
    ranked.sort(key=lambda item: item[0])
    return [task for _, task in ranked]


def bounded_research_worklist(checkpoint, limit=RESEARCH_WORKLIST_LIMIT, *, cheap_screen=None):
    """Read-only, deterministic next-stage research plan for the EXISTING owner.

    A source-screened ticket is still ACTIVE. Never infer price causality,
    valuation certification, a terminal decision or a trade from this plan.
    """
    if type(limit) is not int or not 1 <= limit <= ACTIVE_CAP:
        raise ValueError("RESEARCH_WORKLIST_LIMIT_INVALID")
    if not isinstance(checkpoint, dict):
        raise ValueError("CHECKPOINT_INVALID")
    state = checkpoint.get("cross_radar_handoff") or {}
    reviewed = state.get("opportunity_to_global") or {}
    if not isinstance(reviewed, dict):
        raise ValueError("RESEARCH_CASE_MAP_INVALID")
    ranked, screened, missing_source, terminal, certified = [], 0, 0, 0, 0
    market_stage = {}
    if cheap_screen is not None:
        if (not isinstance(cheap_screen, dict) or
                cheap_screen.get("schema") != "opportunity-cheap-complete-inventory-v1"):
            raise ValueError("RESEARCH_CURRENT_CHEAP_SCREEN_INVALID")
        market_stage = cheap_screen.get("all_ids_stage") or {}
        if not isinstance(market_stage, dict):
            raise ValueError("RESEARCH_CURRENT_PRICE_STAGE_INVALID")
    for identity, rec in reviewed.items():
        if not isinstance(rec, dict):
            raise ValueError("RESEARCH_CASE_INVALID")
        if validate_research_closeout(rec):
            terminal += 1
            continue
        # Prefer immutable event-level PIT economics over the 2026-11-13
        # source triage. Timely filings alone remain non-causal evidence.
        economic = rec.get("issuer_economic_event_review_20261115_v1")
        economic = economic if isinstance(economic, dict) else {}
        economic_evidence_available = (
            economic.get("source_verified_pit") is True and
            economic.get("issuer_economic_mechanism_evaluated") is True)
        economic_ready = economic_evidence_available
        if cheap_screen is not None:
            actual_stage = market_stage.get(identity) or {}
            # A numeric slot requires valid CURRENT price, not stale issuer
            # economics from an old market session.
            economic_ready = (
                economic_ready and actual_stage.get("stage") ==
                "ACTIVE_SOURCE_ECONOMIC_READY_FOR_DEEP_REVIEW" and
                actual_stage.get("price_session_validated") is True)
        evidence = rec.get("primary_source_triage_20261113")
        triage = evidence if isinstance(evidence, dict) else {}
        if economic_evidence_available:
            field = "issuer_economic_event_review_20261115_v1"
            url = (economic.get("sec_exhibit_or_full_primary_text_url") or
                   economic.get("sec_primary_issuer_filing_url"))
            screened += 1
        else:
            field = "primary_source_triage_20261113" if triage else None
            url = triage.get("issuer_source_url") or triage.get("source_url")
            if triage:
                screened += 1
            if not url:
                stage = rec.get("pit_primary_source_stage_20261115_v1")
                stage = stage if isinstance(stage, dict) else {}
                if (stage.get("stage") ==
                        "OFFICIAL_SEC_FILING_ACCEPTED_IN_PRICE_WINDOW__FULL_EXHIBIT_PENDING"
                        and stage.get("issuer_sec_acceptance_ny")):
                    url = stage.get("primary_url")
                    if url:
                        field = "pit_primary_source_stage_20261115_v1"
        if not isinstance(url, str) or not url.startswith("https://"):
            url = None
            missing_source += 1
        if rec.get("full_numeric_deep_underwrite_certified") is True:
            certified += 1
        predicate = str(rec.get("price_predicate") or "")
        kind_order = {"1D_SHOCK": 0, "1D_PUMP": 1,
                      "5D_SHOCK": 2, "5D_PUMP": 3}
        try:
            severity = abs(float(rec.get("adjusted_return_pct") or 0))
        except (TypeError, ValueError):
            severity = 0.0
        next_gate = ("NORMALIZED_FCF_BEAR_UPSIDE_NET_RR_VENUE"
                     if economic_ready else
                     "VERIFY_CURRENT_EXECUTABLE_PRICE_AND_PIT"
                     if economic_evidence_available and cheap_screen is not None else
                     "VERIFY_DATED_PRIMARY_SOURCE" if url is None else
                     "ISSUER_EXHIBIT_SEMANTICS_AND_PIT_PRICE_LINK"
                     if field == "pit_primary_source_stage_20261115_v1" else
                     "PIT_ISSUER_PRICE_LINK_AND_CASHFLOW_DOWNSIDE")
        task = {
            "event_id": rec.get("event_id") or identity,
            "symbol": rec.get("symbol"),
            "source_session_date": rec.get("source_session_date"),
            "price_predicate": predicate,
            "adjusted_return_pct": rec.get("adjusted_return_pct"),
            "next_gate": next_gate,
            "existing_evidence_field": field,
            "existing_source_url": url,
            "causality_certified": False,
            "trade_authorized_by_worklist": False,
        }
        ranked.append(((0 if economic_ready else 1 if url is not None else 2,
                        kind_order.get(predicate, 4), -severity,
                        str(rec.get("source_session_date") or ""),
                        str(task["event_id"])), task))
    ranked.sort(key=lambda x: x[0])
    queue = state.get("reverse_queue_v2") or {}
    due_source = _due_source_catalysts(
        state, queue.get("latest_completed_price_session"))
    # At most 3 independently sourced issuer cases consume the SAME eight
    # research slots; the other slots remain for existing price cases. One
    # issuer per pass avoids crowding out unrelated firms, not deduping phases.
    source_limit = min(len(due_source), min(3, max(1, limit // 2)))
    selected_source = []
    selected_issuers = set()
    for case in due_source:
        if len(selected_source) >= source_limit:
            break
        symbols = set(case.get("review_symbols") or ([case["symbol"]] if case.get("symbol") else []))
        if symbols & selected_issuers:
            continue
        selected_source.append(case)
        selected_issuers.update(symbols)
    selected_price = [task for _, task in ranked[:limit - len(selected_source)]]
    worklist = selected_source + selected_price
    # Inspect the newest deferred shock cheaply even when ACTIVE is full;
    # never convert an unverified price-only event to a numeric underwrite.
    deferred_rows = queue.get("deferred") or []
    newest_session = queue.get("latest_completed_price_session")
    fresh_deferred = [x for x in deferred_rows if
                      isinstance(x, dict) and
                      x.get("source_session_date") == newest_session]
    fresh_deferred.sort(key=lambda x: (
        0 if float(x.get("adjusted_return_pct") or 0) < 0 else 1,
        -abs(float(x.get("adjusted_return_pct") or 0)),
        str(x.get("event_id") or "")))
    deferred_price_watch = [{
        "event_id": x.get("event_id"), "symbol": x.get("symbol"),
        "source_session_date": x.get("source_session_date"),
        "price_predicate": x.get("price_predicate"),
        "adjusted_return_pct": x.get("adjusted_return_pct"),
        "stage": "DEFERRED_PRICE_ONLY__NO_CAUSAL_CLAIM",
        "active_slot_reserved": False, "candidate_write_authorized": False,
        "buy_signal": False,
    } for x in fresh_deferred[:5]]
    active = len(ranked)
    cap = queue.get("max_active", ACTIVE_CAP)
    day_new = queue.get("max_new_per_day", DAILY_LIMIT)
    return {
        "schema": "reverse-research-worklist-v1",
        "status": ("RESEARCH_BACKLOG_OPEN" if (active or due_source)
                   else "NO_ACTIVE_RESEARCH_CASES"),
        "active_pending": active,
        "source_only_catalyst_due": len(due_source),
        "source_only_catalyst_selected": len(selected_source),
        "source_only_catalyst_deferred": len(due_source) - len(selected_source),
        "newest_deferred_price_only_watch": deferred_price_watch,
        "terminal_cases": terminal,
        "source_screened_active": screened,
        "missing_dated_source_active": missing_source,
        "full_numeric_certified_active": certified,
        "deferred": int(queue.get("deferred_count") or 0),
        "selected_count": len(worklist),
        "not_selected_active": max(0, active - len(selected_price)),
        "next_full_daily_intake_needs_closeouts": max(0, active + day_new - cap),
        "saturates_cap_if_next_full_daily_intake": active + day_new >= cap,
        "selection_rule": ("Verified FOLLOW catalyst -> new independently sourced "
                           "issuer event (at most 3 source slots) -> PIT price "
                           "economics -> existing price case. Source-only cases "
                           "do not consume ACTIVE=40; newest deferred price "
                           "shock stays diagnostic only."),
        "worklist": worklist,
        "no_state_write_or_trade": True,
    }
