#!/usr/bin/env python3
"""Finalize Runner15 manifests without any manual direct-source dependency."""

import argparse
import copy
import json
from pathlib import Path

import rss_manifest_finalize as legacy


def normalize_runner15(obj):
    obj["version"] = max(int(obj.get("version") or 0), 8)
    obj["scope"] = "rss-kept-manifest-runner15"
    obj["filterPolicyVersion"] = "2026-09-11-canonical-source-policy-v8-apple-event-dedupe-runner15-replay-safe"
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
        "appleLaunchEventDedupRequired": True,
        "replayRule": "Use the immutable Runner15 date/hash manifest; render exact source titles with summaries; freeze served render when available.",
    })
    obj["renderContract"] = render

    contract = dict(obj.get("contract") or {})
    contract.update({
        "directVerificationSnapshotRequired": False,
        "finalRenderRequiresDirectVerification": False,
        "all15SourcesBackedByRunnerMirrors": True,
        "complete15SourceAccountingRequired": True,
        "appleLaunchEventDedupRequired": True,
    })
    obj["contract"] = contract

    # Immutable archive identity must include the active filtering/dedupe policy.
    # The legacy hash covers only manifest rows, so a policy-only upgrade (v7->v8)
    # could otherwise reuse the same <date>/<hash>.json path with different payload
    # and correctly trip the immutable-collision guard.
    content_hash = str(obj.get("manifestHash") or "")
    if content_hash:
        obj["contentManifestHash"] = content_hash
        obj["manifestHash"] = legacy.sha256_obj({
            "contentManifestHash": content_hash,
            "filterPolicyVersion": obj["filterPolicyVersion"],
            "scope": obj["scope"],
            "version": obj["version"],
        })
        obj["manifestArchiveKey"] = f"{obj.get('date')}/{obj['manifestHash']}.json"
    return obj


def _configure_runner15_legacy():
    legacy.DIRECT_KEYS = set()
    legacy.SOURCE_PRIORITY.update({"hoquoctuan": 93, "vnhacker": 91})
    # Source-local keys are not globally unique. Use canonical URL as the
    # cross-source replay identity and retain key only as a fallback.
    legacy.stable_id = lambda item: item.get("canonicalUrl") or item.get("key")


def finalize(obj):
    _configure_runner15_legacy()
    return normalize_runner15(legacy.rebuild_manifest(copy.deepcopy(obj)))


def self_test():
    _configure_runner15_legacy()
    legacy.self_test()
    probe = normalize_runner15({"version": 8, "sourceRows": [], "manifestHash": "content-hash", "date": "2026-09-11"})
    assert probe["version"] >= 8
    assert probe["filterPolicyVersion"] == "2026-09-11-canonical-source-policy-v8-apple-event-dedupe-runner15-replay-safe"
    assert probe["renderContract"]["appleLaunchEventDedupRequired"] is True
    assert probe["contract"]["appleLaunchEventDedupRequired"] is True
    assert probe["contentManifestHash"] == "content-hash"
    assert probe["manifestHash"] != probe["contentManifestHash"]
    assert probe["manifestArchiveKey"] == f"2026-09-11/{probe['manifestHash']}.json"
    again = normalize_runner15({"version": 8, "sourceRows": [], "manifestHash": "content-hash", "date": "2026-09-11"})
    assert again["manifestHash"] == probe["manifestHash"]
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
