#!/usr/bin/env python3

import argparse
import json
import re
from collections import defaultdict
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
    p.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )


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
            return ""
    return raw


def parsed_dt(value):
    raw = str(value or "").strip()
    if not raw:
        return None
    if re.fullmatch(r"\d{9,13}", raw):
        raw = normalize_timestamp(raw)
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def timestamp_from_node(node):
    if node is None:
        return ""
    selectors = [
        "time[datetime]",
        "time",
        ".u-dt",
        "[data-time]",
        "[data-timestamp]",
        "[data-date-string]",
        ".message-attribution-main",
        ".message-attribution-opposite",
    ]
    for selector in selectors:
        for t in node.select(selector):
            for attr in (
                "datetime",
                "data-time",
                "data-timestamp",
                "data-date-string",
                "title",
            ):
                value = t.get(attr)
                if value:
                    parsed = normalize_timestamp(value)
                    if parsed:
                        return parsed
            text = t.get_text(" ", strip=True)
            if text:
                parsed = normalize_timestamp(text)
                if parsed:
                    return parsed
    return ""


def build_post_timestamp_map(html):
    soup = BeautifulSoup(html or "", "html.parser")
    out = {}
    nodes = soup.select(
        "article.message, li.message, div.message.message--post, "
        "div[data-content^='post-'], article[data-content^='post-']"
    )
    for node in nodes:
        pid = str(node.get("data-content") or node.get("id") or "")
        if not pid:
            continue
        ts = timestamp_from_node(node)
        if not ts:
            continue
        out[pid] = ts
        match = POST_DIGITS_RE.search(pid)
        if match:
            out[match.group(1)] = ts
    return out


def recover_otofun_for_url(url, headers, timeout):
    try:
        response = requests.get(
            url,
            headers=headers,
            timeout=timeout,
            allow_redirects=True,
        )
        if response.status_code >= 400:
            return url, {}, f"http_{response.status_code}"
        mapping = build_post_timestamp_map(response.text)
        return url, mapping, "" if mapping else "no_post_timestamps"
    except requests.RequestException as exc:
        return url, {}, type(exc).__name__


def enrich_otofun(rows, cache):
    recovered = 0
    unresolved = 0
    for row in rows:
        if not str(row.get("source") or "").startswith("OF-"):
            continue
        if str(row.get("timestamp") or "").strip():
            continue
        url = str(row.get("fetched_url") or row.get("thread_url") or "")
        mapping = cache.get(url) or {}
        pid = str(row.get("post_id") or "")
        ts = mapping.get(pid, "")
        if not ts:
            match = POST_DIGITS_RE.search(pid)
            if match:
                ts = mapping.get(match.group(1), "")
        if ts:
            row["timestamp"] = ts
            row["timestamp_recovered"] = True
            row["timestamp_recovery_source"] = "otofun_http_metadata"
            recovered += 1
        else:
            unresolved += 1
    return recovered, unresolved


def apply_tinhte_activity_proxy(rows, per_thread):
    """Give only the latest extracted comments in each active Tinhte thread a
    conservative freshness proxy.

    Tinhte's rendered comment DOM currently exposes useful comment bodies but
    not a stable per-comment timestamp that survives public headless fetches.
    The source itself is discovered from Tinhte's live homepage and the ranker
    keeps the tail of each selected thread, so fetched_at is a defensible
    thread-activity timestamp for only the newest few extracted comments.

    The proxy is explicitly labelled and never applied to page_fallback rows.
    """
    by_thread = defaultdict(list)
    for idx, row in enumerate(rows):
        if str(row.get("source") or "") != "Tinhte":
            continue
        if str(row.get("extraction") or "") != "structured_post":
            continue
        key = str(row.get("thread_key") or row.get("thread_url") or "")
        if key:
            by_thread[key].append(idx)

    assigned = 0
    already_exact = 0
    missing_fetch_time = 0
    for indices in by_thread.values():
        for idx in indices[-per_thread:]:
            row = rows[idx]
            if str(row.get("timestamp") or "").strip():
                already_exact += 1
                continue
            fetched_at = str(row.get("fetched_at") or "").strip()
            if parsed_dt(fetched_at) is None:
                missing_fetch_time += 1
                continue
            row["timestamp"] = fetched_at
            row["timestamp_recovered"] = True
            row["timestamp_proxy"] = True
            row["timestamp_recovery_source"] = "tinhte_active_thread_fetch"
            row["freshness_confidence"] = "thread_activity_proxy"
            assigned += 1
    return assigned, already_exact, missing_fetch_time, len(by_thread)


