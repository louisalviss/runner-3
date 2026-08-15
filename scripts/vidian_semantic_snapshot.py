#!/usr/bin/env python3
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import vidian_pipeline as vp


def run(snapshot_path, outdir, index, count, parse_group_size):
    rows = []
    for line in Path(snapshot_path).open(encoding="utf-8"):
        if line.strip():
            rows.append(json.loads(line))
    if not rows:
        raise SystemExit("snapshot is empty")
    bad = [r for r in rows if r.get("status") != "fetched" or not r.get("paragraphs")]
    if bad:
        raise SystemExit(f"snapshot contains {len(bad)} incomplete articles")

    prepared = []
    for r in rows:
        prepared.append({
            "url": r["url"],
            "listing_title": r.get("listing_title", ""),
            "status": "fetched",
            "http_status": r.get("http_status", 200),
            "title": r.get("title", ""),
            "paragraph_count": r.get("paragraph_count", len(r.get("paragraphs", []))),
            "sentence_count": 0,
            "parse_success_sentences": 0,
            "parse_failed_sentences": 0,
            "sections": [],
            "source_prose_persisted": False,
            "schema": "semantic-reconstruction-frames-v3",
            "html_sha256": r.get("html_sha256", ""),
            "clean_body_sha256": r.get("clean_body_sha256", ""),
            "fetch_elapsed_sec": r.get("fetch_elapsed_sec", 0),
            "_paragraphs": r["paragraphs"],
        })

    semantic_started = datetime.now(timezone.utc)
    prepared = vp.semanticize_prepared(prepared, parse_group_size=parse_group_size)
    out = Path(outdir)
    out.mkdir(parents=True, exist_ok=True)
    p = out / f"vidian_semantic_frame_chunk_{index:02d}.jsonl"
    total = parsed = parse_failed = failed_articles = 0
    with p.open("w", encoding="utf-8", buffering=1) as f:
        for rec in prepared:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            total += rec.get("sentence_count", 0)
            parsed += rec.get("parse_success_sentences", 0)
            parse_failed += rec.get("parse_failed_sentences", 0)
            if rec.get("status") not in {"ok", "partial-parse"}:
                failed_articles += 1
    rate = parsed / total if total else 0
    summary = {
        "chunk": index,
        "chunks": count,
        "rows": len(prepared),
        "failed_articles": failed_articles,
        "sentences": total,
        "parse_success": parsed,
        "parse_failed": parse_failed,
        "parse_rate": rate,
        "semantic_started_utc": semantic_started.isoformat(),
        "completed_utc": datetime.now(timezone.utc).isoformat(),
        "network_requests_to_vidian": 0,
    }
    (out / f"chunk_{index:02d}_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False), flush=True)
    if failed_articles:
        raise SystemExit(f"semantic output contains {failed_articles} failed articles")
    if total == 0 or rate < .95:
        raise SystemExit(f"dependency parse rate too low: {rate:.4f}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--snapshot", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--index", type=int, required=True)
    ap.add_argument("--count", type=int, default=32)
    ap.add_argument("--parse-group-size", type=int, default=512)
    a = ap.parse_args()
    run(a.snapshot, a.out, a.index, a.count, a.parse_group_size)


if __name__ == "__main__":
    main()
