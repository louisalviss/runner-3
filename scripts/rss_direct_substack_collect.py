#!/usr/bin/env python3
"""Collect Hồ Quốc Tuấn and vnhacker as first-class Runner sources.

GitHub-hosted runners receive 403 from the public `/feed` endpoint for these
Substacks. The publication archive API remains public and exposes canonical post
metadata, so this collector uses that API as the primary transport and persists
normal Runner mirrors. This removes the old manual direct-verification gap.
"""

import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import requests
import rss_reader_collect_v2 as hardened

base = hardened.base
ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "rss-reader"
SOURCES_ROOT = DATA / "sources"
HEALTH_PATH = DATA / "direct-substack-health.json"
TIMEOUT = 45

SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://substack.com/",
})

SOURCES = [
    {
        "key": "hoquoctuan",
        "name": "Hồ Quốc Tuấn",
        "publication": "https://hoquoctuan.substack.com",
    },
    {
        "key": "vnhacker",
        "name": "vnhacker",
        "publication": "https://vnhacker.substack.com",
    },
]


def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def load_json(path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _post_url(source, post):
    value = (
        post.get("canonical_url") or post.get("canonicalUrl")
        or post.get("post_url") or post.get("postUrl") or post.get("url")
    )
    if value and str(value).startswith(("http://", "https://")):
        return base.canonicalize_url(value, source["key"])
    slug = post.get("slug")
    if slug:
        return f"{source['publication'].rstrip('/')}/p/{slug}"
    return None


def _post_dt(post):
    for key in (
        "post_date", "postDate", "published_at", "publishedAt",
        "publication_date", "publicationDate", "created_at", "createdAt",
    ):
        dt = base.parse_dt(post.get(key))
        if dt is not None:
            return dt
    return None


def _description(post):
    for key in (
        "subtitle", "description", "truncated_body_text", "truncatedBodyText",
        "body_preview", "bodyPreview", "social_title", "socialTitle",
    ):
        value = base.clean_text(post.get(key))
        if value:
            return value
    return None


def fetch_archive(source):
    archive_url = source["publication"].rstrip("/") + "/api/v1/archive"
    attempts = []
    for limit in (50, 25, 10):
        try:
            response = SESSION.get(
                archive_url,
                params={"sort": "new", "limit": limit},
                timeout=TIMEOUT,
                allow_redirects=True,
            )
            attempts.append({"transport": "substack-archive-api", "url": response.url, "status": response.status_code})
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, list) or not payload:
                raise RuntimeError("archive payload is not a non-empty list")
            items = []
            for post in payload:
                if not isinstance(post, dict):
                    continue
                title = base.clean_text(post.get("title"))
                url = _post_url(source, post)
                dt = _post_dt(post)
                if not title or not url or dt is None:
                    continue
                post_id = post.get("id") or post.get("post_id") or post.get("postId")
                key = f"substack-post:{post_id}" if post_id is not None else base.stable_key(url)
                items.append({
                    "key": key,
                    "articleId": str(post_id) if post_id is not None else None,
                    "canonicalUrl": url,
                    "title": title,
                    "publishedAt": base.dt_iso(dt),
                    "publishedTs": int(dt.timestamp() * 1000),
                    "thumbnail": None,
                    "author": source["name"],
                    "description": _description(post),
                    "contentSource": "substack_archive_api",
                    "itemType": "article",
                })
            items = base.dedupe_fresh_items(items)
            if not items:
                raise RuntimeError("archive returned no parseable posts")
            return items, response.url, attempts
        except Exception as exc:
            attempts.append({"transport": "substack-archive-api", "url": archive_url, "limit": limit, "error": f"{type(exc).__name__}: {exc}"})
    raise RuntimeError(json.dumps(attempts, ensure_ascii=False))


def collect_one(source):
    key = source["key"]
    path = SOURCES_ROOT / f"{key}.json"
    old = load_json(path, {})
    old_items = old.get("items") or []
    fresh_items, final_url, attempts = fetch_archive(source)
    merged = base.merge_items(old_items, fresh_items)
    newest = merged[0].get("publishedAt") if merged else None
    transport = "substack-archive-api"
    content_changed = (
        not old
        or old.get("items") != merged
        or old.get("transport") != transport
        or old.get("finalFeedUrl") != final_url
    )
    if content_changed:
        mirror = {
            "source": source["name"],
            "sourceKey": key,
            "collector": "runner-3",
            "transport": transport,
            "feedUrl": source["publication"].rstrip("/") + "/api/v1/archive",
            "finalFeedUrl": final_url,
            "lastContentChangeAt": now_iso(),
            "freshItemCount": len(fresh_items),
            "totalStored": len(merged),
            "count": len(merged),
            "newestPublishedAt": newest,
            "items": merged,
        }
        base.write_json(path, mirror)
    return {
        "ok": True,
        "transport": transport,
        "checkedAt": now_iso(),
        "contentChanged": content_changed,
        "newestPublishedAt": newest,
        "freshItemCount": len(fresh_items),
        "totalStored": len(merged),
        "attempts": attempts,
    }


def main():
    SOURCES_ROOT.mkdir(parents=True, exist_ok=True)
    health = {
        "version": 2,
        "collector": "runner-3",
        "scope": "2-substack-archive-api-sources",
        "runStartedAt": now_iso(),
        "sourceCount": len(SOURCES),
        "sources": {},
    }
    ok_count = 0
    for source in SOURCES:
        key = source["key"]
        mirror = load_json(SOURCES_ROOT / f"{key}.json", {})
        try:
            health["sources"][key] = collect_one(source)
            ok_count += 1
        except Exception as exc:
            health["sources"][key] = {
                "ok": False,
                "checkedAt": now_iso(),
                "preservedExistingMirror": bool(mirror.get("items")),
                "newestPublishedAt": mirror.get("newestPublishedAt"),
                "error": f"{type(exc).__name__}: {exc}",
            }
    health["runFinishedAt"] = now_iso()
    health["okCount"] = ok_count
    health["failedCount"] = len(SOURCES) - ok_count
    health["status"] = "healthy" if ok_count == len(SOURCES) else ("degraded" if ok_count else "failed")
    base.write_json(HEALTH_PATH, health)
    print(json.dumps({
        "collector": "runner-3",
        "scope": health["scope"],
        "status": health["status"],
        "ok": health["okCount"],
        "failed": health["failedCount"],
        "health": str(HEALTH_PATH.relative_to(ROOT)),
    }, ensure_ascii=False))
    return 0 if health["status"] == "healthy" else 2


if __name__ == "__main__":
    raise SystemExit(main())