def clean_tinhte_fallback(rows):
    cleaned = []
    removed = 0
    for row in rows:
        if (
            str(row.get("source") or "") == "Tinhte"
            and str(row.get("extraction") or "") != "structured_post"
        ):
            removed += 1
            continue
        cleaned.append(row)
    return cleaned, removed


def promote_tinhte_snapshot(delta_rows, snapshot_rows, max_age_hours):
    now = datetime.now(timezone.utc)
    delta, delta_fallback_removed = clean_tinhte_fallback(delta_rows)
    snapshot, snapshot_fallback_removed = clean_tinhte_fallback(snapshot_rows)

    seen = {
        (
            str(row.get("source") or ""),
            str(row.get("thread_key") or row.get("thread_url") or ""),
            str(row.get("post_id") or ""),
            str(row.get("text") or ""),
        )
        for row in delta
    }

    promoted = 0
    for row in snapshot:
        if str(row.get("source") or "") != "Tinhte":
            continue
        if str(row.get("extraction") or "") != "structured_post":
            continue
        dt = parsed_dt(row.get("timestamp"))
        if dt is None:
            continue
        age_hours = (now - dt.astimezone(timezone.utc)).total_seconds() / 3600.0
        if age_hours < -2 or age_hours > max_age_hours:
            continue
        key = (
            "Tinhte",
            str(row.get("thread_key") or row.get("thread_url") or ""),
            str(row.get("post_id") or ""),
            str(row.get("text") or ""),
        )
        if key in seen:
            continue
        copy = dict(row)
        copy["snapshot_promoted"] = True
        delta.append(copy)
        seen.add(key)
        promoted += 1

    return (
        delta,
        snapshot,
        promoted,
        delta_fallback_removed,
        snapshot_fallback_removed,
    )


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Recover Otofun post timestamps and keep current Tinhte discussion "
            "usable with an explicitly-labelled active-thread freshness proxy"
        )
    )
    parser.add_argument("--output-dir", default="crawl_output")
    parser.add_argument("--timeout", type=int, default=12)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--tinhte-max-age-hours", type=int, default=72)
    parser.add_argument("--tinhte-proxy-posts-per-thread", type=int, default=5)
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()

    if not 1 <= args.tinhte_proxy_posts_per_thread <= 12:
        raise SystemExit("tinhte-proxy-posts-per-thread must be 1..12")

    if args.validate_only:
        print(
            json.dumps(
                {
                    "timestamp_recovery": "forum-signal-timestamp-v5",
                    "tinhte_freshness": "active_thread_proxy",
                    "tinhte_proxy_posts_per_thread": args.tinhte_proxy_posts_per_thread,
                    "validated": True,
                }
            )
        )
        return

    root = Path(args.output_dir)
    delta_path = root / "forum_signal.jsonl"
    snapshot_path = root / "forum_signal_snapshot.jsonl"
    delta_rows = read_jsonl(delta_path)
    snapshot_rows = read_jsonl(snapshot_path)

    otofun_urls = sorted(
        {
            str(row.get("fetched_url") or row.get("thread_url") or "")
            for row in delta_rows
            if str(row.get("source") or "").startswith("OF-")
            and not str(row.get("timestamp") or "").strip()
            and str(row.get("fetched_url") or row.get("thread_url") or "")
        }
    )
    headers = {
        "User-Agent": DEFAULT_UA,
        "Accept": "text/html,application/xhtml+xml",
    }
    otofun_cache = {}
    otofun_errors = {}
    if otofun_urls:
        with ThreadPoolExecutor(max_workers=max(1, min(args.workers, 12))) as pool:
            futures = [
                pool.submit(recover_otofun_for_url, url, headers, args.timeout)
                for url in otofun_urls
            ]
            for future in as_completed(futures):
                url, mapping, err = future.result()
                otofun_cache[url] = mapping
                if err:
                    otofun_errors[url] = err

    delta_otofun_recovered, delta_otofun_unresolved = enrich_otofun(
        delta_rows, otofun_cache
    )
    snapshot_otofun_recovered, snapshot_otofun_unresolved = enrich_otofun(
        snapshot_rows, otofun_cache
    )

    (
        tinhte_proxy_assigned,
        tinhte_exact_kept,
        tinhte_missing_fetch_time,
        tinhte_threads,
    ) = apply_tinhte_activity_proxy(
        snapshot_rows, args.tinhte_proxy_posts_per_thread
    )

    # Mirror proxy timestamps into any matching delta Tinhte rows that already
    # exist in this run. Most current Tinhte value is intentionally sourced from
    # the snapshot because the delta state can be empty across adjacent runs.
    snapshot_lookup = {
        (
            str(row.get("thread_key") or row.get("thread_url") or ""),
            str(row.get("post_id") or ""),
            str(row.get("text") or ""),
        ): row
        for row in snapshot_rows
        if str(row.get("source") or "") == "Tinhte"
        and str(row.get("extraction") or "") == "structured_post"
    }
    delta_proxy_mirrored = 0
    for row in delta_rows:
        if str(row.get("source") or "") != "Tinhte":
            continue
        if str(row.get("extraction") or "") != "structured_post":
            continue
        key = (
            str(row.get("thread_key") or row.get("thread_url") or ""),
            str(row.get("post_id") or ""),
            str(row.get("text") or ""),
        )
        source_row = snapshot_lookup.get(key)
        if not source_row or not source_row.get("timestamp_proxy"):
            continue
        row["timestamp"] = source_row.get("timestamp", "")
        row["timestamp_recovered"] = True
        row["timestamp_proxy"] = True
        row["timestamp_recovery_source"] = "tinhte_active_thread_fetch"
        row["freshness_confidence"] = "thread_activity_proxy"
        delta_proxy_mirrored += 1

    (
        delta_rows,
        snapshot_rows,
        tinhte_snapshot_promoted,
        tinhte_delta_fallback_removed,
        tinhte_snapshot_fallback_removed,
    ) = promote_tinhte_snapshot(
        delta_rows,
        snapshot_rows,
        args.tinhte_max_age_hours,
    )

    write_jsonl(delta_path, delta_rows)
    write_jsonl(snapshot_path, snapshot_rows)

    print(
        json.dumps(
            {
                "timestamp_recovery": "forum-signal-timestamp-v5",
                "otofun_urls_refetched": len(otofun_urls),
                "otofun_url_errors": len(otofun_errors),
                "otofun_delta_recovered": delta_otofun_recovered,
                "otofun_delta_unresolved": delta_otofun_unresolved,
                "otofun_snapshot_recovered": snapshot_otofun_recovered,
                "otofun_snapshot_unresolved": snapshot_otofun_unresolved,
                "tinhte_threads_with_structured_posts": tinhte_threads,
                "tinhte_proxy_posts_per_thread": args.tinhte_proxy_posts_per_thread,
                "tinhte_proxy_assigned": tinhte_proxy_assigned,
                "tinhte_proxy_mirrored_to_delta": delta_proxy_mirrored,
                "tinhte_exact_timestamps_kept": tinhte_exact_kept,
                "tinhte_missing_fetch_time": tinhte_missing_fetch_time,
                "tinhte_snapshot_promoted": tinhte_snapshot_promoted,
                "tinhte_delta_fallback_removed": tinhte_delta_fallback_removed,
                "tinhte_snapshot_fallback_removed": tinhte_snapshot_fallback_removed,
                "tinhte_max_age_hours": args.tinhte_max_age_hours,
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
