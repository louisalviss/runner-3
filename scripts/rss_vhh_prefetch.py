#!/usr/bin/env python3

import argparse
import hashlib
import html
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
DATA_ROOT = ROOT / "data" / "rss-reader"
MIRROR_PATH = DATA_ROOT / "sources" / "vohoanghac.json"
INDEX_PATH = DATA_ROOT / "vhh-prefetch-index.json"
ARTIFACT_DIR = Path("/tmp/rss-vhh-prefetch")
ARTIFACT_PATH = ARTIFACT_DIR / "payload.json"
UA = "Mozilla/5.0 (compatible; runner-3-vhh-prefetch/1.0; +https://github.com/louisalviss/runner-3)"
DIRECT_TIMEOUT = 8
JINA_TIMEOUT = 25
MIN_TEXT_CHARS = 800
TTL_DAYS = 7
BOOTSTRAP_PREFETCH = 3
MAX_OBSERVED = 100


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
    text = html.unescape(str(value or ""))
    text = re.sub(r"\s+", " ", text).strip()
    return text


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
    return title or (urlparse(final_url).hostname or "Võ Hoàng Hạc"), body


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
    return {"route": "direct", "canonicalUrl": r.url, "title": title, "rawText": text}


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
    title = clean_text(title_match.group(1)) if title_match else "Võ Hoàng Hạc"
    canonical = source_match.group(1).strip() if source_match else url
    body = re.sub(r"(?mi)^(Title|URL Source|Published Time|Markdown Content):\s*.*$", "", raw)
    body = body.strip()
    if len(body) < MIN_TEXT_CHARS:
        raise RuntimeError(f"jina body too thin: {len(body)}")
    return {"route": "jina-live", "canonicalUrl": canonical, "title": title, "rawText": body}


def extract(url):
    errors = []
    try:
        return extract_direct(url)
    except Exception as exc:
        errors.append(f"direct={type(exc).__name__}: {exc}")
    try:
        return extract_jina(url)
    except Exception as exc:
        errors.append(f"jina={type(exc).__name__}: {exc}")
    raise RuntimeError("; ".join(errors))


def current_articles(mirror):
    items = [dict(x) for x in (mirror.get("items") or []) if x.get("itemType") == "article" and x.get("canonicalUrl")]
    items.sort(key=lambda x: x.get("publishedTs") or 0, reverse=True)
    return items


def observed_snapshot(articles):
    out = {}
    for item in articles[:MAX_OBSERVED]:
        url = item.get("canonicalUrl")
        if not url:
            continue
        out[url] = {
            "contentHash": item.get("contentHash"),
            "publishedAt": item.get("publishedAt"),
            "title": item.get("title"),
        }
    return out


def entry_is_fresh(entry, item, now):
    if not isinstance(entry, dict):
        return False
    if item.get("contentHash") and entry.get("contentHash") != item.get("contentHash"):
        return False
    expires = entry.get("expiresAt")
    if not expires:
        return False
    try:
        dt = datetime.fromisoformat(str(expires).replace("Z", "+00:00"))
    except Exception:
        return False
    return dt > now


