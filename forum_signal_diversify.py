#!/usr/bin/env python3

import argparse
import json
from collections import Counter
from pathlib import Path


def load_jsonl(path):
    p = Path(path)
    if not p.exists():
        return []
    rows = []
    for line in p.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def write_jsonl(path, rows):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def main():
    ap = argparse.ArgumentParser(description="Prevent mega threads from dominating Forum Signal candidates")
    ap.add_argument("--input", default="crawl_output/forum_insight_candidates.jsonl")
    ap.add_argument("--audit", default="crawl_output/forum_f91_diversity.json")
    ap.add_argument("--source", default="VOZ-F91")
    ap.add_argument("--per-thread", type=int, default=3)
    ap.add_argument("--source-cap", type=int, default=36)
    args = ap.parse_args()

    if not 1 <= args.per_thread <= 20:
        raise SystemExit("per-thread must be 1..20")
    if not 1 <= args.source_cap <= 200:
        raise SystemExit("source-cap must be 1..200")

    rows = load_jsonl(args.input)
    rows.sort(key=lambda r: (-float(r.get("score") or 0), str(r.get("source") or ""), str(r.get("thread_title") or "")))

    kept = []
    dropped = []
    thread_counts = Counter()
    source_count = 0

    for row in rows:
        if str(row.get("source") or "") != args.source:
            kept.append(row)
            continue
        key = str(row.get("thread_key") or row.get("thread_title") or "")
        if thread_counts[key] >= args.per_thread:
            item = dict(row)
            item["diversity_rejection"] = "per_thread_cap"
            dropped.append(item)
            continue
        if source_count >= args.source_cap:
            item = dict(row)
            item["diversity_rejection"] = "source_cap"
            dropped.append(item)
            continue
        thread_counts[key] += 1
        source_count += 1
        kept.append(row)

    write_jsonl(args.input, kept)
    audit = {
        "diversifier": "forum-signal-diversify-v1",
        "source": args.source,
        "input_rows": len(rows),
        "output_rows": len(kept),
        "source_rows_kept": source_count,
        "source_threads_kept": len(thread_counts),
        "per_thread_cap": args.per_thread,
        "source_cap": args.source_cap,
        "dropped": len(dropped),
        "drop_reasons": dict(Counter(x.get("diversity_rejection") for x in dropped)),
    }
    Path(args.audit).write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(audit, ensure_ascii=False))


if __name__ == "__main__":
    main()
