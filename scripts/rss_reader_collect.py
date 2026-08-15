#!/usr/bin/env python3

import hashlib
import html
import json
import re
import sys
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
HEALTH_PATH = DATA_ROOT / "health.json"
MAX_ARCHIVE_ITEMS = 1000
TIMEOUT = 45

UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36 runner-3-rss/1.0"
)

SOURCES = [
    {
        "key": "tinhte",
        "name": "Tinhte",
        "kind": "rss",
        "urls": ["https://tinhte.vn/rss", "https://feeds.feedburner.com/tinhte"],
    },
    {
        "key": "genk",
        "name": "GenK",
        "kind": "rss",
        "urls": ["https://genk.vn/rss/home.rss"],
    },
    {
        "key": "gamek",
        "name": "GameK",
        "kind": "rss",
        "urls": ["https://gamek.vn/trang-chu.rss"],
    },
    {
        "key": "hoquoctuan",
        "name": "Hồ Quốc Tuấn / Đọc Chậm",
        "kind": "substack",
        "urls": ["https://hoquoctuan.substack.com/feed"],
        "archive_api": "https://hoquoctuan.substack.com/api/v1/archive?sort=new&limit=12&offset=0",
        "profile_url": "https://substack.com/@hoquoctuan",
        "canonical_base": "https://hoquoctuan.substack.com",
    },
    {
        "key": "vohoanghac",
        "name": "Võ Hoàng Hạc",
        "kind": "substack",
        "urls": ["https://vohoanghac.com/feed", "https://vohoanghac.substack.com/feed"],
        "archive_api": "https://vohoanghac.com/api/v1/archive?sort=new&limit=12&offset=0",
        "profile_url": "https://substack.com/@vohoanghac",
        "canonical_base": "https://vohoanghac.com",
    },
    {
        "key": "fulcrum",
        "name": "Fulcrum",
        "kind": "rss",
        "urls": ["https://fulcrum.sg/feed/"],
    },
    {
        "key": "nghiencuuquocte",
        "name": "Nghiên cứu Quốc tế",
        "kind": "rss",
        "urls": ["https://nghiencuuquocte.org/feed/"],
    },
    {
        "key": "vnhacker",
        "name": "ThaiDN / vnhacker",
        "kind": "substack",
        "urls": ["https://vnhacker.substack.com/feed"],
        "archive_api": "https://vnhacker.substack.com/api/v1/archive?sort=new&limit=12&offset=0",
        "profile_url": "https://substack.com/@vnhacker",
        "canonical_base": "https://vnhacker.substack.com",
    },
    {
        "key": "noema",
        "name": "Noema",
        "kind": "rss",
        "urls": ["https://www.noemamag.com/feed/"],
    },
    {
        "key": "projectsyndicate",
        "name": "Project Syndicate",
        "kind": "rss",
        "urls": ["https://www.project-syndicate.org/rss"],
    },
]

SESSION = requests.Session()
SESSION.headers.update(
    {
        "User-Agent": UA,
        "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml, application/json, text/html;q=0.8, */*;q=0.5",
    }
)


def now_iso():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def parse_dt(value):
    if not value:
        return None
    value = str(value).strip()
    if not value:
        return None

    # Several Vietnamese RSS feeds emit non-standard timezone suffixes such as
    # "+07" or "GMT+7". Normalize them to RFC-2822 "+0700" before parsing.
    value = re.sub(r"\sGMT([+-])(\d{1,2})$", lambda m: f" {m.group(1)}{int(m.group(2)):02d}00", value)
    value = re.sub(r"\s([+-])(\d{2})$", lambda m: f" {m.group(1)}{m.group(2)}00", value)

    try:
        dt = parsedate_to_datetime(value)
        if dt:
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc)
    except Exception:
        pass
    try:
        normalized = value.replace("Z", "+00:00")
        dt = datetime.fromisoformat(normalized)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def dt_iso(dt):
    if not dt:
        return None
    return dt.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def clean_text(value):
    if value is None:
        return None
    text = BeautifulSoup(html.unescape(str(value)), "html.parser").get_text(" ", strip=True)
    text = re.sub(r"\s+", " ", text).strip()
    return text or None


