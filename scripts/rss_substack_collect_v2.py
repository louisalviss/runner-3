#!/usr/bin/env python3

import json
import time
from pathlib import Path
from urllib.parse import quote, urlsplit, urlunsplit, parse_qsl, urlencode

import requests

import rss_substack_collect as base

ROOT = Path(__file__).resolve().parents[1]
HEALTH_PATH = ROOT / "data" / "rss-reader" / "substack-health.json"

UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
SESSION = requests.Session()
SESSION.headers.update({"User-Agent": UA, "Accept": "application/rss+xml,application/xml,text/xml,*/*;q=0.5"})


def cache_bust(url):
    p = urlsplit(url)
    q = parse_qsl(p.query, keep_blank_values=True)
    q.append(("_runner3", str(int(time.time()))))
    return urlunsplit((p.scheme, p.netloc, p.path, urlencode(q), p.fragment))


def fetch_candidates(feed_url):
    fresh = cache_bust(feed_url)
    encoded = quote(fresh, safe="")
    return [
        ("rss-direct", feed_url, None),
        ("rss-codetabs", "https://api.codetabs.com/v1/proxy?quest=" + encoded, None),
        ("rss-allorigins", "https://api.allorigins.win/raw?url=" + encoded + "&_=" + str(int(time.time())), None),
    ]


def validate_items(items, source):
    if not items:
        raise RuntimeError("feed parsed but contained no valid items")
    expected = {
        "hoquoctuan": {"hoquoctuan.substack.com"},
        "vohoanghac": {"vohoanghac.com"},
        "vnhacker": {"vnhacker.substack.com"},
    }[source["key"]]
    good = []
    for item in items:
        host = urlsplit(item.get("canonicalUrl") or "").netloc.lower()
        if host in expected or any(host.endswith("." + e) for e in expected):
            good.append(item)
    if not good:
        raise RuntimeError("feed items failed canonical-host validation")
    return good


def load_json(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def main():
    base.SOURCES_ROOT.mkdir(parents=True, exist_ok=True)
    health = {"version": 2, "collector": "runner-3", "scope": "3-substack-rss", "runStartedAt": base.now_iso(), "sources": {}}
    ok = 0

    for source in base.SOURCES:
        key = source["key"]
        path = base.SOURCES_ROOT / f"{key}.json"
        old = load_json(path)
        old_items = old.get("items") or []
        attempts = []
        success = None

        for transport, fetch_url, _ in fetch_candidates(source["url"]):
            try:
                r = SESSION.get(fetch_url, timeout=12, allow_redirects=True)
                attempts.append({"transport": transport, "status": r.status_code, "bytes": len(r.content)})
                r.raise_for_status()
                fresh = validate_items(base.parse_feed(r.content, source), source)
                success = (transport, fetch_url, r.url, fresh)
                break
            except Exception as exc:
                attempts.append({"transport": transport, "error": f"{type(exc).__name__}: {exc}"})

        if not success:
            health["sources"][key] = {
                "ok": False,
                "preservedExistingMirror": bool(old_items),
                "newestPublishedAt": old.get("newestPublishedAt"),
                "attempts": attempts,
                "error": "all live RSS transports failed",
            }
            continue

        transport, fetch_url, final_url, fresh = success
        changes = base.detect_hash_changes(old_items, fresh) if source.get("track_content_hash") else []
        merged = base.merge_items(old_items, fresh)
        changed = old.get("items") != merged or old.get("transport") != transport or bool(changes)

        if changed:
            mirror = {
                "source": source["name"],
                "sourceKey": key,
                "collector": "runner-3",
                "transport": transport,
                "feedUrl": source["url"],
                "fetchUrl": fetch_url,
                "finalFeedUrl": final_url,
                "lastContentChangeAt": base.now_iso(),
                "freshItemCount": len(fresh),
                "totalStored": len(merged),
                "count": len(merged),
                "newestPublishedAt": merged[0]["publishedAt"],
                "items": merged,
            }
            if source.get("track_content_hash"):
                mirror["lastContentHashChangeAt"] = base.now_iso() if changes else old.get("lastContentHashChangeAt")
                mirror["lastContentHashChanges"] = changes if changes else old.get("lastContentHashChanges", [])
            base.write_json(path, mirror)

        health["sources"][key] = {
            "ok": True,
            "transport": transport,
            "checkedAt": base.now_iso(),
            "contentChanged": changed,
            "freshItemCount": len(fresh),
            "newestPublishedAt": merged[0]["publishedAt"],
            "contentHashChangeCount": len(changes),
            "contentHashChanges": changes,
            "attempts": attempts,
        }
        ok += 1

    health["runFinishedAt"] = base.now_iso()
    health["okCount"] = ok
    health["failedCount"] = len(base.SOURCES) - ok
    health["status"] = "healthy" if ok == len(base.SOURCES) else ("degraded" if ok else "failed")
    base.write_json(HEALTH_PATH, health)
    print(json.dumps({"collector": "runner-3", "scope": "3-substack-rss", "status": health["status"], "ok": ok, "failed": len(base.SOURCES)-ok}, ensure_ascii=False))
    raise SystemExit(0 if health["status"] == "healthy" else 2)


if __name__ == "__main__":
    main()
