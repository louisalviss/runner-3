#!/usr/bin/env python3

import argparse
import json
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

import requests
from bs4 import BeautifulSoup

from crawler import DEFAULT_UA

POST_DIGITS_RE = re.compile(r"(\d{5,})")


def read_jsonl(path):
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
    p.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")


def normalize_timestamp(value):
    raw = str(value or "").strip()
    if not raw:
        return ""
    if re.fullmatch(r"\d{9,13}", raw):
        n = int(raw)
        if n > 10_000_000_000:
            n //= 1000
        try:
            return datetime.fromtimestamp(n, tz=timezone.utc).isoformat()
        except (OverflowError, OSError, ValueError):
            return raw
    return raw


def timestamp_from_node(node):
    if node is None:
        return ""
    selectors = [
        "time[datetime]", "time", ".u-dt", "[data-time]", "[data-timestamp]",
        "[data-date-string]", ".message-attribution-main", ".message-attribution-opposite",
    ]
    for selector in selectors:
        for t in node.select(selector):
            for attr in ("datetime", "data-time", "data-timestamp", "data-date-string", "title"):
                value = t.get(attr)
                if value:
                    return normalize_timestamp(value)
            text = t.get_text(" ", strip=True)
            if text:
                return normalize_timestamp(text)
    return ""


def build_post_timestamp_map(html):
    soup = BeautifulSoup(html or "", "html.parser")
    out = {}
    post_nodes = soup.select(
        "article.message, li.message, div.message.message--post, div[data-content^='post-'], article[data-content^='post-']"
    )
    for node in post_nodes:
        pid = str(node.get("data-content") or node.get("id") or "")
        if not pid:
            continue
        ts = timestamp_from_node(node)
        if ts:
            out[pid] = ts
            m = POST_DIGITS_RE.search(pid)
            if m:
                out[m.group(1)] = ts

    for a in soup.find_all("a", href=True):
        href = str(a.get("href") or "")
        m = re.search(r"(?:post-|/post-?|#post-?)(\d{5,})", href)
        if not m:
            continue
        digits = m.group(1)
        ts = timestamp_from_node(a)
        if not ts and a.parent is not None:
            ts = timestamp_from_node(a.parent)
        if ts:
            out[digits] = ts
            out[f"post-{digits}"] = ts
    return out


def recover_for_url(url, headers, timeout):
    try:
        r = requests.get(url, headers=headers, timeout=timeout, allow_redirects=True)
        if r.status_code >= 400:
            return url, {}, f"http_{r.status_code}"
        return url, build_post_timestamp_map(r.text), ""
    except requests.RequestException as exc:
        return url, {}, type(exc).__name__


def enrich(rows, cache):
    recovered = 0
    unresolved = 0
    for row in rows:
        if not str(row.get("source") or "").startswith("OF-"):
            continue
        if str(row.get("timestamp") or "").strip():
            continue
        url = str(row.get("fetched_url") or row.get("thread_url") or "")
        if url not in cache:
            continue
        pid = str(row.get("post_id") or "")
        mapping = cache.get(url) or {}
        ts = mapping.get(pid, "")
        if not ts:
            m = POST_DIGITS_RE.search(pid)
            if m:
                ts = mapping.get(m.group(1), "")
        if ts:
            row["timestamp"] = ts
            row["timestamp_recovered"] = True
            recovered += 1
        else:
            unresolved += 1
    return recovered, unresolved


def main():
    ap = argparse.ArgumentParser(description="Recover missing Otofun/XenForo post timestamps")
    ap.add_argument("--output-dir", default="crawl_output")
    ap.add_argument("--timeout", type=int, default=10)
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--validate-only", action="store_true")
    args = ap.parse_args()
    if args.validate_only:
        print(json.dumps({"timestamp_recovery": "forum-signal-timestamp-v2", "validated": True}))
        return

    root = Path(args.output_dir)
    delta_path = root / "forum_signal.jsonl"
    snapshot_path = root / "forum_signal_snapshot.jsonl"
    delta_rows = read_jsonl(delta_path)
    snapshot_rows = read_jsonl(snapshot_path)

    # Only delta rows can reach the scorer. Refetching every selected Otofun thread
    # would add latency without improving the current decision.
    urls = sorted({
        str(r.get("fetched_url") or r.get("thread_url") or "")
        for r in delta_rows
        if str(r.get("source") or "").startswith("OF-")
        and not str(r.get("timestamp") or "").strip()
        and str(r.get("fetched_url") or r.get("thread_url") or "")
    })
    headers = {"User-Agent": DEFAULT_UA, "Accept": "text/html,application/xhtml+xml"}
    cache = {}
    errors = {}
    if urls:
        with ThreadPoolExecutor(max_workers=max(1, min(args.workers, 12))) as pool:
            futures = [pool.submit(recover_for_url, url, headers, args.timeout) for url in urls]
            for fut in as_completed(futures):
                url, mapping, err = fut.result()
                cache[url] = mapping
                if err:
                    errors[url] = err

    delta_recovered, delta_unresolved = enrich(delta_rows, cache)
    snapshot_recovered, snapshot_unresolved = enrich(snapshot_rows, cache)
    write_jsonl(delta_path, delta_rows)
    write_jsonl(snapshot_path, snapshot_rows)

    print(json.dumps({
        "timestamp_recovery": "forum-signal-timestamp-v2",
        "delta_urls_refetched": len(urls),
        "url_errors": len(errors),
        "delta_recovered": delta_recovered,
        "delta_unresolved": delta_unresolved,
        "snapshot_recovered_for_same_threads": snapshot_recovered,
        "snapshot_unresolved_for_same_threads": snapshot_unresolved,
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
