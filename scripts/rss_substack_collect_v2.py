#!/usr/bin/env python3

"""Hardened entrypoint for the canonical Võ Hoàng Hạc hybrid scanner.

The base module owns the canonical parsing, identity, timestamp, mirror merge,
content-hash, fail-closed, and health rules. This wrapper only hardens Substack
transport/discovery so GitHub-hosted Runner3 can keep using the same strict
Note validator when Substack changes profile-page plumbing or blocks GitHub
Actions egress.

Hồ Quốc Tuấn and vnhacker remain ChatGPT-direct sources at reader runtime.
"""

from collections import Counter
import json
from urllib.parse import urlparse

import requests
import rss_substack_collect as base


base.SESSION.headers.update(
    {
        "User-Agent": (
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
        ),
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://substack.com/",
    }
)

_legacy_resolve_profile_user_id = base.resolve_profile_user_id


def _top_level_profile_id(payload, handle):
    if not isinstance(payload, dict):
        return None
    payload_handle = str(payload.get("handle") or payload.get("username") or "").lstrip("@").lower()
    payload_id = payload.get("id") or payload.get("user_id") or payload.get("userId")
    if payload_handle == handle.lower() and str(payload_id).isdigit() and int(payload_id) > 0:
        return int(payload_id)
    return None


def _publication_base_url():
    parsed = urlparse(base.SOURCE["article_feed"])
    return f"{parsed.scheme}://{parsed.netloc}"


def _profile_id_from_publication_archive(handle):
    """Resolve verified profile id from public publication archive byline."""
    archive_url = _publication_base_url() + "/api/v1/archive"
    response = base.SESSION.get(
        archive_url,
        params={"sort": "new", "limit": 10},
        timeout=base.TIMEOUT,
        allow_redirects=True,
        headers={"Accept": "application/json, text/plain, */*"},
    )
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, list):
        raise RuntimeError("publication archive returned a non-list payload")

    target = handle.lower()
    verified_ids = set()
    for post in payload:
        if not isinstance(post, dict):
            continue
        bylines = post.get("publishedBylines") or post.get("published_bylines") or []
        if not isinstance(bylines, list):
            continue
        for byline in bylines:
            if not isinstance(byline, dict):
                continue
            byline_handle = str(byline.get("handle") or byline.get("username") or "").lstrip("@").lower()
            byline_id = byline.get("id") or byline.get("user_id") or byline.get("userId")
            if byline_handle == target and str(byline_id).isdigit() and int(byline_id) > 0:
                verified_ids.add(int(byline_id))

    if len(verified_ids) != 1:
        raise RuntimeError(
            f"publication archive did not yield exactly one verified @{handle} user id; "
            f"found={sorted(verified_ids)}"
        )
    return next(iter(verified_ids)), response.url, "publication_archive_byline"


def hardened_resolve_profile_user_id(handle):
    errors = []

    try:
        return _profile_id_from_publication_archive(handle)
    except Exception as exc:
        errors.append(f"publication archive: {type(exc).__name__}: {exc}")

    candidates = [
        f"https://substack.com/api/v1/user/{handle}/public_profile",
        f"https://substack.com/api/v1/user/{handle}/public_profile/self",
    ]
    for url in candidates:
        try:
            payload, final_url = base.get_json(url)
            user_id = _top_level_profile_id(payload, handle) or base.extract_profile_user_id(payload, handle)
            if user_id is not None:
                return user_id, final_url, "public_profile_json"
            keys = sorted(payload.keys()) if isinstance(payload, dict) else []
            errors.append(f"{url}: profile JSON did not contain verified @{handle} id; keys={keys}")
        except Exception as exc:
            errors.append(f"{url}: {type(exc).__name__}: {exc}")

    try:
        return _legacy_resolve_profile_user_id(handle)
    except Exception as exc:
        errors.append(f"legacy profile discovery: {type(exc).__name__}: {exc}")

    raise RuntimeError("unable to resolve verified Substack profile user id; " + " | ".join(errors))


def _validate_profile_payload(payload):
    if not isinstance(payload, dict):
        raise RuntimeError("profile feed returned a non-object payload")
    items = payload.get("items")
    if not isinstance(items, list):
        raise RuntimeError(f"profile feed missing items[]; keys={sorted(payload.keys())}")
    return payload


def _extract_relay_json(text):
    """Parse target JSON from Jina Reader text transport without trusting wrapper text."""
    raw = (text or "").strip()
    candidates = [raw]
    first = raw.find("{")
    last = raw.rfind("}")
    if first >= 0 and last > first:
        candidates.append(raw[first:last + 1])
    errors = []
    for candidate in candidates:
        try:
            return _validate_profile_payload(json.loads(candidate))
        except Exception as exc:
            errors.append(f"{type(exc).__name__}: {exc}")
    raise RuntimeError("live relay did not return parseable canonical profile-feed JSON; " + " | ".join(errors))


