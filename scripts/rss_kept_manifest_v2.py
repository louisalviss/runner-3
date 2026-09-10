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


APPLE_TOPIC_RULES = [
    # One keynote overview may survive, but duplicate recap posts should not.
    ("apple-keynote-2026-overview", [
        r"(?:tom tat su kien apple|apple event|su kien apple)",
        r"(?:iphone duo|airpods 5|apple watch|john ternus)",
    ]),
    # Preserve the genuinely distinct manufacturing/industrial angle.
    ("apple-iphone-duo-manufacturing", [
        r"(?:iphone duo|folding iphone|foldable iphone|iphone man hinh gap|iphone gap)",
        r"(?:ban le|hinge)",
        r"(?:3d|additive|in 3d|\bai\b)",
    ]),
    # Collapse repetitive launch/spec/reaction posts about the same iPhone Duo event.
    ("apple-iphone-duo-launch", [
        r"(?:iphone duo|folding iphone|foldable iphone|iphone man hinh gap|iphone gap)",
        r"(?:ra mat|launch|chinh thuc|can anh|animation|anh dong|nep gap|crease|magsafe|camera duoi man hinh|under.?display|wow|samsung|fold8|mo man hinh|thiet ke moi la|tai dinh nghia)",
    ]),
    ("apple-airpods5-launch", [
        r"airpods 5",
        r"(?:ra mat|chinh thuc|anc|chong on|129|3[.,]4|gia)",
    ]),
    ("apple-watch-ultra4-launch", [r"apple watch ultra 4"]),
    ("apple-watch-series12-launch", [r"apple watch series 12"]),
]


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

    obj["version"] = max(int(obj.get("version") or 0), 8)
    obj["scope"] = "rss-kept-manifest-runner15"
    obj["filterPolicyVersion"] = "2026-09-11-canonical-source-policy-v8-apple-event-dedupe"
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
        "appleLaunchEventDedupRequired": True,
    })
    obj["contract"] = contract
    render = dict(obj.get("renderContract") or {})
    render.update({
        "all15SourcesBackedByRunnerMirrors": True,
        "directVerificationRequired": False,
        "sourceOmissionFailsClosed": True,
        "appleLaunchEventDedupRequired": True,
    })
    obj["renderContract"] = render
    return obj


def install_runner15_overrides():
    legacy.DIRECT_KEYS = set()
    legacy.SOURCE_PRIORITY.update({"hoquoctuan": 93, "vnhacker": 91})

    # Explicit event rules run before generic title-similarity dedupe. Replace any
    # rule with the same key so repeated invocations remain idempotent.
    replacement_keys = {key for key, _ in APPLE_TOPIC_RULES}
    legacy.TOPIC_RULES = APPLE_TOPIC_RULES + [
        rule for rule in legacy.TOPIC_RULES if rule[0] not in replacement_keys
    ]

    # Article keys are not guaranteed to be globally unique across sources
    # (for example date-derived IDs such as id:20260903). Canonical URLs are.
    legacy.stable_id = lambda item: item.get("canonicalUrl") or item.get("key")


def build(root, inventory_path):
    install_runner15_overrides()
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
        "topicDuplicateFilteredCount": obj["topicDuplicateFilteredCount"],
        "summaryEvidenceMissingCount": obj["summaryEvidenceMissingCount"],
        "runnerAccountingOk": obj["runnerAccountingOk"],
        "complete15SourceRenderReady": obj["complete15SourceRenderReady"],
    }, ensure_ascii=False))
    return 0 if obj["runnerAccountingOk"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
