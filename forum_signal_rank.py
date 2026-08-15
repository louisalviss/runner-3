#!/usr/bin/env python3

import argparse
import json
import math
import re
import sys
import time
from pathlib import Path

import forum_signal_v2 as base
from crawler import DEFAULT_UA, now_iso

NUMERIC_SIGNAL_RE = re.compile(
    r"(?:\b\d+(?:[.,]\d+)?\s*(?:%|km|km/h|kwh|wh|mah|gb|tb|fps|hz|khz|triệu|tỷ|tr|usd|vnd|đồng)\b|\brc\d+\b)",
    re.I,
)
URL_RE = re.compile(r"https?://|www\.", re.I)


def contains_keyword(text, keyword):
    text = base.normalize_text(text)
    keyword = base.normalize_text(keyword)
    if not keyword:
        return False
    # Avoid substring false positives such as app -> Apple, xe -> pixel-like fragments.
    if " " not in keyword and len(keyword) <= 5:
        return bool(re.search(rf"(?<!\w){re.escape(keyword)}(?!\w)", text, flags=re.I))
    return keyword in text


def keyword_hits(text, keywords):
    return [k for k in keywords if contains_keyword(text, k)]


def score_content(candidate, posts, source):
    if not posts:
        return 0.0, {"reason": "no_posts"}

    recent = posts[-5:]
    texts = [base.normalize_text(p.get("text", "")) for p in recent]
    joined = " ".join(texts)
    title = base.normalize_text(candidate.get("title", ""))

    priority_hits = keyword_hits(joined, source["priority_keywords"])
    title_priority = keyword_hits(title, source["priority_keywords"])
    aligned_hits = [k for k in title_priority if contains_keyword(joined, k)]
    firsthand_hits = keyword_hits(joined, base.FIRSTHAND_MARKERS)
    reasoning_hits = keyword_hits(joined, base.REASONING_MARKERS)
    negative_hits = keyword_hits(joined, source["deprioritize_keywords"])
    news_hits = keyword_hits(joined, base.NEWS_MARKERS)

    lengths = [len(t) for t in texts]
    useful_posts = sum(1 for n in lengths if n >= 120)
    substantial_posts = sum(1 for n in lengths if n >= 220)
    short_posts = sum(1 for n in lengths if n < 70)
    linkish_posts = sum(1 for t in texts if len(t) < 180 and URL_RE.search(t))
    numeric_signals = len(NUMERIC_SIGNAL_RE.findall(joined))

    # Content value is intentionally driven by what people are saying now, not lifetime thread size.
    score = 0.35
    score += min(1.25, useful_posts * 0.25)
    score += min(0.8, substantial_posts * 0.2)
    score += min(1.7, len(set(firsthand_hits)) * 0.55)
    score += min(1.35, len(set(reasoning_hits)) * 0.22)
    score += min(1.55, len(set(priority_hits)) * 0.35)
    score += min(1.0, len(set(aligned_hits)) * 0.42)
    score += min(1.1, numeric_signals * 0.18)

    if recent:
        score -= (short_posts / len(recent)) * 1.15
        score -= (linkish_posts / len(recent)) * 0.8

    score -= min(1.0, len(set(negative_hits)) * 0.35)
    if news_hits and not firsthand_hits and len(set(reasoning_hits)) < 2:
        score -= min(1.1, 0.4 + len(set(news_hits)) * 0.15)

    # Topic drift: title promises a useful domain but latest posts no longer discuss it.
    if title_priority and not aligned_hits and not firsthand_hits:
        score -= 0.75

    score = max(0.0, min(6.0, score))
    details = {
        "priority_hits": sorted(set(priority_hits))[:12],
        "title_priority_hits": sorted(set(title_priority))[:10],
        "aligned_hits": sorted(set(aligned_hits))[:10],
        "firsthand_hits": sorted(set(firsthand_hits))[:10],
        "reasoning_hits": sorted(set(reasoning_hits))[:10],
        "negative_hits": sorted(set(negative_hits))[:8],
        "news_hits": sorted(set(news_hits))[:8],
        "numeric_signals": numeric_signals,
        "useful_posts": useful_posts,
        "substantial_posts": substantial_posts,
        "short_posts": short_posts,
        "linkish_posts": linkish_posts,
        "sampled_posts": len(recent),
    }
    return round(score, 3), details


