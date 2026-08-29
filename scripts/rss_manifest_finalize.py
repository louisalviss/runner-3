#!/usr/bin/env python3
"""Finalize Runner13 RSS kept manifests for replay-safe rendering.

This is a second, fail-closed contract gate after rss_kept_manifest.py.
It strengthens:
- GameK negative semantic filtering
- high-confidence cross-source same-event dedupe
- exact/verbatim title render contract
- immutable date/hash manifest snapshots for deterministic replay
"""

import argparse
import copy
import hashlib
import json
import re
import unicodedata
from pathlib import Path

DIRECT_KEYS = {"hoquoctuan", "vnhacker"}
SOURCE_PRIORITY = {
    "economist": 100,
    "quanta": 98,
    "scientificamerican": 96,
    "projectsyndicate": 94,
    "fulcrum": 92,
    "noema": 90,
    "nghiencuuquocte": 88,
    "theatlantic": 86,
    "grimlogs": 82,
    "vohoanghac": 80,
    "tinhte": 65,
    "genk": 60,
    "gamek": 45,
}

GAMEK_HARD_REJECT = [
    r"\bhot girl\b", r"\bmỹ nhân\b", r"\bmy nhan\b", r"\bnhan sắc\b", r"\bnhan sac\b",
    r"\bvóc dáng\b", r"\bvoc dang\b", r"\bcosplay\b", r"\bstreamer\b", r"\bfandom\b",
    r"\bbạn gái\b", r"\bban gai\b", r"\bbạn trai\b", r"\bban trai\b", r"\bngười yêu\b",
    r"\bnguoi yeu\b", r"\bđời tư\b", r"\bdoi tu\b", r"\bdrama\b", r"\bhẹn hò\b",
    r"\bhen ho\b", r"\brò rỉ clip\b", r"\bro ri clip\b", r"\bbody[- ]?shaming\b",
    r"\bkhiến fan\b", r"\bkhien fan\b", r"\bfan nghi\b", r"\bfan .*xôn xao\b",
    r"\bfan .*xon xao\b", r"\bfan .*đào lại\b", r"\bfan .*dao lai\b",
    r"\bfan .*phát sốt\b", r"\bfan .*phat sot\b", r"\bfan .*tranh cãi\b",
    r"\bfan .*tranh cai\b", r"\bphát sốt.*nhan sắc\b", r"\bphat sot.*nhan sac\b",
    r"\btop \d+\b", r"\bgiftcode\b", r"\bmiễn phí\b", r"\bmien phi\b",
]

# Rules are deliberately narrow. They only collapse high-confidence same-event packages.
TOPIC_RULES = [
    ("spacex-louisiana-spaceport", [r"spacex", r"(?:spaceport|starbase|louisiana)"]),
    ("meta-youth-social-harms-settlement", [r"meta", r"(?:under.?18|children|tre em|youth)", r"(?:settle|lawsuit|harm|gioi han|18 billion|\$18|dong y)"]),
    ("dolly-parton-remembrance", [r"dolly parton"]),
    ("apple-mac-mini-m6-launch", [r"mac mini", r"\bm6\b"]),
    ("apple-mac-studio-m5-launch", [r"mac studio", r"m5 (?:max|ultra)|m5 max|m5 ultra"]),
    ("apple-iphone18-sept9-launch", [r"iphone", r"(?:9/9|september 9|9 september|iphone 18|iphone gap|foldable)"]),
    ("hasselblad-mirrorless-10y", [r"hasselblad", r"mirrorless"]),
    ("bhxh-national-id-sept1", [r"(?:bhxh|bao hiem xa hoi)", r"(?:1/9|1-9|september 1|dinh danh|cccd)"]),
    ("xiaomi-xring-o3", [r"xiaomi", r"xring o3"]),
    ("gta6-113gb-malware", [r"gta ?6", r"113 ?gb|ma doc|malware"]),
    ("rog-20th-anniversary", [r"(?:rog|asus)", r"20 nam|20th|edition 20|ky niem 20"]),
    (
        "galaxy-s26-fe-vn-launch",
        [r"\bgalaxy s26 fe\b", r"(?:viet nam|mở bán|mo ban|18[,.]99|giá từ|gia tu)"],
    ),
    (
        "windows-on-arm-maturity-2026",
        [r"\bwindows on arm\b", r"(?:giai đoạn mới|giai doan moi|trưởng thành|truong thanh|hạng hai|hang hai|sẵn sàng|san sang)"],
    ),
    (
        "lg-french-door-fit-max-vn-launch",
        [r"\blg\b", r"\bfrench door\b", r"\bfit\s*&\s*max\b"],
    ),
    (
        "apple-hust-supply-chain-education-center",
        [r"\bapple\b", r"(?:bách khoa|bach khoa|hust)", r"(?:trung tâm giáo dục|trung tam giao duc|chuỗi cung ứng|chuoi cung ung|đại bản doanh|dai ban doanh)"],
    ),
]


