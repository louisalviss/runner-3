#!/usr/bin/env python3
"""Read-only source LIST vs target S3 HEAD metadata diagnosis for WP R2.

No PUT, POST, DELETE, credential printing, user object keys or payload reads.
This is a metadata diagnostic only: no key SHA/bytes parity is claimed.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
from pathlib import Path

import cloudflare_r2_native_batch as batch
from cloudflare_r2_native_canary import GateError, source_list, source_properties, verify_properties

MAX_OBJECTS = 500
MAX_BYTES = 300_000_000
MAX_ISSUE_DETAIL = 30
OUT = Path("migration-out/wp-metadata-drift.json")
CHECK_NAMES = (
    "ContentType", "ContentEncoding", "ContentLanguage",
    "ContentDisposition", "CacheControl", "Expires", "StorageClass",
)


def metadata_diff(expected, head):
    """Only classify fields, never include raw source/destination header values."""
    mismatches = []
    for field in CHECK_NAMES:
        left = expected.get(field)
        right = head.get(field)
        if field == "StorageClass":
            right = right or "STANDARD"
        if field == "Expires":
            if left is not None and (
                right is None or
                not hasattr(right, "timestamp") or
                int(right.timestamp()) != int(left.timestamp())
            ):
                mismatches.append(field)
        elif left is not None and str(left) != str(right or ""):
            mismatches.append(field)
    if head.get("Metadata") is None and expected.get("Metadata"):
        mismatches.append("CustomMetadata")
    elif isinstance(head.get("Metadata"), dict) and head.get("Metadata") != expected.get("Metadata"):
        mismatches.append("CustomMetadata")
    if not mismatches:
        try:
            verify_properties(expected, head)
        except GateError:
            mismatches.append("UnclassifiedMetadata")
    return sorted(set(mismatches))


def audit(reader, target, head):
    source = reader()
    if len(source) > MAX_OBJECTS or sum(int(o.get("size") or 0) for o in source) > MAX_BYTES:
        raise GateError("METADATA_AUDIT_SOURCE_BUDGET")
    target_sizes = target()
    existing, missing = batch.preflight(source, target_sizes)
    result = {
        "schema": "wp-r2-readonly-metadata-drift-v1",
        "source_count": len(source),
        "target_count": len(target_sizes),
        "existing_key_count": len(existing),
        "missing_count": len(missing),
        "verified_metadata_count": 0,
        "metadata_mismatch_count": 0,
        "unsupported_metadata_count": 0,
        "issues": [],
        "truncated_issues": False,
        "source_deleted": False,
        "target_overwritten": False,
        "cutover_ready": False,
        "sha256_bytes_parity_verified": False,
        "captured_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
    }
    for obj in existing:
        digest = hashlib.sha256(obj["key"].encode()).hexdigest()
        try:
            expected = source_properties(obj)
        except GateError:
            result["unsupported_metadata_count"] += 1
            fields = ["UnsupportedSourceMetadata"]
        else:
            try:
                h = head(obj["key"])
            except Exception:
                raise GateError("METADATA_TARGET_HEAD_FAILED") from None
            if not isinstance(h, dict):
                raise GateError("METADATA_TARGET_HEAD_INVALID")
            if h.get("ContentLength") != obj["size"]:
                fields = ["ContentLength"]
            else:
                fields = metadata_diff(expected, h)
            if not fields:
                result["verified_metadata_count"] += 1
                continue
        result["metadata_mismatch_count"] += 1
        if len(result["issues"]) < MAX_ISSUE_DETAIL:
            result["issues"].append({
                "object_key_sha256": digest,
                "fields": fields,
            })
        else:
            result["truncated_issues"] = True
    result["status"] = (
        "METADATA_MISMATCH_REQUIRES_REVIEW"
        if result["metadata_mismatch_count"] or result["missing_count"]
        else "METADATA_SNAPSHOT_MATCH_ONLY"
    )
    return result


def main():
    token = os.environ.get("CLOUDFLARE_API_TOKEN")
    if not token or os.environ.get("CLOUDFLARE_ACCOUNT_ID") != batch.SOURCE_ACCOUNT:
        raise SystemExit("SOURCE_ACCOUNT_CREDENTIAL_NOT_READY")
    client = batch.target_s3()
    try:
        result = audit(
            reader=lambda: source_list(token, batch.BUCKET),
            target=lambda: batch.target_list(client),
            head=lambda k: client.head_object(Bucket=batch.BUCKET, Key=k),
        )
    except GateError as exc:
        print("METADATA_AUDIT_BLOCKED", str(exc))
        raise SystemExit(3) from None
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print("WP_METADATA_AUDIT", json.dumps({
        "status": result["status"], "source_count": result["source_count"],
        "target_count": result["target_count"],
        "missing_count": result["missing_count"],
        "metadata_mismatch_count": result["metadata_mismatch_count"],
        "verified_metadata_count": result["verified_metadata_count"],
        "cutover_ready": False,
    }, sort_keys=True))


if __name__ == "__main__":
    main()