def fetch_candidate(candidate, source, policy, headers, user_agent):
    thread_url = candidate["url"]
    result, errors = base.fetch(thread_url, policy, headers, user_agent)
    if not result or not result.get("ok"):
        return {"candidate": candidate, "ok": False, "errors": errors, "posts": []}

    latest_url = base.find_last_page_url(
        result.get("html", ""), result.get("final_url") or thread_url, source
    )
    if (
        base.canonical_thread_key(latest_url) == base.canonical_thread_key(thread_url)
        and base.page_number(latest_url) > base.page_number(result.get("final_url") or thread_url)
    ):
        time.sleep(policy["delay_ms"] / 1000)
        latest_result, latest_errors = base.fetch(latest_url, policy, headers, user_agent)
        errors = list(errors or []) + list(latest_errors or [])
        if latest_result and latest_result.get("ok"):
            result = latest_result

    fetched_url = result.get("final_url") or thread_url
    thread_title, posts = base.extract_posts(result.get("html", ""), fetched_url, policy["max_posts"])
    content_score, content_details = score_content(candidate, posts, source)
    # Discovery score contributes only 25%; fresh post content dominates selection.
    final_score = round(0.25 * candidate["pre_score"] + 0.75 * content_score, 3)
    return {
        "candidate": candidate,
        "ok": bool(posts),
        "errors": errors or [],
        "thread_title": thread_title,
        "fetched_url": fetched_url,
        "posts": posts,
        "content_score": content_score,
        "content_score_details": content_details,
        "final_score": final_score,
    }