def norm(value):
    return re.sub(r"\s+", " ", (value or "").strip()).lower()


def ascii_norm(value):
    value = (value or "").replace("đ", "d").replace("Đ", "D")
    value = unicodedata.normalize("NFKD", value)
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    return norm(value)


def stable_id(item):
    return item.get("key") or item.get("canonicalUrl")


def canonical_json(obj):
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256_obj(obj):
    return hashlib.sha256(canonical_json(obj).encode("utf-8")).hexdigest()


def reason_add(row, reason):
    summary = row.setdefault("filterReasonSummary", {})
    summary[reason] = summary.get(reason, 0) + 1


def hard_reject_gamek(item):
    text = ascii_norm(f"{item.get('title') or ''} {item.get('summaryEvidence') or ''}")
    return any(re.search(pattern, text, flags=re.I) for pattern in GAMEK_HARD_REJECT)


def explicit_topic_key(item):
    text = ascii_norm(f"{item.get('title') or ''} {item.get('summaryEvidence') or ''}")
    for key, required in TOPIC_RULES:
        if all(re.search(pattern, text, flags=re.I) for pattern in required):
            return key
    return None


def representative_score(item):
    # Reliability dominates; evidence density and freshness break ties.
    return (
        SOURCE_PRIORITY.get(item.get("sourceKey"), 50),
        min(len(item.get("summaryEvidence") or ""), 1600),
        item.get("publishedAt") or "",
    )


def row_item_with_source(item, source):
    out = dict(item)
    out["sourceKey"] = source
    return out


def move_kept_to_filtered(row, identity, reason):
    kept = row.get("keptItems") or []
    target = next((item for item in kept if stable_id(item) == identity), None)
    if target is None:
        return False
    row["keptItems"] = [item for item in kept if stable_id(item) != identity]
    moved = dict(target)
    moved["filterReason"] = reason
    row.setdefault("filteredItems", []).append(moved)
    reason_add(row, reason)
    return True