def _get_profile_feed_page(feed_url, params):
    """Direct first; if GitHub egress is blocked, use a forced-fresh live relay."""
    variants = [dict(params or {})]
    if params and "limit" in params:
        without_limit = {k: v for k, v in params.items() if k != "limit"}
        if without_limit not in variants:
            variants.append(without_limit)

    errors = []
    for variant in variants:
        try:
            response = base.SESSION.get(
                feed_url,
                params=variant or None,
                timeout=base.TIMEOUT,
                allow_redirects=True,
                headers={"Accept": "application/json, text/plain, */*"},
            )
            response.raise_for_status()
            payload = _validate_profile_payload(response.json())
            return payload, response.url, {"params": variant, "transport": "direct"}
        except Exception as exc:
            errors.append(f"direct params={variant}: {type(exc).__name__}: {exc}")

    # Jina Reader is used only as live egress relay, with cache explicitly bypassed.
    # The returned body is not trusted as identity: every candidate still has to pass
    # base.parse_original_note() against the profile id verified from vohoanghac.com.
    for variant in variants:
        target_url = requests.Request("GET", feed_url, params=variant or None).prepare().url
        relay_url = "https://r.jina.ai/" + target_url
        try:
            response = base.SESSION.get(
                relay_url,
                timeout=base.TIMEOUT,
                allow_redirects=True,
                headers={
                    "Accept": "text/plain, */*",
                    "X-No-Cache": "true",
                    "DNT": "1",
                    "X-Respond-With": "text",
                },
            )
            response.raise_for_status()
            payload = _extract_relay_json(response.text)
            return payload, target_url, {
                "params": variant,
                "transport": "jina-live-relay",
                "relayNoCache": True,
                "relayDNT": True,
            }
        except Exception as exc:
            errors.append(f"relay params={variant}: {type(exc).__name__}: {exc}")

    raise RuntimeError("profile feed request failed; " + " | ".join(errors))


def hardened_fetch_notes(handle):
    user_id, profile_lookup_url, profile_id_source = hardened_resolve_profile_user_id(handle)
    feed_url = f"https://substack.com/api/v1/reader/feed/profile/{user_id}"

    all_raw = []
    cursor = None
    final_url = feed_url
    request_variants = []

    for _ in range(base.MAX_NOTE_PAGES):
        params = {"limit": base.NOTE_PAGE_LIMIT}
        if cursor:
            params["cursor"] = cursor

        payload, final_url, used_params = _get_profile_feed_page(feed_url, params)
        request_variants.append(used_params)
        items = payload["items"]
        all_raw.extend(items)

        next_cursor = payload.get("nextCursor") or payload.get("next_cursor")
        if not next_cursor or not items:
            break
        cursor = str(next_cursor)

    notes_by_id = {}
    comment_activity_count = 0
    item_types = Counter()
    context_types = Counter()
    comment_types = Counter()

    for raw in all_raw:
        if not isinstance(raw, dict):
            item_types["<non-object>"] += 1
            continue
        item_types[str(raw.get("type"))] += 1
        context = raw.get("context")
        if isinstance(context, dict):
            context_types[str(context.get("type"))] += 1
        comment = raw.get("comment")
        if isinstance(comment, dict):
            comment_activity_count += 1
            comment_types[str(comment.get("type"))] += 1

        parsed = base.parse_original_note(raw, user_id, handle)
        if parsed:
            notes_by_id[parsed["noteId"]] = parsed

    notes = list(notes_by_id.values())
    notes.sort(key=lambda x: x["publishedTs"], reverse=True)

    if not notes:
        raise RuntimeError(
            f"profile feed reachable for verified user {user_id} but yielded no canonical original Notes "
            f"from {len(all_raw)} entries; itemTypes={dict(item_types)}; "
            f"contextTypes={dict(context_types)}; commentTypes={dict(comment_types)}"
        )

    transports = sorted({v.get("transport") for v in request_variants if isinstance(v, dict) and v.get("transport")})
    return notes, {
        "userId": user_id,
        "profileLookupUrl": profile_lookup_url,
        "profileIdSource": profile_id_source,
        "feedUrl": final_url,
        "rawProfileEntryCount": len(all_raw),
        "commentActivityCount": comment_activity_count,
        "validOriginalNoteCount": len(notes),
        "requestVariants": request_variants,
        "feedTransports": transports,
        "liveRelayUsed": "jina-live-relay" in transports,
    }


base.resolve_profile_user_id = hardened_resolve_profile_user_id
base.fetch_notes = hardened_fetch_notes


if __name__ == "__main__":
    raise SystemExit(base.main())
