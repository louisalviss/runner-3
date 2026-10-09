#!/usr/bin/env python3
"""Private R2 durable optimizer event ledger. Single VPS writer per site.

Events are immutable, idempotent and SHA-verified via existing Runner3 Core.
A per-run manifest indexes events and is verified after each update.
No retired WP D1, database schema change, credentials or site mutation.
"""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re

PROJECT = "wordpress-optimizer"
SCOPE = "a2z"
PREFIX = "ledger-v1"
VALID = re.compile(r"^[a-z0-9][a-z0-9_-]{0,79}$")
KINDS = {"site.upsert", "candidate.upsert", "run.start", "run.finish",
         "measurement.upsert", "gate.upsert", "decision.upsert", "artifact.add"}
KEYS = {
    "site.upsert": ("site_id",),
    "candidate.upsert": ("candidate_id",),
    "run.start": ("run_id",),
    "run.finish": ("run_id",),
    "measurement.upsert": ("run_id", "phase", "sample_no"),
    "gate.upsert": ("run_id", "gate_name"),
    "decision.upsert": ("run_id",),
    "artifact.add": ("run_id", "kind"),
}

def canonical(data):
    return (json.dumps(data, sort_keys=True, ensure_ascii=False,
                       separators=(",", ":"), allow_nan=False) + "\n").encode()

def hash_bytes(blob):
    return hashlib.sha256(blob).hexdigest()

def valid(value, label):
    if not isinstance(value, str) or not VALID.fullmatch(value):
        raise ValueError("invalid " + label)
    return value

def validate(site, event):
    valid(site, "site")
    if not isinstance(event, dict) or event.get("type") not in KINDS:
        raise ValueError("event type not supported")
    if event.get("site_id") not in (None, site):
        raise ValueError("site mismatch")
    for key in KEYS[event["type"]]:
        if event.get(key) is None:
            raise ValueError("missing " + key)
    if any(s in canonical(event).lower() for s in (
        b'"password":', b'"token":', b'"secret":', b'"cookie":',
        b'"authorization":', b'"applicationpassword":',
    )):
        raise ValueError("credential field disallowed")
    run = valid(str(event.get("run_id", "site-events")), "run_id")
    if len(canonical(event)) > 160000:
        raise ValueError("event too large for small structured store")
    return run

def event_key(site, run, digest):
    return f"{PREFIX}/{site}/{run}/events/{digest}.json"

def manifest_key(site, run):
    return f"{PREFIX}/{site}/{run}/manifest.json"

class Store:
    def __init__(self):
        import runner3_core
        import r2_durable_commit
        self.core, self.durable = runner3_core, r2_durable_commit
    def get(self, key):
        return self.core.get_artifact_bytes(PROJECT, SCOPE, key, timeout=45)
    def put(self, key, content):
        obj = json.loads(content)
        receipt = self.durable.durable_put_json(
            PROJECT, SCOPE, key, obj, source_system="runner-vps1",
            producer="wp-optimizer-ledger", kind="wp-optimizer-event", timeout=90)
        expected = canonical(obj)
        if receipt.get("sha256") != hash_bytes(expected) or self.get(key) != expected:
            raise RuntimeError("R2 byte/hash readback mismatch")

class MockStore:
    def __init__(self):
        self.blobs = {}
        self.writes = 0
    def get(self, key):
        return self.blobs.get(key)
    def put(self, key, content):
        self.writes += 1
        self.blobs[key] = content

def append(store, site, event):
    run = validate(site, event)
    blob = canonical(event)
    digest = hash_bytes(blob)
    key = event_key(site, run, digest)
    old = store.get(key)
    if old is not None and old != blob:
        raise RuntimeError("immutable event collision")
    if old is None:
        store.put(key, blob)
    mk = manifest_key(site, run)
    raw = store.get(mk)
    m = json.loads(raw) if raw else {
        "schema": "wordpress-optimizer-ledger-v1",
        "site_id": site, "run_id": run, "events": [], "verdict": None
    }
    if m.get("site_id") != site or m.get("run_id") != run or not isinstance(m.get("events"), list):
        raise RuntimeError("manifest identity/schema mismatch")
    if not any(x["sha256"] == digest for x in m["events"]):
        m["events"].append({"sha256": digest, "key": key, "type": event["type"]})
        if event["type"] == "run.finish":
            m["status"] = event.get("status")
        elif event["type"] == "decision.upsert":
            m["verdict"] = event.get("verdict")
        store.put(mk, canonical(m))
    if store.get(mk) != canonical(m) or store.get(key) != blob:
        raise RuntimeError("manifest or event readback mismatch")
    return {
        "site_id": site, "run_id": run, "result": "DUPLICATE" if old else "STORED",
        "event_sha256": digest, "event_count": len(m["events"]),
        "manifest_sha256": hash_bytes(canonical(m)), "verified": True,
        "event_key": key, "manifest_key": mk
    }

def inspect(store, site, run):
    valid(site, "site"); valid(run, "run")
    raw = store.get(manifest_key(site, run))
    if raw is None:
        return {"found": False}
    m = json.loads(raw)
    if m["site_id"] != site or m["run_id"] != run:
        raise RuntimeError("manifest owner mismatch")
    for row in m["events"]:
        data = store.get(row["key"])
        if data is None or hash_bytes(data) != row["sha256"]:
            raise RuntimeError("missing/corrupted event")
    return {"found": True, "event_count": len(m["events"]),
            "status": m.get("status"), "verdict": m.get("verdict"),
            "integrity": "PASS", "site_id": site, "run_id": run}

def selftest():
    s = MockStore()
    e = {"type":"run.start","site_id":"site2","run_id":"fixture001","phase":"baseline"}
    assert append(s,"site2",e)["result"] == "STORED"
    assert append(s,"site2",e)["result"] == "DUPLICATE"
    assert append(s,"site2",{"type":"gate.upsert","run_id":"fixture001","gate_name":"functional","status":"PASS"})["event_count"]==2
    assert append(s,"site2",{"type":"decision.upsert","run_id":"fixture001","verdict":"ROLLBACK"})["event_count"]==3
    assert inspect(s,"site2","fixture001")["integrity"]=="PASS"
    assert s.writes==6
    print(json.dumps({"selftest":"PASS","idempotency":"PASS","bytes_verified":"PASS","writes":6}))

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--site-id")
    p.add_argument("--run-id")
    p.add_argument("--event-file")
    p.add_argument("--inspect",action="store_true")
    p.add_argument("--self-test",action="store_true")
    a=p.parse_args()
    if a.self_test: selftest(); return
    site=valid(a.site_id,"site")
    lockdir=Path("/var/lib/website-a2z/locks")
    lockdir.mkdir(mode=0o700,parents=True,exist_ok=True)
    lockfile=lockdir/(site+".lock")
    with lockfile.open("a+b") as fd:
        os.chmod(lockfile,0o600)
        fcntl.flock(fd,fcntl.LOCK_EX)
        try:
            store=Store()
            if a.inspect:
                print(json.dumps(inspect(store,site,valid(a.run_id,"run_id"))))
            else:
                if not a.event_file: p.error("--event-file required")
                event=json.loads(Path(a.event_file).read_text())
                print(json.dumps(append(store,site,event)))
        finally:
            fcntl.flock(fd,fcntl.LOCK_UN)

if __name__=="__main__":
    main()
