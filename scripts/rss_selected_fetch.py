#!/usr/bin/env python3

import argparse
import hashlib
import html
import json
import re
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
DATA_ROOT = ROOT / "data" / "rss-reader"
CACHE_INDEX_PATH = DATA_ROOT / "analysis-cache-index.json"
ARTIFACT_DIR = Path("/tmp/rss-analysis-fetch")
ARTIFACT_PATH = ARTIFACT_DIR / "payload.json"
UA = "Mozilla/5.0 (compatible; runner-3-rss-analysis/1.0; +https://github.com/louisalviss/runner-3)"
DIRECT_TIMEOUT = 6
JINA_TIMEOUT = 20
MIN_TEXT_CHARS = 600
TTL_DAYS = 7
MAX_CACHE_ENTRIES = 300
MAX_BATCH_ITEMS = 20
MAX_WORKERS = 6


def now_dt():
    return datetime.now(timezone.utc)


def iso(dt):
    return dt.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def load_json(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def write_json(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def clean_text(value):
    return re.sub(r"\s+", " ", html.unescape(str(value or ""))).strip()


def normalize_url(url):
    return str(url or "").strip()


def valid_http_url(url):
    try:
        p = urlparse(url)
        return p.scheme in {"http", "https"} and bool(p.netloc)
    except Exception:
        return False


def extract_html_text(raw_html, final_url):
    soup = BeautifulSoup(raw_html, "html.parser")
    title = clean_text(soup.title.get_text(" ", strip=True) if soup.title else "")
    for tag in soup(["script", "style", "nav", "footer", "header", "aside", "form", "svg", "noscript"]):
        tag.decompose()
    root = soup.find("article") or soup.find("main") or soup.body or soup
    pieces = []
    for node in root.find_all(["h1", "h2", "h3", "p", "li", "blockquote"]):
        text = clean_text(node.get_text(" ", strip=True))
        if len(text) >= 20:
            pieces.append(text)
    body = "\n\n".join(pieces).strip()
    if len(body) < MIN_TEXT_CHARS:
        raise RuntimeError(f"direct text too thin: {len(body)}")
    return title or (urlparse(final_url).hostname or "Article"), body


def extract_direct(url):
    r = requests.get(
        url,
        headers={"User-Agent": UA, "Accept": "text/html,application/xhtml+xml,*/*"},
        timeout=DIRECT_TIMEOUT,
        allow_redirects=True,
    )
    if r.status_code != 200:
        raise RuntimeError(f"direct HTTP {r.status_code}")
    title, text = extract_html_text(r.text, r.url)
    return {
        "route": "direct",
        "resolvedUrl": r.url,
        "title": title,
        "rawText": text,
        "coverage": "best_accessible",
    }


def extract_jina(url):
    target = "https://r.jina.ai/" + url
    r = requests.get(
        target,
        headers={"User-Agent": UA, "Accept": "text/plain", "X-No-Cache": "true", "DNT": "1"},
        timeout=JINA_TIMEOUT,
    )
    if r.status_code != 200:
        raise RuntimeError(f"jina HTTP {r.status_code}")
    raw = r.text
    if len(raw) < MIN_TEXT_CHARS:
        raise RuntimeError(f"jina text too thin: {len(raw)}")
    title_match = re.search(r"(?mi)^Title:\s*(.+)$", raw)
    source_match = re.search(r"(?mi)^URL Source:\s*(https?://\S+)", raw)
    title = clean_text(title_match.group(1)) if title_match else "Article"
    resolved = source_match.group(1).strip() if source_match else url
    body = re.sub(r"(?mi)^(Title|URL Source|Published Time|Markdown Content):\s*.*$", "", raw).strip()
    if len(body) < MIN_TEXT_CHARS:
        raise RuntimeError(f"jina body too thin: {len(body)}")
    return {
        "route": "jina-live",
        "resolvedUrl": resolved,
        "title": title,
        "rawText": body,
        "coverage": "best_accessible",
    }


def extract_one(item):
    url = item["canonicalUrl"]
    errors = []
    try:
        result = extract_direct(url)
        return item, result, None
    except Exception as exc:
        errors.append(f"direct={type(exc).__name__}: {exc}")
    try:
        result = extract_jina(url)
        return item, result, None
    except Exception as exc:
        errors.append(f"jina={type(exc).__name__}: {exc}")
    return item, None, "; ".join(errors)


def parse_expiry(value):
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(timezone.utc)
    except Exception:
        return None


def cache_entry_fresh(entry, item, now):
    if not isinstance(entry, dict) or entry.get("status") != "ready":
        return False
    if normalize_url(entry.get("canonicalUrl")) != item["canonicalUrl"]:
        return False
    if item.get("contentHash") and entry.get("contentHash") and entry.get("contentHash") != item.get("contentHash"):
        return False
    expiry = parse_expiry(entry.get("expiresAt"))
    return bool(expiry and expiry > now and entry.get("artifactName") and entry.get("rawTextSha256"))


def load_request(path):
    obj = load_json(path)
    request_id = clean_text(obj.get("requestId"))
    raw_items = obj.get("items") or []
    if not request_id:
        raise RuntimeError("requestId is required")
    if not isinstance(raw_items, list) or not raw_items:
        raise RuntimeError("items[] is required")
    if len(raw_items) > MAX_BATCH_ITEMS:
        raise RuntimeError(f"too many items: {len(raw_items)} > {MAX_BATCH_ITEMS}")

    items = []
    seen = set()
    for raw in raw_items:
        if not isinstance(raw, dict):
            continue
        url = normalize_url(raw.get("canonicalUrl"))
        if not valid_http_url(url) or url in seen:
            continue
        seen.add(url)
        items.append({
            "displayIndex": raw.get("displayIndex"),
            "sourceKey": clean_text(raw.get("sourceKey")) or "unknown",
            "sourceName": clean_text(raw.get("sourceName")) or None,
            "canonicalUrl": url,
            "title": clean_text(raw.get("title")) or url,
            "publishedAt": raw.get("publishedAt"),
            "contentHash": raw.get("contentHash"),
            "itemType": clean_text(raw.get("itemType")) or "article",
        })
    if not items:
        raise RuntimeError("request has no valid HTTP(S) canonical URLs")
    return request_id, items


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--request", default="data/rss-reader/analysis-request.json")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    request_path = ROOT / args.request
    request_id, items = load_request(request_path)
    now = now_dt()
    cache = load_json(CACHE_INDEX_PATH)
    entries = dict(cache.get("entries") or {})
    cache_hits = []
    misses = []

    for item in items:
        entry = entries.get(item["canonicalUrl"])
        if not args.force and cache_entry_fresh(entry, item, now):
            cache_hits.append({
                "displayIndex": item.get("displayIndex"),
                "canonicalUrl": item["canonicalUrl"],
                "artifactName": entry.get("artifactName"),
                "runId": entry.get("runId"),
                "rawTextSha256": entry.get("rawTextSha256"),
                "expiresAt": entry.get("expiresAt"),
                "status": "cache_hit",
            })
        else:
            misses.append(item)

    artifact_name = f"rss-analysis-{request_id}-{args.run_id}"
    payload_items = []
    errors = []

    if misses:
        with ThreadPoolExecutor(max_workers=min(MAX_WORKERS, len(misses))) as pool:
            futures = [pool.submit(extract_one, item) for item in misses]
            for future in as_completed(futures):
                item, result, error = future.result()
                url = item["canonicalUrl"]
                if error:
                    errors.append({
                        "displayIndex": item.get("displayIndex"),
                        "sourceKey": item.get("sourceKey"),
                        "canonicalUrl": url,
                        "title": item.get("title"),
                        "error": error,
                    })
                    old = dict(entries.get(url) or {})
                    old.update({
                        **item,
                        "status": "error",
                        "lastError": error,
                        "lastErrorAt": iso(now_dt()),
                    })
                    entries[url] = old
                    continue

                raw_text = result.pop("rawText")
                fetched_at = now_dt()
                raw_hash = "sha256:" + hashlib.sha256(raw_text.encode("utf-8")).hexdigest()
                payload_item = {
                    **item,
                    "route": result.get("route"),
                    "resolvedUrl": result.get("resolvedUrl"),
                    "extractedTitle": result.get("title"),
                    "coverage": result.get("coverage"),
                    "rawTextSha256": raw_hash,
                    "rawText": raw_text,
                }
                payload_items.append(payload_item)
                entries[url] = {
                    **item,
                    "runId": int(args.run_id) if str(args.run_id).isdigit() else str(args.run_id),
                    "requestId": request_id,
                    "artifactName": artifact_name,
                    "route": result.get("route"),
                    "coverage": result.get("coverage"),
                    "chars": len(raw_text),
                    "rawTextSha256": raw_hash,
                    "fetchedAt": iso(fetched_at),
                    "expiresAt": iso(fetched_at + timedelta(days=TTL_DAYS)),
                    "status": "ready",
                }

    # Bound pointer metadata only; raw article text is artifact-only.
    ordered = sorted(
        entries.items(),
        key=lambda kv: str((kv[1] or {}).get("fetchedAt") or (kv[1] or {}).get("lastErrorAt") or ""),
        reverse=True,
    )[:MAX_CACHE_ENTRIES]
    entries = dict(ordered)

    index = {
        "version": 1,
        "policy": "lazy-selected-analysis-fetch; parallel-batch; raw-text-artifact-ttl-7d; repo-stores-pointer-only",
        "updatedAt": iso(now_dt()),
        "latestRequestId": request_id,
        "latestRunId": int(args.run_id) if str(args.run_id).isdigit() else str(args.run_id),
        "latestArtifactName": artifact_name if payload_items else None,
        "requestedCount": len(items),
        "cacheHitCount": len(cache_hits),
        "fetchedCount": len(payload_items),
        "errorCount": len(errors),
        "entries": entries,
        "latestRequest": {
            "requestId": request_id,
            "cacheHits": cache_hits,
            "fetched": [
                {
                    "displayIndex": x.get("displayIndex"),
                    "sourceKey": x.get("sourceKey"),
                    "canonicalUrl": x.get("canonicalUrl"),
                    "route": x.get("route"),
                    "chars": len(x.get("rawText") or ""),
                    "rawTextSha256": x.get("rawTextSha256"),
                    "artifactName": artifact_name,
                }
                for x in payload_items
            ],
            "errors": errors,
        },
    }
    write_json(CACHE_INDEX_PATH, index)

    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    if payload_items:
        write_json(ARTIFACT_PATH, {
            "version": 1,
            "requestId": request_id,
            "runId": index["latestRunId"],
            "artifactName": artifact_name,
            "createdAt": iso(now_dt()),
            "ttlDays": TTL_DAYS,
            "items": payload_items,
        })
    elif ARTIFACT_PATH.exists():
        ARTIFACT_PATH.unlink()

    summary = {
        "ok": len(errors) == 0,
        "requestId": request_id,
        "requestedCount": len(items),
        "cacheHitCount": len(cache_hits),
        "fetchedCount": len(payload_items),
        "errorCount": len(errors),
        "artifactName": artifact_name if payload_items else None,
        "artifactPath": str(ARTIFACT_PATH) if payload_items else None,
        "indexPath": str(CACHE_INDEX_PATH.relative_to(ROOT)),
        "cacheHits": cache_hits,
        "fetched": [
            {"index": x.get("displayIndex"), "url": x.get("canonicalUrl"), "chars": len(x.get("rawText") or ""), "route": x.get("route")}
            for x in payload_items
        ],
        "errors": errors,
    }
    print(json.dumps(summary, ensure_ascii=False))
    return 0 if not errors else 2


if __name__ == "__main__":
    sys.exit(main())
