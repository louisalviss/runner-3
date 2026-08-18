#!/usr/bin/env python3

import hashlib
import html
import json
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import urlparse, urlunparse

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
DATA_ROOT = ROOT / "data" / "rss-reader"
SOURCES_ROOT = DATA_ROOT / "sources"
HEALTH_PATH = DATA_ROOT / "substack-health.json"
MAX_ARCHIVE_ITEMS = 1000
MAX_NOTE_PAGES = 3
TIMEOUT = 45

# Võ Hoàng Hạc is one logical source with two REQUIRED freshness components:
# 1) long-form publication posts via the publication RSS feed;
# 2) short-form Substack Notes via the public profile reader feed.
# If either component cannot be verified, the source fails closed.
SOURCE = {
    "key": "vohoanghac",
    "name": "Võ Hoàng Hạc",
    "article_feed": "https://vohoanghac.com/feed",
    "handle": "vohoanghac",
    "profile_url": "https://substack.com/@vohoanghac",
    "track_content_hash": True,
}

SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": "Mozilla/5.0 (compatible; runner-3-rss-reader/2.0; +https://github.com/louisalviss/runner-3)",
})


def now_dt():
    return datetime.now(timezone.utc)


def now_iso():
    return now_dt().isoformat(timespec="seconds").replace("+00:00", "Z")


def local_name(tag):
    return tag.split("}", 1)[-1].lower()


def child_text(node, names):
    wanted = set(names)
    for child in list(node):
        if local_name(child.tag) in wanted and child.text and child.text.strip():
            return child.text.strip()
    return None


def clean_text(value):
    if value is None:
        return None
    text = BeautifulSoup(html.unescape(str(value)), "html.parser").get_text(" ", strip=True)
    return re.sub(r"\s+", " ", text).strip() or None


def parse_dt(value):
    if value is None:
        return None

    if isinstance(value, (int, float)):
        number = float(value)
        if number > 10_000_000_000:
            number /= 1000.0
        if number > 1_000_000_000:
            try:
                return datetime.fromtimestamp(number, tz=timezone.utc)
            except Exception:
                return None

    value = str(value).strip()
    if not value:
        return None

    try:
        dt = parsedate_to_datetime(value)
    except Exception:
        dt = None
    if dt is None:
        try:
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except Exception:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def canonicalize_url(value):
    if not value or not value.startswith(("http://", "https://")):
        return None
    p = urlparse(html.unescape(value.strip()))
    return urlunparse((p.scheme, p.netloc.lower(), p.path, "", "", ""))


def find_link(node):
    direct = child_text(node, {"link"})
    if direct and direct.startswith(("http://", "https://")):
        return direct
    for child in list(node):
        if local_name(child.tag) == "link":
            href = child.attrib.get("href")
            if href and child.attrib.get("rel", "alternate") in ("alternate", ""):
                return href
    return None


def stable_key(url, guid=None):
    if guid:
        guid = str(guid).strip()
        match = re.search(r"(?:^|/)(\d{5,})(?:/|$)", guid)
        if match:
            return f"id:{match.group(1)}"
    return "url:" + hashlib.sha1(url.encode("utf-8")).hexdigest()[:20]


def content_hash(node):
    candidates = []
    for child in list(node):
        if local_name(child.tag) in {"description", "summary", "content", "encoded"} and child.text:
            text = clean_text(child.text)
            if text:
                candidates.append(text)
    if not candidates:
        return None
    body = max(candidates, key=len)
    return "sha256:" + hashlib.sha256(body.encode("utf-8")).hexdigest()


