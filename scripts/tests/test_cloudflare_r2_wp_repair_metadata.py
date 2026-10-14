#!/usr/bin/env python3
"""Synthetic, offline safety tests for exactly-one R2 metadata-only repair.

No real network calls and no Cloudflare credentials are used.
"""
import hashlib
import io
import os
from unittest.mock import patch

import cloudflare_r2_wp_repair_metadata as m

KEY = "canary-14-bytes"
RAW = b"CANARY-TEST-14"
assert len(RAW) == 14
SOURCE = [{
    "key": KEY, "size": len(RAW),
    "http_metadata": {"cacheControl": "public, max-age=90"},
}]
SHA = hashlib.sha256(RAW).hexdigest()


class Events:
    def __init__(self): self.calls = {}
    def register(self, name, fn): self.calls[name] = fn
    def unregister(self, name, fn):
        assert self.calls[name] is fn
        del self.calls[name]


class Client:
    def __init__(self, etag='"orig-etag"', source_mismatch=False):
        self.etag = etag
        self.cachecontrol = "public, max-age=30"
        self.events = Events()
        self.meta = type("Meta", (), {"events": self.events})()
        self.writes = 0
        self.payload = RAW
        self.signed_destination_guard = False
        self.fail_copy = False
        self.changed_metadata_during_recheck = False

    def head_object(self, **kw):
        assert kw == {"Bucket": m.BUCKET, "Key": KEY}
        return {
            "ETag": self.etag,
            "ContentLength": len(RAW), "Metadata": {},
            "CacheControl": self.cachecontrol, "StorageClass": "STANDARD",
        }

    def get_object(self, **kw):
        assert kw == {"Bucket": m.BUCKET, "Key": KEY}
        return {"Body": io.BytesIO(self.payload)}

    def copy_object(self, **kw):
        assert kw["Bucket"] == m.BUCKET and kw["Key"] == KEY
        assert kw["CopySource"] == {"Bucket": m.BUCKET, "Key": KEY}
        assert kw["CopySourceIfMatch"] == self.etag
        assert kw["MetadataDirective"] == "REPLACE"
        assert kw["CacheControl"] == "public, max-age=90"
        req = type("Request", (), {"headers": {}})()
        self.events.calls["before-sign.s3.CopyObject"](req)
        assert req.headers["cf-copy-destination-if-match"] == self.etag
        self.signed_destination_guard = True
        self.writes += 1
        self.cachecontrol = kw["CacheControl"]

    def put_object(self, **kw):
        raise AssertionError("Repair must not call PutObject")

    def delete_object(self, **kw):
        raise AssertionError("Repair must never delete")


def setup(client):
    return (
        patch.object(m, "KEY_HASH", hashlib.sha256(KEY.encode()).hexdigest()),
        patch.object(m, "EXPECTED_SHA", SHA),
        patch.object(m, "source_list", return_value=SOURCE),
        patch.object(m, "source_bytes", return_value=RAW),
        patch.object(m.batch, "target_list", return_value={KEY: 14}),
        patch.dict(os.environ, {"CLOUDFLARE_ACCOUNT_ID": m.batch.SOURCE_ACCOUNT}),
    )


client = Client()
p = setup(client)
with p[0], p[1], p[2], p[3], p[4], p[5]:
    result = m.run("preflight", client, "dummy")
    assert result["status"] == "READY_READ_ONLY"
    assert result["target_payload_sha256_matches"] is True
    assert result["cutover_ready"] is False and result["source_deleted"] is False
    assert client.writes == 0
print("PASS preflight is pure read and validates both payload hashes")


client = Client()
p = setup(client)
with p[0], p[1], p[2], p[3], p[4], p[5]:
    result = m.run("repair", client, "dummy")
    assert result["status"] == "ONE_OBJECT_METADATA_REPAIRED_VERIFIED"
    assert result["metadata_mismatch_fields_after"] == []
    assert result["source_authoritative_rollback_retained"] is True
    assert client.writes == 1 and client.signed_destination_guard
    assert client.cachecontrol == "public, max-age=90"
    assert not client.events.calls
    assert result["cutover_ready"] is False and result["source_deleted"] is False
print("PASS one guarded same-key CopyObject, SHA+metadata readback, no source/delete")


client = Client()
p = setup(client)
with p[0], p[1], p[2], p[3], p[4], p[5]:
    client.payload = b"BROKEN-SHA-14!"
    assert len(client.payload) == 14
    try:
        m.run("repair", client, "dummy")
        raise AssertionError("Mismatched payload cannot be repaired")
    except m.GateError as exc:
        assert str(exc) == "REPAIR_PAYLOAD_SHA_CHANGED"
    assert client.writes == 0
print("PASS source-vs-target payload drift aborts before any write")


client = Client()
p = setup(client)
with p[0], p[1], p[2], p[3], p[4], p[5]:
    with patch.object(m, "check_same_head", side_effect=m.GateError("REPAIR_CONCURRENT_CHANGE")):
        try:
            m.run("repair", client, "dummy")
            raise AssertionError("changed ETag cannot be bypassed")
        except m.GateError as exc:
            assert str(exc) == "REPAIR_CONCURRENT_CHANGE"
        assert client.writes == 0
print("PASS changed destination metadata/ETag fails before CopyObject")


client = Client()
p = setup(client)
with p[0], p[1], p[2], p[3], p[4], p[5]:
    try:
        m.run("not-a-mode", client, "dummy")
        raise AssertionError("unsafe mode should be rejected")
    except m.GateError as exc:
        assert str(exc) == "REPAIR_MODE_NOT_ALLOWED"
    assert client.writes == 0
print("PASS unrecognized mode cannot mutate")
