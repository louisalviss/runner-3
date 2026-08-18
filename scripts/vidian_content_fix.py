#!/usr/bin/env python3
import argparse
import hashlib
import json
import random
import re
from collections import Counter, defaultdict
from pathlib import Path

import vidian_pipeline as vp
import vidian_snapshot as vs
import vidian_semantic_snapshot as vss

UI_NOISE = {"video", "rank", "tìm kiếm", "chat", "user"}
STOP_PREFIXES = (
    "từ khóa",
    "ủng hộ tác giả",
    "thư hữu cần",
    "bài viết ngẫu nhiên",
    "tiên hiền thư viện",
    "liên hệ quảng cáo",
)
META_PREFIXES = (
    "tác giả", "người làm", "người dịch", "dịch giả", "dịch", "convert",
    "biên tập", "sưu tầm", "thể loại", "nguồn", "editor", "translator",
)
KNOWN_REGRESSIONS = {
    "https://vidian.vn/chi-tiet/de-ba-toan-tap-phan-i": ("Cửu Đại Thiên Bảo", "Giới thiệu"),
    "https://vidian.vn/chi-tiet/de-ba-toan-tap-phan-ii": ("Cửu Giới", "Thế Giới"),
}


def norm(text):
    return vp.clean(text or "")


def meaningful_fragment(text):
    text = norm(text)
    if not text:
        return False
    if text.lower() in UI_NOISE:
        return False
    if re.fullmatch(r"[\W_]+", text, flags=re.UNICODE):
        return False
    if re.fullmatch(r"\d+[.)]?", text):
        return False
    # Common decorative separators such as ---o0o---, ====, ....
    compact = re.sub(r"\s+", "", text).lower()
    if compact and re.fullmatch(r"[-_=*.·•…o0]+", compact):
        return False
    return bool(re.search(r"[0-9A-Za-zÀ-ỹĐđ]", text))


def is_marker_v2(text):
    low = norm(text).lower().strip(" :-–—")
    # IMPORTANT: `Nguồn:` can appear before the actual article body on Vidian,
    # so it must never terminate extraction. We stop at the real post-body UI.
    return any(low == p or low.startswith(p + ":") or low.startswith(p + " ") for p in STOP_PREFIXES)


def extract_v2(root):
    for node in root.xpath("//script|//style|//noscript|//template|//svg|//form"):
        try:
            node.drop_tree()
        except Exception:
            pass
    h1s = root.xpath("//h1[1]")
    if not h1s:
        raise ValueError("missing-h1")
    h1 = h1s[0]
    paras, buf = [], []
    last_parent = None

    def flush():
        nonlocal buf
        text = norm(" ".join(buf))
        buf = []
        if meaningful_fragment(text):
            paras.append(text)

    for node in h1.xpath("following::text()"):
        parent = node.getparent()
        text = norm(str(node))
        if not text:
            continue
        if is_marker_v2(text):
            flush()
            break
        if text.lower() in UI_NOISE:
            continue
        pid = id(parent)
        if last_parent is not None and pid != last_parent:
            flush()
        buf.append(text)
        last_parent = pid
    flush()
    if sum(map(len, paras)) < 20:
        raise ValueError("article-region-too-short")
    return paras


def sentence_split_v2(text):
    text = norm(text)
    if not meaningful_fragment(text):
        return []
    raw = re.split(r'(?<=[.!?…])\s+(?=[A-ZÀ-ỸĐ0-9“"(\[])', text)
    out = [norm(x) for x in raw if meaningful_fragment(x)]
    return out or [text]


def patch_runtime():
    vp.is_marker = is_marker_v2
    vp.extract = extract_v2
    vp.sentence_split = sentence_split_v2


def load_snapshot_files(root):
    files = sorted(Path(root).rglob("vidian_snapshot_chunk_*.jsonl"))
    if not files:
        raise SystemExit(f"no snapshot files under {root}")
    rows = []
    for path in files:
        m = re.search(r"chunk_(\d+)\.jsonl$", path.name)
        if not m:
            continue
        chunk = int(m.group(1))
        for line in path.open(encoding="utf-8"):
            if line.strip():
                rec = json.loads(line)
                rec["_chunk"] = chunk
                rows.append(rec)
    return files, rows