def rebuild_manifest(obj):
    problems = []
    rows = obj.get("sourceRows") or []
    by_source = {row.get("sourceKey"): row for row in rows}

    # 1) Strengthen GameK hard reject.
    gamek = by_source.get("gamek")
    if gamek:
        for item in list(gamek.get("keptItems") or []):
            if hard_reject_gamek(item):
                identity = stable_id(item)
                reason = "v6 hard reject: fandom/relationship/celebrity/speculation/filler"
                if not move_kept_to_filtered(gamek, identity, reason):
                    problems.append(f"gamek: failed hard reject move for {identity}")

    # 2) Gather surviving items.
    all_kept = []
    for row in rows:
        source = row.get("sourceKey")
        if source in DIRECT_KEYS:
            continue
        for item in row.get("keptItems") or []:
            all_kept.append(row_item_with_source(item, source))

    # 3) Narrow high-confidence same-event dedupe.
    groups = {}
    for item in all_kept:
        topic = explicit_topic_key(item)
        if topic:
            groups.setdefault(topic, []).append(item)

    topic_drops = []
    for topic, group in groups.items():
        if len(group) < 2:
            continue
        winner = max(group, key=representative_score)
        winner_id = stable_id(winner)
        for item in group:
            if stable_id(item) == winner_id:
                continue
            source = item.get("sourceKey")
            row = by_source.get(source)
            reason = f"v6 topic duplicate [{topic}] of {winner.get('canonicalUrl')}"
            if row and move_kept_to_filtered(row, stable_id(item), reason):
                topic_drops.append((item, winner, topic))
            else:
                problems.append(f"dedupe: failed move for {stable_id(item)} topic={topic}")

    # 4) Recompute row counts and ledger invariants.
    for row in rows:
        if row.get("sourceKey") in DIRECT_KEYS:
            continue
        row["keptCount"] = len(row.get("keptItems") or [])
        row["filteredCount"] = len(row.get("filteredItems") or [])
        raw = row.get("rawCount")
        if raw != row["keptCount"] + row["filteredCount"]:
            problems.append(
                f"{row.get('sourceKey')}: raw {raw} != kept {row['keptCount']} + filtered {row['filteredCount']}"
            )

    # 5) Rebuild chronological manifest from row truth.
    manifest = []
    seen = set()
    for row in rows:
        source = row.get("sourceKey")
        if source in DIRECT_KEYS:
            continue
        for item in row.get("keptItems") or []:
            enriched = row_item_with_source(item, source)
            identity = stable_id(enriched)
            if not identity:
                problems.append(f"{source}: kept item missing stable identity")
                continue
            if identity in seen:
                problems.append(f"duplicate stable identity: {identity}")
                continue
            seen.add(identity)
            manifest.append(enriched)

    manifest.sort(key=lambda item: item.get("publishedAt") or "", reverse=True)
    for number, item in enumerate(manifest, 1):
        item["number"] = number

    runner_raw = sum(
        row.get("rawCount") or 0 for row in rows if row.get("sourceKey") not in DIRECT_KEYS
    )
    runner_kept = sum(
        row.get("keptCount") or 0 for row in rows if row.get("sourceKey") not in DIRECT_KEYS
    )
    runner_filtered = sum(
        row.get("filteredCount") or 0 for row in rows if row.get("sourceKey") not in DIRECT_KEYS
    )

    if runner_raw != runner_kept + runner_filtered:
        problems.append(f"runner raw {runner_raw} != kept {runner_kept} + filtered {runner_filtered}")
    if runner_kept != len(manifest):
        problems.append(f"runner kept {runner_kept} != manifest {len(manifest)}")

    missing_evidence = sum(
        1 for item in manifest if item.get("summaryEvidenceStatus") != "rss-description"
    )

    # Preserve original count plus new post-gate drops.
    previous_topic_drops = int(obj.get("topicDuplicateFilteredCount") or 0)
    obj["runnerRawCount"] = runner_raw
    obj["runnerKeptCount"] = runner_kept
    obj["runnerFilteredCount"] = runner_filtered
    obj["runnerManifestCount"] = len(manifest)
    obj["topicDuplicateFilteredCount"] = previous_topic_drops + len(topic_drops)
    obj["summaryEvidenceMissingCount"] = missing_evidence
    obj["manifest"] = manifest
    obj["filterPolicyVersion"] = "2026-08-30-canonical-source-policy-v6-replay-safe"
    obj["version"] = max(int(obj.get("version") or 0), 6)

    render_contract = dict(obj.get("renderContract") or {})
    render_contract.update(
        {
            "version": 3,
            "itemFormat": "N. [Source] [EXACT_SOURCE_TITLE](canonicalUrl) — concise Vietnamese summary",
            "titleClickableRequired": True,
            "titleVerbatimRequired": True,
            "titleRewriteForbidden": True,
            "summaryRequired": True,
            "summaryMustAddBeyondTitleWhenEvidenceAllows": True,
            "summaryEvidenceFirst": True,
            "missingEvidenceAction": "direct-verify canonical URL before writing summary; never silently omit summary and never invent facts",
            "exactManifestNumberingRequired": True,
            "allKeptItemsMustRender": True,
            "sourceAccountingMustReconcileBeforeRender": True,
            "fandomRelationshipDramaForbidden": True,
            "sameEventTopicDedupeRequired": True,
            "relativeDateTimezone": "Asia/Ho_Chi_Minh",
            "historicalManifestArchiveRequired": True,
            "directVerificationSnapshotRequired": True,
            "servedRenderSnapshotRequiredForBitExactReplay": True,
            "replayRule": "If a frozen served render exists for target date/renderId, replay it exactly. Otherwise use the immutable date/hash manifest, complete direct verification, render exact source titles, then freeze the served render.",
        }
    )
    obj["renderContract"] = render_contract
    obj["manifestHash"] = sha256_obj(manifest)
    obj["manifestArchiveKey"] = f"{obj.get('date')}/{obj['manifestHash']}.json"
    obj["replay"] = {
        "timezone": "Asia/Ho_Chi_Minh",
        "relativeDateResolution": {
            "today": "current calendar date in Asia/Ho_Chi_Minh",
            "yesterday": "previous calendar date in Asia/Ho_Chi_Minh",
        },
        "manifestHash": obj["manifestHash"],
        "archiveKey": obj["manifestArchiveKey"],
        "exactTitleSource": "manifest.title",
        "bitExactUserVisibleReplayRequiresServedRenderSnapshot": True,
    }

    inherited = [p for p in (obj.get("problems") or []) if p]
    obj["problems"] = inherited + problems
    obj["runnerAccountingOk"] = not obj["problems"]
    obj["complete15SourceRenderReady"] = False
    contract = dict(obj.get("contract") or {})
    contract.update(
        {
            "titleVerbatimRequired": True,
            "historicalManifestArchiveRequired": True,
            "directVerificationSnapshotRequired": True,
            "servedRenderSnapshotRequiredForBitExactReplay": True,
        }
    )
    obj["contract"] = contract
    return obj


