#!/usr/bin/env python3

"""Compatibility/hardening entrypoint for the 12 core RSS collectors.

RSS feeds can bump an existing item's pubDate/updated timestamp without creating
new content (Tinhte does this when an old thread resurfaces). Reader identity is
canonical URL/article ID, so a timestamp-only bump must not turn a seen item into
a new item or move its high-water position.

This wrapper preserves the earliest Runner3-observed source timestamp for an
existing canonical identity while still refreshing title/description/thumbnail
from the latest RSS payload. If a feed later supplies an earlier timestamp, the
earlier value wins as a correction.

It also extends the legacy base collector with Scientific American and Quanta,
enforces the canonical health gate, bounds RSS discovery descriptions so mirrors
do not become article-body archives, and verifies each persisted source mirror
before a run is allowed to report healthy.
"""

import contextlib
import io
import json
import os

import rss_reader_collect as base


EXTRA_SOURCES = [
    {
        "key": "scientificamerican",
        "name": "Scientific American",
        "urls": [
            "https://rss.sciam.com/ScientificAmerican-Global",
            "http://rss.sciam.com/ScientificAmerican-Global",
        ],
    },
    {
        "key": "quanta",
        "name": "Quanta Magazine",
        "urls": [
            "https://api.quantamagazine.org/feed/",
            "https://www.quantamagazine.org/feed/",
        ],
    },
]

# Mirrors are freshness/discovery surfaces, not article-body storage. Some feeds
# (notably The Atlantic) place full transcripts/articles in RSS description.
# Keeping a bounded excerpt avoids multi-megabyte JSON mirrors and connector
# read failures while retaining ample discovery context.
MAX_MIRROR_DESCRIPTION_CHARS = 4000

_existing_source_keys = {source["key"] for source in base.SOURCES}
base.SOURCES.extend(source for source in EXTRA_SOURCES if source["key"] not in _existing_source_keys)

_base_merge_items = base.merge_items
_base_write_json = base.write_json


def _compact_description(item):
    compacted = dict(item)
    description = compacted.get("description")
    if isinstance(description, str) and len(description) > MAX_MIRROR_DESCRIPTION_CHARS:
        compacted["description"] = description[:MAX_MIRROR_DESCRIPTION_CHARS].rstrip() + "…"
        compacted["descriptionTruncated"] = True
    elif compacted.get("descriptionTruncated") and isinstance(description, str):
        # Keep the audit flag only when the currently stored text is actually
        # bounded by this wrapper.
        compacted["descriptionTruncated"] = True
    return compacted


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

    merged = _base_merge_items(old_items, stabilized)
    return [_compact_description(item) for item in merged]


def _atomic_verified_write_json(path, obj):
    """Atomically persist JSON and fail closed if a source mirror cannot read back."""
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(obj, indent=2, ensure_ascii=False) + "\n"
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        with tmp.open("w", encoding="utf-8") as fh:
            fh.write(text)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)

        if path.parent == base.SOURCES_ROOT:
            persisted = json.loads(path.read_text(encoding="utf-8"))
            items = persisted.get("items")
            expected_key = path.stem
            if persisted.get("sourceKey") != expected_key:
                raise RuntimeError(
                    f"mirror_readback_source_mismatch:{expected_key}:{persisted.get('sourceKey')}"
                )
            if not isinstance(items, list):
                raise RuntimeError(f"mirror_readback_items_invalid:{expected_key}")
            expected_count = persisted.get("count")
            expected_total = persisted.get("totalStored")
            if expected_count != len(items) or expected_total != len(items):
                raise RuntimeError(
                    f"mirror_readback_count_mismatch:{expected_key}:"
                    f"count={expected_count}:total={expected_total}:items={len(items)}"
                )
            if obj.get("items") and not items:
                raise RuntimeError(f"mirror_readback_unexpected_empty:{expected_key}")
    finally:
        try:
            tmp.unlink(missing_ok=True)
        except Exception:
            pass


def _main_with_complete_health_gate():
    # The legacy base collector still owns parsing/mirror writes. Suppress its
    # legacy 10-source status line, then normalize the health metadata here.
    with contextlib.redirect_stdout(io.StringIO()):
        base.main()

    health = base.load_json(base.HEALTH_PATH, {})
    expected = len(base.SOURCES)
    health["version"] = max(int(health.get("version") or 0), 4)
    health["scope"] = f"{expected}-runner3-rss-sources"
    health["sourceCount"] = expected
    health["directSources"] = ["hoquoctuan", "vnhacker"]
    base.write_json(base.HEALTH_PATH, health)

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

    print(
        json.dumps(
            {
                "collector": "runner-3",
                "scope": health["scope"],
                "status": health.get("status"),
                "ok": health.get("okCount"),
                "failed": health.get("failedCount"),
                "health": str(base.HEALTH_PATH.relative_to(base.ROOT)),
            },
            ensure_ascii=False,
        )
    )
    return 0 if complete else 2


base.merge_items = _stable_merge_items
base.write_json = _atomic_verified_write_json


if __name__ == "__main__":
    raise SystemExit(_main_with_complete_health_gate())