def main():
    parser = argparse.ArgumentParser(description="Two-stage forum signal ranker")
    parser.add_argument("job_file")
    parser.add_argument("--output", default="crawl_output")
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()

    try:
        job_path = Path(args.job_file)
        job = json.loads(job_path.read_text(encoding="utf-8"))
        policy = base.validate_signal_job(job)
        probe_threads = int(job.get("probe_threads_per_source", 14))
        min_probe_score = float(job.get("min_probe_score", 1.2))
        min_final_score = float(job.get("min_final_score", 1.8))
        if not 1 <= probe_threads <= 40:
            raise ValueError("probe_threads_per_source must be 1..40")
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(f"SECURITY_POLICY_ERROR: {exc}", file=sys.stderr)
        raise SystemExit(2)

    if args.validate_only:
        print(json.dumps({
            "job": job.get("name", job_path.stem),
            "runner": "forum_signal_rank",
            "sources": [s["name"] for s in policy["sources"]],
            "probe_threads_per_source": probe_threads,
            "retain_threads_per_source": policy["max_threads"],
            "min_probe_score": min_probe_score,
            "min_final_score": min_final_score,
            "validated": True,
        }, ensure_ascii=False))
        return

    out_root = Path(args.output)
    out_root.mkdir(parents=True, exist_ok=True)
    jsonl_path = out_root / "forum_signal.jsonl"
    candidates_path = out_root / "forum_candidates.json"

    user_agent = str(job.get("user_agent", DEFAULT_UA))
    headers = {
        "User-Agent": user_agent,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }
    headers.update({str(k): str(v) for k, v in (job.get("headers") or {}).items()})

    manifest = {
        "job_name": job.get("name", job_path.stem),
        "runner": "forum_signal_rank",
        "started_at": now_iso(),
        "probe_threads_per_source": probe_threads,
        "max_threads_per_source": policy["max_threads"],
        "max_posts_per_thread": policy["max_posts"],
        "min_probe_score": min_probe_score,
        "min_final_score": min_final_score,
        "sources": [],
    }
    all_rows = []
    audits = []

    for source in policy["sources"]:
        src_meta = {
            "source": source["name"],
            "discovery_ok": 0,
            "discovered_thread_links": 0,
            "threads_probed": 0,
            "threads_selected": 0,
            "threads_ok": 0,
            "structured_posts": 0,
            "fallback_pages": 0,
            "errors": [],
            "selected_threads": [],
        }

        discovered = []
        discovery_order = 0
        for discovery_url in source["discovery_urls"]:
            result, errors = base.fetch(discovery_url, policy, headers, user_agent)
            if errors:
                src_meta["errors"].extend(f"{discovery_url}: {e}" for e in errors)
            if not result or not result.get("ok"):
                continue
            src_meta["discovery_ok"] += 1
            batch, discovery_order = base.collect_thread_candidates(
                result.get("html", ""), result.get("final_url") or discovery_url, source, discovery_order
            )
            discovered.extend(batch)

        ranked, _ = base.rank_candidates(discovered, source, 999, -10)
        src_meta["discovered_thread_links"] = len(ranked)
        probe_candidates = [c for c in ranked if c["pre_score"] >= min_probe_score][:probe_threads]

        probed = []
        for candidate in probe_candidates:
            item = fetch_candidate(candidate, source, policy, headers, user_agent)
            src_meta["threads_probed"] += 1
            if item["errors"]:
                src_meta["errors"].extend(f"{candidate['url']}: {e}" for e in item["errors"])
            probed.append(item)
            time.sleep(policy["delay_ms"] / 1000)

        probed.sort(key=lambda x: (-x.get("final_score", 0), x["candidate"]["discovery_order"]))
        selected = [x for x in probed if x.get("ok") and x.get("final_score", 0) >= min_final_score][:policy["max_threads"]]
        src_meta["threads_selected"] = len(selected)

        for item in selected:
            c = item["candidate"]
            src_meta["selected_threads"].append({
                "title": item.get("thread_title") or c.get("title", ""),
                "url": c["url"],
                "pre_score": c["pre_score"],
                "content_score": item["content_score"],
                "final_score": item["final_score"],
                "content_score_details": item["content_score_details"],
            })
            if item["posts"]:
                src_meta["threads_ok"] += 1
            for post in item["posts"]:
                row = {
                    "source": source["name"],
                    "thread_title": item.get("thread_title", ""),
                    "thread_key": base.canonical_thread_key(item["fetched_url"]),
                    "thread_url": c["url"],
                    "fetched_url": item["fetched_url"],
                    "fetched_at": now_iso(),
                    "pre_score": c["pre_score"],
                    "content_score": item["content_score"],
                    "final_score": item["final_score"],
                    "content_score_details": item["content_score_details"],
                    **post,
                }
                all_rows.append(row)
                if post["extraction"] == "structured_post":
                    src_meta["structured_posts"] += 1
                else:
                    src_meta["fallback_pages"] += 1

        audits.append({
            "source": source["name"],
            "selected": src_meta["selected_threads"],
            "probed": [
                {
                    "title": x.get("thread_title") or x["candidate"].get("title", ""),
                    "url": x["candidate"]["url"],
                    "pre_score": x["candidate"]["pre_score"],
                    "content_score": x.get("content_score", 0),
                    "final_score": x.get("final_score", 0),
                    "content_score_details": x.get("content_score_details", {}),
                    "preview": " ".join((p.get("text", "") for p in x.get("posts", [])[-2:]))[:600],
                }
                for x in probed
            ],
        })
        manifest["sources"].append(src_meta)

    with jsonl_path.open("w", encoding="utf-8") as f:
        for row in all_rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    candidates_path.write_text(json.dumps(audits, ensure_ascii=False, indent=2), encoding="utf-8")

    manifest["finished_at"] = now_iso()
    manifest["total_rows"] = len(all_rows)
    manifest["total_structured_posts"] = sum(s["structured_posts"] for s in manifest["sources"])
    manifest["total_fallback_pages"] = sum(s["fallback_pages"] for s in manifest["sources"])
    manifest["total_threads_probed"] = sum(s["threads_probed"] for s in manifest["sources"])
    manifest["total_threads_selected"] = sum(s["threads_selected"] for s in manifest["sources"])
    (out_root / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps({
        "job": manifest["job_name"],
        "runner": "forum_signal_rank",
        "sources": len(manifest["sources"]),
        "probed_threads": manifest["total_threads_probed"],
        "selected_threads": manifest["total_threads_selected"],
        "rows": manifest["total_rows"],
        "structured_posts": manifest["total_structured_posts"],
        "fallback_pages": manifest["total_fallback_pages"],
        "output": str(out_root),
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
