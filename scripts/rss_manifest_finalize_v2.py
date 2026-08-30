#!/usr/bin/env python3
"""Finalize Runner15 manifests without any manual direct-source dependency."""

import argparse
import copy
import json
from pathlib import Path

import rss_manifest_finalize as legacy


def normalize_runner15(obj):
    obj["version"] = max(int(obj.get("version") or 0), 7)
    obj["scope"] = "rss-kept-manifest-runner15"
    obj["filterPolicyVersion"] = "2026-08-31-canonical-source-policy-v7-runner15-replay-safe"
    obj["logicalSourceCount"] = 15
    obj["runnerSourceCount"] = 15
    obj["directSourceCount"] = 0
    obj["directVerificationPending"] = []

    rows = obj.get("sourceRows") or []
    problems = [p for p in (obj.get("problems") or []) if p]
    if len(rows) != 15:
        problems.append(f"source row count {len(rows)} != 15")
    for row in rows:
        if row.get("status") != "ok":
            problems.append(f"{row.get('sourceKey')}: status={row.get('status')} expected=ok")
        raw = row.get("rawCount")
        kept = row.get("keptCount")
        filtered = row.get("filteredCount")
        if None in (raw, kept, filtered):
            problems.append(f"{row.get('sourceKey')}: incomplete accounting")
        elif raw != kept + filtered:
            problems.append(f"{row.get('sourceKey')}: raw {raw} != kept {kept} + filtered {filtered}")

    obj["problems"] = problems
    obj["runnerAccountingOk"] = not problems
    obj["complete15SourceRenderReady"] = not problems

    render = dict(obj.get("renderContract") or {})
    render.update({
        "version": 4,
        "directVerificationSnapshotRequired": False,
        "directVerificationRequired": False,
        "all15SourcesBackedByRunnerMirrors": True,
        "sourceOmissionFailsClosed": True,
        "replayRule": "Use the immutable Runner15 date/hash manifest; render exact source titles with summaries; freeze served render when available.",
    })
    obj["renderContract"] = render

    contract = dict(obj.get("contract") or {})
    contract.update({
        "directVerificationSnapshotRequired": False,
        "finalRenderRequiresDirectVerification": False,
        "all15SourcesBackedByRunnerMirrors": True,
        "complete15SourceAccountingRequired": True,
    })
    obj["contract"] = contract
    return obj


def finalize(obj):
    legacy.DIRECT_KEYS = set()
    legacy.SOURCE_PRIORITY.update({"hoquoctuan": 93, "vnhacker": 91})
    return normalize_runner15(legacy.rebuild_manifest(copy.deepcopy(obj)))


def self_test():
    legacy.DIRECT_KEYS = set()
    legacy.self_test()
    return True


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest")
    parser.add_argument("--out")
    parser.add_argument("--archive-root", default="data/rss-reader/manifests")
    parser.add_argument("--archive-mode", choices=["none", "latest", "immutable"], default="immutable")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        self_test()
        print(json.dumps({"selfTest": True, "status": "pass", "runnerSourceCount": 15}))
        return 0
    if not args.manifest or not args.out:
        parser.error("--manifest and --out are required unless --self-test is used")

    obj = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
    finalized = finalize(obj)
    legacy.write_json_atomic(args.out, finalized)
    immutable, latest = legacy.archive_manifest(finalized, args.archive_root, args.archive_mode)
    print(json.dumps({
        "date": finalized.get("date"),
        "runnerRawCount": finalized.get("runnerRawCount"),
        "runnerKeptCount": finalized.get("runnerKeptCount"),
        "runnerFilteredCount": finalized.get("runnerFilteredCount"),
        "runnerManifestCount": finalized.get("runnerManifestCount"),
        "runnerSourceCount": finalized.get("runnerSourceCount"),
        "summaryEvidenceMissingCount": finalized.get("summaryEvidenceMissingCount"),
        "runnerAccountingOk": finalized.get("runnerAccountingOk"),
        "complete15SourceRenderReady": finalized.get("complete15SourceRenderReady"),
        "manifestHash": finalized.get("manifestHash"),
        "archiveMode": args.archive_mode,
        "immutableArchive": str(immutable) if immutable else None,
        "latestArchive": str(latest) if latest else None,
    }, ensure_ascii=False))
    return 0 if finalized.get("runnerAccountingOk") else 2


if __name__ == "__main__":
    raise SystemExit(main())
