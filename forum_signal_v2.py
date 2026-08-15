#!/usr/bin/env python3

import argparse
import hashlib
import json
import math
import re
import sys
import time
from pathlib import Path
from urllib.parse import urljoin, urlparse, urlunparse

from bs4 import BeautifulSoup

from crawler import (
    DEFAULT_UA,
    crawl_one,
    now_iso,
    scan_for_forbidden_keys,
    validate_public_url,
)

DEFAULT_KEYWORDS = {
    "voz": {
        "priority": [
            "kinh nghiệm", "trải nghiệm", "thực tế", "review", "lương", "việc làm",
            "tuyển dụng", "thất nghiệp", "nhà", "chung cư", "bất động sản", "thuê",
            "giá", "ngân hàng", "thuế", "bảo hiểm", "visa", "xe", "pin", "lỗi",
            "mua", "bán", "đầu tư", "chứng khoán", "chi phí", "dịch vụ",
        ],
        "deprioritize": ["meme", "gái", "crush", "tâm sự", "hóng", "clip vui", "ảnh vui"],
    },
    "otofun": {
        "priority": [
            "kinh nghiệm", "trải nghiệm", "thực tế", "review", "chung cư", "bất động sản",
            "thuê", "mua nhà", "bán nhà", "giá", "xe", "sạc", "pin", "đăng kiểm",
            "bảo dưỡng", "bảo hiểm", "đường", "cao tốc", "nội bài", "roadtrip", "lỗi",
            "tiêu hao", "thanh khoản", "dự án",
        ],
        "deprioritize": ["chúc mừng", "ảnh vui", "thơ", "giao lưu vui", "tán gẫu"],
    },
    "gamevn": {
        "priority": [
            "patch", "update", "meta", "build", "team", "leak", "beta", "buff", "nerf",
            "banner", "skill", "boss", "theory", "chapter", "chương", "manga", "anime",
            "lore", "ending", "review", "performance", "fps", "bug", "dlc", "gameplay",
            "combat", "release",
        ],
        "deprioritize": ["meme", "waifu", "gái", "spam", "tán gẫu"],
    },
    "tinhte": {
        "priority": [
            "review", "trải nghiệm", "thực tế", "lỗi", "pin", "nhiệt", "benchmark",
            "hiệu năng", "bảo hành", "update", "firmware", "camera", "màn hình", "sạc",
            "ứng dụng", "app", "so sánh", "đã dùng", "đang dùng", "khắc phục",
        ],
        "deprioritize": ["khuyến mãi", "giảm giá", "tin nhanh", "mở bán", "quà tặng"],
    },
}

FIRSTHAND_MARKERS = [
    "mình đã", "tôi đã", "em đã", "đã dùng", "đang dùng", "đã mua", "đang xài",
    "nhà mình", "xe mình", "máy mình", "trải nghiệm", "thực tế", "kinh nghiệm",
    "vừa mua", "vừa dùng", "vừa đi", "vừa test", "review",
]

REASONING_MARKERS = [
    "vì", "do đó", "nên", "so với", "theo mình", "theo tôi", "khả năng", "có lẽ",
    "nếu", "nhưng", "đổi lại", "ưu điểm", "nhược điểm", "lý do", "phân tích",
]

NEWS_MARKERS = [
    "vnexpress", "dantri", "dân trí", "tuổi trẻ", "cafef", "vietnamnet", "theo báo",
    "nguồn:", "link báo", "báo viết",
]


def normalize_text(value):
    return re.sub(r"\s+", " ", str(value or "")).strip().lower()


