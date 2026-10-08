#!/usr/bin/env python3
"""Local-only contract: WP Media one-run continuation uses no production API."""
import importlib.util
import json
import tempfile
from pathlib import Path
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("auto", "scripts/cloudflare_r2_wp_autopilot.py")
auto = importlib.util.module_from_spec(spec)
spec.loader.exec_module(auto)


def audit(eligible, missing, large=0):
    return {
        "source_inventory_count": 3, "target_inventory_count_before": 1,
        "missing_before": missing, "eligible_missing_count": eligible,
        "skipped_large_count": large, "skipped_metadata_count": 0,
        "planned_bytes": 10,
    }


class FakeClient:
    pass


src = [{"key": "small-1", "size": 10}, {"key": "large", "size": 20_000_000}]

with tempfile.TemporaryDirectory() as folder:
    auto.OUT = Path(folder)
    auto.PROGRESS = auto.OUT / "progress.json"
    auto.SUMMARY = auto.OUT / "receipt.json"
    with patch.dict("os.environ", {
        "CLOUDFLARE_API_TOKEN": "fake",
        "CLOUDFLARE_ACCOUNT_ID": auto.batch.SOURCE_ACCOUNT,
    }), patch.object(auto, "check_source_budget", return_value=src), \
        patch.object(auto.batch, "run", side_effect=[
            audit(1, 2, 1),
            {"result": "BOUNDED_BATCH_VERIFIED", "verified_count": 1,
             "uploaded_count": 1, "verified_bytes": 10,
             "already_present_verified_count": 0, "missing_after_snapshot": 1},
            audit(0, 1, 1),
            audit(0, 1, 1),
        ]), patch.object(auto.batch, "target_s3", return_value=FakeClient()), \
        patch.object(auto.batch, "target_list", return_value={"small-1": 10}), \
        patch.object(auto.batch, "preflight", return_value=([src[0]], [src[1]])), \
        patch.object(auto, "source_properties", return_value={}), \
        patch.object(auto, "verify_existing_read_only", return_value=10):
        state = auto.run()
        assert state["status"] == "SMALL_OBJECTS_VERIFIED", state
        assert state["batch_count"] == 1 and state["uploaded_count"] == 1
        assert state["remaining_count"] == 1 and state["cutover_ready"] is False
        assert state["full_bucket_parity_verified"] is False
        assert state["verified_existing_final"] == 1
        assert json.loads(auto.SUMMARY.read_text())["status"] == "SMALL_OBJECTS_VERIFIED"
        print("PASS batch auto-resume, final verify and oversize quarantine")

with tempfile.TemporaryDirectory() as folder:
    auto.OUT = Path(folder)
    auto.PROGRESS = auto.OUT / "progress.json"
    auto.SUMMARY = auto.OUT / "receipt.json"
    with patch.dict("os.environ", {
        "CLOUDFLARE_API_TOKEN": "fake",
        "CLOUDFLARE_ACCOUNT_ID": auto.batch.SOURCE_ACCOUNT,
    }), patch.object(auto, "check_source_budget", return_value=src), \
        patch.object(auto.batch, "run", side_effect=auto.GateError("MOCK_SAFE_GATE")):
        state = auto.run()
        assert state["status"] == "BLOCKED" and state["reason"] == "MOCK_SAFE_GATE"
        assert state["uploaded_count"] == 0 and auto.PROGRESS.exists()
        print("PASS fail-closed with durable-on-graceful-error local receipt")

# Direct verifier cannot PUT, including if an existing key disappears.
class ReadOnly:
    def __init__(self):
        self.reads = 0
        self.puts = 0
    def head_object(self, **kwargs):
        self.reads += 1
        return {"ContentLength": 4, "Metadata": {}, "StorageClass": "STANDARD"}
    def get_object(self, **kwargs):
        self.reads += 1
        class Body:
            def read(self, n): return b"proof"
        return {"Body": Body()}
    def put_object(self, **kwargs):
        self.puts += 1
        raise AssertionError("READ_ONLY_VERIFIER_MUST_NOT_WRITE")

ro = ReadOnly()
with patch.object(auto, "source_bytes", return_value=b"proof"), \
     patch.object(auto, "source_properties", return_value={"Metadata": {}, "StorageClass": "STANDARD"}):
    try:
        auto.verify_existing_read_only(ro, "fake", {"key": "proof", "size": 4})
        assert False, "length mismatch must be detected"
    except auto.GateError as e:
        assert str(e) == "FINAL_READ_ONLY_SIZE_MISMATCH"
        assert ro.puts == 0
print("PASS read-only final verifier refuses mismatched target and never PUTs")


# Read-only positive verification checks SHA256, metadata and size.
class ReadOnlyGood(ReadOnly):
    def head_object(self, **kwargs):
        self.reads += 1
        return {"ContentLength": 5, "Metadata": {}, "StorageClass": "STANDARD"}

good = ReadOnlyGood()
with patch.object(auto, "source_bytes", return_value=b"proof"), \
     patch.object(auto, "source_properties", return_value={"Metadata": {}, "StorageClass": "STANDARD"}):
    size = auto.verify_existing_read_only(good, "fake", {"key": "proof", "size": 5})
    assert size == 5 and good.puts == 0 and good.reads == 2
print("PASS read-only existing-object SHA and metadata verification")

# Different bytes of the same length must fail SHA, never overwrite.
class ReadOnlyCorrupt(ReadOnlyGood):
    def get_object(self, **kwargs):
        self.reads += 1
        class Body:
            def read(self, n): return b"wrong"
        return {"Body": Body()}

corrupt = ReadOnlyCorrupt()
with patch.object(auto, "source_bytes", return_value=b"proof"), \
     patch.object(auto, "source_properties", return_value={"Metadata": {}, "StorageClass": "STANDARD"}):
    try:
        auto.verify_existing_read_only(corrupt, "fake", {"key": "proof", "size": 5})
        assert False, "SHA drift must fail"
    except auto.GateError as e:
        assert str(e) == "FINAL_READ_ONLY_SHA256_MISMATCH"
        assert corrupt.puts == 0
print("PASS read-only existing-object SHA drift refuses overwrite")
