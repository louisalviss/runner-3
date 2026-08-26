#!/usr/bin/env python3

import argparse
import hashlib
import json
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests
from bs4 import BeautifulSoup

from crawler import DEFAULT_UA, browser_fetch, looks_blocked

POST_DIGITS_RE = re.compile(r"(\d{5,})")
TINHTE_TZ = timezone(timedelta(hours=7))
TINHTE_DATE_RE = re.compile(r"\b(\d{1,2})/(\d{1,2})/(\d{2,4})(?:\s+(\d{1,2}):(\d{2}))?\b")
TINHTE_REL_RE = re.compile(r"\b(\d+)\s*(phút|giờ|ngày)\s*(?:trước)?\b", re.I)
TINHTE_BODY_SELECTOR = (
    ".post-body, [class*='post-body'], [class*='postBody'], "
    ".comment-content, .commentContent, [class*='comment-content'], "
    "[class*='commentContent'], [class*='reply-content'], [class*='replyContent']"
)
TINHTE_NODE_SELECTORS = [
    "div.post-item__container",
    "[class*='post-item__container']",
    "[data-comment-id]",
    "[data-reply-id]",
    "[data-post-id]",
    "[id^='comment-']",
    "[id^='reply-']",
    ".comment-item",
    ".commentItem",
    "[class*='comment-item']",
    "[class*='reply-item']",
    "article[class*='comment']",
    "li[class*='comment']",
]


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


def normalize_space(value):
    return " ".join(str(value or "").split())


def text_key(value):
    text = normalize_space(value).casefold()
    return hashlib.sha1(text.encode("utf-8", errors="ignore")).hexdigest()


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


def parse_tinhte_timestamp(value):
    raw = normalize_space(value)
    if not raw:
        return ""
    if re.fullmatch(r"\d{9,13}", raw):
        return normalize_timestamp(raw)
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=TINHTE_TZ)
        return dt.isoformat()
    except ValueError:
        pass

    m = TINHTE_DATE_RE.search(raw)
    if m:
        day, month = map(int, m.group(1, 2))
        year = int(m.group(3))
        if year < 100:
            year += 2000
        hour = int(m.group(4) or 0)
        minute = int(m.group(5) or 0)
        try:
            return datetime(year, month, day, hour, minute, tzinfo=TINHTE_TZ).isoformat()
        except ValueError:
            return ""

    lowered = raw.lower()
    now = datetime.now(TINHTE_TZ)
    if "vừa xong" in lowered or "vừa mới" in lowered:
        return now.isoformat()
    if "hôm qua" in lowered:
        clock = re.search(r"\b(\d{1,2}):(\d{2})\b", lowered)
        dt = now - timedelta(days=1)
        if clock:
            dt = dt.replace(hour=int(clock.group(1)), minute=int(clock.group(2)), second=0, microsecond=0)
        return dt.isoformat()
    if "hôm nay" in lowered:
        clock = re.search(r"\b(\d{1,2}):(\d{2})\b", lowered)
        if clock:
            return now.replace(hour=int(clock.group(1)), minute=int(clock.group(2)), second=0, microsecond=0).isoformat()
    m = TINHTE_REL_RE.search(lowered)
    if m:
        amount = int(m.group(1))
        unit = m.group(2).lower()
        if unit == "phút":
            dt = now - timedelta(minutes=amount)
        elif unit == "giờ":
            dt = now - timedelta(hours=amount)
        else:
            dt = now - timedelta(days=amount)
        return dt.isoformat()
    return ""


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
        if ts:
            out[pid] = ts
            m = POST_DIGITS_RE.search(pid)
            if m:
                out[m.group(1)] = ts
    return out


def recover_otofun_for_url(url, headers, timeout):
    try:
        r = requests.get(url, headers=headers, timeout=timeout, allow_redirects=True)
        if r.status_code >= 400:
            return url, {}, f"http_{r.status_code}"
        mapping = build_post_timestamp_map(r.text)
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
            m = POST_DIGITS_RE.search(pid)
            if m:
                ts = mapping.get(m.group(1), "")
        if ts:
            row["timestamp"] = ts
            row["timestamp_recovered"] = True
            row["timestamp_recovery_source"] = "otofun_http_metadata"
            recovered += 1
        else:
            unresolved += 1
    return recovered, unresolved