def select_candidates(index, articles, explicit_urls, force, max_items, now):
    by_url = {x.get("canonicalUrl"): x for x in articles if x.get("canonicalUrl")}
    entries = index.get("entries") or {}
    previous_observed = index.get("observed") or {}
    initialized = bool(index.get("initializedAt"))
    selected = []
    seen = set()

    for url in explicit_urls:
        item = dict(by_url.get(url) or {"canonicalUrl": url, "title": url, "publishedAt": None, "publishedTs": 0, "contentHash": None, "itemType": "article"})
        if force or not entry_is_fresh(entries.get(url), item, now):
            selected.append(item)
            seen.add(url)

    if explicit_urls:
        return selected[:max_items]

    if not initialized:
        for item in articles[:BOOTSTRAP_PREFETCH]:
            url = item.get("canonicalUrl")
            if url and url not in seen:
                selected.append(item)
                seen.add(url)
        return selected[:max_items]

    for item in articles:
        url = item.get("canonicalUrl")
        if not url or url in seen:
            continue
        old = previous_observed.get(url)
        is_new_identity = old is None
        hash_changed = bool(old and old.get("contentHash") and item.get("contentHash") and old.get("contentHash") != item.get("contentHash"))
        cached_stale = url in entries and not entry_is_fresh(entries.get(url), item, now)
        if is_new_identity or hash_changed or cached_stale:
            selected.append(item)
            seen.add(url)
        if len(selected) >= max_items:
            break
    return selected


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--url", action="append", default=[])
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--max-items", type=int, default=3)
    args = parser.parse_args()

    mirror = load_json(MIRROR_PATH)
    articles = current_articles(mirror)
    if not articles and not args.url:
        raise SystemExit("VHH mirror has no article items")

    index = load_json(INDEX_PATH)
    if not isinstance(index, dict):
        index = {}
    now = now_dt()
    candidates = select_candidates(index, articles, args.url, args.force, max(1, args.max_items), now)
    artifact_name = f"rss-vhh-prefetch-{args.run_id}"
    payload_items = []
    errors = []
    entries = dict(index.get("entries") or {})

    for item in candidates:
        url = item.get("canonicalUrl")
        try:
            result = extract(url)
            raw_text = result.pop("rawText")
            fetched_at = now_dt()
            cache_key = "sha256:" + hashlib.sha256(raw_text.encode("utf-8")).hexdigest()
            payload_items.append({
                "sourceKey": "vohoanghac",
                "itemType": "article",
                "canonicalUrl": url,
                "title": item.get("title") or result.get("title"),
                "publishedAt": item.get("publishedAt"),
                "contentHash": item.get("contentHash"),
                "route": result.get("route"),
                "rawTextSha256": cache_key,
                "rawText": raw_text,
            })
            entries[url] = {
                "canonicalUrl": url,
                "title": item.get("title") or result.get("title"),
                "publishedAt": item.get("publishedAt"),
                "contentHash": item.get("contentHash"),
                "runId": int(args.run_id) if str(args.run_id).isdigit() else str(args.run_id),
                "artifactName": artifact_name,
                "route": result.get("route"),
                "chars": len(raw_text),
                "rawTextSha256": cache_key,
                "fetchedAt": iso(fetched_at),
                "expiresAt": iso(fetched_at + timedelta(days=TTL_DAYS)),
                "status": "ready",
            }
        except Exception as exc:
            errors.append({"canonicalUrl": url, "error": f"{type(exc).__name__}: {exc}"})
            old = dict(entries.get(url) or {})
            old.update({
                "canonicalUrl": url,
                "title": item.get("title"),
                "publishedAt": item.get("publishedAt"),
                "contentHash": item.get("contentHash"),
                "lastErrorAt": iso(now_dt()),
                "lastError": f"{type(exc).__name__}: {exc}",
                "status": "error",
            })
            entries[url] = old

    # Keep metadata bounded; raw article text never enters the repo.
    ordered_urls = [x.get("canonicalUrl") for x in articles if x.get("canonicalUrl")]
    kept = {}
    for url in ordered_urls[:MAX_OBSERVED]:
        if url in entries:
            kept[url] = entries[url]
    for url in args.url:
        if url in entries:
            kept[url] = entries[url]

    new_index = {
        "version": 1,
        "sourceKey": "vohoanghac",
        "policy": "prefetch-canonical-article-on-detect; raw-text-artifact-ttl-7d; repo-stores-pointer-only",
        "initializedAt": index.get("initializedAt") or iso(now),
        "updatedAt": iso(now_dt()),
        "latestRunId": int(args.run_id) if str(args.run_id).isdigit() else str(args.run_id),
        "latestArtifactName": artifact_name if payload_items else None,
        "prefetchedCount": len(payload_items),
        "errorCount": len(errors),
        "observed": observed_snapshot(articles),
        "entries": kept,
        "errors": errors[-10:],
    }
    write_json(INDEX_PATH, new_index)

    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    if payload_items:
        write_json(ARTIFACT_PATH, {
            "version": 1,
            "sourceKey": "vohoanghac",
            "runId": new_index["latestRunId"],
            "artifactName": artifact_name,
            "createdAt": iso(now_dt()),
            "ttlDays": TTL_DAYS,
            "items": payload_items,
        })
    elif ARTIFACT_PATH.exists():
        ARTIFACT_PATH.unlink()

    print(json.dumps({
        "ok": not errors,
        "candidateCount": len(candidates),
        "prefetchedCount": len(payload_items),
        "errorCount": len(errors),
        "artifactName": artifact_name if payload_items else None,
        "indexPath": str(INDEX_PATH.relative_to(ROOT)),
        "artifactPath": str(ARTIFACT_PATH) if payload_items else None,
        "items": [{"url": x["canonicalUrl"], "chars": len(x["rawText"]), "route": x["route"]} for x in payload_items],
        "errors": errors,
    }, ensure_ascii=False))
    return 0 if not errors else 2


if __name__ == "__main__":
    sys.exit(main())