def parse_article_feed(raw):
    root = ET.fromstring(raw)
    if local_name(root.tag) == "rss":
        channel = next((c for c in list(root) if local_name(c.tag) == "channel"), None)
        nodes = [c for c in list(channel or []) if local_name(c.tag) == "item"]
    else:
        nodes = [n for n in root.iter() if local_name(n.tag) in {"item", "entry"}]

    out = []
    for node in nodes:
        title = clean_text(child_text(node, {"title"}))
        url = canonicalize_url(find_link(node))
        dt = parse_dt(child_text(node, {"pubdate", "published", "updated", "date"}))
        if not title or not url or not dt:
            continue
        desc_raw = child_text(node, {"description", "summary", "content", "encoded"})
        key = stable_key(url, child_text(node, {"guid", "id"}))
        out.append({
            "key": key,
            "articleId": key[3:] if key.startswith("id:") else None,
            "canonicalUrl": url,
            "title": title,
            "publishedAt": dt.isoformat(timespec="seconds").replace("+00:00", "Z"),
            "publishedTs": int(dt.timestamp() * 1000),
            "thumbnail": None,
            "author": clean_text(child_text(node, {"author", "creator"})),
            "description": clean_text(desc_raw),
            "contentSource": "rss_radar",
            "itemType": "article",
            "contentHash": content_hash(node),
        })
    out.sort(key=lambda x: x["publishedTs"], reverse=True)
    return out