def tinhte_timestamp_from_comment_node(node):
    candidates = []
    for selector in (
        "time", "[data-time]", "[data-timestamp]", "[data-date]", "[data-date-string]",
        "[data-created-at]", "[data-created]", "[class*='time']", "[class*='date']"
    ):
        try:
            candidates.extend(node.select(selector))
        except Exception:
            continue
    candidates.append(node)
    for item in candidates:
        for attr in (
            "datetime", "data-time", "data-timestamp", "data-date", "data-date-string",
            "data-created-at", "data-created", "title", "aria-label"
        ):
            value = item.get(attr) if hasattr(item, "get") else None
            ts = parse_tinhte_timestamp(value)
            if ts:
                return ts

    meta = BeautifulSoup(str(node), "html.parser")
    for body in meta.select(TINHTE_BODY_SELECTOR):
        body.decompose()
    return parse_tinhte_timestamp(meta.get_text(" ", strip=True))


def build_tinhte_comment_timestamp_map(html):
    soup = BeautifulSoup(html or "", "html.parser")
    nodes = []
    seen_nodes = set()
    for selector in TINHTE_NODE_SELECTORS:
        try:
            matches = soup.select(selector)
        except Exception:
            continue
        for node in matches:
            marker = id(node)
            if marker in seen_nodes:
                continue
            seen_nodes.add(marker)
            nodes.append(node)

    out = {}
    for node in nodes:
        body = node.select_one(TINHTE_BODY_SELECTOR)
        if body is None:
            continue
        clone = BeautifulSoup(str(body), "html.parser")
        for bad in clone.select("script, style, button, nav, footer, form, svg, blockquote, .quote, .post-quote"):
            bad.decompose()
        text = "\n".join(x.strip() for x in clone.get_text("\n", strip=True).splitlines() if x.strip())
        if not (20 <= len(text) <= 12000):
            continue
        ts = tinhte_timestamp_from_comment_node(node)
        if ts:
            out[text_key(text)] = ts
    return out


def recover_tinhte_for_url(url, timeout):
    try:
        result = browser_fetch(url, timeout, 3000, {}, DEFAULT_UA)
    except Exception as exc:
        return url, {}, f"browser_{type(exc).__name__}"
    if result is None:
        return url, {}, "browser_none"
    status = result.get("status")
    html = result.get("html", "")
    text = result.get("text", "")
    if status is not None and status >= 400:
        return url, {}, f"browser_http_{status}"
    if looks_blocked(status, html, text):
        return url, {}, "browser_blocked"
    mapping = build_tinhte_comment_timestamp_map(html)
    return url, mapping, "" if mapping else "no_comment_timestamps"


def enrich_tinhte(rows, cache):
    recovered = 0
    unresolved = 0
    for row in rows:
        if str(row.get("source") or "") != "Tinhte":
            continue
        if str(row.get("extraction") or "") != "structured_post":
            continue
        if str(row.get("timestamp") or "").strip():
            continue
        url = str(row.get("fetched_url") or row.get("thread_url") or "")
        ts = (cache.get(url) or {}).get(text_key(row.get("text", "")), "")
        if ts:
            row["timestamp"] = ts
            row["timestamp_recovered"] = True
            row["timestamp_recovery_source"] = "tinhte_browser_metadata"
            recovered += 1
        else:
            unresolved += 1
    return recovered, unresolved


def parsed_dt(value):
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=TINHTE_TZ)
        return dt
    except ValueError:
        return None


def promote_tinhte_snapshot(delta_rows, snapshot_rows, max_age_hours):
    now = datetime.now(timezone.utc)
    delta = [
        r for r in delta_rows
        if not (str(r.get("source") or "") == "Tinhte" and str(r.get("extraction") or "") != "structured_post")
    ]
    snapshot = [
        r for r in snapshot_rows
        if not (str(r.get("source") or "") == "Tinhte" and str(r.get("extraction") or "") != "structured_post")
    ]
    seen = {
        (str(r.get("source") or ""), str(r.get("thread_key") or r.get("thread_url") or ""), text_key(r.get("text", "")))
        for r in delta
    }
    promoted = 0
    for row in snapshot:
        if str(row.get("source") or "") != "Tinhte" or str(row.get("extraction") or "") != "structured_post":
            continue
        dt = parsed_dt(row.get("timestamp"))
        if dt is None:
            continue
        age = (now - dt.astimezone(timezone.utc)).total_seconds() / 3600
        if age < -2 or age > max_age_hours:
            continue
        key = ("Tinhte", str(row.get("thread_key") or row.get("thread_url") or ""), text_key(row.get("text", "")))
        if key in seen:
            continue
        copy = dict(row)
        copy["snapshot_promoted"] = True
        delta.append(copy)
        seen.add(key)
        promoted += 1
    return delta, snapshot, promoted


