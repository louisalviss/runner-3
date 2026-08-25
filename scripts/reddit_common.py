#!/usr/bin/env python3
"""Shared public Reddit acquisition primitives for Runner-3.

This module owns source access mechanics only. Product/workload semantics live in
the callers:
- reddit_read.py: one current/live Reddit URL
- reddit_deep_sweep_cloudflare.py: subreddit/corpus research

Acquisition order:
1. direct Reddit JSON (www, then old.reddit)
2. authenticated Runner-3 Cloudflare Reddit bridge
3. Arctic Shift public archive for listings/thread trees

Reddit /s/ share URLs are resolved through rxddit redirect metadata before fetch.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import time
import urllib.error
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
STATUS_PATH = ROOT / "ops/audio-library/chatgpt-bridge-status.json"
UA = "runner3-reddit-read/2.0 (+public read-only research)"
ARCHIVE_BASE = "https://arctic-shift.photon-reddit.com"

LISTING_RE = re.compile(r"^/r/([A-Za-z0-9_]+)/(top|new|hot)\.json$")
THREAD_RE = re.compile(r"^/comments/([A-Za-z0-9]+)\.json$")
POST_RE = re.compile(r"/comments/([A-Za-z0-9]+)/", re.I)


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def canonical_from_url(value: str) -> tuple[str | None, str | None]:
    value = (value or "").strip()
    try:
        parts = urllib.parse.urlsplit(value)
    except ValueError:
        return None, None
    host = (parts.hostname or "").lower()
    if not (host == "reddit.com" or host.endswith(".reddit.com") or host in {"rxddit.com", "www.rxddit.com"}):
        return None, None
    match = POST_RE.search(parts.path or "")
    if not match:
        return None, None
    pid = match.group(1)
    canonical = urllib.parse.urlunsplit(("https", "www.reddit.com", parts.path, "", ""))
    return canonical.rstrip("/") + "/", pid


def resolve_reddit_url(url: str) -> tuple[str, str, dict]:
    canonical, pid = canonical_from_url(url)
    if canonical and pid:
        return canonical, pid, {"via": "canonical", "diagnostics": ["already-canonical"]}

    parts = urllib.parse.urlsplit((url or "").strip())
    host = (parts.hostname or "").lower()
    if not (host == "reddit.com" or host.endswith(".reddit.com")) or "/s/" not in parts.path:
        raise RuntimeError("unsupported_reddit_url: expected canonical /comments/ URL or Reddit /s/ share URL")

    target = urllib.parse.urlunsplit(("https", "rxddit.com", parts.path, parts.query, ""))
    req = urllib.request.Request(
        target,
        headers={
            "User-Agent": UA,
            "Accept": "text/html,application/xhtml+xml,*/*;q=0.1",
            "Accept-Language": "en-US,en;q=0.5",
        },
    )
    opener = urllib.request.build_opener(NoRedirect)
    status = None
    location = ""
    body = ""
    try:
        with opener.open(req, timeout=45) as resp:
            status = resp.status
            location = resp.headers.get("Location", "")
            body = resp.read(200_000).decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        status = exc.code
        location = exc.headers.get("Location", "")
        try:
            body = exc.read(200_000).decode("utf-8", "replace")
        except Exception:
            body = ""

    diagnostics = [f"rxddit:{status}:{'location' if location else 'no-location'}:{len(body)}"]
    candidates: list[str] = []
    if location:
        candidates.append(urllib.parse.urljoin(target, location))
    candidates.extend(
        re.findall(r"https?://[^\s\"'<>]+/comments/[A-Za-z0-9]+/[^\s\"'<>]*", body, re.I)
    )
    for candidate in candidates:
        cparts = urllib.parse.urlsplit(candidate)
        if (cparts.hostname or "").lower() in {"rxddit.com", "www.rxddit.com"}:
            candidate = urllib.parse.urlunsplit(("https", "www.reddit.com", cparts.path, "", ""))
        canonical, pid = canonical_from_url(candidate)
        if canonical and pid:
            return canonical, pid, {"via": "rxddit", "diagnostics": diagnostics}

    raise RuntimeError("reddit_shortlink_unresolved:" + ";".join(diagnostics))


def reddit_url(host: str, path: str, query: dict | None) -> str:
    suffix = path
    if query:
        suffix += ("&" if "?" in suffix else "?") + urllib.parse.urlencode(query)
    return f"https://{host}{suffix}"


def direct_request_json(path: str, query: dict | None = None, tries: int = 2):
    errors: list[str] = []
    for host in ("www.reddit.com", "old.reddit.com"):
        url = reddit_url(host, path, query)
        for attempt in range(1, tries + 1):
            req = urllib.request.Request(
                url,
                headers={
                    "User-Agent": UA,
                    "Accept": "application/json",
                    "Accept-Language": "en-US,en;q=0.5",
                },
            )
            try:
                with urllib.request.urlopen(req, timeout=45) as resp:
                    raw = resp.read()
                    if resp.status != 200:
                        raise RuntimeError(f"http_{resp.status}")
                return json.loads(raw.decode("utf-8")), {
                    "url": url,
                    "bytes": len(raw),
                    "via": f"reddit-json:{host}",
                }
            except Exception as exc:
                errors.append(f"{host}:attempt={attempt}:{type(exc).__name__}:{exc}")
                if attempt < tries:
                    time.sleep(attempt)
    raise RuntimeError("direct_reddit_failed:" + " | ".join(errors[-6:]))


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


def bridge_request_json(path: str, query: dict | None = None):
    target = reddit_url("www.reddit.com", path, query)
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
    errors: list[str] = []
    for attempt in range(1, 4):
        req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read()
                status = resp.status
            if status != 200:
                raise RuntimeError(f"archive_http_{status}")
            return json.loads(raw.decode("utf-8")), {
                "url": url,
                "bytes": len(raw),
                "via": "arctic-shift",
            }
        except Exception as exc:
            errors.append(f"attempt={attempt}:{type(exc).__name__}:{exc}")
            if attempt < 3:
                time.sleep(attempt)
    raise RuntimeError("arctic_shift_failed:" + " | ".join(errors[-3:]))


def iso_utc(epoch: int | float) -> str:
    return (
        dt.datetime.fromtimestamp(float(epoch), tz=dt.timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


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
    params: dict[str, object] = {"subreddit": subreddit, "sort": "desc", "limit": "auto"}
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
    stamps = [int(p.get("created_utc") or 0) for p in posts if int(p.get("created_utc") or 0) > 0]
    next_cursor = f"archive:{min(stamps) - 1}" if posts and stamps else None
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
        "/api/comments/tree", {"link_id": "t3_" + pid, "limit": 9999}, timeout=100
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
    if LISTING_RE.match(path):
        return archive_listing(path, query)
    if THREAD_RE.match(path):
        return archive_thread(path, query)
    raise RuntimeError(f"public_fallback_path_not_supported:{path}")


def resilient_request_json(path: str, query: dict | None = None, tries: int = 2):
    errors: list[str] = []
    try:
        return direct_request_json(path, query, tries)
    except Exception as exc:
        errors.append(str(exc))

    try:
        return bridge_request_json(path, query)
    except Exception as exc:
        errors.append("bridge_failed:" + str(exc))

    try:
        return public_fallback_request_json(path, query)
    except Exception as exc:
        errors.append("public_fallback_failed:" + str(exc))
        raise RuntimeError(" | ".join(errors)) from exc


def _flatten_live_comment(child: dict, out: list[dict], depth: int = 0):
    if not isinstance(child, dict) or child.get("kind") != "t1":
        return
    data = dict(child.get("data") or {})
    data["depth"] = int(data.get("depth") if data.get("depth") is not None else depth)
    replies = data.get("replies")
    data["replies"] = ""
    out.append(data)
    if isinstance(replies, dict):
        for nested in ((replies.get("data") or {}).get("children") or []):
            _flatten_live_comment(nested, out, depth + 1)


def normalize_thread_payload(payload, post_id: str) -> tuple[dict, list[dict]]:
    if not isinstance(payload, list) or len(payload) < 2:
        raise RuntimeError("reddit_thread_payload_invalid")
    post_children = ((payload[0] or {}).get("data") or {}).get("children") or []
    if not post_children:
        raise RuntimeError("reddit_thread_post_missing")
    post = dict((post_children[0] or {}).get("data") or {})
    post = normalize_post(post, str(post.get("subreddit") or ""))

    comments: list[dict] = []
    for child in ((payload[1] or {}).get("data") or {}).get("children") or []:
        _flatten_live_comment(child, comments, 0)

    if not comments:
        for child in ((payload[1] or {}).get("data") or {}).get("children") or []:
            if isinstance(child, dict) and child.get("kind") == "t1":
                row = dict(child.get("data") or {})
                row["depth"] = int(row.get("depth") or 0)
                row["replies"] = ""
                comments.append(row)

    for row in comments:
        if row.get("parent_id") == post_id:
            row["parent_id"] = "t3_" + post_id
    return post, comments


def read_current_thread(url: str):
    canonical, post_id, resolver = resolve_reddit_url(url)
    path = f"/comments/{post_id}.json"
    query = {"limit": 9999, "depth": 10, "sort": "top", "raw_json": 1}
    payload, meta = resilient_request_json(path, query)
    post, comments = normalize_thread_payload(payload, post_id)
    return canonical, post_id, resolver, post, comments, meta