def validate_signal_job(job):
    if not isinstance(job, dict):
        raise ValueError("job JSON must be an object")
    scan_for_forbidden_keys(job)
    if str(job.get("source_visibility", "")).lower() != "public":
        raise ValueError("forum signal jobs accept public sources only")

    artifact_policy = str(job.get("artifact_policy", "text")).lower()
    if artifact_policy not in {"text", "raw"}:
        raise ValueError("forum signal artifact_policy must be text or raw")

    mode = str(job.get("mode", "http")).lower()
    if mode not in {"http", "browser", "auto"}:
        raise ValueError("mode must be http, browser, or auto")

    timeout = int(job.get("timeout_seconds", 35))
    wait_ms = int(job.get("wait_after_load_ms", 800))
    max_threads = int(job.get("max_threads_per_source", 8))
    max_posts = int(job.get("max_posts_per_thread", 12))
    delay_ms = int(job.get("request_delay_ms", 150))
    min_pre_score = float(job.get("min_pre_score", 1.6))

    if not 1 <= timeout <= 120:
        raise ValueError("timeout_seconds must be 1..120")
    if not 0 <= wait_ms <= 30000:
        raise ValueError("wait_after_load_ms must be 0..30000")
    if not 1 <= max_threads <= 50:
        raise ValueError("max_threads_per_source must be 1..50")
    if not 1 <= max_posts <= 100:
        raise ValueError("max_posts_per_thread must be 1..100")
    if not 0 <= delay_ms <= 5000:
        raise ValueError("request_delay_ms must be 0..5000")
    if not -10 <= min_pre_score <= 20:
        raise ValueError("min_pre_score must be between -10 and 20")

    sources = job.get("sources") or []
    if not isinstance(sources, list) or not sources:
        raise ValueError("sources must be a non-empty array")

    normalized = []
    for src in sources:
        if not isinstance(src, dict):
            raise ValueError("each source must be an object")
        name = str(src.get("name", "")).strip()
        discovery_urls = src.get("discovery_urls") or []
        thread_regex = str(src.get("thread_regex", "")).strip()
        if not name or not discovery_urls or not thread_regex:
            raise ValueError("each source needs name, discovery_urls, thread_regex")
        try:
            compiled = re.compile(thread_regex)
        except re.error as exc:
            raise ValueError(f"invalid thread_regex for {name}: {exc}") from exc

        hosts = set()
        for url in discovery_urls:
            validate_public_url(url)
            hosts.add((urlparse(url).hostname or "").lower())

        defaults = DEFAULT_KEYWORDS.get(name.lower(), {"priority": [], "deprioritize": []})
        priority = [normalize_text(x) for x in src.get("priority_keywords", defaults["priority"])]
        deprioritize = [normalize_text(x) for x in src.get("deprioritize_keywords", defaults["deprioritize"])]

        normalized.append(
            {
                "name": name,
                "discovery_urls": discovery_urls,
                "thread_regex": compiled,
                "hosts": hosts,
                "priority_keywords": priority,
                "deprioritize_keywords": deprioritize,
            }
        )

    return {
        "artifact_policy": artifact_policy,
        "mode": mode,
        "timeout": timeout,
        "wait_ms": wait_ms,
        "max_threads": max_threads,
        "max_posts": max_posts,
        "delay_ms": delay_ms,
        "min_pre_score": min_pre_score,
        "sources": normalized,
    }


def clean_url(url):
    p = urlparse(url)
    return urlunparse((p.scheme, p.netloc, p.path, "", p.query, ""))


def page_number(url):
    path = urlparse(url).path
    m = re.search(r"/page-(\d+)(?:/|$)", path)
    if not m:
        m = re.search(r"/page/(\d+)(?:/|$)", path)
    return int(m.group(1)) if m else 1


def canonical_thread_key(url):
    p = urlparse(url)
    path = re.sub(r"/page-(\d+)(?:/|$)", "/", p.path)
    path = re.sub(r"/page/(\d+)(?:/|$)", "/", path)
    path = re.sub(r"/+", "/", path).rstrip("/")
    return f"{p.hostname or ''}{path}".lower()


def node_text(node):
    if node is None:
        return ""
    return "\n".join(x.strip() for x in node.get_text("\n").splitlines() if x.strip())


def nearest_context(a):
    selectors = [".structItem", ".contentRow", "article", "li", ".block-row", ".message", "tr"]
    for selector in selectors:
        node = a.find_parent(class_=selector[1:]) if selector.startswith(".") else a.find_parent(selector)
        if node:
            text = node_text(node)
            if text:
                return text[:1200]
    parent = a.parent
    return node_text(parent)[:1200] if parent else node_text(a)[:1200]


def parse_activity_hint(text):
    t = normalize_text(text)
    values = []
    patterns = [
        r"(?:replies|reply|trả lời|bình luận|comments?)\s*[:：]?\s*([0-9][0-9.,kKmM]*)",
        r"([0-9][0-9.,kKmM]*)\s*(?:replies|reply|trả lời|bình luận|comments?)",
    ]
    for pattern in patterns:
        for raw in re.findall(pattern, t, flags=re.I):
            raw = raw.replace(",", "").strip()
            mult = 1
            if raw.lower().endswith("k"):
                mult, raw = 1000, raw[:-1]
            elif raw.lower().endswith("m"):
                mult, raw = 1000000, raw[:-1]
            try:
                values.append(int(float(raw) * mult))
            except ValueError:
                pass
    return max(values) if values else 0


