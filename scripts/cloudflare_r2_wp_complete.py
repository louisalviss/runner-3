#!/usr/bin/env python3
"""One authorized invocation to complete bounded WP Media R2 staging.

Small (<=10MB), medium (10-20MB) and streamed large (20-256MB) objects.
Every write is the existing signed conditional PutObject. No source deletion,
no destination overwrites and NO production cutover. All final object hashes
and metadata are compared read-only before snapshot eligibility is reported.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import tempfile
import time
from pathlib import Path

import cloudflare_r2_native_batch as batch
from cloudflare_r2_native_canary import GateError, source_list, source_properties
from cloudflare_r2_native_large import stream_source, verify_s3_read_only
from cloudflare_r2_wp_autopilot import verify_existing_read_only

OUT = Path("migration-out")
PROGRESS = OUT / "wp-complete-progress.json"
RECEIPT = OUT / "receipt.json"
MAX_SOURCE_BYTES = 300_000_000
MAX_SOURCE_OBJECTS = 500
MAX_UPLOADED_BYTES = 300_000_000
MAX_RECHECK_BYTES = 300_000_000
MAX_OPERATIONS = 50
MAX_SECONDS = 40 * 60
BUCKET = batch.BUCKET


def save(state):
    OUT.mkdir(exist_ok=True)
    for path in (PROGRESS, RECEIPT):
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n")
        tmp.replace(path)


def bounded_source(token):
    result = source_list(token, BUCKET)
    size = sum(int(x.get("size") or 0) for x in result)
    if len(result) > MAX_SOURCE_OBJECTS or size > MAX_SOURCE_BYTES:
        raise GateError("WP_COMPLETE_SOURCE_BUDGET")
    return result, size


def manifest_signature(items):
    # Includes metadata and all known version-sensitive source attributes.
    result = []
    for item in items:
        result.append({
            field: item.get(field) for field in (
                "key", "size", "custom_metadata", "http_metadata",
                "storage_class", "ssec", "uploaded", "etag", "checksums",
            )
        })
    return result


def verify_full_snapshot(client, token, start, state):
    source, source_bytes = bounded_source(token)
    target = batch.target_list(client)
    existing, missing = batch.preflight(source, target)
    if missing or len(existing) != len(source):
        raise GateError("WP_COMPLETE_OBJECTS_MISSING")
    if source_bytes > MAX_RECHECK_BYTES:
        raise GateError("WP_COMPLETE_RECHECK_BYTE_GATE")

    state["verification_stage"] = "READ_ONLY"
    state["read_only_verified_count"] = 0
    save(state)
    checked_bytes = 0
    for obj in existing:
        if time.monotonic() - start >= MAX_SECONDS:
            raise GateError("WP_COMPLETE_VERIFY_TIME_BUDGET")
        if obj["size"] <= batch.MAX_NATIVE_SOURCE_BYTES:
            verified = verify_existing_read_only(client, token, obj)
        else:
            # Never call PUT from parity check. For large objects stream source
            # to a temporary bounded file, then read target HEAD/GET.
            props = source_properties(obj)
            with tempfile.TemporaryFile(mode="w+b") as tmp:
                sha, _ = stream_source(token, obj, tmp)
            verified = verify_s3_read_only(client, obj, sha, props)
        checked_bytes += verified
        state["read_only_verified_count"] += 1
        state["read_only_verified_bytes"] = checked_bytes
        save(state)
    check_source, _ = bounded_source(token)
    check_target = batch.target_list(client)
    if manifest_signature(check_source) != manifest_signature(source):
        raise GateError("WP_COMPLETE_SOURCE_CHANGED_DURING_VERIFY")
    if check_target != target:
        raise GateError("WP_COMPLETE_TARGET_CHANGED_DURING_VERIFY")

    state["verified_snapshot_count"] = len(source)
    state["verified_snapshot_bytes"] = source_bytes
    state["snapshot_keyspace_sha_metadata_parity"] = True
    state["full_bucket_parity_verified"] = False   # live-write delta unknown
    state["cutover_ready"] = False
    state["status"] = "SNAPSHOT_VERIFIED_NOT_CUTOVER"
    state["stop_reason"] = "LIVE_DELTA_AND_RUNTIME_BINDINGS_PENDING"
    save(state)


def main_run():
    start = time.monotonic()
    state = {
        "schema": "wp-r2-native-complete-v1", "mode": "auto-complete",
        "bucket": BUCKET, "status": "RUNNING",
        "small_batches": 0, "medium_objects": 0, "large_objects": 0,
        "uploaded_objects": 0, "uploaded_bytes": 0,
        "source_deleted": False, "overwritten": False,
        "cutover_ready": False, "full_bucket_parity_verified": False,
        "snapshot_keyspace_sha_metadata_parity": False,
        "secret_exposed": False,
        "started_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
    }
    save(state)
    try:
        token = os.environ.get("CLOUDFLARE_API_TOKEN")
        if not token or os.environ.get("CLOUDFLARE_ACCOUNT_ID") != batch.SOURCE_ACCOUNT:
            raise GateError("SOURCE_CREDENTIAL_NOT_READY")
        source, _ = bounded_source(token)
        client = batch.target_s3()
        for _ in range(MAX_OPERATIONS):
            if time.monotonic() - start >= MAX_SECONDS:
                raise GateError("WP_COMPLETE_WALLCLOCK_BUDGET")
            target = batch.target_list(client)
            _, missing = batch.preflight(source, target)
            if not missing:
                break
            small, _ = batch.plan_batch(missing)
            medium, _ = batch.medium_plan(missing)
            large, _ = batch.large_plan(missing)
            if small:
                mode, size = "batch", sum(o["size"] for o in small)
            elif medium:
                mode, size = "medium-one", medium[0]["size"]
            elif large:
                mode, size = "large-one", large[0]["size"]
            else:
                raise GateError("WP_COMPLETE_UNSUPPORTED_MISSING_OBJECTS")
            if state["uploaded_bytes"] + size > MAX_UPLOADED_BYTES:
                raise GateError("WP_COMPLETE_UPLOAD_BYTE_BUDGET")
            result = batch.run(mode)
            code = {
                "batch": "BOUNDED_BATCH_VERIFIED",
                "medium-one": "BOUNDED_MEDIUM_VERIFIED",
                "large-one": "BOUNDED_LARGE_VERIFIED",
            }[mode]
            if result.get("result") != code or result.get("verified_count", 0) < 1:
                raise GateError("WP_COMPLETE_BATCH_FAILED")
            if mode == "batch":
                state["small_batches"] += 1
            elif mode == "medium-one":
                state["medium_objects"] += 1
            else:
                state["large_objects"] += 1
            state["uploaded_objects"] += result["uploaded_count"]
            state["uploaded_bytes"] += result["verified_bytes"]
            state["last_missing_count"] = result["missing_after_snapshot"]
            save(state)
            # Detect source delta before writing more; never remove old source.
            changed, _ = bounded_source(token)
            if manifest_signature(changed) != manifest_signature(source):
                raise GateError("WP_COMPLETE_SOURCE_CHANGED_DURING_UPLOAD")
        else:
            raise GateError("WP_COMPLETE_OPERATION_COUNT_BUDGET")
        verify_full_snapshot(client, token, start, state)
        state["finished_at_utc"] = dt.datetime.now(dt.timezone.utc).isoformat()
        save(state)
    except Exception as exc:
        state["status"] = "BLOCKED"
        state["reason"] = str(exc) if isinstance(exc, GateError) else "UNEXPECTED_" + type(exc).__name__
        state["finished_at_utc"] = dt.datetime.now(dt.timezone.utc).isoformat()
        save(state)
    return state


def main():
    result = main_run()
    # Print sanitized totals only, never object names, API headers or secrets.
    print("WP_R2_COMPLETE", json.dumps(result, sort_keys=True))
    if result["status"] != "SNAPSHOT_VERIFIED_NOT_CUTOVER":
        raise SystemExit(3)


if __name__ == "__main__":
    main()
