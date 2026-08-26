#!/usr/bin/env python3

import argparse
import hashlib
import json
import re
from collections import Counter
from pathlib import Path

import forum_signal_score as base


F91_SOURCE = "VOZ-F91"
TECH = [
    "ai", "llm", "claude", "codex", "cursor", "vibe code", "vibe coding", "agent", "agentic", "mcp",
    "api", "openrouter", "backend", "frontend", "fullstack", "database", "data engineer", "data analyst",
    "devops", "sre", "cloud", "aws", "azure", "gcp", "kubernetes", "docker", "terraform", "linux",
    "security", "cybersecurity", "bug", "performance", "benchmark", "qa", "tester", "automation test",
    "embedded", "firmware", "vi mạch", "semiconductor", "system design", "microservice", "redis", "kafka",
]
CAREER = [
    "lương", "salary", "offer", "deal lương", "phỏng vấn", "interview", "công ty", "company", "hr",
    "fresher", "intern", "senior", "staff", "remote", "hybrid", "outsourcing", "outsource", "nhảy việc",
    "sa thải", "layoff", "career", "nghề", "kinh nghiệm", "tuyển dụng", "apply", "cv", "thạc sĩ", "xuất ngoại",
]
LISTING = [
    "ib cv", "gửi cv", "send cv", "apply now", "job description", "requirements:", "responsibilities:",
    "degree in", "proven experience", "we are hiring", "đang tuyển", "tuyển fresher", "tuyển senior",
]


def norm(value):
    return re.sub(r"\s+", " ", str(value or "")).strip().lower()


def load_jsonl(path):
    p = Path(path)
    if not p.exists():
        return []
    return [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines() if x.strip()]


def write_jsonl(path, rows):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def row_key(row):
    fp = str(row.get("fingerprint") or "").strip()
    if fp:
        return fp
    raw = "|".join([
        str(row.get("source") or ""),
        str(row.get("thread_key") or ""),
        str(row.get("post_id") or ""),
        norm(row.get("text")),
    ])
    return hashlib.sha1(raw.encode("utf-8", errors="ignore")).hexdigest()


def marker_hits(text, markers):
    return sorted({m for m in markers if m in text})


def main():
    ap = argparse.ArgumentParser(description="Add F91-specific technical/career insight candidates")
    ap.add_argument("--raw", default="crawl_output/forum_signal.jsonl")
    ap.add_argument("--candidates", default="crawl_output/forum_insight_candidates.jsonl")
    ap.add_argument("--audit", default="crawl_output/forum_f91_candidate_boost.json")
    ap.add_argument("--min-score", type=float, default=3.0)
    ap.add_argument("--max-age-hours", type=float, default=72.0)
    args = ap.parse_args()

    existing = load_jsonl(args.candidates)
    raw = [r for r in load_jsonl(args.raw) if str(r.get("source") or "") == F91_SOURCE]
    delta_counts = Counter(str(r.get("thread_key") or "") for r in raw)

    boosted = []
    listing_rejected = 0
    for row in raw:
        text = norm(row.get("text"))
        title = norm(row.get("thread_title"))
        joined = f"{title} {text}"
        tech = marker_hits(joined, TECH)
        career = marker_hits(joined, CAREER)
        domain = sorted(set(tech + career))
        if not domain:
            continue

        meta = base.score_row(row, args.max_age_hours)
        if not meta.get("fresh", True) or meta.get("signal_type") in {"stale", "timestamp_error"}:
            continue

        n = len(str(row.get("text") or "").strip())
        reasoning = meta.get("reasoning_hits") or []
        firsthand = meta.get("firsthand_hits") or []
        numeric = int(meta.get("numeric_count") or 0)

        looks_listing = any(m in text for m in LISTING)
        if looks_listing and not reasoning and not firsthand:
            listing_rejected += 1
            continue

        # Require substance: domain vocabulary alone is not enough.
        if n < 90 and not firsthand and not reasoning:
            continue
        if len(domain) < 2 and n < 160 and not firsthand:
            continue

        bonus = 0.0
        bonus += min(0.75, 0.18 * len(domain))
        if n >= 140:
            bonus += 0.3
        if n >= 300:
            bonus += 0.2
        if reasoning:
            bonus += min(0.45, 0.15 * len(reasoning))
        if firsthand:
            bonus += min(0.45, 0.2 * len(firsthand))
        if numeric:
            bonus += min(0.3, 0.08 * numeric)
        if tech and career:
            bonus += 0.25

        item = dict(row)
        item.update(meta)
        item["score"] = round(min(5.0, float(meta.get("score") or 0) + bonus), 2)
        if item["score"] < args.min_score:
            continue
        item["scorer"] = "forum-signal-f91-v1"
        item["f91_domain_hits"] = domain[:16]
        item["thread_delta_posts"] = delta_counts[str(row.get("thread_key") or "")]
        item["consensus_candidate"] = False
        boosted.append(item)

    merged = {}
    for row in existing + boosted:
        key = row_key(row)
        current = merged.get(key)
        if current is None or float(row.get("score") or 0) > float(current.get("score") or 0):
            merged[key] = row
    rows = list(merged.values())
    rows.sort(key=lambda r: (-float(r.get("score") or 0), str(r.get("source") or ""), str(r.get("thread_title") or "")))

    kept_counts = Counter(str(r.get("thread_key") or "") for r in rows if str(r.get("source") or "") == F91_SOURCE)
    for row in rows:
        if str(row.get("source") or "") == F91_SOURCE:
            row["consensus_candidate"] = kept_counts[str(row.get("thread_key") or "")] >= 3

    write_jsonl(args.candidates, rows)
    audit = {
        "scorer": "forum-signal-f91-v1",
        "raw_f91_rows": len(raw),
        "existing_candidates": len(existing),
        "boosted_candidates": len(boosted),
        "merged_candidates": len(rows),
        "f91_candidates_after_merge": sum(1 for r in rows if str(r.get("source") or "") == F91_SOURCE),
        "f91_threads_after_merge": len({str(r.get("thread_key") or "") for r in rows if str(r.get("source") or "") == F91_SOURCE}),
        "listing_rejected": listing_rejected,
        "min_score": args.min_score,
        "max_age_hours": args.max_age_hours,
    }
    Path(args.audit).write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(audit, ensure_ascii=False))


if __name__ == "__main__":
    main()