def canonicalize_url(value):
    if not value:
        return None
    value = html.unescape(str(value)).strip()
    if not value.startswith(("http://", "https://")):
        return None
    p = urlparse(value)
    return urlunparse((p.scheme, p.netloc.lower(), p.path, "", "", ""))


def stable_key(url, guid=None):
    if guid:
        guid = str(guid).strip()
        if guid:
            match = re.search(r"(?:^|/)(\d{5,})(?:/|$)", guid)
            if match:
                return f"id:{match.group(1)}"
    if url:
        match = re.search(r"(?:thread/.*\.|[-/])(\d{8,})(?:[./-]|$)", url)
        if match:
            return f"id:{match.group(1)}"
        digest = hashlib.sha1(url.encode("utf-8")).hexdigest()[:20]
        return f"url:{digest}"
    return None


def local_name(tag):
    return tag.split("}", 1)[-1].lower()


def child_text(node, names):
    wanted = set(names)
    for child in list(node):
        if local_name(child.tag) in wanted:
            if child.text and child.text.strip():
                return child.text.strip()
    return None


def find_link(node):
    direct = child_text(node, {"link"})
    if direct and direct.startswith(("http://", "https://")):
        return direct
    for child in list(node):
        if local_name(child.tag) != "link":
            continue
        href = child.attrib.get("href")
        rel = child.attrib.get("rel", "alternate")
        if href and rel in ("alternate", ""):
            return href
    return None


def find_thumbnail(node, description=None):
    for child in node.iter():
        lname = local_name(child.tag)
        if lname in {"thumbnail", "content"}:
            url = child.attrib.get("url")
            medium = child.attrib.get("medium")
            typ = child.attrib.get("type", "")
            if url and (lname == "thumbnail" or medium == "image" or typ.startswith("image/")):
                return canonicalize_url(url) or url
        if lname == "enclosure":
            url = child.attrib.get("url")
            typ = child.attrib.get("type", "")
            if url and typ.startswith("image/"):
                return canonicalize_url(url) or url
    if description:
        soup = BeautifulSoup(description, "html.parser")
        img = soup.find("img")
        if img and img.get("src"):
            return img.get("src")
    return None


def parse_feed(xml_content, source):
    root = ET.fromstring(xml_content)
    root_name = local_name(root.tag)
    nodes = []
    if root_name == "rss":
        channel = next((c for c in list(root) if local_name(c.tag) == "channel"), None)
        if channel is not None:
            nodes = [c for c in list(channel) if local_name(c.tag) == "item"]
    elif root_name == "feed":
        nodes = [c for c in list(root) if local_name(c.tag) == "entry"]
    else:
        nodes = [n for n in root.iter() if local_name(n.tag) in {"item", "entry"}]

    items = []
    for node in nodes:
        title = child_text(node, {"title"})
        url = canonicalize_url(find_link(node))
        guid = child_text(node, {"guid", "id"})
        pub_raw = child_text(node, {"pubdate", "published", "updated", "date"})
        dt = parse_dt(pub_raw)
        desc_raw = child_text(node, {"description", "summary", "content", "encoded"})
        desc = clean_text(desc_raw)
        if not title or not url or not dt:
            continue
        key = stable_key(url, guid)
        items.append(
            {
                "key": key,
                "articleId": key[3:] if key and key.startswith("id:") else None,
                "canonicalUrl": url,
                "title": clean_text(title) or title.strip(),
                "publishedAt": dt_iso(dt),
                "publishedTs": int(dt.timestamp() * 1000),
                "thumbnail": find_thumbnail(node, desc_raw),
                "author": clean_text(child_text(node, {"author", "creator"})),
                "description": desc,
                "contentSource": "rss",
            }
        )
    return items