def load_json(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def write_json(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def normalize_old_items(items):
    normalized = []
    for raw in items or []:
        item = dict(raw)
        if not item.get("itemType"):
            url = item.get("canonicalUrl") or ""
            item["itemType"] = "note" if "/note/c-" in url else "article"
        normalized.append(item)
    return normalized


def merge_items(old_items, fresh_items):
    merged = {}
    for item in normalize_old_items(old_items):
        identity = item.get("canonicalUrl") or item.get("key")
        if identity:
            merged[identity] = item
    for item in fresh_items or []:
        identity = item.get("canonicalUrl") or item.get("key")
        if identity:
            merged[identity] = item
    values = list(merged.values())
    values.sort(key=lambda x: x.get("publishedTs") or 0, reverse=True)
    return values[:MAX_ARCHIVE_ITEMS]


def detect_hash_changes(old_items, fresh_articles):
    old_by_id = {
        (i.get("canonicalUrl") or i.get("key")): i
        for i in normalize_old_items(old_items)
        if i.get("itemType") == "article"
    }
    changes = []
    for item in fresh_articles:
        ident = item.get("canonicalUrl") or item.get("key")
        old = old_by_id.get(ident)
        old_hash = (old or {}).get("contentHash")
        new_hash = item.get("contentHash")
        if old and old_hash and new_hash and old_hash != new_hash:
            changes.append({
                "key": item.get("key"),
                "canonicalUrl": item.get("canonicalUrl"),
                "title": item.get("title"),
                "publishedAt": item.get("publishedAt"),
                "oldContentHash": old_hash,
                "newContentHash": new_hash,
            })
    return changes


def get_json(url, *, params=None):
    response = SESSION.get(
        url,
        params=params,
        timeout=TIMEOUT,
        allow_redirects=True,
        headers={"Accept": "application/json, text/plain, */*"},
    )
    response.raise_for_status()
    return response.json(), response.url


def extract_profile_user_id(obj, handle):
    target = handle.lower()

    def walk(value):
        if isinstance(value, dict):
            obj_handle = str(value.get("handle") or value.get("username") or "").lstrip("@").lower()
            obj_id = value.get("id") or value.get("user_id") or value.get("userId")
            if obj_handle == target and str(obj_id).isdigit():
                return int(obj_id)
            for child in value.values():
                found = walk(child)
                if found is not None:
                    return found
        elif isinstance(value, list):
            for child in value:
                found = walk(child)
                if found is not None:
                    return found
        return None

    found = walk(obj)
    if found is not None:
        return found

    if isinstance(obj, dict):
        top_id = obj.get("id") or obj.get("user_id") or obj.get("userId")
        if str(top_id).isdigit():
            return int(top_id)
    return None


def resolve_profile_user_id(handle):
    # Substack does not document a public Notes RSS feed. The web client exposes
    # a public profile JSON surface; this is deliberately treated as fragile and
    # fail-closed so an upstream change cannot produce a false "healthy" result.
    candidates = [
        f"https://substack.com/api/v1/user/{handle}/public_profile",
        f"https://substack.com/api/v1/user/{handle}/public_profile/self",
    ]
    errors = []
    for url in candidates:
        try:
            payload, final_url = get_json(url)
            user_id = extract_profile_user_id(payload, handle)
            if user_id is not None:
                return user_id, final_url
            errors.append(f"{url}: JSON returned but user id was not found")
        except Exception as exc:
            errors.append(f"{url}: {type(exc).__name__}: {exc}")

    # Last-resort discovery from the public profile HTML/hydration only.
    try:
        response = SESSION.get(
            f"https://substack.com/@{handle}",
            timeout=TIMEOUT,
            allow_redirects=True,
            headers={"Accept": "text/html,application/xhtml+xml"},
        )
        response.raise_for_status()
        raw = response.text
        patterns = [
            r"/api/v1/reader/feed/profile/(\d+)",
            r'"user_id"\s*:\s*(\d+)',
            r'"userId"\s*:\s*(\d+)',
        ]
        for pattern in patterns:
            for match in re.finditer(pattern, raw):
                candidate = int(match.group(1))
                if candidate > 0:
                    return candidate, response.url
        errors.append("public profile HTML returned but user id was not discoverable")
    except Exception as exc:
        errors.append(f"profile HTML: {type(exc).__name__}: {exc}")

    raise RuntimeError("unable to resolve Substack profile user id; " + " | ".join(errors))


def value_at(obj, path):
    cur = obj
    for key in path:
        if not isinstance(cur, dict) or key not in cur:
            return None
        cur = cur[key]
    return cur


def extract_feed_dt(item):
    preferred_paths = [
        ("context", "timestamp"),
        ("context", "published_at"),
        ("context", "publishedAt"),
        ("context", "created_at"),
        ("context", "createdAt"),
        ("timestamp",),
        ("published_at",),
        ("publishedAt",),
        ("created_at",),
        ("createdAt",),
        ("comment", "date"),
        ("comment", "created_at"),
        ("comment", "createdAt"),
    ]
    for path in preferred_paths:
        dt = parse_dt(value_at(item, path))
        if dt is not None:
            return dt

    keys = {"timestamp", "published_at", "publishedAt", "created_at", "createdAt", "date"}

    def walk(value):
        if isinstance(value, dict):
            for key, child in value.items():
                if key in keys:
                    dt = parse_dt(child)
                    if dt is not None:
                        return dt
            for child in value.values():
                dt = walk(child)
                if dt is not None:
                    return dt
        elif isinstance(value, list):
            for child in value:
                dt = walk(child)
                if dt is not None:
                    return dt
        return None

    return walk(item)


def collect_ids(value):
    ids = set()
    if isinstance(value, dict):
        for key, child in value.items():
            if key in {"id", "user_id", "userId"} and str(child).isdigit():
                ids.add(int(child))
            elif key in {"users", "user", "author", "profile"}:
                ids.update(collect_ids(child))
    elif isinstance(value, list):
        for child in value:
            ids.update(collect_ids(child))
    return ids


def extract_note_excerpt(item):
    paths = [
        ("context", "comment", "body"),
        ("context", "comment", "body_text"),
        ("context", "comment", "bodyText"),
        ("context", "comment", "truncated_body_text"),
        ("comment", "body"),
        ("comment", "body_text"),
        ("comment", "bodyText"),
        ("body",),
        ("body_text",),
        ("bodyText",),
        ("truncated_body_text",),
    ]
    for path in paths:
        value = value_at(item, path)
        if isinstance(value, str):
            text = clean_text(value)
            if text:
                return text
    return None


def parse_note_item(item, target_user_id, handle, detected_dt):
    if not isinstance(item, dict):
        return None

    entity_key = item.get("entity_key") or item.get("entityKey")
    if not entity_key:
        entity_key = value_at(item, ("context", "entity_key")) or value_at(item, ("context", "entityKey"))
    entity_key = str(entity_key or "")
    match = re.fullmatch(r"c-(\d+)", entity_key)
    if not match:
        return None

    # Profile feeds can include likes/restacks. When author/user metadata is
    # present, reject entities that clearly belong to another user.
    scoped_ids = set()
    for path in [
        ("context", "users"),
        ("users",),
        ("context", "user"),
        ("context", "author"),
        ("author",),
    ]:
        scoped_ids.update(collect_ids(value_at(item, path)))
    if scoped_ids and target_user_id not in scoped_ids:
        return None

    note_id = match.group(1)
    dt = extract_feed_dt(item)
    time_source = "profile_feed"
    if dt is None:
        dt = detected_dt
        time_source = "collector_detected"

    excerpt = extract_note_excerpt(item)
    title = excerpt[:140].strip() if excerpt else f"Võ Hoàng Hạc Note {entity_key}"
    if excerpt and len(excerpt) > 140:
        title = title.rstrip(" .,:;-") + "…"

    return {
        "key": f"note:{entity_key}",
        "articleId": note_id,
        "canonicalUrl": f"https://substack.com/@{handle}/note/{entity_key}",
        "title": title,
        "publishedAt": dt.isoformat(timespec="seconds").replace("+00:00", "Z"),
        "publishedTs": int(dt.timestamp() * 1000),
        "publishedTimeSource": time_source,
        "thumbnail": None,
        "author": "Võ Hoàng Hạc",
        "description": excerpt,
        "contentSource": "substack_profile_radar",
        "itemType": "note",
        "noteId": entity_key,
    }


def fetch_notes(handle):
    detected_dt = now_dt()
    user_id, profile_endpoint = resolve_profile_user_id(handle)
    feed_url = f"https://substack.com/api/v1/reader/feed/profile/{user_id}"

    all_raw = []
    cursor = None
    final_url = feed_url
    for _ in range(MAX_NOTE_PAGES):
        params = [("types[]", "note")]
        if cursor:
            params.append(("cursor", cursor))
        payload, final_url = get_json(feed_url, params=params)
        if not isinstance(payload, dict):
            raise RuntimeError("profile feed returned a non-object payload")
        items = payload.get("items")
        if not isinstance(items, list):
            raise RuntimeError(f"profile feed missing items[]; keys={sorted(payload.keys())}")
        all_raw.extend(items)

        next_cursor = payload.get("nextCursor") or payload.get("next_cursor") or payload.get("cursor")
        if not next_cursor or not items:
            break
        cursor = str(next_cursor)

    notes_by_url = {}
    for raw in all_raw:
        parsed = parse_note_item(raw, user_id, handle, detected_dt)
        if parsed:
            notes_by_url[parsed["canonicalUrl"]] = parsed

    notes = list(notes_by_url.values())
    notes.sort(key=lambda x: x["publishedTs"], reverse=True)
    if not notes:
        raise RuntimeError(
            f"profile feed was reachable for user {user_id} but yielded no author-owned Notes "
            f"from {len(all_raw)} activity items"
        )

    return notes, {
        "userId": user_id,
        "profileLookupUrl": profile_endpoint,
        "feedUrl": final_url,
        "rawActivityCount": len(all_raw),
        "validNoteCount": len(notes),
    }


def fetch_articles():
    response = SESSION.get(
        SOURCE["article_feed"],
        timeout=TIMEOUT,
        allow_redirects=True,
        headers={"Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml, */*;q=0.5"},
    )
    response.raise_for_status()
    fresh = parse_article_feed(response.content)
    if not fresh:
        raise RuntimeError("article feed parsed but contained no valid items")
    return fresh, response.url


def main():
    SOURCES_ROOT.mkdir(parents=True, exist_ok=True)
    key = SOURCE["key"]
    path = SOURCES_ROOT / f"{key}.json"
    old = load_json(path)
    old_items = old.get("items") or []

    health = {
        "version": 2,
        "collector": "runner-3",
        "scope": "1-substack-hybrid",
        "runStartedAt": now_iso(),
        "sources": {},
    }
    components = {}
    fresh_articles = []
    fresh_notes = []
    article_final_url = None
    note_meta = {}
    changes = []

    try:
        fresh_articles, article_final_url = fetch_articles()
        changes = detect_hash_changes(old_items, fresh_articles)
        components["articles"] = {
            "ok": True,
            "transport": "rss",
            "feedUrl": SOURCE["article_feed"],
            "finalFeedUrl": article_final_url,
            "freshItemCount": len(fresh_articles),
            "newestPublishedAt": fresh_articles[0]["publishedAt"],
            "contentHashChangeCount": len(changes),
        }
    except Exception as exc:
        components["articles"] = {
            "ok": False,
            "transport": "rss",
            "error": f"{type(exc).__name__}: {exc}",
        }

    try:
        fresh_notes, note_meta = fetch_notes(SOURCE["handle"])
        components["notes"] = {
            "ok": True,
            "transport": "substack-public-profile",
            "profileUrl": SOURCE["profile_url"],
            "freshItemCount": len(fresh_notes),
            "newestPublishedAt": fresh_notes[0]["publishedAt"],
            **note_meta,
        }
    except Exception as exc:
        components["notes"] = {
            "ok": False,
            "transport": "substack-public-profile",
            "profileUrl": SOURCE["profile_url"],
            "error": f"{type(exc).__name__}: {exc}",
        }

    overall_ok = all(component.get("ok") for component in components.values()) and len(components) == 2
    merged = merge_items(old_items, fresh_articles + fresh_notes) if (fresh_articles or fresh_notes) else normalize_old_items(old_items)
    changed = (
        old.get("items") != merged
        or old.get("transport") != "hybrid-rss+substack-profile"
        or old.get("finalFeedUrl") != article_final_url
        or bool(changes)
    )

    # Only write a new mirror when BOTH components are verified. This keeps the
    # mirror itself aligned with the same fail-closed semantics as health.
    if overall_ok and changed:
        article_count = sum(1 for item in merged if item.get("itemType") == "article")
        note_count = sum(1 for item in merged if item.get("itemType") == "note")
        mirror = {
            "source": SOURCE["name"],
            "sourceKey": key,
            "collector": "runner-3",
            "transport": "hybrid-rss+substack-profile",
            "feedUrl": SOURCE["article_feed"],
            "finalFeedUrl": article_final_url,
            "profileUrl": SOURCE["profile_url"],
            "profileUserId": note_meta.get("userId"),
            "lastContentChangeAt": now_iso(),
            "freshArticleCount": len(fresh_articles),
            "freshNoteCount": len(fresh_notes),
            "totalStored": len(merged),
            "articleCount": article_count,
            "noteCount": note_count,
            "count": len(merged),
            "newestPublishedAt": merged[0]["publishedAt"] if merged else None,
            "items": merged,
        }
        mirror["lastContentHashChangeAt"] = now_iso() if changes else old.get("lastContentHashChangeAt")
        mirror["lastContentHashChanges"] = changes if changes else old.get("lastContentHashChanges", [])
        write_json(path, mirror)

    health["sources"][key] = {
        "ok": overall_ok,
        "transport": "hybrid-rss+substack-profile",
        "checkedAt": now_iso(),
        "preservedExistingMirror": not overall_ok and bool(old_items),
        "contentChanged": bool(changed) if overall_ok else False,
        "components": components,
        "contentHashChangeCount": len(changes),
        "contentHashChanges": changes,
        "newestPublishedAt": merged[0]["publishedAt"] if merged else old.get("newestPublishedAt"),
    }
    health["runFinishedAt"] = now_iso()
    health["okCount"] = 1 if overall_ok else 0
    health["failedCount"] = 0 if overall_ok else 1
    health["status"] = "healthy" if overall_ok else "failed"
    write_json(HEALTH_PATH, health)

    print(json.dumps({
        "collector": "runner-3",
        "scope": "1-substack-hybrid",
        "status": health["status"],
        "articles_ok": components.get("articles", {}).get("ok", False),
        "notes_ok": components.get("notes", {}).get("ok", False),
        "fresh_articles": len(fresh_articles),
        "fresh_notes": len(fresh_notes),
    }, ensure_ascii=False))
    return 0 if overall_ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
