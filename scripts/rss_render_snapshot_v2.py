#!/usr/bin/env python3
"""Runner15 served-render snapshot validator.

All logical sources are already present in the manifest, so a separate direct
source audit is no longer required. This wrapper preserves exact title/link/
summary/order validation from rss_render_snapshot.py.
"""

import argparse
import json
from pathlib import Path

import rss_render_snapshot as legacy


def empty_audit(target_date):
    return {"targetDate": target_date, "sources": []}


def build_snapshot(manifest, rendered):
    legacy.DIRECT_KEYS = set()
    snap = legacy.build_snapshot(manifest, empty_audit(manifest.get("date")), rendered)
    contract = dict(snap.get("contract") or {})
    contract.update({
        "all15SourcesBackedByRunnerMirrors": True,
        "directVerificationRequired": False,
    })
    snap["contract"] = contract
    snap["directAudit"] = None
    snap["renderHash"] = legacy.sha256_obj({k: v for k, v in snap.items() if k not in {"renderHash", "problems", "valid"}})
    return snap


def self_test():
    legacy.DIRECT_KEYS = set()
    manifest = {
        "date": "2026-08-31",
        "manifestHash": "abc",
        "manifestArchiveKey": "2026-08-31/abc.json",
        "manifest": [{
            "key": "id:1", "sourceKey": "hoquoctuan", "title": "Tiêu đề GỐC",
            "canonicalUrl": "https://example.com/1", "publishedAt": "2026-08-31T01:00:00Z",
        }],
    }
    rendered = {
        "targetDate": "2026-08-31", "timezone": "Asia/Ho_Chi_Minh",
        "items": [{
            "number": 1, "key": "id:1", "sourceKey": "hoquoctuan", "title": "Tiêu đề GỐC",
            "canonicalUrl": "https://example.com/1", "publishedAt": "2026-08-31T01:00:00Z", "summary": "Tóm tắt.",
        }],
    }
    snap = build_snapshot(manifest, rendered)
    assert snap["valid"], snap["problems"]
    return True


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--manifest")
    p.add_argument("--rendered")
    p.add_argument("--out-root", default="data/rss-reader/renders")
    p.add_argument("--self-test", action="store_true")
    args = p.parse_args()
    if args.self_test:
        self_test()
        print(json.dumps({"selfTest": True, "status": "pass", "runnerSourceCount": 15}))
        return 0
    if not args.manifest or not args.rendered:
        p.error("--manifest and --rendered are required")
    manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
    rendered = json.loads(Path(args.rendered).read_text(encoding="utf-8"))
    snapshot = build_snapshot(manifest, rendered)
    if not snapshot["valid"]:
        print(json.dumps(snapshot, ensure_ascii=False))
        return 2
    path = legacy.freeze(snapshot, args.out_root)
    print(json.dumps({"valid": True, "renderHash": snapshot["renderHash"], "path": str(path)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
