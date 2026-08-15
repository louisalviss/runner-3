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
HEALTH_PATH = DATA_ROOT / "health.json"
MAX_ARCHIVE_ITEMS = 1000
TIMEOUT = 45

UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36 runner-3-rss/2.0"
)

# Runner3 intentionally owns only the seven non-direct sources below.
# ChatGPT reads these three Substack publications directly at reader runtime:
#   hoquoctuan, vohoanghac, vnhacker
SOURCES = [
    {
        "key": "tinhte",
        "name": "Tinhte",
        "urls": ["https://tinhte.vn/rss", "https://feeds.feedburner.com/tinhte"],
    },
    {
        "key": "genk",
        "name": "GenK",
        "urls": ["https://genk.vn/rss/home.rss"],
    },
    {
        "key": "gamek",
        "name": "GameK",
        "urls": ["https://gamek.vn/trang-chu.rss"],
    },
    {
        "key": "fulcrum",
        "name": "Fulcrum",
        "urls": ["https://fulcrum.sg/feed/"],
    },
    {
        "key": "nghiencuuquocte",
        "name": "Nghiên cứu Quốc tế",
        "urls": ["https://nghiencuuquocte.org/feed/"],
    },
    {
        "key": "noema",
        "name": "Noema",
        "urls": ["https://www.noemamag.com/feed/"],
    },
    {
        "key": "projectsyndicate",
        "name": "Project Syndicate",
        "urls": ["https://www.project-syndicate.org/rss"],
    },
]

SESSION = requests.Session()
SESSION.headers.update(
    {
        "User-Agent": UA,
        "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml, */*;q=0.5",
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
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
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


def canonicalize_url(value, source_key=None):
    if not value:
        return None
    value = html.unescape(str(value)).strip()
    if not value.startswith(("http://", "https://")):
        return None
    p = urlparse(value)
    host = p.netloc.lower()
    if source_key == "gamek" and host.endswith(".cnnd.vn"):
        host = "gamek.vn"
    return urlunparse(("https" if p.scheme == "https" else p.scheme, host, p.path, "", "", ""))


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
        return "url:" + hashlib.sha1(url.encode("utf-8")).hexdigest()[:20]
    return None


def local_name(tag):
    return tag.split("}", 1)[-1].lower()


def child_text(node, names):
    wanted = set(names)
    for child in list(node):
        if local_name(child.tag) in wanted and child.text and child.text.strip():
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
    if root_name == "rss":
        channel = next((c for c in list(root) if local_name(c.tag) == "channel"), None)
        nodes = [c for c in list(channel or []) if local_name(c.tag) == "item"]
    elif root_name == "feed":
        nodes = [c for c in list(root) if local_name(c.tag) == "entry"]
    else:
        nodes = [n for n in root.iter() if local_name(n.tag) in {"item", "entry"}]

    items = []
    for node in nodes:
        title = child_text(node, {"title"})
        url = canonicalize_url(find_link(node), source["key"])
        guid = child_text(node, {"guid", "id"})
        dt = parse_dt(child_text(node, {"pubdate", "published", "updated", "date"}))
        desc_raw = child_text(node, {"description", "summary", "content", "encoded"})
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
                "description": clean_text(desc_raw),
                "contentSource": "rss",
            }
        )
    return items


def collect_source(source):
    attempts = []
    for url in source["urls"]:
        try:
            r = SESSION.get(url, timeout=TIMEOUT, allow_redirects=True)
            attempts.append({"transport": "rss", "url": url, "status": r.status_code})
            if r.status_code < 400:
                items = parse_feed(r.content, source)
                if items:
                    return items, r.url, attempts
        except Exception as exc:
            attempts.append({"transport": "rss", "url": url, "error": f"{type(exc).__name__}: {exc}"})
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
        "version": 2,
        "collector": "runner-3",
        "scope": "7-non-direct-sources",
        "directSources": ["hoquoctuan", "vohoanghac", "vnhacker"],
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
            fresh_items, final_url, attempts = collect_source(source)
            merged = merge_items(old_items, fresh_items)
            newest = merged[0].get("publishedAt") if merged else None
            content_changed = (
                not old
                or old.get("items") != merged
                or old.get("transport") != "rss"
                or old.get("finalFeedUrl") != final_url
            )
            if content_changed:
                mirror = {
                    "source": source["name"],
                    "sourceKey": key,
                    "collector": "runner-3",
                    "transport": "rss",
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
            health["sources"][key] = {
                "ok": True,
                "transport": "rss",
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

    print(
        json.dumps(
            {
                "collector": "runner-3",
                "scope": "7-non-direct-sources",
                "status": health["status"],
                "ok": ok_count,
                "failed": len(SOURCES) - ok_count,
                "health": str(HEALTH_PATH.relative_to(ROOT)),
            },
            ensure_ascii=False,
        )
    )
    return 0 if ok_count else 2


if __name__ == "__main__":
    raise SystemExit(main())
