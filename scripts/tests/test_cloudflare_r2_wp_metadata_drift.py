#!/usr/bin/env python3
"""Offline only. No Cloudflare credentials or network."""
import cloudflare_r2_wp_metadata_drift as audit

objs = [
    {"key": "same", "size": 1, "http_metadata": {"cacheControl": "public, max-age=100"}},
    {"key": "diff", "size": 2, "http_metadata": {"cacheControl": "public, max-age=100"}},
    {"key": "missing", "size": 3},
]
target = {"same": 1, "diff": 2}
heads = {
    "same": {"ContentLength": 1, "CacheControl": "public, max-age=100",
             "Metadata": {}, "StorageClass": "STANDARD"},
    "diff": {"ContentLength": 2, "CacheControl": "max-age=200",
             "Metadata": {}, "StorageClass": "STANDARD"},
}
result = audit.audit(lambda: objs, lambda: target, lambda k: heads[k])
assert result["status"] == "METADATA_MISMATCH_REQUIRES_REVIEW"
assert result["verified_metadata_count"] == 1
assert result["metadata_mismatch_count"] == 1
assert result["missing_count"] == 1
assert result["issues"][0]["fields"] == ["CacheControl"]
assert result["issues"][0]["object_key_sha256"] != "diff"
assert result["sha256_bytes_parity_verified"] is False
assert result["source_deleted"] is False and result["target_overwritten"] is False
print("PASS read-only CacheControl drift hashed key, missing-count no-cutover")

all_good = audit.audit(lambda: [objs[0]], lambda: {"same": 1}, lambda k: heads[k])
assert all_good["status"] == "METADATA_SNAPSHOT_MATCH_ONLY"
assert all_good["verified_metadata_count"] == 1
assert all_good["sha256_bytes_parity_verified"] is False
print("PASS metadata-only audit never claims payload SHA parity")

def fail_head(_):
    raise ValueError("pretend network broke")
try:
    audit.audit(lambda: [objs[0]], lambda: {"same": 1}, fail_head)
    raise AssertionError("missing HEAD should fail")
except audit.GateError as exc:
    assert str(exc) == "METADATA_TARGET_HEAD_FAILED"
print("PASS unreadable HEAD fails closed")