def collect_thread_candidates(html, base_url, source, start_order=0):
    soup = BeautifulSoup(html or "", "html.parser")
    found = []
    order = start_order
    for a in soup.find_all("a", href=True):
        href = clean_url(urljoin(base_url, a.get("href", "")))
        p = urlparse(href)
        if (p.hostname or "").lower() not in source["hosts"]:
            continue
        if not source["thread_regex"].search(p.path):
            continue
        title = node_text(a).strip()
        context = nearest_context(a)
        found.append(
            {
                "url": href,
                "thread_key": canonical_thread_key(href),
                "title": title,
                "context": context,
                "discovery_order": order,
                "activity_hint": parse_activity_hint(context),
            }
        )
        order += 1
    return found, order


def score_candidate(candidate, source):
    title = normalize_text(candidate.get("title"))
    context = normalize_text(candidate.get("context"))
    text = f"{title} {context}".strip()
    order = int(candidate.get("discovery_order", 0))
    replies = int(candidate.get("activity_hint", 0))

    recency = max(0.35, 2.0 - min(order, 55) * 0.03)
    activity = min(1.35, math.log10(replies + 1) * 0.42) if replies else 0.0

    positive_hits = [k for k in source["priority_keywords"] if k and k in text]
    negative_hits = [k for k in source["deprioritize_keywords"] if k and k in text]
    firsthand_hits = [k for k in FIRSTHAND_MARKERS if k in text]
    reasoning_hits = [k for k in REASONING_MARKERS if k in text]
    news_hits = [k for k in NEWS_MARKERS if k in text]

    positive = min(3.2, len(set(positive_hits)) * 0.75)
    firsthand = min(1.8, len(set(firsthand_hits)) * 0.65)
    reasoning = min(1.0, len(set(reasoning_hits)) * 0.25)
    penalty = min(2.8, len(set(negative_hits)) * 0.9)

    # Reposted news is not automatically bad, but without firsthand/reasoning it is replaceable.
    news_penalty = 0.0
    if news_hits and not firsthand_hits and len(reasoning_hits) < 2:
        news_penalty = min(1.2, 0.45 + 0.2 * len(set(news_hits)))

    if len(title) < 8:
        penalty += 0.35

    score = recency + activity + positive + firsthand + reasoning - penalty - news_penalty
    return round(score, 3), {
        "recency": round(recency, 3),
        "activity": round(activity, 3),
        "priority_hits": sorted(set(positive_hits))[:10],
        "firsthand_hits": sorted(set(firsthand_hits))[:8],
        "reasoning_hits": sorted(set(reasoning_hits))[:8],
        "deprioritize_hits": sorted(set(negative_hits))[:8],
        "news_hits": sorted(set(news_hits))[:6],
        "penalty": round(penalty + news_penalty, 3),
    }


def rank_candidates(candidates, source, limit, min_score):
    grouped = {}
    for c in candidates:
        key = c["thread_key"]
        current = grouped.get(key)
        if current is None:
            grouped[key] = dict(c)
            continue
        # Keep richer discovery context and the highest explicit page URL.
        if page_number(c["url"]) > page_number(current["url"]):
            current["url"] = c["url"]
        if len(c.get("context", "")) > len(current.get("context", "")):
            current["context"] = c["context"]
            current["title"] = c.get("title") or current.get("title", "")
            current["activity_hint"] = max(current.get("activity_hint", 0), c.get("activity_hint", 0))
        current["discovery_order"] = min(current["discovery_order"], c["discovery_order"])

    ranked = []
    for c in grouped.values():
        score, details = score_candidate(c, source)
        c["pre_score"] = score
        c["pre_score_details"] = details
        ranked.append(c)

    ranked.sort(key=lambda x: (-x["pre_score"], x["discovery_order"]))
    selected = [c for c in ranked if c["pre_score"] >= min_score][:limit]
    return ranked, selected


