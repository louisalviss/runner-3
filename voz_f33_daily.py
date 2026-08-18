#!/usr/bin/env python3

import argparse
import hashlib
import json
import re
import time
from pathlib import Path
from urllib.parse import urljoin, urlparse, urlunparse

from bs4 import BeautifulSoup

from crawler import DEFAULT_UA, crawl_one, now_iso
from forum_signal_v2 import extract_posts

DISCOVERY_URL = "https://voz.vn/f/diem-bao.33/"
THREAD_RE = re.compile(r"^/t/[^?#]+\.\d+(?:/page-\d+)?/?$")
BAD_PAGE_MARKERS = (
    "cache miss",
    "upstream request timeout",
    "temporarily unavailable",
    "checking your browser",
    "verify you are human",
    "attention required",
)


def clean_url(url):
    p = urlparse(url)
    return urlunparse((p.scheme, p.netloc, p.path, "", p.query, ""))


def canonical_thread_url(url):
    p = urlparse(clean_url(url))
    path = re.sub(r"/page-\d+/?$", "", p.path).rstrip("/")
    return urlunparse((p.scheme, p.netloc, path, "", "", ""))


def canonical_thread_key(url):
    p = urlparse(canonical_thread_url(url))
    return f"{(p.hostname or '').lower()}{p.path.lower().rstrip('/')}"


def page_url(base_url, page_no):
    base = canonical_thread_url(base_url).rstrip("/")
    return base if page_no <= 1 else f"{base}/page-{page_no}"


def page_is_bad(result):
    if not result:
        return True
    if not result.get("status") or int(result.get("status") or 0) >= 400:
        return True
    if result.get("blocked_or_challenge"):
        return True
    text = (result.get("text") or "").strip()
    if len(text) < 300:
        return True
    low = text[:5000].lower()
    return any(marker in low for marker in BAD_PAGE_MARKERS)


def robust_fetch(url, timeout=35, wait_ms=800, retries=3, delay=0.7):
    errors = []
    headers = {
        "User-Agent": DEFAULT_UA,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Referer": "https://voz.vn/",
    }

    modes = ["http", "browser", "auto", "browser"]
    for attempt in range(1, retries + 1):
        mode = modes[min(attempt - 1, len(modes) - 1)]
        result, attempt_errors = crawl_one(
            url, mode, timeout, wait_ms, headers, DEFAULT_UA
        )
        errors.extend(attempt_errors or [])
        if not page_is_bad(result):
            result["attempt"] = attempt
            return result, errors
        if result:
            errors.append(
                f"attempt {attempt}: unusable page status={result.get('status')} "
                f"engine={result.get('engine')} text_chars={len(result.get('text') or '')}"
            )
        if attempt < retries:
            time.sleep(delay * attempt)
    return None, errors


def is_sticky_struct_item(node):
    classes = " ".join(node.get("class", []))
    if "sticky" in classes.lower():
        return True
    if node.select_one(".structItem-status--sticky, [title*='Sticky'], [aria-label*='Sticky']"):
        return True
    text = node.get_text(" ", strip=True).lower()
    return text.startswith("sticky ") or " ghim " in f" {text} "


def discover_page1_threads(html, base_url):
    soup = BeautifulSoup(html or "", "html.parser")
    rows = []
    seen = set()

    nodes = soup.select(".structItem--thread")
    if nodes:
        for node in nodes:
            if is_sticky_struct_item(node):
                continue
            anchor = node.select_one(".structItem-title a[href]")
            if not anchor:
                continue
            href = clean_url(urljoin(base_url, anchor.get("href", "")))
            p = urlparse(href)
            if (p.hostname or "").lower() != "voz.vn":
                continue
            if not THREAD_RE.search(p.path):
                continue
            key = canonical_thread_key(href)
            if key in seen:
                continue
            seen.add(key)
            rows.append(
                {
                    "title": anchor.get_text(" ", strip=True),
                    "url": canonical_thread_url(href),
                    "thread_key": key,
                }
            )
        return rows

    # Fallback if XenForo markup changes.
    for anchor in soup.find_all("a", href=True):
        href = clean_url(urljoin(base_url, anchor.get("href", "")))
        p = urlparse(href)
        if (p.hostname or "").lower() != "voz.vn" or not THREAD_RE.search(p.path):
            continue
        parent = anchor.find_parent(class_=re.compile(r"structItem", re.I))
        if parent and is_sticky_struct_item(parent):
            continue
        key = canonical_thread_key(href)
        if key in seen:
            continue
        title = anchor.get_text(" ", strip=True)
        if len(title) < 6:
            continue
        seen.add(key)
        rows.append({"title": title, "url": canonical_thread_url(href), "thread_key": key})
    return rows