def main():
    ap = argparse.ArgumentParser(description="Recover Otofun/Tinhte timestamps and promote fresh Tinhte snapshot comments")
    ap.add_argument("--output-dir", default="crawl_output")
    ap.add_argument("--timeout", type=int, default=12)
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--tinhte-max-age-hours", type=int, default=72)
    ap.add_argument("--validate-only", action="store_true")
    args = ap.parse_args()

    if args.validate_only:
        print(json.dumps({"timestamp_recovery": "forum-signal-timestamp-v4", "validated": True}))
        return

    root = Path(args.output_dir)
    delta_path = root / "forum_signal.jsonl"
    snapshot_path = root / "forum_signal_snapshot.jsonl"
    delta_rows = read_jsonl(delta_path)
    snapshot_rows = read_jsonl(snapshot_path)

    otofun_urls = sorted({
        str(r.get("fetched_url") or r.get("thread_url") or "")
        for r in delta_rows
        if str(r.get("source") or "").startswith("OF-")
        and not str(r.get("timestamp") or "").strip()
        and str(r.get("fetched_url") or r.get("thread_url") or "")
    })
    headers = {"User-Agent": DEFAULT_UA, "Accept": "text/html,application/xhtml+xml"}
    otofun_cache = {}
    otofun_errors = {}
    if otofun_urls:
        with ThreadPoolExecutor(max_workers=max(1, min(args.workers, 12))) as pool:
            futures = [pool.submit(recover_otofun_for_url, url, headers, args.timeout) for url in otofun_urls]
            for fut in as_completed(futures):
                url, mapping, err = fut.result()
                otofun_cache[url] = mapping
                if err:
                    otofun_errors[url] = err

    delta_otofun_recovered, delta_otofun_unresolved = enrich_otofun(delta_rows, otofun_cache)
    snapshot_otofun_recovered, snapshot_otofun_unresolved = enrich_otofun(snapshot_rows, otofun_cache)

    tinhte_urls = sorted({
        str(r.get("fetched_url") or r.get("thread_url") or "")
        for r in (snapshot_rows + delta_rows)
        if str(r.get("source") or "") == "Tinhte"
        and str(r.get("extraction") or "") == "structured_post"
        and not str(r.get("timestamp") or "").strip()
        and str(r.get("fetched_url") or r.get("thread_url") or "")
    })
    tinhte_cache = {}
    tinhte_errors = {}
    for url in tinhte_urls:
        recovered_url, mapping, err = recover_tinhte_for_url(url, args.timeout)
        tinhte_cache[recovered_url] = mapping
        if err:
            tinhte_errors[recovered_url] = err

    delta_tinhte_recovered, delta_tinhte_unresolved = enrich_tinhte(delta_rows, tinhte_cache)
    snapshot_tinhte_recovered, snapshot_tinhte_unresolved = enrich_tinhte(snapshot_rows, tinhte_cache)

    delta_rows, snapshot_rows, promoted = promote_tinhte_snapshot(
        delta_rows, snapshot_rows, args.tinhte_max_age_hours
    )
    write_jsonl(delta_path, delta_rows)
    write_jsonl(snapshot_path, snapshot_rows)

    print(json.dumps({
        "timestamp_recovery": "forum-signal-timestamp-v4",
        "otofun_urls_refetched": len(otofun_urls),
        "otofun_url_errors": len(otofun_errors),
        "otofun_delta_recovered": delta_otofun_recovered,
        "otofun_delta_unresolved": delta_otofun_unresolved,
        "otofun_snapshot_recovered": snapshot_otofun_recovered,
        "otofun_snapshot_unresolved": snapshot_otofun_unresolved,
        "tinhte_urls_rendered": len(tinhte_urls),
        "tinhte_url_errors": len(tinhte_errors),
        "tinhte_delta_recovered": delta_tinhte_recovered,
        "tinhte_delta_unresolved": delta_tinhte_unresolved,
        "tinhte_snapshot_recovered": snapshot_tinhte_recovered,
        "tinhte_snapshot_unresolved": snapshot_tinhte_unresolved,
        "tinhte_snapshot_promoted": promoted,
        "tinhte_max_age_hours": args.tinhte_max_age_hours,
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
