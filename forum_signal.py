#!/usr/bin/env python3

import argparse
import hashlib
import json
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
            host = urlparse(url).hostname or ""
            hosts.add(host.lower())
        normalized.append(
            {
                "name": name,
                "discovery_urls": discovery_urls,
                "thread_regex": compiled,
                "hosts": hosts,
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


def collect_thread_links(html, base_url, source):
    soup = BeautifulSoup(html or "", "html.parser")
    found = []
    seen = set()
    for a in soup.find_all("a", href=True):
        href = clean_url(urljoin(base_url, a.get("href", "")))
        p = urlparse(href)
        if (p.hostname or "").lower() not in source["hosts"]:
            continue
        if not source["thread_regex"].search(p.path):
            continue
        key = canonical_thread_key(href)
        marker = (key, href)
        if marker in seen:
            continue
        seen.add(marker)
        found.append(href)
    return found


def best_discovered_links(links, limit):
    order = []
    grouped = {}
    for link in links:
        key = canonical_thread_key(link)
        if key not in grouped:
            order.append(key)
            grouped[key] = link
        elif page_number(link) > page_number(grouped[key]):
            grouped[key] = link
    return [grouped[k] for k in order[:limit]]


def find_last_page_url(html, current_url, source):
    key = canonical_thread_key(current_url)
    best = current_url
    for link in collect_thread_links(html, current_url, source):
        if canonical_thread_key(link) == key and page_number(link) > page_number(best):
            best = link
    return best


def node_text(node):
    return "\n".join(x.strip() for x in node.get_text("\n").splitlines() if x.strip())


def extract_posts(html, url, max_posts):
    soup = BeautifulSoup(html or "", "html.parser")
    title_node = soup.select_one("h1.p-title-value, h1.thread-title, h1")
    thread_title = node_text(title_node) if title_node else ""
    if not thread_title and soup.title:
        thread_title = soup.title.get_text(" ", strip=True)

    candidates = []
    selectors = [
        "article.message",
        "li.message",
        "div.message.message--post",
        "div[data-content^='post-']",
        "article[data-content^='post-']",
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

        author_node = node.select_one(
            ".message-name, .username, [itemprop='name'], .message-userDetails a"
        )
        time_node = node.select_one("time")
        post_id = node.get("data-content") or node.get("id") or ""
        timestamp = ""
        if time_node:
            timestamp = (
                time_node.get("datetime")
                or time_node.get("title")
                or time_node.get("data-date-string")
                or node_text(time_node)
            )
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

    # Fallback for custom/non-XenForo layouts: retain one score-ready page text row.
    for tag in soup(["script", "style", "noscript", "svg", "template"]):
        tag.decompose()
    text = node_text(soup)
    if len(text) > 500:
        return thread_title, [
            {
                "post_id": "",
                "author": "",
                "timestamp": "",
                "text": text[-30000:],
                "text_chars": min(len(text), 30000),
                "extraction": "page_fallback",
            }
        ]
    return thread_title, []


def fetch(url, policy, headers, user_agent):
    result, errors = crawl_one(
        url,
        policy["mode"],
        policy["timeout"],
        policy["wait_ms"],
        headers,
        user_agent,
    )
    if result is None:
        return None, errors
    ok = bool(
        result.get("status")
        and result.get("status") < 400
        and not result.get("blocked_or_challenge")
    )
    result["ok"] = ok
    return result, errors


def main():
    parser = argparse.ArgumentParser(description="Forum delta/signal extraction crawler")
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
        print(
            json.dumps(
                {
                    "job": job.get("name", job_path.stem),
                    "runner": "forum_signal",
                    "sources": [s["name"] for s in policy["sources"]],
                    "max_threads_per_source": policy["max_threads"],
                    "max_posts_per_thread": policy["max_posts"],
                    "validated": True,
                },
                ensure_ascii=False,
            )
        )
        return

    out_root = Path(args.output)
    out_root.mkdir(parents=True, exist_ok=True)
    jsonl_path = out_root / "forum_signal.jsonl"
    user_agent = str(job.get("user_agent", DEFAULT_UA))
    headers = {
        "User-Agent": user_agent,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }
    headers.update({str(k): str(v) for k, v in (job.get("headers") or {}).items()})

    manifest = {
        "job_name": job.get("name", job_path.stem),
        "runner": "forum_signal",
        "started_at": now_iso(),
        "max_threads_per_source": policy["max_threads"],
        "max_posts_per_thread": policy["max_posts"],
        "sources": [],
    }

    all_rows = []
    for source in policy["sources"]:
        src_meta = {
            "source": source["name"],
            "discovery_urls": source["discovery_urls"],
            "discovery_ok": 0,
            "discovered_thread_links": 0,
            "threads_attempted": 0,
            "threads_ok": 0,
            "structured_posts": 0,
            "fallback_pages": 0,
            "errors": [],
        }
        discovered = []

        for discovery_url in source["discovery_urls"]:
            result, errors = fetch(discovery_url, policy, headers, user_agent)
            if errors:
                src_meta["errors"].extend(f"{discovery_url}: {e}" for e in errors)
            if not result or not result.get("ok"):
                continue
            src_meta["discovery_ok"] += 1
            discovered.extend(
                collect_thread_links(result.get("html", ""), result.get("final_url") or discovery_url, source)
            )

        selected = best_discovered_links(discovered, policy["max_threads"])
        src_meta["discovered_thread_links"] = len({canonical_thread_key(u) for u in discovered})

        for thread_url in selected:
            src_meta["threads_attempted"] += 1
            result, errors = fetch(thread_url, policy, headers, user_agent)
            if errors:
                src_meta["errors"].extend(f"{thread_url}: {e}" for e in errors)
            if not result or not result.get("ok"):
                continue

            latest_url = find_last_page_url(
                result.get("html", ""), result.get("final_url") or thread_url, source
            )
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

    manifest["finished_at"] = now_iso()
    manifest["total_rows"] = len(all_rows)
    manifest["total_structured_posts"] = sum(s["structured_posts"] for s in manifest["sources"])
    manifest["total_fallback_pages"] = sum(s["fallback_pages"] for s in manifest["sources"])
    (out_root / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print(
        json.dumps(
            {
                "job": manifest["job_name"],
                "runner": "forum_signal",
                "sources": len(manifest["sources"]),
                "rows": manifest["total_rows"],
                "structured_posts": manifest["total_structured_posts"],
                "fallback_pages": manifest["total_fallback_pages"],
                "output": str(out_root),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
