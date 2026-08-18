#!/usr/bin/env python3

"""Compatibility entrypoint + hardening for Võ Hoàng Hạc hybrid scanner.

The base collector handles the shared mirror/health logic. This wrapper keeps
Notes ingestion aligned with the current public Substack profile-feed shape:
- fetch the unfiltered profile feed (filters can return empty results);
- accept only comment entities whose context.type == "note";
- require a real source timestamp rather than assigning collection time;
- prefer the Note's own canonical_url when present.

Hồ Quốc Tuấn and vnhacker remain ChatGPT-direct sources at reader runtime.
"""

import re

import rss_substack_collect as base


def _note_timestamp(item):
    candidates = [
        base.value_at(item, ("comment", "date")),
        base.value_at(item, ("comment", "created_at")),
        base.value_at(item, ("context", "timestamp")),
        base.value_at(item, ("trackingParameters", "item_content_timestamp")),
        base.value_at(item, ("trackingParameters", "item_context_timestamp")),
    ]
    for value in candidates:
        dt = base.parse_dt(value)
        if dt is not None:
            return dt
    return None


def _parse_note_item(item, target_user_id, handle, detected_dt=None):
    if not isinstance(item, dict):
        return None
    if str(item.get("type") or "").lower() != "comment":
        return None
    if str(base.value_at(item, ("context", "type")) or "").lower() != "note":
        return None

    entity_key = str(item.get("entity_key") or item.get("entityKey") or "")
    match = re.fullmatch(r"c-(\d+)", entity_key)
    if not match:
        return None

    # Public profile feeds may include activity around other people's content.
    # Keep only Notes whose author/context identifies the requested profile.
    scoped_ids = set()
    for path in [
        ("context", "users"),
        ("users",),
        ("comment", "user_id"),
        ("comment", "userId"),
        ("trackingParameters", "item_content_user_id"),
        ("trackingParameters", "item_context_user_id"),
    ]:
        value = base.value_at(item, path)
        if isinstance(value, (int, str)) and str(value).isdigit():
            scoped_ids.add(int(value))
        else:
            scoped_ids.update(base.collect_ids(value))
    if scoped_ids and target_user_id not in scoped_ids:
        return None

    dt = _note_timestamp(item)
    if dt is None:
        return None

    note_id = match.group(1)
    excerpt = base.extract_note_excerpt(item)
    raw_url = base.value_at(item, ("comment", "canonical_url")) or base.value_at(item, ("comment", "canonicalUrl"))
    canonical_url = base.canonicalize_url(raw_url) if isinstance(raw_url, str) else None
    if not canonical_url:
        canonical_url = f"https://substack.com/@{handle}/note/{entity_key}"

    title = excerpt[:140].strip() if excerpt else f"Võ Hoàng Hạc Note {entity_key}"
    if excerpt and len(excerpt) > 140:
        title = title.rstrip(" .,:;-") + "…"

    return {
        "key": f"note:{entity_key}",
        "articleId": note_id,
        "canonicalUrl": canonical_url,
        "title": title,
        "publishedAt": dt.isoformat(timespec="seconds").replace("+00:00", "Z"),
        "publishedTs": int(dt.timestamp() * 1000),
        "publishedTimeSource": "profile_feed",
        "thumbnail": None,
        "author": "Võ Hoàng Hạc",
        "description": excerpt,
        "contentSource": "substack_profile_radar",
        "itemType": "note",
        "noteId": entity_key,
    }


def _fetch_notes(handle):
    user_id, profile_endpoint = base.resolve_profile_user_id(handle)
    feed_url = f"https://substack.com/api/v1/reader/feed/profile/{user_id}"

    all_raw = []
    cursor = None
    final_url = feed_url
    for _ in range(base.MAX_NOTE_PAGES):
        params = [("cursor", cursor)] if cursor else None
        payload, final_url = base.get_json(feed_url, params=params)
        if not isinstance(payload, dict):
            raise RuntimeError("profile feed returned a non-object payload")
        items = payload.get("items")
        if not isinstance(items, list):
            raise RuntimeError(f"profile feed missing items[]; keys={sorted(payload.keys())}")
        all_raw.extend(items)

        next_cursor = payload.get("nextCursor") or payload.get("next_cursor")
        if not next_cursor or not items:
            break
        cursor = str(next_cursor)

    notes_by_url = {}
    for raw in all_raw:
        parsed = _parse_note_item(raw, user_id, handle)
        if parsed:
            notes_by_url[parsed["canonicalUrl"]] = parsed

    notes = list(notes_by_url.values())
    notes.sort(key=lambda x: x["publishedTs"], reverse=True)
    if not notes:
        raise RuntimeError(
            f"profile feed reachable for user {user_id} but yielded no verified author-owned Notes "
            f"from {len(all_raw)} activity items"
        )

    return notes, {
        "userId": user_id,
        "profileLookupUrl": profile_endpoint,
        "feedUrl": final_url,
        "rawActivityCount": len(all_raw),
        "validNoteCount": len(notes),
        "parser": "profile-comment-context-note-v2",
    }


# Harden the base implementation without duplicating its mirror/health/state code.
base.parse_note_item = _parse_note_item
base.fetch_notes = _fetch_notes


if __name__ == "__main__":
    raise SystemExit(base.main())
