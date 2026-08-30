#!/usr/bin/env python3
"""Runner15 kept-manifest wrapper.

Reuses canonical filtering/dedupe logic while treating Hồ Quốc Tuấn and
vnhacker as normal Runner-backed sources. This removes the old manual direct
verification hole from final feed accounting.
"""

import argparse
import json
from pathlib import Path

import rss_kept_manifest as legacy


def normalize_runner15(obj):
    rows = obj.get("sourceRows") or []
    problems = list(obj.get("problems") or [])
    if len(rows) != 15:
        problems.append(f"source row count {len(rows)} != 15")
    for row in rows:
        if row.get("status") != "ok":
            problems.append(f"{row.get('sourceKey')}: status={row.get('status')} expected=ok")
        if row.get("rawCount") is None or row.get("keptCount") is None or row.get("filteredCount") is None:
            problems.append(f"{row.get('sourceKey')}: incomplete accounting counts")

    obj["version"] = max(int(obj.get("version") or 0), 7)
    obj["scope"] = "rss-kept-manifest-runner15"
    obj["filterPolicyVersion"] = "2026-08-31-canonical-source-policy-v7-runner15"
    obj["logicalSourceCount"] = 15
    obj["runnerSourceCount"] = 15
    obj["directSourceCount"] = 0
    obj["directVerificationPending"] = []
    obj["problems"] = problems
    obj["runnerAccountingOk"] = not problems
    obj["complete15SourceRenderReady"] = not problems
    contract = dict(obj.get("contract") or {})
    contract.update({
        "finalRenderRequiresDirectVerification": False,
        "all15SourcesBackedByRunnerMirrors": True,
        "complete15SourceAccountingRequired": True,
    })
    obj["contract"] = contract
    render = dict(obj.get("renderContract") or {})
    render.update({
        "all15SourcesBackedByRunnerMirrors": True,
        "directVerificationRequired": False,
        "sourceOmissionFailsClosed": True,
    })
    obj["renderContract"] = render
    return obj


def build(root, inventory_path):
    legacy.DIRECT_KEYS = set()
    legacy.SOURCE_PRIORITY.update({"hoquoctuan": 93, "vnhacker": 91})
    obj = legacy.build(root, inventory_path)
    return normalize_runner15(obj)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".")
    parser.add_argument("--inventory", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    root = Path(args.root).resolve()
    obj = build(root, Path(args.inventory))
    output = Path(args.out)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "date": obj["date"],
        "runnerRawCount": obj["runnerRawCount"],
        "runnerKeptCount": obj["runnerKeptCount"],
        "runnerFilteredCount": obj["runnerFilteredCount"],
        "runnerManifestCount": obj["runnerManifestCount"],
        "runnerSourceCount": obj["runnerSourceCount"],
        "summaryEvidenceMissingCount": obj["summaryEvidenceMissingCount"],
        "runnerAccountingOk": obj["runnerAccountingOk"],
        "complete15SourceRenderReady": obj["complete15SourceRenderReady"],
    }, ensure_ascii=False))
    return 0 if obj["runnerAccountingOk"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
