#!/usr/bin/env python3
"""Offline large R2 source-stream / S3 conditional PUT safety contracts."""
import base64
import hashlib
import io
import os
import tempfile
from unittest.mock import patch

import cloudflare_r2_native_large as m

N = m.MIN_BYTES_EXCLUSIVE + 1
DATA = b"A" * N
OBJ = {"key": "private-large", "size": N, "custom_metadata": {"flow": "proof"}}


class FakeResponse:
    status = 200
    def __init__(self, data): self.body = io.BytesIO(data)
    def __enter__(self): return self
    def __exit__(self, *args): self.body.close()
    def read(self, n): return self.body.read(n)


with tempfile.TemporaryFile(mode="w+b") as out, \
     patch.object(m.urllib.request, "urlopen", return_value=FakeResponse(DATA)):
    sha, md5 = m.stream_source("dummy", OBJ, out)
    assert out.read() == DATA
    assert sha == hashlib.sha256(DATA).hexdigest()
    assert md5 == base64.b64encode(hashlib.md5(DATA).digest()).decode()
print("PASS streamed source exact bytes SHA-256/MD5")


with tempfile.TemporaryFile(mode="w+b") as out, \
     patch.object(m.urllib.request, "urlopen", return_value=FakeResponse(DATA + b"!")):
    try:
        m.stream_source("dummy", OBJ, out)
        raise AssertionError("overflow should fail")
    except m.GateError as err:
        assert str(err) == "LARGE_SOURCE_STREAM_OVERFLOW"
print("PASS source streaming overflow fail closed")


class FakeEvents:
    def __init__(self): self.callbacks = {}
    def register(self, event, callback): self.callbacks[event] = callback
    def unregister(self, event, callback):
        assert self.callbacks[event] is callback
        del self.callbacks[event]


class FakeClient:
    def __init__(self, present=False):
        self.present = present
        self.meta = type("Meta", (), {"events": FakeEvents()})()
        self.puts = 0
        self.headers = None

    def put_object(self, **kwargs):
        assert kwargs["ContentLength"] == N
        assert kwargs["Bucket"] == m.BUCKET
        assert kwargs["Key"] == OBJ["key"]
        assert kwargs["ContentMD5"]
        assert self.meta.events.callbacks
        signed = type("Request", (), {"headers": {}})()
        self.meta.events.callbacks["before-sign.s3.PutObject"](signed)
        self.headers = signed.headers
        assert self.headers.get("If-None-Match") == "*"
        self.puts += 1

fake = FakeClient()
with patch.dict(os.environ, {"CLOUDFLARE_ACCOUNT_ID": m.SOURCE_ACCOUNT}), \
     patch.object(m, "stream_source", return_value=("dummy-sha", "dummy-md5")), \
     patch.object(m, "head_or_none", return_value=None), \
     patch.object(m, "verify_s3_read_only", return_value=N):
    result = m.copy_one_large(fake, "dummy", OBJ)
    assert result["uploaded"] and result["verified"] and fake.puts == 1
    assert result["source_deleted"] is False and result["overwritten"] is False
    assert not fake.meta.events.callbacks
print("PASS conditional large PUT signed no-overwrite and SHA recheck invocation")


fake = FakeClient(present=True)
with patch.dict(os.environ, {"CLOUDFLARE_ACCOUNT_ID": m.SOURCE_ACCOUNT}), \
     patch.object(m, "stream_source", return_value=("dummy-sha", "dummy-md5")), \
     patch.object(m, "head_or_none", return_value={"ContentLength": N}), \
     patch.object(m, "verify_s3_read_only", return_value=N):
    result = m.copy_one_large(fake, "dummy", OBJ)
    assert not result["uploaded"] and fake.puts == 0
print("PASS existing large target is never overwritten")


for o in [{"key": "too-small", "size": m.MIN_BYTES_EXCLUSIVE},
          {"key": "too-large", "size": m.MAX_BYTES + 1}]:
    try:
        m.check_object(o)
        raise AssertionError("bound not enforced")
    except m.GateError as err:
        assert str(err) == "LARGE_OBJECT_SIZE_GATE"
print("PASS strict large object size bounds")
