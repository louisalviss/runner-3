#!/usr/bin/env python3
"""Run reddit_deep_sweep with resilient public-source fallbacks.

Acquisition order:
1. Reddit / old Reddit JSON directly.
2. Authenticated Cloudflare Reddit-only bridge.
3. Source-specific public fallbacks:
   - Arctic Shift for subreddit listings and thread/comment trees.
   - Jina Reader mirror for subreddit wiki pages.

The canonical ranking/storage code remains in reddit_deep_sweep.py.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import time
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
COLLECTOR = Path(__file__).with_name("reddit_deep_sweep.py")
STATUS_PATH = ROOT / "ops/audio-library/chatgpt-bridge-status.json"
UA = "runner3-reddit-deep-sweep/3.0 (+public read-only research)"
ARCHIVE_BASE = "https://arctic-shift.photon-reddit.com"
JINA_BASE = "https://r.jina.ai/https://www.reddit.com"
LISTING_RE = re.compile(r"^/r/([A-Za-z0-9_]+)/(top|new|hot)\.json$")
THREAD_RE = re.compile(r"^/comments/([A-Za-z0-9]+)\.json$")
WIKI_RE = re.compile(r"^/r/([A-Za-z0-9_]+)/wiki/([A-Za-z0-9_.-]+)\.json$")


def load_collector():
    spec = importlib.util.spec_from_file_location("runner3_reddit_deep_sweep", COLLECTOR)
    if spec is None or spec.loader is None:
        raise RuntimeError("unable_to_load_reddit_collector")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def bridge_url() -> str:
    data = json.loads(STATUS_PATH.read_text(encoding="utf-8"))
    value = str(data.get("url") or data.get("worker_url") or "").rstrip("/")
    if not value.startswith("https://"):
        raise RuntimeError("cloudflare_reddit_bridge_url_missing")
    return value


def queue_token() -> str:
    token = os.environ.get("CLOUDFLARE_API_TOKEN", "")
    if not token:
        raise RuntimeError("CLOUDFLARE_API_TOKEN_missing")
    return hashlib.sha256(b"runner3-chatgpt-queue-v2\0" + token.encode()).hexdigest()


def reddit_url(path: str, query: dict[str, str | int] | None) -> str:
    suffix = path
    if query:
        suffix += ("&" if "?" in suffix else "?") + urllib.parse.urlencode(query)
    return "https://www.reddit.com" + suffix


def bridge_request_json(path: str, query: dict[str, str | int] | None = None):
    target = reddit_url(path, query)
    payload = json.dumps({"url": target}).encode("utf-8")
    errors: list[str] = []
    endpoint = bridge_url() + "/source/reddit-json"
    for attempt in range(1, 3):
        req = urllib.request.Request(
            endpoint,
            data=payload,
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
                "User-Agent": UA,
                "X-Runner-Token": queue_token(),
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=40) as resp:
                raw = resp.read()
                status = resp.status
            envelope = json.loads(raw.decode("utf-8"))
            if status != 200 or envelope.get("ok") is not True:
                raise RuntimeError(envelope.get("error") or f"bridge_http_{status}")
            data = envelope.get("data")
            if data is None:
                raise RuntimeError("bridge_missing_data")
            return data, {
                "url": target,
                "bytes": int(envelope.get("bytes") or len(raw)),
                "via": "cloudflare-reddit-json:" + str(envelope.get("via") or "unknown"),
            }
        except Exception as exc:
            errors.append(f"attempt={attempt}:{type(exc).__name__}:{exc}")
            if attempt < 2:
                time.sleep(1)
    raise RuntimeError("cloudflare_reddit_json_failed:" + " | ".join(errors[-2:]))


def archive_get(path: str, query: dict[str, object], timeout: int = 70):
    url = ARCHIVE_BASE + path + "?" + urllib.parse.urlencode(query)
    errors = []
    for attempt in range(1, 4):
        req = urllib.request.Request(
            url,
            headers={"User-Agent": UA, "Accept": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read()
                status = resp.status
            if status != 200:
                raise RuntimeError(f"archive_http_{status}")
            body = json.loads(raw.decode("utf-8"))
            return body, {"url": url, "bytes": len(raw), "via": "arctic-shift"}
        except Exception as exc:
            errors.append(f"attempt={attempt}:{type(exc).__name__}:{exc}")
            if attempt < 3:
                time.sleep(attempt)
    raise RuntimeError("arctic_shift_failed:" + " | ".join(errors[-3:]))


def jina_wiki(path: str):
    match = WIKI_RE.match(path)
    if not match:
        raise RuntimeError("jina_wiki_path_not_supported")
    subreddit, page = match.groups()
    source_url = f"https://www.reddit.com/r/{subreddit}/wiki/{page}/"
    url = f"{JINA_BASE}/r/{subreddit}/wiki/{page}/"
    errors = []
    for attempt in range(1, 4):
        req = urllib.request.Request(
            url,
            headers={"User-Agent": UA, "Accept": "text/plain,text/markdown,*/*;q=0.1"},
        )
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                raw = resp.read()
                status = resp.status
            if status != 200:
                raise RuntimeError(f"jina_http_{status}")
            text = raw.decode("utf-8", "replace").strip()
            if len(text) < 100:
                raise RuntimeError("jina_wiki_too_short")
            payload = {
                "kind": "wikipage",
                "data": {
                    "content_md": text,
                    "content_html": "",
                    "revision_date": None,
                },
                "_runner3_mirror": {
                    "source_url": source_url,
                    "reader_url": url,
                },
            }
            return payload, {
                "url": source_url,
                "bytes": len(raw),
                "via": "jina-reader",
            }
        except Exception as exc:
            errors.append(f"attempt={attempt}:{type(exc).__name__}:{exc}")
            if attempt < 3:
                time.sleep(attempt)
    raise RuntimeError("jina_wiki_failed:" + " | ".join(errors[-3:]))


def iso_utc(epoch: int | float) -> str:
    return dt.datetime.fromtimestamp(float(epoch), tz=dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def period_floor(period: str | None) -> str | None:
    now = dt.datetime.now(dt.timezone.utc)
    delta = {
        "hour": dt.timedelta(hours=2),
        "day": dt.timedelta(days=2),
        "week": dt.timedelta(days=8),
        "month": dt.timedelta(days=32),
        "year": dt.timedelta(days=367),
    }.get(str(period or "").lower())
    if not delta:
        return None
    return (now - delta).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def normalize_post(row: dict, subreddit_hint: str = "") -> dict:
    post = dict(row or {})
    pid = str(post.get("id") or "").removeprefix("t3_")
    subreddit = str(post.get("subreddit") or subreddit_hint)
    post["id"] = pid
    post["subreddit"] = subreddit
    post["title"] = str(post.get("title") or "")
    post["selftext"] = str(post.get("selftext") or "")
    post["author"] = post.get("author")
    post["score"] = int(post.get("score") or 0)
    post["num_comments"] = int(post.get("num_comments") or 0)
    post["created_utc"] = int(float(post.get("created_utc") or 0))
    if not post.get("permalink") and pid:
        post["permalink"] = f"/r/{subreddit}/comments/{pid}/"
    return post


def archive_listing(path: str, query: dict[str, object] | None):
    match = LISTING_RE.match(path)
    if not match:
        raise RuntimeError("archive_listing_path_not_supported")
    subreddit, endpoint = match.groups()
    query = dict(query or {})
    params: dict[str, object] = {
        "subreddit": subreddit,
        "sort": "desc",
        "limit": "auto",
    }
    floor = period_floor(str(query.get("t") or "")) if endpoint == "top" else None
    if floor:
        params["after"] = floor

    cursor = str(query.get("after") or "")
    if cursor.startswith("archive:"):
        try:
            params["before"] = iso_utc(int(cursor.split(":", 1)[1]))
        except Exception:
            pass

    body, meta = archive_get("/api/posts/search", params)
    rows = body.get("data") if isinstance(body, dict) else None
    if not isinstance(rows, list):
        rows = []
    posts = [normalize_post(row, subreddit) for row in rows if isinstance(row, dict) and row.get("id")]
    posts = [p for p in posts if p.get("id")]

    next_cursor = None
    stamps = [int(p.get("created_utc") or 0) for p in posts if int(p.get("created_utc") or 0) > 0]
    if posts and stamps:
        next_cursor = f"archive:{min(stamps) - 1}"

    payload = {
        "kind": "Listing",
        "data": {
            "children": [{"kind": "t3", "data": p} for p in posts],
            "after": next_cursor,
            "before": None,
        },
        "_runner3_archive": {
            "endpoint": endpoint,
            "period": query.get("t"),
            "source_meta": meta,
        },
    }
    return payload, meta


def collect_archive_comments(obj, out: dict[str, dict], depth: int = 0):
    if isinstance(obj, list):
        for item in obj:
            collect_archive_comments(item, out, depth)
        return
    if not isinstance(obj, dict):
        return

    cid = str(obj.get("id") or "").removeprefix("t1_")
    body = obj.get("body")
    if cid and isinstance(body, str):
        out[cid] = {
            "id": cid,
            "parent_id": obj.get("parent_id"),
            "author": obj.get("author"),
            "depth": int(obj.get("depth") if obj.get("depth") is not None else depth),
            "body": body,
            "score": int(obj.get("score") or 0),
            "created_utc": int(float(obj.get("created_utc") or 0)),
            "replies": "",
        }

    for key, value in obj.items():
        if key in {"body", "body_html", "selftext", "selftext_html"}:
            continue
        collect_archive_comments(value, out, depth + (1 if key in {"replies", "children"} else 0))


def archive_thread(path: str, query: dict[str, object] | None):
    match = THREAD_RE.match(path)
    if not match:
        raise RuntimeError("archive_thread_path_not_supported")
    pid = match.group(1)

    post_body, post_meta = archive_get("/api/posts/ids", {"ids": pid})
    rows = post_body.get("data") if isinstance(post_body, dict) else None
    if not isinstance(rows, list):
        rows = post_body.get("posts") if isinstance(post_body, dict) else None
    if not isinstance(rows, list) or not rows:
        raise RuntimeError(f"arctic_shift_post_not_found:{pid}")
    post = normalize_post(rows[0] if isinstance(rows[0], dict) else {}, "")

    comments_body, comments_meta = archive_get(
        "/api/comments/tree",
        {"link_id": "t3_" + pid, "limit": 9999},
        timeout=100,
    )
    comments: dict[str, dict] = {}
    collect_archive_comments(comments_body, comments)
    children = [{"kind": "t1", "data": row} for row in comments.values()]

    payload = [
        {"kind": "Listing", "data": {"children": [{"kind": "t3", "data": post}]}},
        {"kind": "Listing", "data": {"children": children}},
    ]
    meta = {
        "url": comments_meta.get("url"),
        "bytes": int(post_meta.get("bytes") or 0) + int(comments_meta.get("bytes") or 0),
        "via": "arctic-shift",
    }
    return payload, meta


def public_fallback_request_json(path: str, query: dict[str, object] | None = None):
    if WIKI_RE.match(path):
        return jina_wiki(path)
    if LISTING_RE.match(path):
        return archive_listing(path, query)
    if THREAD_RE.match(path):
        return archive_thread(path, query)
    raise RuntimeError(f"public_fallback_path_not_supported:{path}")


def main():
    collector = load_collector()
    direct_request_json = collector.request_json
    bridge_available = True

    def request_json(path: str, query=None, tries: int = 3):
        nonlocal bridge_available
        direct_error = None
        bridge_error = None
        try:
            return direct_request_json(path, query, tries)
        except Exception as exc:
            direct_error = exc

        if bridge_available:
            try:
                return bridge_request_json(path, query)
            except Exception as exc:
                bridge_error = exc
                bridge_available = False

        try:
            return public_fallback_request_json(path, query)
        except Exception as fallback_exc:
            raise RuntimeError(
                " | ".join(
                    part for part in [
                        f"direct_reddit_failed:{direct_error}" if direct_error else "",
                        f"bridge_failed:{bridge_error}" if bridge_error else ("bridge_disabled" if not bridge_available else ""),
                        f"public_fallback_failed:{fallback_exc}",
                    ] if part
                )
            ) from fallback_exc

    collector.request_json = request_json
    collector.main()


if __name__ == "__main__":
    main()
