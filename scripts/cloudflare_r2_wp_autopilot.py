#!/usr/bin/env python3
"""Bounded single-run continuation of the already-verified R2 WP Media migration.

Does not schedule itself, mutate source, overwrite target, or cut over
production. One execution handles consecutive, idempotent small-object batches
and checkpoints after every verified batch; only a separately approved start
is needed. Large/unsupported objects remain quarantined.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import time

import cloudflare_r2_native_batch as batch
from cloudflare_r2_native_canary import (GateError, source_list, source_properties,
                                         source_bytes, verify_properties)

MAX_BATCHES = 80
MAX_UPLOADED_BYTES = 250_000_000
MAX_RUNTIME_SECONDS = 40 * 60
MAX_SOURCE_OBJECTS = 500
MAX_SOURCE_BYTES = 300_000_000

OUT = Path("migration-out")
PROGRESS = OUT / "wp-auto-progress.json"
SUMMARY = OUT / "receipt.json"


def utc_now():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def save(progress):
    OUT.mkdir(exist_ok=True)
    tmp = PROGRESS.with_suffix(".tmp")
    tmp.write_text(json.dumps(progress, sort_keys=True, indent=2) + "\n")
    tmp.replace(PROGRESS)
    SUMMARY.write_text(json.dumps(progress, sort_keys=True, indent=2) + "\n")


def started_state():
    return {
        "status": "RUNNING",
        "mode": "auto-small",
        "bucket": batch.BUCKET,
        "batch_limit": MAX_BATCHES,
        "max_total_copy_bytes": MAX_UPLOADED_BYTES,
        "max_runtime_seconds": MAX_RUNTIME_SECONDS,
        "batch_count": 0,
        "uploaded_count": 0,
        "uploaded_bytes": 0,
        "existing_verified_in_batch": 0,
        "verified_existing_final": 0,
        "source_deleted": False,
        "overwritten": False,
        "cutover_ready": False,
        "full_bucket_parity_verified": False,
        "credential_values_exposed": False,
        "started_at_utc": utc_now(),
    }


def check_source_budget(token):
    source = source_list(token, batch.BUCKET)
    if len(source) > MAX_SOURCE_OBJECTS:
        raise GateError("SOURCE_OBJECT_COUNT_BUDGET")
    total = sum(int(obj.get("size") or 0) for obj in source)
    if total > MAX_SOURCE_BYTES:
        raise GateError("SOURCE_TOTAL_BYTE_BUDGET")
    return source


def time_ok(start):
    return time.monotonic() - start < MAX_RUNTIME_SECONDS


def verify_existing_read_only(client, token, obj):
    """Verify an existing destination object without even attempting PUT."""
    key = obj["key"]
    properties = source_properties(obj)
    raw = source_bytes(token, batch.BUCKET, obj)
    try:
        head = client.head_object(Bucket=batch.BUCKET, Key=key)
        response = client.get_object(Bucket=batch.BUCKET, Key=key)
        content = response["Body"].read(len(raw) + 1)
    except Exception:
        raise GateError("FINAL_READ_ONLY_TARGET_READ_FAILED") from None
    if head.get("ContentLength") != len(raw):
        raise GateError("FINAL_READ_ONLY_SIZE_MISMATCH")
    if len(content) != len(raw) or hashlib.sha256(content).digest() != hashlib.sha256(raw).digest():
        raise GateError("FINAL_READ_ONLY_SHA256_MISMATCH")
    verify_properties(properties, head)
    return len(raw)


def run():
    start = time.monotonic()
    state = started_state()
    save(state)
    try:
        token = os.environ.get("CLOUDFLARE_API_TOKEN", "")
        if not token or os.environ.get("CLOUDFLARE_ACCOUNT_ID") != batch.SOURCE_ACCOUNT:
            raise GateError("SOURCE_CREDENTIAL_NOT_READY")
        check_source_budget(token)
        eligible_remaining = None

        for _ in range(MAX_BATCHES):
            if not time_ok(start):
                state["stop_reason"] = "WALLCLOCK_BUDGET"
                break
            audit = batch.run("audit")
            eligible_remaining = audit["eligible_missing_count"]
            state["last_audit"] = {
                "source_inventory_count": audit["source_inventory_count"],
                "target_inventory_count": audit["target_inventory_count_before"],
                "missing_count": audit["missing_before"],
                "eligible_missing_count": eligible_remaining,
                "skipped_large_count": audit["skipped_large_count"],
                "skipped_metadata_count": audit["skipped_metadata_count"],
            }
            save(state)
            if eligible_remaining == 0:
                state["stop_reason"] = "NO_SMALL_MISSING"
                break
            if state["uploaded_bytes"] + audit["planned_bytes"] > MAX_UPLOADED_BYTES:
                state["stop_reason"] = "BYTE_BUDGET"
                break

            result = batch.run("batch")
            if result.get("result") != "BOUNDED_BATCH_VERIFIED" or result.get("verified_count", 0) == 0:
                raise GateError("BATCH_NOT_VERIFIED")
            state["batch_count"] += 1
            state["uploaded_count"] += result["uploaded_count"]
            state["uploaded_bytes"] += result["verified_bytes"]
            state["existing_verified_in_batch"] += result["already_present_verified_count"]
            state["last_batch"] = {
                "verified_count": result["verified_count"],
                "uploaded_count": result["uploaded_count"],
                "verified_bytes": result["verified_bytes"],
                "missing_after_snapshot": result["missing_after_snapshot"],
            }
            save(state)
        else:
            state["stop_reason"] = "BATCH_COUNT_LIMIT"

        # Read-only reconciliation after all bounded writes.
        if not time_ok(start):
            state["stop_reason"] = "WALLCLOCK_BUDGET"
            state["status"] = "PARTIAL_VERIFIED"
            save(state)
            return state

        final = batch.run("audit")
        state["last_audit"] = {
            "source_inventory_count": final["source_inventory_count"],
            "target_inventory_count": final["target_inventory_count_before"],
            "missing_count": final["missing_before"],
            "eligible_missing_count": final["eligible_missing_count"],
            "skipped_large_count": final["skipped_large_count"],
            "skipped_metadata_count": final["skipped_metadata_count"],
        }
        save(state)
        if final["eligible_missing_count"] != 0:
            state["status"] = "PARTIAL_VERIFIED"
            state["stop_reason"] = state.get("stop_reason") or "ELIGIBLE_OBJECTS_REMAIN"
            save(state)
            return state

        # Existing target keys were not necessarily verified during earlier
        # batches. Verify all small keys AGAIN without writes for strict proof,
        # subject to the same runtime/byte upper limits.
        client = batch.target_s3()
        source = check_source_budget(token)
        target = batch.target_list(client)
        existing, missing = batch.preflight(source, target)
        final_verified = 0
        final_bytes = 0
        for obj in existing:
            if not time_ok(start):
                state["status"] = "PARTIAL_VERIFIED"
                state["stop_reason"] = "FINAL_VERIFY_TIME_BUDGET"
                save(state)
                return state
            if int(obj["size"]) > batch.MAX_BATCH_BYTES:
                continue
            try:
                source_properties(obj)
            except GateError:
                continue
            if final_bytes + obj["size"] > MAX_UPLOADED_BYTES:
                state["status"] = "PARTIAL_VERIFIED"
                state["stop_reason"] = "FINAL_VERIFY_BYTE_BUDGET"
                save(state)
                return state
            verified_bytes = verify_existing_read_only(client, token, obj)
            final_verified += 1
            final_bytes += verified_bytes
            state["verified_existing_final"] = final_verified
            state["verified_existing_final_bytes"] = final_bytes
            save(state)

        # This is a small-object snapshot only. Oversize objects remain for
        # an explicit multipart/memory-budgeted route. No automatic cutover.
        state["status"] = "SMALL_OBJECTS_VERIFIED"
        state["stop_reason"] = "LARGE_OR_UNSUPPORTED_REMAIN" if missing else "SNAPSHOT_RECHECKED"
        state["remaining_count"] = len(missing)
        state["finished_at_utc"] = utc_now()
        save(state)
        return state
    except Exception as exc:
        state["status"] = "BLOCKED"
        state["reason"] = str(exc) if isinstance(exc, GateError) else "UNEXPECTED_" + type(exc).__name__
        state["finished_at_utc"] = utc_now()
        save(state)
        return state


def main():
    result = run()
    # Print only totals/reasons. Key names and object bodies are excluded.
    print("WP_MEDIA_AUTOPILOT", json.dumps(result, sort_keys=True))
    if result["status"] not in ("SMALL_OBJECTS_VERIFIED", "PARTIAL_VERIFIED"):
        raise SystemExit(3)


if __name__ == "__main__":
    main()