def detect_last_page(html, thread_url):
    key = canonical_thread_key(thread_url)
    soup = BeautifulSoup(html or "", "html.parser")
    best = 1
    for a in soup.find_all("a", href=True):
        href = clean_url(urljoin(thread_url, a.get("href", "")))
        if canonical_thread_key(href) != key:
            continue
        m = re.search(r"/page-(\d+)(?:/|$)", urlparse(href).path)
        if m:
            best = max(best, int(m.group(1)))
        label = (a.get("aria-label") or "") + " " + a.get_text(" ", strip=True)
        for raw in re.findall(r"\b(\d{1,4})\b", label):
            if "/page-" in href:
                best = max(best, int(raw))
    return best


def post_fingerprint(post):
    post_id = str(post.get("post_id") or "").strip()
    if post_id:
        return f"id:{post_id}"
    raw = "|".join(
        [
            str(post.get("author") or "").strip().lower(),
            str(post.get("timestamp") or "").strip(),
            re.sub(r"\s+", " ", str(post.get("text") or "")).strip().lower(),
        ]
    )
    return "sha1:" + hashlib.sha1(raw.encode("utf-8", errors="ignore")).hexdigest()


def crawl_thread(thread, request_delay_ms=180, max_pages=250):
    first, errors = robust_fetch(thread["url"])
    if not first:
        return {
            **thread,
            "status": "FAILED",
            "expected_pages": None,
            "fetched_pages": [],
            "failed_pages": [1],
            "errors": errors,
            "posts": [],
        }

    expected = min(max_pages, detect_last_page(first.get("html", ""), thread["url"]))
    page_results = {1: first}
    failed_pages = []
    all_errors = list(errors)

    def fetch_range(start, end):
        for page_no in range(start, end + 1):
            if page_no in page_results:
                continue
            time.sleep(request_delay_ms / 1000)
            result, page_errors = robust_fetch(page_url(thread["url"], page_no))
            all_errors.extend(f"page {page_no}: {e}" for e in page_errors)
            if result:
                page_results[page_no] = result
            else:
                failed_pages.append(page_no)

    fetch_range(2, expected)

    # Pagination can grow while a busy thread is being crawled.
    for _ in range(2):
        if not page_results:
            break
        probe_page = max(page_results)
        probe = page_results[probe_page]
        expanded = min(max_pages, detect_last_page(probe.get("html", ""), thread["url"]))
        if expanded <= expected:
            # XenForo often exposes "last" more reliably on page 1, so recheck once.
            refreshed, refresh_errors = robust_fetch(thread["url"], retries=2)
            all_errors.extend(f"refresh: {e}" for e in refresh_errors)
            if refreshed:
                page_results[1] = refreshed
                expanded = min(max_pages, detect_last_page(refreshed.get("html", ""), thread["url"]))
        if expanded <= expected:
            break
        old_expected = expected
        expected = expanded
        fetch_range(old_expected + 1, expected)

    posts = []
    seen_posts = set()
    thread_title = thread["title"]
    page_post_counts = {}

    for page_no in sorted(page_results):
        result = page_results[page_no]
        fetched_url = result.get("final_url") or page_url(thread["url"], page_no)
        title, page_posts = extract_posts(result.get("html", ""), fetched_url, 1000)
        if title:
            thread_title = title
        page_post_counts[str(page_no)] = len(page_posts)
        for page_post_order, post in enumerate(page_posts, 1):
            fp = post_fingerprint(post)
            if fp in seen_posts:
                continue
            seen_posts.add(fp)
            posts.append(
                {
                    "page": page_no,
                    "page_post_order": page_post_order,
                    "fetched_url": fetched_url,
                    **post,
                }
            )

    # One retry pass for holes after the rest of the crawl has cooled down.
    if failed_pages:
        retry_holes = list(dict.fromkeys(failed_pages))
        failed_pages = []
        for page_no in retry_holes:
            time.sleep(max(0.4, request_delay_ms / 1000))
            result, page_errors = robust_fetch(page_url(thread["url"], page_no), retries=4, delay=1.0)
            all_errors.extend(f"hole page {page_no}: {e}" for e in page_errors)
            if not result:
                failed_pages.append(page_no)
                continue
            page_results[page_no] = result
            fetched_url = result.get("final_url") or page_url(thread["url"], page_no)
            title, page_posts = extract_posts(result.get("html", ""), fetched_url, 1000)
            if title:
                thread_title = title
            page_post_counts[str(page_no)] = len(page_posts)
            for page_post_order, post in enumerate(page_posts, 1):
                fp = post_fingerprint(post)
                if fp in seen_posts:
                    continue
                seen_posts.add(fp)
                posts.append(
                    {
                        "page": page_no,
                        "page_post_order": page_post_order,
                        "fetched_url": fetched_url,
                        **post,
                    }
                )

    posts.sort(key=lambda x: (int(x.get("page") or 1), int(x.get("page_post_order") or 0)))
    status = "HEALTHY" if not failed_pages and len(page_results) >= expected else "DEGRADED"
    return {
        **thread,
        "title": thread_title,
        "status": status,
        "expected_pages": expected,
        "fetched_pages": sorted(page_results),
        "failed_pages": sorted(set(failed_pages)),
        "page_post_counts": page_post_counts,
        "errors": all_errors[-80:],
        "posts": posts,
    }