def parse_substack_archive_json(payload, source):
    if isinstance(payload, dict):
        candidates = payload.get("posts") or payload.get("items") or payload.get("results") or []
    elif isinstance(payload, list):
        candidates = payload
    else:
        candidates = []
    items = []
    base = source.get("canonical_base", "").rstrip("/")
    for post in candidates:
        if not isinstance(post, dict):
            continue
        if post.get("type") not in (None, "", "newsletter", "podcast"):
            continue
        title = post.get("title")
        url = post.get("canonical_url") or post.get("canonicalUrl")
        slug = post.get("slug")
        if not url and slug and base:
            url = f"{base}/p/{slug}"
        url = canonicalize_url(url)
        raw_dt = (
            post.get("post_date")
            or post.get("published_at")
            or post.get("publishedAt")
            or post.get("publication_date")
        )
        dt = parse_dt(raw_dt)
        if not title or not url or not dt:
            continue
        key = stable_key(url, post.get("id"))
        items.append(
            {
                "key": key,
                "articleId": str(post.get("id")) if post.get("id") is not None else None,
                "canonicalUrl": url,
                "title": clean_text(title) or str(title),
                "publishedAt": dt_iso(dt),
                "publishedTs": int(dt.timestamp() * 1000),
                "thumbnail": post.get("cover_image") or post.get("social_image"),
                "author": clean_text(post.get("byline") or post.get("author_name")),
                "description": clean_text(post.get("subtitle") or post.get("description")),
                "contentSource": "substack:archive-api",
            }
        )
    return items


def extract_next_data_json(text):
    try:
        soup = BeautifulSoup(text, "html.parser")
    except Exception:
        return None
    script = soup.find("script", id="__NEXT_DATA__")
    if script and script.string:
        try:
            return json.loads(script.string)
        except Exception:
            return None
    return None