def collect_thread_links(html, base_url, source):
    candidates, _ = collect_thread_candidates(html, base_url, source)
    return [c["url"] for c in candidates]


def find_last_page_url(html, current_url, source):
    key = canonical_thread_key(current_url)
    best = current_url
    for link in collect_thread_links(html, current_url, source):
        if canonical_thread_key(link) == key and page_number(link) > page_number(best):
            best = link
    return best


def extract_posts(html, url, max_posts):
    soup = BeautifulSoup(html or "", "html.parser")
    title_node = soup.select_one("h1.p-title-value, h1.thread-title, h1")
    thread_title = node_text(title_node) if title_node else ""
    if not thread_title and soup.title:
        thread_title = soup.title.get_text(" ", strip=True)

    candidates = []
    selectors = [
        "article.message", "li.message", "div.message.message--post",
        "div[data-content^='post-']", "article[data-content^='post-']",
    ]
    seen_nodes = set()
    for selector in selectors:
        for node in soup.select(selector):
            marker = id(node)
            if marker in seen_nodes:
                continue
            seen_nodes.add(marker)
            candidates.append(node)

    rows = []
    fingerprints = set()
    for node in candidates:
        body = node.select_one(
            ".message-body .bbWrapper, .message-body, .message-content .bbWrapper, .message-content, .bbWrapper"
        )
        if body is None:
            continue
        for quote in body.select("blockquote, .bbCodeBlock-expandLink, .message-signature"):
            quote.decompose()
        text = node_text(body)
        if len(text) < 30:
            continue
        fp = hashlib.sha1(text.encode("utf-8", errors="ignore")).hexdigest()
        if fp in fingerprints:
            continue
        fingerprints.add(fp)

        author_node = node.select_one(".message-name, .username, [itemprop='name'], .message-userDetails a")
        time_node = node.select_one("time")
        post_id = node.get("data-content") or node.get("id") or ""
        timestamp = ""
        if time_node:
            timestamp = time_node.get("datetime") or time_node.get("title") or time_node.get("data-date-string") or node_text(time_node)
        rows.append(
            {
                "post_id": post_id,
                "author": node_text(author_node) if author_node else "",
                "timestamp": timestamp,
                "text": text,
                "text_chars": len(text),
                "extraction": "structured_post",
            }
        )

    if rows:
        return thread_title, rows[-max_posts:]

    for tag in soup(["script", "style", "noscript", "svg", "template"]):
        tag.decompose()
    text = node_text(soup)
    if len(text) > 500:
        return thread_title, [{
            "post_id": "", "author": "", "timestamp": "", "text": text[-30000:],
            "text_chars": min(len(text), 30000), "extraction": "page_fallback",
        }]
    return thread_title, []


def fetch(url, policy, headers, user_agent):
    result, errors = crawl_one(url, policy["mode"], policy["timeout"], policy["wait_ms"], headers, user_agent)
    if result is None:
        return None, errors
    result["ok"] = bool(result.get("status") and result.get("status") < 400 and not result.get("blocked_or_challenge"))
    return result, errors


