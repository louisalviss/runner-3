#!/usr/bin/env python3
"""Validate and freeze exact user-visible RSS renders.

A served render snapshot is the only authority for bit-exact replay of titles,
numbering, links and Vietnamese summaries. The Runner13 kept manifest remains
the authority for runner item identities; direct-source items are supplied by
the explicit direct audit.
"""

import argparse
import hashlib
import json
from pathlib import Path

DIRECT_KEYS = {"hoquoctuan", "vnhacker"}


def canonical_json(obj):
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256_obj(obj):
    return hashlib.sha256(canonical_json(obj).encode("utf-8")).hexdigest()


def stable_id(item):
    return item.get("key") or item.get("canonicalUrl")


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_atomic(path, obj):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def validate_direct_audit(audit, target_date):
    problems = []
    if audit.get("targetDate") != target_date:
        problems.append(f"direct audit targetDate={audit.get('targetDate')} expected={target_date}")
    rows = audit.get("sources") or []
    by_key = {row.get("sourceKey"): row for row in rows}
    for source in sorted(DIRECT_KEYS):
        row = by_key.get(source)
        if not row:
            problems.append(f"direct audit missing {source}")
            continue
        if row.get("status") not in {"checked", "ok"}:
            problems.append(f"direct audit {source} status={row.get('status')}")
        if not row.get("checkedAt"):
            problems.append(f"direct audit {source} missing checkedAt")
        kept = row.get("keptItems") or []
        for item in kept:
            if not item.get("title") or not item.get("canonicalUrl"):
                problems.append(f"direct audit {source} kept item missing title/url")
    return problems, by_key


def build_snapshot(manifest, direct_audit, rendered):
    problems = []
    target_date = manifest.get("date")
    if rendered.get("targetDate") != target_date:
        problems.append(f"render targetDate={rendered.get('targetDate')} expected={target_date}")
    if rendered.get("timezone") != "Asia/Ho_Chi_Minh":
        problems.append(f"render timezone={rendered.get('timezone')} expected=Asia/Ho_Chi_Minh")

    direct_problems, direct_by_key = validate_direct_audit(direct_audit, target_date)
    problems.extend(direct_problems)

    runner = manifest.get("manifest") or []
    runner_by_id = {stable_id(item): item for item in runner}
    direct_items = []
    for source, row in direct_by_key.items():
        for item in row.get("keptItems") or []:
            enriched = dict(item)
            enriched["sourceKey"] = source
            direct_items.append(enriched)
    expected_by_id = dict(runner_by_id)
    for item in direct_items:
        identity = stable_id(item)
        if not identity:
            problems.append(f"direct item {item.get('sourceKey')} missing identity")
            continue
        if identity in expected_by_id:
            problems.append(f"direct item duplicate identity with runner: {identity}")
        expected_by_id[identity] = item

    items = rendered.get("items") or []
    if len(items) != len(expected_by_id):
        problems.append(f"rendered count {len(items)} != expected {len(expected_by_id)}")

    numbers = [item.get("number") for item in items]
    if numbers != list(range(1, len(items) + 1)):
        problems.append("render numbering is not contiguous 1..N")

    seen = set()
    for out in items:
        identity = stable_id(out)
        if not identity:
            problems.append(f"render item #{out.get('number')} missing stable identity")
            continue
        if identity in seen:
            problems.append(f"render duplicate identity {identity}")
            continue
        seen.add(identity)
        source = expected_by_id.get(identity)
        if not source:
            problems.append(f"render item #{out.get('number')} not present in runner/direct ledger: {identity}")
            continue
        if out.get("title") != source.get("title"):
            problems.append(f"render item #{out.get('number')} title rewritten; verbatim title required")
        if out.get("canonicalUrl") != source.get("canonicalUrl"):
            problems.append(f"render item #{out.get('number')} canonicalUrl mismatch")
        if out.get("sourceKey") != source.get("sourceKey"):
            problems.append(f"render item #{out.get('number')} sourceKey mismatch")
        summary = (out.get("summary") or "").strip()
        if not summary:
            problems.append(f"render item #{out.get('number')} missing summary")

    missing = set(expected_by_id) - seen
    if missing:
        problems.append(f"render missing {len(missing)} expected identities")

    expected_order = sorted(
        expected_by_id.values(),
        key=lambda item: item.get("publishedAt") or "",
        reverse=True,
    )
    expected_ids = [stable_id(item) for item in expected_order]
    actual_ids = [stable_id(item) for item in items]
    if actual_ids != expected_ids:
        problems.append("render order differs from chronological runner+direct ledger")

    snapshot_core = {
        "schemaVersion": 1,
        "scope": "rss-served-render",
        "targetDate": target_date,
        "timezone": "Asia/Ho_Chi_Minh",
        "manifestHash": manifest.get("manifestHash"),
        "sourceManifestArchiveKey": manifest.get("manifestArchiveKey"),
        "directAudit": direct_audit,
        "items": items,
        "itemCount": len(items),
        "contract": {
            "titleVerbatim": True,
            "clickableCanonicalUrl": True,
            "summaryRequired": True,
            "exactNumbering": True,
            "chronologicalOrder": True,
            "bitExactReplayAuthority": True,
        },
    }
    render_hash = sha256_obj(snapshot_core)
    snapshot = dict(snapshot_core)
    snapshot["renderHash"] = render_hash
    snapshot["problems"] = problems
    snapshot["valid"] = not problems
    return snapshot


