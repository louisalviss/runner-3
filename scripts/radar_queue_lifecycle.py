"""Bounded event-specific Opportunity -> Global research queue lifecycle.

Pure projection module.  Existing verified price ledger, one existing Dropbox
checkpoint, no new scheduler, database, notification or trading authority.
A documented research no-trade / waiting closeout is not certified price causality.
"""
from __future__ import annotations

import copy
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
    linked_keys = {x.get("linked_global_material_update_key") for x in reviewed.values()}
    valid = []
    for c in all_candidates.values():
        if ready(c, linked_keys):
            valid.append(c)
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
    # Deterministic backpressure: oldest session first, preserving rank.
    remaining.sort(key=lambda x: x["source_session_date"])
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


RESEARCH_WORKLIST_LIMIT = 8


def bounded_research_worklist(checkpoint, limit=RESEARCH_WORKLIST_LIMIT):
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
    for identity, rec in reviewed.items():
        if not isinstance(rec, dict):
            raise ValueError("RESEARCH_CASE_INVALID")
        if validate_research_closeout(rec):
            terminal += 1
            continue
        evidence = rec.get("primary_source_triage_20261113")
        triage = evidence if isinstance(evidence, dict) else {}
        if triage:
            screened += 1
        url = triage.get("issuer_source_url") or triage.get("source_url")
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
        next_gate = ("VERIFY_DATED_PRIMARY_SOURCE" if url is None else
                     "PIT_ISSUER_PRICE_LINK_AND_CASHFLOW_DOWNSIDE")
        task = {
            "event_id": rec.get("event_id") or identity,
            "symbol": rec.get("symbol"),
            "source_session_date": rec.get("source_session_date"),
            "price_predicate": predicate,
            "adjusted_return_pct": rec.get("adjusted_return_pct"),
            "next_gate": next_gate,
            "existing_evidence_field": ("primary_source_triage_20261113"
                                        if triage else None),
            "existing_source_url": url,
            "causality_certified": False,
            "trade_authorized_by_worklist": False,
        }
        ranked.append(((0 if url is None else 1,
                        kind_order.get(predicate, 4), -severity,
                        str(rec.get("source_session_date") or ""),
                        str(task["event_id"])), task))
    ranked.sort(key=lambda x: x[0])
    queue = state.get("reverse_queue_v2") or {}
    active = len(ranked)
    cap = queue.get("max_active", ACTIVE_CAP)
    day_new = queue.get("max_new_per_day", DAILY_LIMIT)
    return {
        "schema": "reverse-research-worklist-v1",
        "status": "RESEARCH_BACKLOG_OPEN" if active else "NO_ACTIVE_RESEARCH_CASES",
        "active_pending": active,
        "terminal_cases": terminal,
        "source_screened_active": screened,
        "missing_dated_source_active": missing_source,
        "full_numeric_certified_active": certified,
        "deferred": int(queue.get("deferred_count") or 0),
        "selected_count": min(active, limit),
        "not_selected_active": max(0, active - limit),
        "next_full_daily_intake_needs_closeouts": max(0, active + day_new - cap),
        "saturates_cap_if_next_full_daily_intake": active + day_new >= cap,
        "selection_rule": "missing source; then 1D shocks, 1D pumps, 5D shocks, 5D pumps; severity desc",
        "worklist": [task for _, task in ranked[:limit]],
        "no_state_write_or_trade": True,
    }