def write_json_atomic(path, obj):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def archive_manifest(obj, archive_root, mode="immutable"):
    archive_root = Path(archive_root)
    date = obj.get("date")
    manifest_hash = obj.get("manifestHash")
    if not date or not manifest_hash:
        raise ValueError("archive requires date and manifestHash")
    date_dir = archive_root / date
    date_dir.mkdir(parents=True, exist_ok=True)
    immutable = date_dir / f"{manifest_hash}.json"
    payload = json.dumps(obj, ensure_ascii=False, indent=2) + "\n"
    if mode == "immutable":
        if immutable.exists():
            existing = immutable.read_text(encoding="utf-8")
            if existing != payload:
                raise RuntimeError(f"immutable manifest collision at {immutable}")
        else:
            immutable.write_text(payload, encoding="utf-8")
    latest = date_dir / "latest.json"
    if mode in {"immutable", "latest"}:
        write_json_atomic(latest, obj)
    index = {
        "version": 1,
        "date": date,
        "timezone": obj.get("timezone"),
        "latestManifestHash": manifest_hash,
        "latestPath": str((immutable if mode == "immutable" else latest)).replace("\\", "/"),
        "archiveMode": mode,
        "runnerRawCount": obj.get("runnerRawCount"),
        "runnerKeptCount": obj.get("runnerKeptCount"),
        "runnerFilteredCount": obj.get("runnerFilteredCount"),
        "runnerManifestCount": obj.get("runnerManifestCount"),
        "topicDuplicateFilteredCount": obj.get("topicDuplicateFilteredCount"),
        "summaryEvidenceMissingCount": obj.get("summaryEvidenceMissingCount"),
        "runnerAccountingOk": obj.get("runnerAccountingOk"),
    }
    if mode in {"immutable", "latest"}:
        write_json_atomic(date_dir / "index.json", index)
    return (immutable if mode == "immutable" else None), (latest if mode in {"immutable", "latest"} else None)


