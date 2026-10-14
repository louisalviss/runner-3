#!/usr/bin/env python3
"""Only fake source and target clients; all read-only targeted SHA contracts."""
import hashlib
from unittest.mock import patch

import cloudflare_r2_wp_targeted_sha as m

KEY = "canary-wp-cachecontrol"
META = {"cacheControl": "public, max-age=60"}
TARGET_META = "public, max-age=120"
OBJECT = {"key": KEY, "size": 4, "http_metadata": META}
SRC = [OBJECT, {"key": "medium-missing", "size": 12_000_000},
       {"key": "large-missing", "size": 32_000_000}]
TARGET = {KEY: 4}
HEAD = {"ContentLength": 4, "CacheControl": TARGET_META,
        "Metadata": {}, "StorageClass": "STANDARD", "ETag": "a",
        "LastModified": None}
SHA = hashlib.sha256(b"same").hexdigest()


def call(*, equal=True, after=None, reread=None):
    heads = iter([HEAD, HEAD if after is None else after])
    return m.diagnose(
        source_items=SRC, target_sizes=TARGET,
        head_fn=lambda _: next(heads),
        src_hash_fn=lambda _: (SHA, 4),
        dest_hash_fn=lambda _: (SHA if equal else hashlib.sha256(b"diff").hexdigest(), 4),
        source_recheck_fn=lambda: SRC if reread is None else reread,
        target_recheck_fn=lambda: TARGET,
    )


with patch.object(m, "KEY_HASH", hashlib.sha256(KEY.encode()).hexdigest()):
    result = call()
    assert result["status"] == "PAYLOAD_MATCH_METADATA_DRIFT"
    assert result["sha256_equal"]
    assert result["differing_metadata_fields"] == ["CacheControl"]
    assert result["missing_count"] == 2
    assert result["missing_size_bands"]["medium_10_to_20mb"]["count"] == 1
    assert result["missing_size_bands"]["large_20_to_256mb"]["count"] == 1
    assert result["source_deleted"] is False and result["target_overwritten"] is False
    assert result["cutover_ready"] is False and result["full_bucket_parity_verified"] is False
    assert KEY not in str(result)
    print("PASS targeted read-only exact object SHA equality and size bands")

    mismatch = call(equal=False)
    assert mismatch["status"] == "PAYLOAD_MISMATCH_AND_METADATA_DRIFT"
    assert mismatch["sha256_equal"] is False
    print("PASS differing payload digest never marked parity")

    drifted = dict(HEAD, ETag="changed")
    try:
        call(after=drifted)
        raise AssertionError("changed target must abort")
    except m.GateError as exc:
        assert str(exc) == "TARGETED_SHA_TARGET_CHANGED_DURING_READ"
    print("PASS changing target HEAD during read fails closed")

    changed_src = [{**OBJECT, "size": 5}, *SRC[1:]]
    try:
        call(reread=changed_src)
        raise AssertionError("changed source must abort")
    except m.GateError as exc:
        assert str(exc) == "TARGETED_SHA_SOURCE_CHANGED_DURING_READ"
    print("PASS changing source manifest during read fails closed")

    with patch.object(m, "KEY_HASH", "f" * 64):
        try:
            call()
            raise AssertionError("unmatched selector must abort")
        except m.GateError as exc:
            assert str(exc) == "TARGETED_SHA_EXACT_OBJECT_NOT_FOUND"
    print("PASS exact hashed selector cannot guess objects")


class ReadBody:
    def __init__(self, raw):
        self.raw = raw
        self.pos = 0
        self.closed = False

    def read(self, count):
        data = self.raw[self.pos:self.pos + count]
        self.pos += len(data)
        return data

    def close(self):
        self.closed = True


class ReadOnlyClient:
    def __init__(self, raw):
        self.body = ReadBody(raw)
    def get_object(self, **kwargs):
        assert kwargs["Key"] == KEY
        return {"Body": self.body}
    def put_object(self, **_):
        raise AssertionError("read-only workflow must not PUT")
    def delete_object(self, **_):
        raise AssertionError("read-only workflow must not DELETE")


client = ReadOnlyClient(b"same")
hashed, size = m.target_sha(client, OBJECT)
assert hashed == SHA and size == 4 and client.body.closed
print("PASS streamed target SHA from GET with no mutation")

try:
    m.target_sha(ReadOnlyClient(b"longer"), OBJECT)
    raise AssertionError("size overflow must stop")
except m.GateError as exc:
    assert str(exc) == "TARGETED_SHA_TARGET_SIZE_OVERFLOW"
print("PASS target stream overflow blocks")
