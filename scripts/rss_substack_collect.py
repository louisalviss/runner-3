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
TIMEOUT = 45

SOURCES = [
    {"key": "hoquoctuan", "name": "Hồ Quốc Tuấn / Đọc Chậm", "url": "https://hoquoctuan.substack.com/feed"},
    {"key": "vohoanghac", "name": "Võ Hoàng Hạc", "url": "https://vohoanghac.com/feed", "track_content_hash": True},
    {"key": "vnhacker", "name": "ThaiDN / vnhacker", "url": "https://vnhacker.substack.com/feed"},
]

SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": "Mozilla/5.0 runner-3-substack-rss/1.0",
    "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml, */*;q=0.5",
})


def now_iso():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


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
    if not value:
        return None
    value = str(value).strip()
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


def parse_feed(raw, source):
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
        item = {
            "key": key,
            "articleId": key[3:] if key.startswith("id:") else None,
            "canonicalUrl": url,
            "title": title,
            "publishedAt": dt.isoformat(timespec="seconds").replace("+00:00", "Z"),
            "publishedTs": int(dt.timestamp() * 1000),
            "thumbnail": None,
            "author": clean_text(child_text(node, {"author", "creator"})),
            "description": clean_text(desc_raw),
            "contentSource": "rss",
        }
        if source.get("track_content_hash"):
            item["contentHash"] = content_hash(node)
        out.append(item)
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


def merge_items(old_items, fresh_items):
    merged = {}
    for item in old_items or []:
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


def detect_hash_changes(old_items, fresh_items):
    old_by_id = {(i.get("canonicalUrl") or i.get("key")): i for i in old_items or []}
    changes = []
    for item in fresh_items:
        ident = item.get("canonicalUrl") or item.get("key")
        old = old_by_id.get(ident)
        old_hash = (old or {}).get("contentHash")
        new_hash = item.get("contentHash")
        if old and old_hash and new_hash and old_hash != new_hash:
            changes.append({
                "key": item.get("key"), "canonicalUrl": item.get("canonicalUrl"),
                "title": item.get("title"), "publishedAt": item.get("publishedAt"),
                "oldContentHash": old_hash, "newContentHash": new_hash,
            })
    return changes


def main():
    SOURCES_ROOT.mkdir(parents=True, exist_ok=True)
    health = {"version": 1, "collector": "runner-3", "scope": "3-substack-rss", "runStartedAt": now_iso(), "sources": {}}
    ok = 0
    for source in SOURCES:
        key = source["key"]
        path = SOURCES_ROOT / f"{key}.json"
        old = load_json(path)
        old_items = old.get("items") or []
        try:
            r = SESSION.get(source["url"], timeout=TIMEOUT, allow_redirects=True)
            r.raise_for_status()
            fresh = parse_feed(r.content, source)
            if not fresh:
                raise RuntimeError("feed parsed but contained no valid items")
            changes = detect_hash_changes(old_items, fresh) if source.get("track_content_hash") else []
            merged = merge_items(old_items, fresh)
            changed = (old.get("items") != merged or old.get("finalFeedUrl") != r.url or bool(changes))
            if changed:
                mirror = {
                    "source": source["name"], "sourceKey": key, "collector": "runner-3",
                    "transport": "rss", "feedUrl": source["url"], "finalFeedUrl": r.url,
                    "lastContentChangeAt": now_iso(), "freshItemCount": len(fresh),
                    "totalStored": len(merged), "count": len(merged),
                    "newestPublishedAt": merged[0]["publishedAt"], "items": merged,
                }
                if source.get("track_content_hash"):
                    mirror["lastContentHashChangeAt"] = now_iso() if changes else old.get("lastContentHashChangeAt")
                    mirror["lastContentHashChanges"] = changes if changes else old.get("lastContentHashChanges", [])
                write_json(path, mirror)
            health["sources"][key] = {
                "ok": True, "transport": "rss", "checkedAt": now_iso(),
                "contentChanged": changed, "freshItemCount": len(fresh),
                "newestPublishedAt": merged[0]["publishedAt"],
                "contentHashChangeCount": len(changes),
                "contentHashChanges": changes,
            }
            ok += 1
        except Exception as exc:
            health["sources"][key] = {
                "ok": False, "preservedExistingMirror": bool(old_items),
                "newestPublishedAt": old.get("newestPublishedAt"),
                "error": f"{type(exc).__name__}: {exc}",
            }
    health["runFinishedAt"] = now_iso()
    health["okCount"] = ok
    health["failedCount"] = len(SOURCES) - ok
    health["status"] = "healthy" if ok == len(SOURCES) else ("degraded" if ok else "failed")
    write_json(HEALTH_PATH, health)
    print(json.dumps({"collector": "runner-3", "scope": "3-substack-rss", "status": health["status"], "ok": ok, "failed": len(SOURCES)-ok}, ensure_ascii=False))
    return 0 if ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
