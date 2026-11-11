#!/usr/bin/env python3
"""Evidence-dated AI answer substitution gate for the existing BUY/BUILD pipeline.

This module reads reviewed decisions only. It has no network calls, model calls,
browser, scanner, timer, or mutation of source-owned records. A title/keyword
cannot itself establish either substitution risk or durable product value.
"""
from __future__ import annotations

import datetime as dt
import json
import pathlib

REVIEWS_FILE = pathlib.Path(__file__).with_name("ai_substitution_reviews.json")
VALID_RESILIENCE = {"RECURRENT_WORKFLOW", "TRANSACTION", "DIRECT_DISTRIBUTION", "PROPRIETARY_DATA"}


def _load_overrides() -> dict:
    try:
        raw = json.loads(REVIEWS_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(raw, dict) or raw.get("schema") != "ai-substitution-reviewed-v1":
        return {}
    reviews = raw.get("reviews")
    return reviews if isinstance(reviews, dict) else {}


def review_for_candidate(identity: str, inline: object = None, as_of: str | None = None) -> dict:
    """Read explicit source-linked risk: HIGH, RESILIENT, or UNREVIEWED.

    The repo-owned override supersedes candidate-side fields when effective,
    preventing a feed from silently reversing a reviewed manual rejection.
    Historical replay before review_date is not retroactively altered.
    """
    result = {"status": "UNREVIEWED", "reviewed": False, "source_refs": [],
              "reason": "AI substitution and defensible non-answer workflow not reviewed"}
    if not isinstance(identity, str) or not identity.strip():
        return result
    if as_of is not None:
        try:
            cutoff = dt.date.fromisoformat(as_of)
        except (TypeError, ValueError):
            return result
    else:
        cutoff = dt.date.today()
    official = _load_overrides().get(identity)
    packet = official if isinstance(official, dict) else inline
    if not isinstance(packet, dict):
        return result
    if packet.get("status") != "REVIEWED" or packet.get("identity") != identity:
        return result
    try:
        reviewed_day = dt.date.fromisoformat(str(packet.get("review_date") or ""))
    except ValueError:
        return result
    if reviewed_day > cutoff:
        # A future curated review must never rewrite historical snapshots.
        return result
    if len(str(packet.get("customer_job") or "").strip()) < 16:
        return result
    if len(str(packet.get("reason") or "").strip()) < 30:
        return result
    refs = packet.get("source_refs")
    if not isinstance(refs, list) or len(refs) < 2 or len(refs) > 8:
        return result
    if not all(isinstance(x, str) and len(x) >= 20
               and (x.startswith("https://") or x.startswith("dropbox:")) for x in refs):
        return result
    if len(set(refs)) != len(refs):
        return result
    risk = packet.get("risk")
    answer_only = packet.get("ai_answer_completes_customer_job")
    click_dependent = packet.get("revenue_depends_on_answer_pageviews")
    resilience = packet.get("resilience_basis")
    if (risk == "HIGH_ANSWER_SUBSTITUTION" and answer_only is True
            and click_dependent is True and resilience == "NONE_VERIFIED"):
        status = "HIGH"
    elif (risk == "RESILIENT_WORKFLOW" and answer_only is False
          and resilience in VALID_RESILIENCE
          and packet.get("non_answer_value_source_checked") is True):
        # Even here, source-linked evidence is still subject to independent DD;
        # a positive review never becomes a BUY/BUILD approval.
        status = "RESILIENT"
    else:
        return result
    return {"status": status, "reviewed": True, "source_refs": list(refs),
            "reason": packet["reason"].strip(), "review_date": reviewed_day.isoformat(),
            "independent_business_dd_still_required": True}
