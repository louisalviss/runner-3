#!/usr/bin/env python3
"""Bounded, fail-closed Cloudflare R2 source REST -> target native S3 copy.

Only the explicitly allowlisted WordPress media bucket. No source mutation,
no overwrite, no credentials or object keys in logs/receipts.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
from pathlib import Path

import boto3
from botocore.client import Config
from botocore.exceptions import ClientError

from cloudflare_r2_native_canary import (
    SOURCE_ACCOUNT, TARGET_ACCOUNT, GateError, source_list, source_properties,
    copy_one,
)

BUCKET = "runner3-wp-media"
MAX_BATCH_OBJECTS = 5
MAX_BATCH_BYTES = 10_000_000
MAX_TARGET_PAGES = 32
MAX_MANIFEST_ITEMS = 50_000


def target_s3():
    access = os.environ.get("CLOUDFLARE_TARGET_R2_ACCESS_KEY_ID", "")
    secret = os.environ.get("CLOUDFLARE_TARGET_R2_SECRET_ACCESS_KEY", "")
    if not access or not secret:
        raise GateError("TARGET_S3_CREDENTIAL_NOT_READY")
    return boto3.client(
        "s3",
        endpoint_url="https://" + TARGET_ACCOUNT + ".r2.cloudflarestorage.com",
        region_name="auto",
        aws_access_key_id=access, aws_secret_access_key=secret,
        config=Config(signature_version="s3v4", s3={"addressing_style": "path"},
                      retries={"mode": "standard", "max_attempts": 2},
                      connect_timeout=15, read_timeout=75),
    )


def target_list(client):
    items = {}
    cursor = None
    seen = set()
    for _ in range(MAX_TARGET_PAGES):
        args = {"Bucket": BUCKET, "MaxKeys": 1000}
        if cursor:
            args["ContinuationToken"] = cursor
        try:
            response = client.list_objects_v2(**args)
        except Exception:
            raise GateError("TARGET_LIST_FAILED") from None
        for obj in response.get("Contents") or []:
            key = obj.get("Key")
            size = obj.get("Size")
            if not isinstance(key, str) or not key or key in items or (
                not isinstance(size, int) or size < 0
            ):
                raise GateError("TARGET_MANIFEST_INVALID")
            items[key] = size
        if len(items) > MAX_MANIFEST_ITEMS:
            raise GateError("TARGET_MANIFEST_ITEM_LIMIT")
        if not response.get("IsTruncated"):
            return items
        next_cursor = response.get("NextContinuationToken")
        if not isinstance(next_cursor, str) or not next_cursor or next_cursor in seen:
            raise GateError("TARGET_CURSOR_INVALID")
        seen.add(next_cursor)
        cursor = next_cursor
    raise GateError("TARGET_PAGE_LIMIT")


def preflight(src, target):
    if len(src) > MAX_MANIFEST_ITEMS:
        raise GateError("SOURCE_MANIFEST_ITEM_LIMIT")
    source_sizes = {obj["key"]: obj.get("size") for obj in src}
    if len(source_sizes) != len(src):
        raise GateError("SOURCE_MANIFEST_DUPLICATE")
    if any(not isinstance(size, int) or size < 0 for size in source_sizes.values()):
        raise GateError("SOURCE_SIZE_INVALID")
    existing = [obj for obj in src if obj["key"] in target]
    drift = [obj for obj in existing if obj["size"] != target[obj["key"]]]
    missing = [obj for obj in src if obj["key"] not in target]
    target_extras = [key for key in target if key not in source_sizes]
    if drift:
        # Never silently accept or overwrite a different-sized destination.
        raise GateError("TARGET_EXISTING_SIZE_DRIFT_ABORT")
    if target_extras:
        raise GateError("TARGET_UNEXPECTED_KEYS_ABORT")
    return existing, missing


def plan_batch(missing):
    eligible = []
    skipped_large = 0
    skipped_metadata = 0
    for obj in missing:
        size = obj["size"]
        if size > MAX_BATCH_BYTES:
            skipped_large += 1
            continue
        try:
            source_properties(obj)
        except GateError:
            skipped_metadata += 1
            continue
        eligible.append(obj)
    eligible.sort(key=lambda obj: (obj["size"], obj["key"]))
    batch = []
    total_bytes = 0
    for obj in eligible:
        if len(batch) >= MAX_BATCH_OBJECTS:
            break
        if total_bytes + obj["size"] > MAX_BATCH_BYTES:
            continue
        batch.append(obj)
        total_bytes += obj["size"]
    return batch, {
        "eligible_missing_count": len(eligible),
        "skipped_large_count": skipped_large,
        "skipped_metadata_count": skipped_metadata,
        "planned_count": len(batch),
        "planned_bytes": total_bytes,
    }


def run(mode):
    if mode not in ("audit", "batch"):
        raise GateError("MODE_NOT_ALLOWED")
    source_token = os.environ.get("CLOUDFLARE_API_TOKEN", "")
    if not source_token or os.environ.get("CLOUDFLARE_ACCOUNT_ID") != SOURCE_ACCOUNT:
        raise GateError("SOURCE_CREDENTIAL_NOT_READY")
    client = target_s3()
    src = source_list(source_token, BUCKET)
    target = target_list(client)
    existing, missing = preflight(src, target)
    planned, details = plan_batch(missing)
    receipt = {
        "status": "PASS", "mode": mode, "bucket": BUCKET,
        "source_inventory_count": len(src), "target_inventory_count_before": len(target),
        "existing_unverified_count": len(existing), "missing_before": len(missing),
        "source_inventory_bytes": sum(obj["size"] for obj in src),
        "source_deleted": False, "overwritten": False,
        "cutover_ready": False, "full_bucket_parity_verified": False,
        "credential_values_exposed": False,
        "time_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        **details,
    }
    if mode == "audit":
        receipt["result"] = "READ_ONLY_AUDIT"
        return receipt
    if not planned:
        # Nothing to upload does NOT mean parity: existing keys may be corrupt,
        # or objects may require a multipart/Unicode metadata route.
        receipt["result"] = "NO_ELIGIBLE_BATCH_OBJECTS"
        return receipt
    verified = []
    for obj in planned:
        verified.append(copy_one(client, source_token, BUCKET, obj))
    # Independently re-list destination and ensure all touched keys exist.
    after = target_list(client)
    for obj in planned:
        if obj["key"] not in after or after[obj["key"]] != obj["size"]:
            raise GateError("TARGET_POST_BATCH_LIST_MISMATCH")
    receipt.update({
        "result": "BOUNDED_BATCH_VERIFIED",
        "verified_count": len(verified),
        "uploaded_count": sum(item["uploaded"] for item in verified),
        "already_present_verified_count": sum(not item["uploaded"] for item in verified),
        "verified_bytes": sum(item["object_bytes"] for item in verified),
        "target_inventory_count_after": len(after),
        "missing_after_snapshot": len([obj for obj in src if obj["key"] not in after]),
        # Full parity remains false until every existing/remaining key is
        # compared by SHA + metadata, and final live-write delta is reconciled.
    })
    return receipt


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("audit", "batch"), required=True)
    args = parser.parse_args()
    try:
        receipt = run(args.mode)
        dest = Path("migration-out")
        dest.mkdir(exist_ok=True)
        (dest / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
        print("R2_NATIVE_BATCH_RESULT", json.dumps(receipt, sort_keys=True))
    except GateError as exc:
        print(json.dumps({"status": "BLOCKED", "reason": str(exc),
                          "secret_exposed": False}))
        raise SystemExit(3)
    except Exception as exc:
        print(json.dumps({"status": "BLOCKED",
                          "reason": "UNEXPECTED_" + type(exc).__name__,
                          "secret_exposed": False}))
        raise SystemExit(3)


if __name__ == "__main__":
    main()