def metadata_tail(paras):
    tail = [norm(x).lower() for x in paras[-4:]]
    return any(any(x.startswith(p + ":") or x == p for p in META_PREFIXES) for x in tail)


def audit(args):
    files, rows = load_snapshot_files(args.input)
    fetched = [r for r in rows if r.get("status") == "fetched"]
    if len(fetched) != args.expected:
        raise SystemExit(f"expected {args.expected} fetched rows, got {len(fetched)}")
    by_hash = defaultdict(list)
    for r in fetched:
        by_hash[r.get("clean_body_sha256", "")].append(r["url"])
    duplicate_urls = {u for h, us in by_hash.items() if h and len(us) > 1 for u in us}

    metrics = {}
    suspects = {}
    for r in fetched:
        paras = r.get("paragraphs") or []
        chars = sum(len(norm(x)) for x in paras)
        pc = len(paras)
        reasons = []
        if pc <= args.max_paragraphs:
            reasons.append(f"paragraphs<={args.max_paragraphs}")
        if chars <= args.max_chars:
            reasons.append(f"chars<={args.max_chars}")
        if metadata_tail(paras):
            reasons.append("metadata-tail")
        if r["url"] in duplicate_urls:
            reasons.append("duplicate-body-hash")
        if r["url"] in KNOWN_REGRESSIONS:
            reasons.append("known-regression")
        metrics[r["url"]] = {
            "url": r["url"],
            "chunk": r["_chunk"],
            "old_paragraph_count": pc,
            "old_chars": chars,
            "old_hash": r.get("clean_body_sha256", ""),
            "reasons": reasons,
        }
        if reasons:
            suspects[r["url"]] = metrics[r["url"]]

    # Deterministic stratified holdout: refetch non-suspects only for coverage QA.
    rng = random.Random(args.seed)
    by_chunk = defaultdict(list)
    for r in fetched:
        if r["url"] not in suspects:
            by_chunk[r["_chunk"]].append(r["url"])
    sample_urls = []
    for chunk in range(64):
        pool = sorted(by_chunk.get(chunk, []))
        rng.shuffle(pool)
        sample_urls.extend(pool[: args.sample_per_chunk])
    for url in sample_urls:
        item = metrics[url]
        item["reasons"] = ["qa-sample"]
        suspects[url] = item

    records = sorted(suspects.values(), key=lambda x: (x["chunk"], x["url"]))
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    payload = {
        "expected": args.expected,
        "snapshot_files": len(files),
        "records_scanned": len(fetched),
        "candidate_count": len(records),
        "qa_sample_count": len(sample_urls),
        "suspect_without_samples": len(records) - len(sample_urls),
        "duplicate_body_hash_urls": len(duplicate_urls),
        "max_paragraphs": args.max_paragraphs,
        "max_chars": args.max_chars,
        "sample_per_chunk": args.sample_per_chunk,
        "records": records,
    }
    (out / "candidates.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    reason_counts = Counter(reason for r in records for reason in r["reasons"])
    summary = {
        k: payload[k] for k in (
            "expected", "snapshot_files", "records_scanned", "candidate_count",
            "qa_sample_count", "suspect_without_samples", "duplicate_body_hash_urls",
            "max_paragraphs", "max_chars", "sample_per_chunk",
        )
    }
    summary["reason_counts"] = dict(reason_counts)
    (out / "audit_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False), flush=True)


def refresh(args):
    patch_runtime()
    candidates = json.loads(Path(args.candidates).read_text(encoding="utf-8"))["records"]
    targets = {r["url"] for r in candidates if int(r["chunk"]) == args.index}
    path = Path(args.snapshot)
    rows = []
    for line in path.open(encoding="utf-8"):
        if line.strip():
            rec = json.loads(line)
            if rec.get("url") in targets:
                rec["status"] = "refresh-needed"
            rows.append(rec)
    with path.open("w", encoding="utf-8") as f:
        for rec in rows:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    print(json.dumps({"chunk": args.index, "refresh_targets": len(targets)}), flush=True)
    vs.run(
        args.inventory, args.out, args.index, 64,
        args.passes, args.delay, args.timeout, str(path), True,
        args.cooldown_429, args.max_429_retries,
    )
    # Hard validation after retry loop.
    output = Path(args.out) / f"vidian_snapshot_chunk_{args.index:02d}.jsonl"
    out_rows = [json.loads(x) for x in output.read_text(encoding="utf-8").splitlines() if x.strip()]
    bad = [r for r in out_rows if r.get("status") != "fetched"]
    if bad:
        raise SystemExit(f"chunk {args.index}: {len(bad)} rows still incomplete")


def coverage(args):
    payload = json.loads(Path(args.candidates).read_text(encoding="utf-8"))
    _, rows = load_snapshot_files(args.snapshots)
    new = {r["url"]: r for r in rows}
    sample_expansions = []
    known = {}
    changed = expanded = 0
    for item in payload["records"]:
        r = new.get(item["url"])
        if not r or r.get("status") != "fetched":
            raise SystemExit(f"missing refreshed row: {item['url']}")
        paras = r.get("paragraphs") or []
        new_chars = sum(len(norm(x)) for x in paras)
        old_chars = int(item.get("old_chars", 0))
        delta = new_chars - old_chars
        ratio = new_chars / max(1, old_chars)
        if r.get("clean_body_sha256") != item.get("old_hash"):
            changed += 1
        if delta > 500 and ratio > 1.35:
            expanded += 1
            if item.get("reasons") == ["qa-sample"]:
                sample_expansions.append({
                    "url": item["url"], "old_chars": old_chars,
                    "new_chars": new_chars, "ratio": round(ratio, 3),
                })
        if item["url"] in KNOWN_REGRESSIONS:
            text = "\n".join(paras)
            needles = KNOWN_REGRESSIONS[item["url"]]
            known[item["url"]] = {
                "old_chars": old_chars,
                "new_chars": new_chars,
                "hash_changed": r.get("clean_body_sha256") != item.get("old_hash"),
                "needles_found": {needle: needle.lower() in text.lower() for needle in needles},
            }

    stop_leaks = []
    separator_paras = 0
    for r in rows:
        for p in r.get("paragraphs") or []:
            low = norm(p).lower().strip(" :-–—")
            if any(low.startswith(x) for x in ("ủng hộ tác giả", "thư hữu cần", "bài viết ngẫu nhiên", "liên hệ quảng cáo")):
                stop_leaks.append(r["url"])
            if not meaningful_fragment(p):
                separator_paras += 1

    summary = {
        "records": len(rows),
        "refreshed_candidates": len(payload["records"]),
        "changed_candidates": changed,
        "materially_expanded_candidates": expanded,
        "qa_sample_material_expansions": sample_expansions,
        "known_regressions": known,
        "stop_marker_leaks": len(set(stop_leaks)),
        "separator_only_paragraphs": separator_paras,
    }
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "coverage_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False), flush=True)
    if len(rows) != payload["expected"]:
        raise SystemExit(f"coverage snapshot count mismatch: {len(rows)}")
    if sample_expansions:
        raise SystemExit(f"coverage holdout detected {len(sample_expansions)} missed truncations; broaden candidate set")
    if stop_leaks:
        raise SystemExit(f"post-body UI leaked into {len(set(stop_leaks))} snapshots")
    for url, check in known.items():
        if not check["hash_changed"] or not all(check["needles_found"].values()):
            raise SystemExit(f"known regression still broken: {url}: {check}")


def semantic(args):
    patch_runtime()
    vss.run(args.snapshot, args.out, args.index, 64, args.parse_group_size)


def qa(args):
    corpus = Path(args.corpus)
    summary = json.loads((corpus / "summary.json").read_text(encoding="utf-8"))
    manifest = json.loads((corpus / "manifest.json").read_text(encoding="utf-8"))
    if summary.get("records") != args.expected or summary.get("unique_urls") != args.expected:
        raise SystemExit(f"corpus count mismatch: {summary}")
    if summary.get("failed_articles") != 0:
        raise SystemExit(f"failed articles remain: {summary.get('failed_articles')}")
    if len({r["url"] for r in manifest}) != args.expected:
        raise SystemExit("manifest URL uniqueness failed")
    dup = defaultdict(list)
    for r in manifest:
        h = r.get("clean_body_sha256", "")
        if h:
            dup[h].append(r["url"])
    duplicate_groups = [us for us in dup.values() if len(us) > 1]
    known_manifest = {r["url"]: r for r in manifest if r["url"] in KNOWN_REGRESSIONS}
    report = {
        "records": summary.get("records"),
        "unique_urls": summary.get("unique_urls"),
        "failed_articles": summary.get("failed_articles"),
        "total_sentences": summary.get("total_sentences"),
        "parse_failed_sentences": summary.get("parse_failed_sentences"),
        "parse_rate": summary.get("parse_rate"),
        "duplicate_body_hash_groups": len(duplicate_groups),
        "known_regressions_manifest": known_manifest,
    }
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "final_qa.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False), flush=True)


def smoke(_args):
    from lxml import html
    fixture = """
    <html><body><h1>Test</h1>
      <p>Tác giả: A</p><p>Nguồn: Tàng Thư Viện</p>
      <p>Giới thiệu:</p><ul><li>Cửu Giới</li><li>Hư Không môn → A2</li><li>---</li></ul>
      <p>Nguồn: TIÊN HIỀN THƯ VIỆN</p><p>Từ khóa: test</p>
      <p>ỦNG HỘ TÁC GIẢ</p><p>comment must not leak</p>
    </body></html>
    """
    paras = extract_v2(html.fromstring(fixture.encode()))
    text = "\n".join(paras)
    assert "Nguồn: Tàng Thư Viện" in text, paras
    assert "Giới thiệu" in text and "Cửu Giới" in text and "Hư Không môn" in text, paras
    assert "Từ khóa" not in text and "comment must not leak" not in text, paras
    assert "---" not in paras, paras
    assert sentence_split_v2("Cửu Giới") == ["Cửu Giới"]
    assert sentence_split_v2("---") == []
    print(json.dumps({"content_fix_smoke": "ok", "paragraphs": paras}, ensure_ascii=False), flush=True)


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("smoke")
    p.set_defaults(func=smoke)

    p = sub.add_parser("audit")
    p.add_argument("--input", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--expected", type=int, default=8826)
    p.add_argument("--max-paragraphs", type=int, default=12)
    p.add_argument("--max-chars", type=int, default=2500)
    p.add_argument("--sample-per-chunk", type=int, default=3)
    p.add_argument("--seed", type=int, default=260816)
    p.set_defaults(func=audit)

    p = sub.add_parser("refresh")
    p.add_argument("--inventory", required=True)
    p.add_argument("--snapshot", required=True)
    p.add_argument("--candidates", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--index", type=int, required=True)
    p.add_argument("--passes", type=int, default=6)
    p.add_argument("--delay", type=float, default=0.6)
    p.add_argument("--timeout", type=float, default=15)
    p.add_argument("--cooldown-429", type=float, default=40)
    p.add_argument("--max-429-retries", type=int, default=8)
    p.set_defaults(func=refresh)

    p = sub.add_parser("coverage")
    p.add_argument("--candidates", required=True)
    p.add_argument("--snapshots", required=True)
    p.add_argument("--out", required=True)
    p.set_defaults(func=coverage)

    p = sub.add_parser("semantic")
    p.add_argument("--snapshot", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--index", type=int, required=True)
    p.add_argument("--parse-group-size", type=int, default=512)
    p.set_defaults(func=semantic)

    p = sub.add_parser("qa")
    p.add_argument("--corpus", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--expected", type=int, default=8826)
    p.set_defaults(func=qa)

    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
