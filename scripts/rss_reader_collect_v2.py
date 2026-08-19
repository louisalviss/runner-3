#!/usr/bin/env python3

"""Compatibility/hardening entrypoint for the 10 core RSS collectors.

RSS feeds can bump an existing item's pubDate/updated timestamp without creating
new content (Tinhte does this when an old thread resurfaces). Reader identity is
canonical URL/article ID, so a timestamp-only bump must not turn a seen item into
a new item or move its high-water position.

This wrapper preserves the earliest Runner3-observed source timestamp for an
existing canonical identity while still refreshing title/description/thumbnail
from the latest RSS payload. If a feed later supplies an earlier timestamp, the
earlier value wins as a correction.

It also enforces the canonical health gate: this entrypoint succeeds only when
all 10 Runner3 core sources are healthy. A degraded 9/10 (or lower) run must
fail the workflow instead of being reported as success.
"""

import rss_reader_collect as base


_base_merge_items = base.merge_items


def _stable_merge_items(old_items, new_items):
    old_by_identity = {}
    for raw in old_items or []:
        identity = raw.get("canonicalUrl") or raw.get("key")
        if identity:
            old_by_identity[identity] = raw

    stabilized = []
    for raw in new_items or []:
        item = dict(raw)
        identity = item.get("canonicalUrl") or item.get("key")
        old = old_by_identity.get(identity)
        if old:
            old_ts = old.get("publishedTs")
            new_ts = item.get("publishedTs")
            # Same identity + later/equal RSS timestamp = bump, not a new item.
            if old_ts is not None and new_ts is not None and old_ts <= new_ts:
                item["publishedTs"] = old_ts
                if old.get("publishedAt"):
                    item["publishedAt"] = old["publishedAt"]
            # Preserve a durable audit hint for runtime/debugging.
            item["firstSeenPublishedAt"] = old.get("firstSeenPublishedAt") or old.get("publishedAt")
        else:
            item["firstSeenPublishedAt"] = item.get("publishedAt")
        stabilized.append(item)

    return _base_merge_items(old_items, stabilized)


def _main_with_complete_health_gate():
    # base.main() performs collection and writes the per-run health file.
    base.main()
    health = base.load_json(base.HEALTH_PATH, {})
    expected = len(base.SOURCES)
    complete = (
        health.get("status") == "healthy"
        and health.get("okCount") == expected
        and health.get("failedCount") == 0
        and len(health.get("sources") or {}) == expected
        and all(
            (health.get("sources") or {}).get(source["key"], {}).get("ok") is True
            for source in base.SOURCES
        )
    )
    return 0 if complete else 2


base.merge_items = _stable_merge_items


if __name__ == "__main__":
    raise SystemExit(_main_with_complete_health_gate())