def main():
    parser = argparse.ArgumentParser(description="Forum signal crawler with information-value pre-ranking")
    parser.add_argument("job_file")
    parser.add_argument("--output", default="crawl_output")
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()

    try:
        job_path = Path(args.job_file)
        job = json.loads(job_path.read_text(encoding="utf-8"))
        policy = validate_signal_job(job)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(f"SECURITY_POLICY_ERROR: {exc}", file=sys.stderr)
        raise SystemExit(2)

    if args.validate_only:
        print(json.dumps({
            "job": job.get("name", job_path.stem),
            "runner": "forum_signal_v2",
            "sources": [s["name"] for s in policy["sources"]],
            "max_threads_per_source": policy["max_threads"],
            "max_posts_per_thread": policy["max_posts"],
            "min_pre_score": policy["min_pre_score"],
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
        "runner": "forum_signal_v2",
        "started_at": now_iso(),
        "max_threads_per_source": policy["max_threads"],
        "max_posts_per_thread": policy["max_posts"],
        "min_pre_score": policy["min_pre_score"],
        "sources": [],
    }
    candidate_audit = []
    all_rows = []

    for source in policy["sources"]:
        src_meta = {
            "source": source["name"],
            "discovery_urls": source["discovery_urls"],
            "discovery_ok": 0,
            "discovered_thread_links": 0,
            "threads_selected": 0,
            "threads_attempted": 0,
            "threads_ok": 0,
            "structured_posts": 0,
            "fallback_pages": 0,
            "errors": [],
            "selected_threads": [],
        }
        discovered = []
        discovery_order = 0

        for discovery_url in source["discovery_urls"]:
            result, errors = fetch(discovery_url, policy, headers, user_agent)
            if errors:
                src_meta["errors"].extend(f"{discovery_url}: {e}" for e in errors)
            if not result or not result.get("ok"):
                continue
            src_meta["discovery_ok"] += 1
            batch, discovery_order = collect_thread_candidates(
                result.get("html", ""), result.get("final_url") or discovery_url, source, discovery_order
            )
            discovered.extend(batch)

        ranked, selected = rank_candidates(
            discovered, source, policy["max_threads"], policy["min_pre_score"]
        )
        src_meta["discovered_thread_links"] = len(ranked)
        src_meta["threads_selected"] = len(selected)
        src_meta["selected_threads"] = [
            {
                "title": c.get("title", ""),
                "url": c["url"],
                "pre_score": c["pre_score"],
                "activity_hint": c.get("activity_hint", 0),
                "score_details": c["pre_score_details"],
            }
            for c in selected
        ]
        candidate_audit.append({
            "source": source["name"],
            "selected": src_meta["selected_threads"],
            "top_ranked": [
                {
                    "title": c.get("title", ""), "url": c["url"], "pre_score": c["pre_score"],
                    "activity_hint": c.get("activity_hint", 0), "score_details": c["pre_score_details"],
                }
                for c in ranked[:20]
            ],
        })

        for candidate in selected:
            thread_url = candidate["url"]
            src_meta["threads_attempted"] += 1
            result, errors = fetch(thread_url, policy, headers, user_agent)
            if errors:
                src_meta["errors"].extend(f"{thread_url}: {e}" for e in errors)
            if not result or not result.get("ok"):
                continue

            latest_url = find_last_page_url(result.get("html", ""), result.get("final_url") or thread_url, source)
            if canonical_thread_key(latest_url) == canonical_thread_key(thread_url) and page_number(latest_url) > page_number(result.get("final_url") or thread_url):
                time.sleep(policy["delay_ms"] / 1000)
                latest_result, latest_errors = fetch(latest_url, policy, headers, user_agent)
                if latest_errors:
                    src_meta["errors"].extend(f"{latest_url}: {e}" for e in latest_errors)
                if latest_result and latest_result.get("ok"):
                    result = latest_result

            fetched_url = result.get("final_url") or thread_url
            thread_title, posts = extract_posts(result.get("html", ""), fetched_url, policy["max_posts"])
            if posts:
                src_meta["threads_ok"] += 1
            for post in posts:
                row = {
                    "source": source["name"],
                    "thread_title": thread_title,
                    "thread_key": canonical_thread_key(fetched_url),
                    "thread_url": thread_url,
                    "fetched_url": fetched_url,
                    "fetched_at": now_iso(),
                    "pre_score": candidate["pre_score"],
                    "pre_score_details": candidate["pre_score_details"],
                    **post,
                }
                all_rows.append(row)
                if post["extraction"] == "structured_post":
                    src_meta["structured_posts"] += 1
                else:
                    src_meta["fallback_pages"] += 1
            time.sleep(policy["delay_ms"] / 1000)

        manifest["sources"].append(src_meta)

    with jsonl_path.open("w", encoding="utf-8") as f:
        for row in all_rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    candidates_path.write_text(json.dumps(candidate_audit, ensure_ascii=False, indent=2), encoding="utf-8")

    manifest["finished_at"] = now_iso()
    manifest["total_rows"] = len(all_rows)
    manifest["total_structured_posts"] = sum(s["structured_posts"] for s in manifest["sources"])
    manifest["total_fallback_pages"] = sum(s["fallback_pages"] for s in manifest["sources"])
    (out_root / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps({
        "job": manifest["job_name"],
        "runner": "forum_signal_v2",
        "sources": len(manifest["sources"]),
        "rows": manifest["total_rows"],
        "structured_posts": manifest["total_structured_posts"],
        "fallback_pages": manifest["total_fallback_pages"],
        "selected_threads": sum(s["threads_selected"] for s in manifest["sources"]),
        "output": str(out_root),
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
