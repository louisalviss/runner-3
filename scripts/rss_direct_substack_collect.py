#!/usr/bin/env python3
"""Collect Hồ Quốc Tuấn and vnhacker as first-class Runner RSS sources.

These publications used to be verified manually at render time. That created an
omission gap whenever ChatGPT rendered a Runner13 manifest without completing
that direct verification. Substack exposes normal RSS feeds, so both sources are
now persisted and health-gated exactly like other Runner mirrors.
"""

import json
from datetime import datetime, timezone
from pathlib import Path

import rss_reader_collect_v2 as hardened

base = hardened.base
ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "rss-reader"
SOURCES_ROOT = DATA / "sources"
HEALTH_PATH = DATA / "direct-substack-health.json"

SOURCES = [
    {
        "key": "hoquoctuan",
        "name": "Hồ Quốc Tuấn",
        "urls": ["https://hoquoctuan.substack.com/feed"],
    },
    {
        "key": "vnhacker",
        "name": "vnhacker",
        "urls": ["https://vnhacker.substack.com/feed"],
    },
]


def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def load_json(path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def collect_one(source):
    key = source["key"]
    path = SOURCES_ROOT / f"{key}.json"
    old = load_json(path, {})
    old_items = old.get("items") or []
    fresh_items, final_url, attempts = base.collect_source(source)
    merged = base.merge_items(old_items, fresh_items)
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
        base.write_json(path, mirror)
    return {
        "ok": True,
        "transport": "rss",
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
        "version": 1,
        "collector": "runner-3",
        "scope": "2-substack-rss-sources",
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
