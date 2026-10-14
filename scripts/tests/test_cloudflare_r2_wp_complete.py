#!/usr/bin/env python3
"""Entirely offline control contracts: no Cloudflare API credentials/network."""
import tempfile
from pathlib import Path
from unittest.mock import patch

import cloudflare_r2_wp_complete as m

SRC = [
    {"key": "small", "size": 4},
    {"key": "medium", "size": 15_000_000},
    {"key": "large", "size": 25_000_000},
]


class FakeClient:
    pass


with tempfile.TemporaryDirectory() as folder:
    m.OUT = Path(folder)
    m.RECEIPT = m.OUT / "receipt.json"
    m.PROGRESS = m.OUT / "progress.json"
    dest = {}
    modes = []

    def fake_run(mode):
        modes.append(mode)
        remaining = [o for o in SRC if o["key"] not in dest]
        small, _ = m.batch.plan_batch(remaining)
        medium, _ = m.batch.medium_plan(remaining)
        large, _ = m.batch.large_plan(remaining)
        planned = small if mode == "batch" else (medium if mode == "medium-one" else large)
        assert planned
        for obj in planned:
            assert obj["key"] not in dest
            dest[obj["key"]] = obj["size"]
        return {
            "result": {
                "batch": "BOUNDED_BATCH_VERIFIED",
                "medium-one": "BOUNDED_MEDIUM_VERIFIED",
                "large-one": "BOUNDED_LARGE_VERIFIED",
            }[mode],
            "verified_count": len(planned),
            "uploaded_count": len(planned),
            "verified_bytes": sum(o["size"] for o in planned),
            "missing_after_snapshot": len(SRC) - len(dest),
        }

    with patch.dict("os.environ", {
        "CLOUDFLARE_API_TOKEN": "dummy",
        "CLOUDFLARE_ACCOUNT_ID": m.batch.SOURCE_ACCOUNT,
    }), patch.object(m, "source_list", return_value=SRC), \
         patch.object(m.batch, "target_s3", return_value=FakeClient()), \
         patch.object(m.batch, "target_list", side_effect=lambda client: dict(dest)), \
         patch.object(m.batch, "run", side_effect=fake_run), \
         patch.object(m, "preflight_existing_metadata", return_value=0), \
         patch.object(m, "verify_existing_read_only", side_effect=lambda client, token, obj: obj["size"]), \
         patch.object(m, "stream_source", return_value=("sha", "md5")), \
         patch.object(m, "verify_s3_read_only", side_effect=lambda client, obj, sha, meta: obj["size"]):
        result = m.main_run()
        assert modes == ["batch", "medium-one", "large-one"], modes
        assert result["status"] == "SNAPSHOT_VERIFIED_NOT_CUTOVER", result
        assert result["uploaded_objects"] == 3
        assert result["verified_snapshot_count"] == 3
        assert result["snapshot_keyspace_sha_metadata_parity"] is True
        assert result["cutover_ready"] is False and result["source_deleted"] is False
        assert result["full_bucket_parity_verified"] is False
print("PASS one-run small/medium/streamed-large staging and read-only full snapshot")


with tempfile.TemporaryDirectory() as folder:
    m.OUT = Path(folder)
    m.RECEIPT = m.OUT / "receipt.json"
    m.PROGRESS = m.OUT / "progress.json"
    with patch.dict("os.environ", {
        "CLOUDFLARE_API_TOKEN": "dummy",
        "CLOUDFLARE_ACCOUNT_ID": m.batch.SOURCE_ACCOUNT,
    }), patch.object(m, "source_list", return_value=SRC), \
         patch.object(m.batch, "target_s3", return_value=FakeClient()), \
         patch.object(m.batch, "target_list", return_value={x["key"]: x["size"] for x in SRC}), \
         patch.object(m, "preflight_existing_metadata", return_value=3), \
         patch.object(m, "verify_existing_read_only", side_effect=m.GateError("HASH_MISMATCH")):
        state = m.main_run()
        assert state["status"] == "BLOCKED"
        assert state["reason"] == "HASH_MISMATCH"
        assert state["cutover_ready"] is False
        assert state["snapshot_keyspace_sha_metadata_parity"] is False
print("PASS final verification aborts on corrupt target, cannot cut over")


# Existing target with differing CacheControl is detected by HEAD first.
# The full one-shot migration must refuse new object PUTs until resolved.
class HeaderClient:
    def head_object(self, **kwargs):
        return {"ContentLength": 5, "Metadata": {},
                "CacheControl": "public, max-age=111", "StorageClass": "STANDARD"}

drift = [{"key": "existing", "size": 5,
          "http_metadata": {"cacheControl": "public, max-age=222"}}]
try:
    m.preflight_existing_metadata(HeaderClient(), drift, {"existing": 5})
    raise AssertionError("pre-existing drift must be rejected")
except m.GateError as exc:
    assert str(exc) == "TARGET_HTTP_METADATA_MISMATCH_CACHECONTROL"
print("PASS early Cache-Control drift HEAD refuses replay")

with tempfile.TemporaryDirectory() as folder:
    m.OUT = Path(folder)
    m.RECEIPT = m.OUT / "receipt.json"
    m.PROGRESS = m.OUT / "progress.json"
    with patch.dict("os.environ", {
        "CLOUDFLARE_API_TOKEN": "dummy",
        "CLOUDFLARE_ACCOUNT_ID": m.batch.SOURCE_ACCOUNT,
    }), patch.object(m, "source_list", return_value=drift), \
         patch.object(m.batch, "target_s3", return_value=HeaderClient()), \
         patch.object(m.batch, "target_list", return_value={"existing": 5}), \
         patch.object(m.batch, "run", side_effect=AssertionError("MUST_NOT_PUT")):
        state = m.main_run()
        assert state["status"] == "BLOCKED"
        assert state["reason"] == "TARGET_HTTP_METADATA_MISMATCH_CACHECONTROL"
        assert state["uploaded_objects"] == 0
        assert state["source_deleted"] is False and state["overwritten"] is False
        assert state["cutover_ready"] is False
print("PASS existing metadata mismatch halts before any batch PUT")