def main():
    parser = argparse.ArgumentParser(description="Full VOZ F33 page-1 daily crawler")
    parser.add_argument("--output", default="voz_f33_output")
    parser.add_argument("--request-delay-ms", type=int, default=180)
    parser.add_argument("--max-pages", type=int, default=250)
    args = parser.parse_args()

    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)

    started_at = now_iso()
    discovery, discovery_errors = robust_fetch(DISCOVERY_URL, retries=4)
    if not discovery:
        manifest = {
            "started_at": started_at,
            "finished_at": now_iso(),
            "status": "FAILED",
            "discovery_url": DISCOVERY_URL,
            "discovery_errors": discovery_errors,
            "threads_discovered": 0,
        }
        (out / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        raise SystemExit(2)

    threads = discover_page1_threads(discovery.get("html", ""), discovery.get("final_url") or DISCOVERY_URL)
    (out / "page1_threads.json").write_text(json.dumps(threads, ensure_ascii=False, indent=2), encoding="utf-8")

    crawled = []
    for idx, thread in enumerate(threads, 1):
        item = crawl_thread(thread, args.request_delay_ms, args.max_pages)
        item["discovery_order"] = idx
        crawled.append(item)

    with (out / "threads_full.jsonl").open("w", encoding="utf-8") as f:
        for item in crawled:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")

    failed_threads = [x for x in crawled if x["status"] == "FAILED"]
    degraded_threads = [x for x in crawled if x["status"] == "DEGRADED"]
    missing_pages = sum(len(x.get("failed_pages", [])) for x in crawled)
    total_posts = sum(len(x.get("posts", [])) for x in crawled)

    if failed_threads:
        overall = "FAILED"
    elif degraded_threads or missing_pages:
        overall = "DEGRADED"
    else:
        overall = "HEALTHY"

    manifest = {
        "started_at": started_at,
        "finished_at": now_iso(),
        "status": overall,
        "discovery_url": DISCOVERY_URL,
        "discovery_engine": discovery.get("engine"),
        "discovery_attempt": discovery.get("attempt"),
        "threads_discovered": len(threads),
        "threads_healthy": sum(x["status"] == "HEALTHY" for x in crawled),
        "threads_degraded": len(degraded_threads),
        "threads_failed": len(failed_threads),
        "expected_pages_total": sum(int(x.get("expected_pages") or 0) for x in crawled),
        "fetched_pages_total": sum(len(x.get("fetched_pages", [])) for x in crawled),
        "missing_pages_total": missing_pages,
        "posts_total": total_posts,
        "thread_health": [
            {
                "title": x["title"],
                "url": x["url"],
                "status": x["status"],
                "expected_pages": x.get("expected_pages"),
                "fetched_pages": len(x.get("fetched_pages", [])),
                "failed_pages": x.get("failed_pages", []),
                "posts": len(x.get("posts", [])),
            }
            for x in crawled
        ],
    }
    (out / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    summary = [
        "# VOZ F33 Daily Full Crawl",
        "",
        f"- status: **{overall}**",
        f"- page-1 normal threads: **{len(threads)}**",
        f"- expected pages: **{manifest['expected_pages_total']}**",
        f"- fetched pages: **{manifest['fetched_pages_total']}**",
        f"- missing pages: **{missing_pages}**",
        f"- extracted posts: **{total_posts}**",
        "",
    ]
    for x in manifest["thread_health"]:
        summary.append(
            f"- [{x['status']}] {x['title']} — pages {x['fetched_pages']}/{x['expected_pages']}, "
            f"posts {x['posts']}, missing {x['failed_pages']}"
        )
    (out / "summary.md").write_text("\n".join(summary) + "\n", encoding="utf-8")

    print(json.dumps(manifest, ensure_ascii=False))


if __name__ == "__main__":
    main()
