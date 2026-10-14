#!/usr/bin/env python3
"""Read-only SHA-256 comparison for the ONE WP Media CacheControl drift object.

The key is selected from the authenticated Cloudflare source listing by its
SHA256 identifier, not by exposing the key or guessing its name.
Reads only GET/HEAD/list. Does not write to either R2 account.
Also reports count/bytes in size bands for remaining missing objects.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import tempfile
from pathlib import Path

import cloudflare_r2_native_batch as batch
from cloudflare_r2_native_canary import (
    GateError, source_bytes, source_list, source_properties,
)
from cloudflare_r2_native_large import stream_source, MAX_BYTES as MAX_STREAM_BYTES
from cloudflare_r2_wp_metadata_drift import metadata_diff

KEY_HASH = "9be9cf6df328bac92b6ca3391cb7ffa61765ed5d5ec52b7c08d9848b13695a16"
MAX_OBJECTS = 500
MAX_SOURCE_TOTAL_BYTES = 300_000_000
CHUNK_BYTES = 1_048_576
OUT = Path("migration-out/wp-targeted-sha.json")


def fingerprint(objects):
    """Detect changed object metadata without exposing any key or header."""
    fields = ("key", "size", "etag", "uploaded", "checksums",
              "storage_class", "custom_metadata", "http_metadata", "ssec")
    selected = [{f: obj.get(f) for f in fields} for obj in objects]
    return hashlib.sha256(json.dumps(
        selected, ensure_ascii=True, sort_keys=True, default=str,
        separators=(",", ":")).encode()).hexdigest()


def check_source(objects):
    if len(objects) > MAX_OBJECTS:
        raise GateError("TARGETED_SHA_SOURCE_COUNT_BUDGET")
    total = sum(int(o.get("size") or 0) for o in objects)
    if total > MAX_SOURCE_TOTAL_BYTES:
        raise GateError("TARGETED_SHA_SOURCE_BYTE_BUDGET")
    found = [x for x in objects if hashlib.sha256(
        x["key"].encode("utf-8")).hexdigest() == KEY_HASH]
    if len(found) != 1:
        raise GateError("TARGETED_SHA_EXACT_OBJECT_NOT_FOUND")
    if not isinstance(found[0].get("size"), int):
        raise GateError("TARGETED_SHA_SOURCE_OBJECT_SIZE_INVALID")
    if not 0 <= found[0]["size"] <= MAX_STREAM_BYTES:
        raise GateError("TARGETED_SHA_OBJECT_TOO_LARGE")
    return found[0]


def missing_bands(missing):
    bands = {
        "small_0_to_10mb": {"count": 0, "bytes": 0},
        "medium_10_to_20mb": {"count": 0, "bytes": 0},
        "large_20_to_256mb": {"count": 0, "bytes": 0},
        "over_256mb": {"count": 0, "bytes": 0},
    }
    for obj in missing:
        size = obj["size"]
        if size <= batch.MAX_BATCH_BYTES:
            tag = "small_0_to_10mb"
        elif size <= batch.MAX_NATIVE_SOURCE_BYTES:
            tag = "medium_10_to_20mb"
        elif size <= MAX_STREAM_BYTES:
            tag = "large_20_to_256mb"
        else:
            tag = "over_256mb"
        bands[tag]["count"] += 1
        bands[tag]["bytes"] += size
    return bands


def source_sha(token, obj):
    if obj["size"] <= batch.MAX_NATIVE_SOURCE_BYTES:
        body = source_bytes(token, batch.BUCKET, obj)
        return hashlib.sha256(body).hexdigest(), len(body)
    with tempfile.TemporaryFile(mode="w+b") as temp:
        sha, _ = stream_source(token, obj, temp)
    return sha, obj["size"]


def target_sha(client, obj):
    """Stream target bytes; never use multipart, update metadata, or PUT."""
    key, expected_size = obj["key"], obj["size"]
    try:
        res = client.get_object(Bucket=batch.BUCKET, Key=key)
    except Exception:
        raise GateError("TARGETED_SHA_TARGET_GET_FAILED") from None
    size = 0
    digest = hashlib.sha256()
    body = res["Body"]
    try:
        while True:
            block = body.read(CHUNK_BYTES)
            if not block:
                break
            size += len(block)
            if size > expected_size:
                raise GateError("TARGETED_SHA_TARGET_SIZE_OVERFLOW")
            digest.update(block)
    except GateError:
        raise
    except Exception:
        raise GateError("TARGETED_SHA_TARGET_STREAM_FAILED") from None
    finally:
        if hasattr(body, "close"):
            body.close()
    if size != expected_size:
        raise GateError("TARGETED_SHA_TARGET_SIZE_MISMATCH")
    return digest.hexdigest(), size


def diagnose(source_items, target_sizes, head_fn, src_hash_fn, dest_hash_fn,
             source_recheck_fn, target_recheck_fn):
    candidate = check_source(source_items)
    existing, missing = batch.preflight(source_items, target_sizes)
    if candidate not in existing:
        raise GateError("TARGETED_SHA_TARGET_OBJECT_MISSING")
    props = source_properties(candidate)
    try:
        before = head_fn(candidate["key"])
    except Exception:
        raise GateError("TARGETED_SHA_TARGET_HEAD_FAILED") from None
    if before.get("ContentLength") != candidate["size"]:
        raise GateError("TARGETED_SHA_TARGET_HEAD_SIZE_DRIFT")
    differing = metadata_diff(props, before)
    if differing != ["CacheControl"]:
        raise GateError("TARGETED_SHA_METADATA_DRIFT_CHANGED")

    sh_src, count_src = src_hash_fn(candidate)
    sh_dest, count_dest = dest_hash_fn(candidate)
    if count_src != candidate["size"] or count_dest != candidate["size"]:
        raise GateError("TARGETED_SHA_READ_SIZE_DRIFT")

    try:
        after = head_fn(candidate["key"])
    except Exception:
        raise GateError("TARGETED_SHA_TARGET_HEAD_RECHECK_FAILED") from None
    if (before.get("ETag") != after.get("ETag")
            or before.get("LastModified") != after.get("LastModified")
            or before.get("ContentLength") != after.get("ContentLength")
            or metadata_diff(props, after) != ["CacheControl"]):
        raise GateError("TARGETED_SHA_TARGET_CHANGED_DURING_READ")
    if fingerprint(source_recheck_fn()) != fingerprint(source_items):
        raise GateError("TARGETED_SHA_SOURCE_CHANGED_DURING_READ")
    if target_recheck_fn() != target_sizes:
        raise GateError("TARGETED_SHA_KEYSPACE_CHANGED_DURING_READ")

    return {
        "schema": "wp-r2-targeted-sha-readonly-v1",
        "status": "PAYLOAD_MATCH_METADATA_DRIFT" if sh_src == sh_dest else "PAYLOAD_MISMATCH_AND_METADATA_DRIFT",
        "object_key_sha256": KEY_HASH,
        "source_sha256": sh_src,
        "target_sha256": sh_dest,
        "sha256_equal": sh_src == sh_dest,
        "readback_bytes": count_dest,
        "differing_metadata_fields": differing,
        "source_inventory_count": len(source_items),
        "target_inventory_count": len(target_sizes),
        "missing_count": len(missing),
        "missing_size_bands": missing_bands(missing),
        "source_deleted": False,
        "target_overwritten": False,
        "cutover_ready": False,
        "full_bucket_parity_verified": False,
        "captured_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
    }


def main():
    token = os.environ.get("CLOUDFLARE_API_TOKEN")
    if not token or os.environ.get("CLOUDFLARE_ACCOUNT_ID") != batch.SOURCE_ACCOUNT:
        raise SystemExit("TARGETED_SHA_SOURCE_CREDENTIAL_UNAVAILABLE")
    try:
        client = batch.target_s3()
        result = diagnose(
            source_items=source_list(token, batch.BUCKET),
            target_sizes=batch.target_list(client),
            head_fn=lambda key: client.head_object(Bucket=batch.BUCKET, Key=key),
            src_hash_fn=lambda obj: source_sha(token, obj),
            dest_hash_fn=lambda obj: target_sha(client, obj),
            source_recheck_fn=lambda: source_list(token, batch.BUCKET),
            target_recheck_fn=lambda: batch.target_list(client),
        )
    except GateError as exc:
        result = {"status": "BLOCKED", "reason": str(exc),
                  "source_deleted": False, "target_overwritten": False,
                  "cutover_ready": False}
    except Exception as exc:
        result = {"status": "BLOCKED", "reason": "UNEXPECTED_" + type(exc).__name__,
                  "source_deleted": False, "target_overwritten": False,
                  "cutover_ready": False}
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(result, sort_keys=True, indent=2) + "\n")
    print("WP_TARGETED_SHA", json.dumps(result, sort_keys=True))
    if result["status"] == "BLOCKED":
        raise SystemExit(3)


if __name__ == "__main__":
    main()