def walk_json(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from walk_json(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk_json(child)


def parse_substack_profile_html(text, source):
    data = extract_next_data_json(text)
    if not data:
        return []
    base = source.get("canonical_base", "").rstrip("/")
    found = {}
    for obj in walk_json(data):
        if not isinstance(obj, dict):
            continue
        title = obj.get("title")
        slug = obj.get("slug")
        raw_dt = obj.get("post_date") or obj.get("published_at") or obj.get("publication_date")
        if not title or not slug or not raw_dt:
            continue
        dt = parse_dt(raw_dt)
        if not dt:
            continue
        url = canonicalize_url(obj.get("canonical_url") or f"{base}/p/{slug}")
        if not url:
            continue
        key = stable_key(url, obj.get("id"))
        item = {
            "key": key,
            "articleId": str(obj.get("id")) if obj.get("id") is not None else None,
            "canonicalUrl": url,
            "title": clean_text(title) or str(title),
            "publishedAt": dt_iso(dt),
            "publishedTs": int(dt.timestamp() * 1000),
            "thumbnail": obj.get("cover_image") or obj.get("social_image"),
            "author": clean_text(obj.get("byline") or obj.get("author_name")),
            "description": clean_text(obj.get("subtitle") or obj.get("description")),
            "contentSource": "substack:profile",
        }
        found[url] = item
    return list(found.values())


def fetch_text(url, accept=None):
    headers = {}
    if accept:
        headers["Accept"] = accept
    return SESSION.get(url, timeout=TIMEOUT, allow_redirects=True, headers=headers)


def collect_source(source):
    attempts = []
    for url in source["urls"]:
        try:
            r = fetch_text(url)
            attempts.append({"transport": "rss", "url": url, "status": r.status_code})
            if r.status_code < 400:
                items = parse_feed(r.content, source)
                if items:
                    return items, "rss", r.url, attempts
        except Exception as exc:
            attempts.append({"transport": "rss", "url": url, "error": f"{type(exc).__name__}: {exc}"})

    if source.get("archive_api"):
        url = source["archive_api"]
        try:
            r = fetch_text(url, "application/json")
            attempts.append({"transport": "substack-archive-api", "url": url, "status": r.status_code})
            if r.status_code < 400:
                items = parse_substack_archive_json(r.json(), source)
                if items:
                    return items, "substack-archive-api", r.url, attempts
        except Exception as exc:
            attempts.append({"transport": "substack-archive-api", "url": url, "error": f"{type(exc).__name__}: {exc}"})

    if source.get("profile_url"):
        url = source["profile_url"]
        try:
            r = fetch_text(url, "text/html")
            attempts.append({"transport": "substack-profile", "url": url, "status": r.status_code})
            if r.status_code < 400:
                items = parse_substack_profile_html(r.text, source)
                if items:
                    return items, "substack-profile", r.url, attempts
        except Exception as exc:
            attempts.append({"transport": "substack-profile", "url": url, "error": f"{type(exc).__name__}: {exc}"})

    raise RuntimeError(json.dumps(attempts, ensure_ascii=False))


def load_json(path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def merge_items(old_items, new_items):
    merged = {}
    for item in old_items or []:
        identity = item.get("canonicalUrl") or item.get("key")
        if identity:
            merged[identity] = item
    for item in new_items or []:
        identity = item.get("canonicalUrl") or item.get("key")
        if identity:
            merged[identity] = item
    values = list(merged.values())
    values.sort(key=lambda x: x.get("publishedTs") or 0, reverse=True)
    return values[:MAX_ARCHIVE_ITEMS]


def write_json(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main():
    SOURCES_ROOT.mkdir(parents=True, exist_ok=True)
    health = {
        "version": 1,
        "collector": "runner-3",
        "runStartedAt": now_iso(),
        "sourceCount": len(SOURCES),
        "sources": {},
    }
    ok_count = 0

    for source in SOURCES:
        key = source["key"]
        path = SOURCES_ROOT / f"{key}.json"
        old = load_json(path, {})
        old_items = old.get("items") or []
        try:
            fresh_items, transport, final_url, attempts = collect_source(source)
            merged = merge_items(old_items, fresh_items)
            newest = merged[0].get("publishedAt") if merged else None
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
                    "feedUrl": source["urls"][0],
                    "finalFeedUrl": final_url,
                    "lastContentChangeAt": now_iso(),
                    "freshItemCount": len(fresh_items),
                    "totalStored": len(merged),
                    "count": len(merged),
                    "newestPublishedAt": newest,
                    "items": merged,
                }
                write_json(path, mirror)
            else:
                mirror = old

            health["sources"][key] = {
                "ok": True,
                "transport": transport,
                "checkedAt": now_iso(),
                "contentChanged": content_changed,
                "newestPublishedAt": newest,
                "freshItemCount": len(fresh_items),
                "totalStored": len(merged),
                "attempts": attempts,
            }
            ok_count += 1
        except Exception as exc:
            health["sources"][key] = {
                "ok": False,
                "preservedExistingMirror": bool(old_items),
                "lastKnownContentChangeAt": old.get("lastContentChangeAt") or old.get("lastCollectedAt"),
                "newestPublishedAt": old.get("newestPublishedAt"),
                "error": str(exc),
            }

    health["runFinishedAt"] = now_iso()
    health["okCount"] = ok_count
    health["failedCount"] = len(SOURCES) - ok_count
    health["status"] = "healthy" if ok_count == len(SOURCES) else ("degraded" if ok_count else "failed")
    write_json(HEALTH_PATH, health)

    print(json.dumps({
        "collector": "runner-3",
        "status": health["status"],
        "ok": ok_count,
        "failed": len(SOURCES) - ok_count,
        "health": str(HEALTH_PATH.relative_to(ROOT)),
    }, ensure_ascii=False))

    if ok_count == 0:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
