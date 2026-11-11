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
    return (isinstance(identity, str) and identity.startswith("flippa:")
            and identity.removeprefix("flippa:") in reviewed_processed_ids(day))
