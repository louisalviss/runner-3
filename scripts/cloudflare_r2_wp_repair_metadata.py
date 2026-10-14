#!/usr/bin/env python3
"""Fail-closed, one-object R2 metadata repair.

The ONLY permitted mutation is a conditional in-place S3 CopyObject for the
previously SHA-verified 14-byte WP canary, replacing metadata with the source
account's metadata. The source R2 object remains the rollback authority.
No source mutations, no DELETE, no unguarded PutObject. No raw keys in output.

No writes occur with --mode preflight. --mode repair requires an independently
user-initiated GitHub workflow, and succeeds only with all guards.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path

from botocore.exceptions import ClientError
import cloudflare_r2_native_batch as batch
from cloudflare_r2_native_canary import (
    GateError, source_list, source_bytes, source_properties, verify_properties,
)
from cloudflare_r2_wp_metadata_drift import metadata_diff

KEY_HASH = "9be9cf6df328bac92b6ca3391cb7ffa61765ed5d5ec52b7c08d9848b13695a16"
EXPECTED_SHA = "888bf708bab0b4b52d6e23c2974ec4f6ec8866e421a44da25683f815afa5755b"
EXPECTED_BYTES = 14
MAX_SOURCE_ITEMS = 500
MAX_SOURCE_BYTES = 300_000_000
BUCKET = batch.BUCKET
OUT = Path("migration-out/wp-metadata-repair.json")


def get_exact_source_object(token):
    items = source_list(token, BUCKET)
    if len(items) > MAX_SOURCE_ITEMS or sum(
        int(obj.get("size") or 0) for obj in items
    ) > MAX_SOURCE_BYTES:
        raise GateError("REPAIR_SOURCE_INVENTORY_BUDGET")
    matches = [obj for obj in items if hashlib.sha256(
        obj["key"].encode("utf-8")).hexdigest() == KEY_HASH]
    if len(matches) != 1 or matches[0].get("size") != EXPECTED_BYTES:
        raise GateError("REPAIR_EXACT_CANARY_NOT_FOUND")
    return matches[0], items


def target_head(client, key):
    try:
        h = client.head_object(Bucket=BUCKET, Key=key)
    except Exception:
        raise GateError("REPAIR_TARGET_HEAD_FAILED") from None
    if h.get("ContentLength") != EXPECTED_BYTES:
        raise GateError("REPAIR_TARGET_SIZE_CHANGED")
    if not isinstance(h.get("ETag"), str) or not h["ETag"]:
        raise GateError("REPAIR_TARGET_ETAG_MISSING")
    return h


def get_target_bytes(client, key):
    try:
        response = client.get_object(Bucket=BUCKET, Key=key)
        body = response["Body"]
        try:
            raw = body.read(EXPECTED_BYTES + 1)
        finally:
            if hasattr(body, "close"):
                body.close()
    except Exception:
        raise GateError("REPAIR_TARGET_GET_FAILED") from None
    if len(raw) != EXPECTED_BYTES:
        raise GateError("REPAIR_TARGET_BYTES_CHANGED")
    return raw


def prepare(client, token):
    obj, source_items = get_exact_source_object(token)
    key = obj["key"]
    sizes = batch.target_list(client)
    existing, _ = batch.preflight(source_items, sizes)
    if obj not in existing:
        raise GateError("REPAIR_TARGET_CANARY_MISSING")
    expected = source_properties(obj)
    head = target_head(client, key)
    if metadata_diff(expected, head) != ["CacheControl"]:
        raise GateError("REPAIR_DRIFT_NOT_EXACT_CACHECONTROL")
    raw_source = source_bytes(token, BUCKET, obj)
    raw_target = get_target_bytes(client, key)
    sh_src = hashlib.sha256(raw_source).hexdigest()
    sh_dest = hashlib.sha256(raw_target).hexdigest()
    if sh_src != EXPECTED_SHA or sh_dest != EXPECTED_SHA:
        raise GateError("REPAIR_PAYLOAD_SHA_CHANGED")
    return {
        "obj": obj, "items": source_items, "sizes": sizes,
        "key": key, "expected": expected, "head": head,
    }


def check_same_head(left, right):
    # Compare both metadata and object concurrency signals. A change in
    # CacheControl before the write means a separate actor touched the key.
    for field in (
        "ETag", "LastModified", "ContentLength", "Metadata", "CacheControl",
        "ContentType", "ContentDisposition", "ContentEncoding",
        "ContentLanguage", "Expires", "StorageClass"
    ):
        if left.get(field) != right.get(field):
            raise GateError("REPAIR_CONCURRENT_CHANGE")


def conditional_metadata_copy(client, key, expected, etag):
    if not isinstance(etag, str) or not etag:
        raise GateError("REPAIR_MISSING_DESTINATION_ETAG")
    applied = {"seen": False}

    def require_original_destination(request, **kwargs):
        # R2 extension: the destination ETag must still be the value
        # from the last read. We never fall back to an unconditional copy.
        request.headers["cf-copy-destination-if-match"] = etag
        applied["seen"] = True

    event = "before-sign.s3.CopyObject"
    client.meta.events.register(event, require_original_destination)
    try:
        args = {
            "Bucket": BUCKET,
            "Key": key,
            "CopySource": {"Bucket": BUCKET, "Key": key},
            "CopySourceIfMatch": etag,
            "MetadataDirective": "REPLACE",
        }
        args.update(expected)
        client.copy_object(**args)
        if not applied["seen"]:
            raise GateError("REPAIR_DESTINATION_CONDITION_NOT_SIGNED")
    except ClientError as exc:
        status = int((exc.response.get("ResponseMetadata") or {}).get("HTTPStatusCode") or 0)
        raise GateError("REPAIR_CONDITIONAL_COPY_HTTP_" + str(status)) from None
    except GateError:
        raise
    except Exception:
        raise GateError("REPAIR_COPY_REJECTED") from None
    finally:
        client.meta.events.unregister(event, require_original_destination)


def run(mode, client, token):
    if mode not in ("preflight", "repair"):
        raise GateError("REPAIR_MODE_NOT_ALLOWED")
    if not token or os.environ.get("CLOUDFLARE_ACCOUNT_ID") != batch.SOURCE_ACCOUNT:
        raise GateError("REPAIR_SOURCE_ACCOUNT_CREDENTIAL_NOT_READY")
    state = prepare(client, token)
    result = {
        "status": "READY_READ_ONLY" if mode == "preflight" else "RUNNING",
        "mode": mode, "bucket": BUCKET, "object_key_sha256": KEY_HASH,
        "expected_sha256": EXPECTED_SHA, "payload_bytes": EXPECTED_BYTES,
        "source_payload_sha256_matches": True,
        "target_payload_sha256_matches": True,
        "metadata_mismatch_fields_before": ["CacheControl"],
        "source_deleted": False, "target_overwritten_unconditionally": False,
        "cutover_ready": False, "full_bucket_parity_verified": False,
        "captured_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
    }
    if mode == "preflight":
        return result

    # Check immutable source and destination keyspace/HEAD once more
    # before the one allowed guarded metadata-only same-key copy.
    source_again = source_list(token, BUCKET)
    if source_again != state["items"]:
        raise GateError("REPAIR_SOURCE_LIST_CHANGED")
    if batch.target_list(client) != state["sizes"]:
        raise GateError("REPAIR_TARGET_LIST_CHANGED")
    check_same_head(state["head"], target_head(client, state["key"]))
    if hashlib.sha256(get_target_bytes(client, state["key"])).hexdigest() != EXPECTED_SHA:
        raise GateError("REPAIR_TARGET_SHA_CHANGED")

    conditional_metadata_copy(
        client, state["key"], state["expected"], state["head"]["ETag"]
    )
    # Source remains authoritative and is never deleted or modified.
    newhead = target_head(client, state["key"])
    verify_properties(state["expected"], newhead)
    if metadata_diff(state["expected"], newhead):
        raise GateError("REPAIR_POST_COPY_METADATA_MISMATCH")
    if hashlib.sha256(get_target_bytes(client, state["key"])).hexdigest() != EXPECTED_SHA:
        raise GateError("REPAIR_POST_COPY_SHA_MISMATCH")
    if source_list(token, BUCKET) != state["items"]:
        raise GateError("REPAIR_SOURCE_CHANGED_AFTER_COPY")
    if batch.target_list(client) != state["sizes"]:
        raise GateError("REPAIR_TARGET_KEYSPACE_CHANGED_AFTER_COPY")
    result["status"] = "ONE_OBJECT_METADATA_REPAIRED_VERIFIED"
    result["metadata_mismatch_fields_after"] = []
    result["one_conditional_copy_executed"] = True
    result["source_authoritative_rollback_retained"] = True
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("preflight", "repair"), required=True)
    args = parser.parse_args()
    result = None
    try:
        token = os.environ.get("CLOUDFLARE_API_TOKEN", "")
        client = batch.target_s3()
        result = run(args.mode, client, token)
    except GateError as exc:
        result = {"status": "BLOCKED", "reason": str(exc),
                  "mode": args.mode, "cutover_ready": False,
                  "source_deleted": False, "repair_completed": False}
    except Exception as exc:
        result = {"status": "BLOCKED", "reason": "UNEXPECTED_" + type(exc).__name__,
                  "mode": args.mode, "cutover_ready": False,
                  "source_deleted": False, "repair_completed": False}
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(result, sort_keys=True, indent=2) + "\n")
    print("WP_METADATA_REPAIR", json.dumps(result, sort_keys=True))
    if result["status"] == "BLOCKED":
        raise SystemExit(3)


if __name__ == "__main__":
    main()