def freeze(snapshot, root):
    if not snapshot.get("valid"):
        raise ValueError("cannot freeze invalid render snapshot")
    date = snapshot["targetDate"]
    render_hash = snapshot["renderHash"]
    date_dir = Path(root) / date
    date_dir.mkdir(parents=True, exist_ok=True)
    immutable = date_dir / f"{render_hash}.json"
    payload = json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n"
    if immutable.exists():
        if immutable.read_text(encoding="utf-8") != payload:
            raise RuntimeError(f"immutable render collision at {immutable}")
    else:
        immutable.write_text(payload, encoding="utf-8")
    write_atomic(date_dir / "latest.json", snapshot)
    write_atomic(
        date_dir / "index.json",
        {
            "schemaVersion": 1,
            "targetDate": date,
            "latestRenderHash": render_hash,
            "latestPath": str(immutable).replace("\\", "/"),
            "itemCount": snapshot["itemCount"],
            "valid": True,
        },
    )
    return immutable


def self_test():
    manifest = {
        "date": "2026-08-29",
        "manifestHash": "abc",
        "manifestArchiveKey": "2026-08-29/abc.json",
        "manifest": [
            {
                "key": "id:1",
                "sourceKey": "tinhte",
                "title": "Tiêu đề GỐC",
                "canonicalUrl": "https://example.com/1",
                "publishedAt": "2026-08-29T10:00:00Z",
            }
        ],
    }
    audit = {
        "targetDate": "2026-08-29",
        "sources": [
            {"sourceKey": "hoquoctuan", "status": "checked", "checkedAt": "2026-08-30T00:00:00Z", "keptItems": []},
            {"sourceKey": "vnhacker", "status": "checked", "checkedAt": "2026-08-30T00:00:00Z", "keptItems": []},
        ],
    }
    rendered = {
        "targetDate": "2026-08-29",
        "timezone": "Asia/Ho_Chi_Minh",
        "items": [
            {
                "number": 1,
                "key": "id:1",
                "sourceKey": "tinhte",
                "title": "Tiêu đề GỐC",
                "canonicalUrl": "https://example.com/1",
                "publishedAt": "2026-08-29T10:00:00Z",
                "summary": "Tóm tắt tiếng Việt.",
            }
        ],
    }
    good = build_snapshot(manifest, audit, rendered)
    assert good["valid"], good["problems"]
    bad = json.loads(json.dumps(rendered, ensure_ascii=False))
    bad["items"][0]["title"] = "Tiêu đề đã sửa"
    bad_snap = build_snapshot(manifest, audit, bad)
    assert not bad_snap["valid"]
    assert any("title rewritten" in p for p in bad_snap["problems"])


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--manifest")
    p.add_argument("--direct-audit")
    p.add_argument("--rendered")
    p.add_argument("--out-root", default="data/rss-reader/renders")
    p.add_argument("--self-test", action="store_true")
    args = p.parse_args()
    if args.self_test:
        self_test()
        print(json.dumps({"selfTest": True, "status": "pass"}))
        return 0
    if not args.manifest or not args.direct_audit or not args.rendered:
        p.error("--manifest, --direct-audit and --rendered are required")
    snapshot = build_snapshot(load(args.manifest), load(args.direct_audit), load(args.rendered))
    if not snapshot["valid"]:
        print(json.dumps(snapshot, ensure_ascii=False))
        return 2
    path = freeze(snapshot, args.out_root)
    print(json.dumps({"valid": True, "renderHash": snapshot["renderHash"], "path": str(path)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
