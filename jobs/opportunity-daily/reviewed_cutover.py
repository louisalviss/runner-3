#!/usr/bin/env python3
"""Immutable user-approved prior-cohort cutover for the existing Acquisition Radar.

Archiving a reviewed listing suppresses repetitive research, not source data.
A reviewed candidate is not necessarily rejected, SOLD, or financially verified.
"""
from __future__ import annotations
import datetime
import json
import pathlib

PATH = pathlib.Path(__file__).with_name("reviewed_cohort_20261112.json")
CUTOVER_DAY = "2026-11-12"
# A relisted ID is not a new business when the older listing already
# identifies an exact redirect target. Never treat unrelated new IDs as old.
VERIFIED_RELIST_ALIASES = {"14595704": "14215867"}


def reviewed_processed_ids(day: str) -> frozenset[str]:
    """Never apply the archival decision to historical scans before cutover."""
    try:
        target = datetime.date.fromisoformat(day)
        cutover = datetime.date.fromisoformat(CUTOVER_DAY)
    except (TypeError, ValueError):
        return frozenset()
    if target < cutover:
        return frozenset()
    try:
        payload = json.loads(PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        # Fail *closed*: a missing/corrupt archive must not accidentally
        # resurrect old DD or allow treating unknown data as a new deal.
        raise RuntimeError("ACQUISITION_REVIEWED_COHORT_UNAVAILABLE")
    ids = payload.get("ids")
    if (payload.get("schema") != "acquisition-processed-review-cohort-v1"
            or payload.get("cutover_date") != CUTOVER_DAY
            or payload.get("original_backlog_active_count") != 87
            or not isinstance(ids, list) or len(ids) != 87
            or any(not isinstance(x, str) or not x.isdecimal() for x in ids)
            or len(set(ids)) != len(ids)):
        raise RuntimeError("ACQUISITION_REVIEWED_COHORT_INVALID")
    return frozenset(ids)


def is_reviewed_prior_listing(identity: str, day: str) -> bool:
    """Flippa identity only; SeoTrends discovery is not suppressed."""
    if not isinstance(identity, str) or not identity.startswith("flippa:"):
        return False
    ident = identity.removeprefix("flippa:")
    prior = reviewed_processed_ids(day)
    return ident in prior or VERIFIED_RELIST_ALIASES.get(ident) in prior

# Dated manual dispositions, distinct from the immutable 87-ID completed cohort.
# Canonical evidence: Acquisition Idea Radar/History/
# 2026-11-25-manual-review-appmint-yieldstone-13817253-14903899.md
MANUAL_REVIEW_DAY = "2026-11-25"
MANUAL_REVIEWED_IDS = frozenset({"13817253", "14903899"})



# Existing canonical Acquisition - Idea Radar.md, revision 016611b3a06f96b000000034da19313.
REFERENCE_REVIEW_DAY = "2026-11-25"
REFERENCE_REVIEW_REF = "ACQUISITION_FLIPPA_SIX_REFERENCE_REVIEW_20261125"
REFERENCE_REVIEWS = {
    "14742170": ("DROP", "Free niche calculators/content; no proven paid wedge or audited profit."),
    "14784037": ("DROP", "Local parking affiliate content; transferable conversion and profit unverified."),
    "14773340": ("DEFER", "Verify exact asset domain, ownership/rights and financial evidence."),
    "14803487": ("WATCH", "Verify source-linked domain, lead quality, conversion, referral contracts and net profit."),
    "14809474": ("DROP", "Generic screenshot tutorials; high substitution exposure and no audited profit."),
    "14816607": ("DROP", "Blog and printables; no demonstrated paid differentiation or audited profit."),
}

def reference_review(identity, day):
    try:
        if datetime.date.fromisoformat(day) < datetime.date.fromisoformat(REFERENCE_REVIEW_DAY):
            return None
    except (TypeError, ValueError):
        return None
    if not isinstance(identity,str) or not identity.startswith("flippa:"):
        return None
    result = REFERENCE_REVIEWS.get(identity.removeprefix("flippa:"))
    if result is None:
        return None
    return {"decision":result[0],"reason":result[1],"reviewed_on":REFERENCE_REVIEW_DAY,
            "review_ref":REFERENCE_REVIEW_REF,"marketplace_status_verified":False}

def reference_reopen_evidence(row, day):
    """Later material evidence only; card movement alone is insufficient."""
    review=reference_review(row.get("identity"),day)
    if not review or day <= REFERENCE_REVIEW_DAY or row.get("verified_detail") is not True:
        return False
    from build_buy_decision import verified_flippa_site_review, verified_flippa_build_gap, positive_number
    site_ok=verified_flippa_site_review(row)
    if not site_ok:
        return False
    if verified_flippa_build_gap(row,site_ok):
        return True
    # A newly source-bound site review is directly relevant to the unresolved
    # domain/workflow questions for the two retained references.
    if review["decision"] in ("DEFER","WATCH"):
        return True
    price=next((positive_number(row.get(k)) for k in ("bin_verified","reserve_verified","asking_verified")
                if positive_number(row.get(k)) is not None),None)
    # This is a new credible BUY review hypothesis, NOT audited earnings.
    return bool(price is not None and price<=10000 and (positive_number(row.get("profit_card")) or 0)>=250)

def qualified_reference_reopened(item, day):
    """Only later normal qualification output can reopen the carried backlog."""
    if not reference_review(item.get("identity"),day) or day <= REFERENCE_REVIEW_DAY:
        return False
    e=item.get("evidence") or {}
    return (item.get("source")=="FLIPPA" and item.get("category") in ("BUY_DD","BUILD_DD","DUAL_DD")
            and e.get("verified_direct_listing") is True and e.get("asset_site_review_complete") is True
            and e.get("asset_domain_identity_verified") is True
            and (e.get("build_serp_gap_verified") is True or
                 (e.get("price_within_cap") is True and
                  isinstance(e.get("profit_card_usd_per_month"),(int,float)) and
                  e["profit_card_usd_per_month"]>=250)))

def is_manual_review_duplicate(row: dict, day: str) -> bool:
    """Suppress repetitive card-only review; allow new direct commercial evidence.

    A verified direct price within budget for AppMint, or a fully validated
    independent BUILD gap, merits a new review, not automatic approval. A relisting or seller card change alone does not.
    """
    try:
        if datetime.date.fromisoformat(day) < datetime.date.fromisoformat(MANUAL_REVIEW_DAY):
            return False
    except (TypeError, ValueError):
        return False
    if not isinstance(row, dict):
        return False
    identity = row.get("identity")
    if not isinstance(identity, str) or not identity.startswith("flippa:"):
        return False
    if reference_review(identity, day):
        return not reference_reopen_evidence(row, day)
    if identity.removeprefix("flippa:") not in MANUAL_REVIEWED_IDS:
        return False
    # Allow a new verified evidence record to reach the normal qualification
    # gates; never turn an asserted evidence flag into a BUY/BUILD approval.
    if row.get("verified_detail") is True:
        from_price = next((row.get(k) for k in ("bin_verified", "reserve_verified", "asking_verified") if row.get(k) is not None), None)
        if isinstance(from_price, (int, float)) and not isinstance(from_price, bool) and 0 < from_price <= 10000:
            if identity == "flippa:13817253":
                return False
        if row.get("asset_domain_verified") is True and isinstance(row.get("independent_build_gap"), dict):
            from build_buy_decision import verified_flippa_site_review, verified_flippa_build_gap
            if verified_flippa_build_gap(row, verified_flippa_site_review(row)):
                return False
    return True