def self_test():
    def mk(source, title, url, evidence="", published="2026-08-29T10:00:00Z"):
        return {
            "key": url,
            "title": title,
            "canonicalUrl": url,
            "publishedAt": published,
            "filterReason": "keep",
            "summaryEvidence": evidence or title,
            "summaryEvidenceStatus": "rss-description",
            "sourceKey": source,
        }

    assert hard_reject_gamek(
        mk("gamek", "Một chi tiết Avengers khiến fan nghi Thanos định xé đôi Iron Man", "https://x/1")
    )
    assert not hard_reject_gamek(
        mk("gamek", "Rockstar công bố GTA 6 trì hoãn đến tháng 11", "https://x/2")
    )

    a = mk("tinhte", "Samsung Galaxy S26 FE mở bán chính hãng từ 28/8, giá từ 18,99 triệu đồng", "https://x/a")
    b = mk("gamek", "Samsung Galaxy S26 FE chính thức bán tại Việt Nam, giá từ 18,99 triệu đồng", "https://x/b")
    assert explicit_topic_key(a) == "galaxy-s26-fe-vn-launch"
    assert explicit_topic_key(b) == "galaxy-s26-fe-vn-launch"

    c = mk("tinhte", "Microsoft: Windows on Arm đã bước sang giai đoạn mới", "https://x/c")
    d = mk("genk", 'Microsoft tuyên bố Windows on Arm thoát mác "nền tảng hạng hai", đã sẵn sàng cho mọi tác vụ', "https://x/d")
    assert explicit_topic_key(c) == "windows-on-arm-maturity-2026"
    assert explicit_topic_key(d) == "windows-on-arm-maturity-2026"

    e = mk("genk", "LG French Door Fit & Max tại Việt Nam", "https://x/e")
    f = mk("tinhte", "Đi coi LG ra mắt tủ lạnh French Door Fit & Max", "https://x/f")
    assert explicit_topic_key(e) == "lg-french-door-fit-max-vn-launch"
    assert explicit_topic_key(f) == "lg-french-door-fit-max-vn-launch"

    # Title is data, never normalized/rewritten in the manifest.
    original = 'Tiêu đề GỐC: giữ nguyên "100%"'
    item = mk("tinhte", original, "https://x/title")
    assert item["title"] == original

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
        print(json.dumps({"selfTest": True, "status": "pass"}))
        return 0

    if not args.manifest or not args.out:
        parser.error("--manifest and --out are required unless --self-test is used")

    source = Path(args.manifest)
    obj = json.loads(source.read_text(encoding="utf-8"))
    finalized = rebuild_manifest(copy.deepcopy(obj))
    write_json_atomic(args.out, finalized)
    immutable, latest = archive_manifest(finalized, args.archive_root, args.archive_mode)
    print(
        json.dumps(
            {
                "date": finalized.get("date"),
                "runnerRawCount": finalized.get("runnerRawCount"),
                "runnerKeptCount": finalized.get("runnerKeptCount"),
                "runnerFilteredCount": finalized.get("runnerFilteredCount"),
                "runnerManifestCount": finalized.get("runnerManifestCount"),
                "topicDuplicateFilteredCount": finalized.get("topicDuplicateFilteredCount"),
                "summaryEvidenceMissingCount": finalized.get("summaryEvidenceMissingCount"),
                "runnerAccountingOk": finalized.get("runnerAccountingOk"),
                "manifestHash": finalized.get("manifestHash"),
                "archiveMode": args.archive_mode,
                "immutableArchive": str(immutable) if immutable else None,
                "latestArchive": str(latest) if latest else None,
            },
            ensure_ascii=False,
        )
    )
    return 0 if finalized.get("runnerAccountingOk") else 2


if __name__ == "__main__":
    raise SystemExit(main())
