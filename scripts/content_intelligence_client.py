#!/usr/bin/env python3
"""Client for Runner3 Content Intelligence API.

Designed for RSS first, but source_type is generic so the same path can ingest
X/Facebook/Reddit/web/YouTube items and user preference events later.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

DEFAULT_CORE_URL = "https://runner3-core.ducduy2411.workers.dev"


def request_json(method: str, path: str, payload: dict[str, Any] | None = None, *, core_url: str | None = None) -> dict[str, Any]:
    base = (core_url or os.environ.get("RUNNER3_CORE_URL") or DEFAULT_CORE_URL).rstrip("/")
    headers = {"Accept": "application/json", "User-Agent": "runner3-content-intelligence/1.0"}
    token = os.environ.get("RUNNER3_CORE_TOKEN", "").strip()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = None
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(base + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return json.load(resp)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code}: {body}") from exc


def load_json(path: str) -> Any:
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def cmd_ingest_manifest(args: argparse.Namespace) -> int:
    obj = load_json(args.manifest)
    items = obj.get("manifest") or []
    rows = []
    for item in items:
        rows.append({
            "item_id": item.get("stableIdentity") or item.get("itemId") or item.get("canonicalUrl"),
            "canonical_url": item.get("canonicalUrl"),
            "source_type": args.source_type,
            "source_name": item.get("sourceName") or item.get("sourceKey"),
            "source_key": item.get("sourceKey"),
            "title": item.get("title"),
            "published_at": item.get("publishedAt"),
            "language": item.get("language"),
            "raw_ref": item.get("rawRef"),
            "metadata": {
                "render_number": item.get("number"),
                "summary_evidence_status": item.get("summaryEvidenceStatus"),
            },
        })
    result = request_json("POST", "/content-intelligence/items", {"rows": rows}, core_url=args.core_url)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


def cmd_event(args: argparse.Namespace) -> int:
    payload = {
        "item_id": args.item_id,
        "event_type": args.event_type,
        "render_id": args.render_id,
        "assistant_recommended": args.assistant_recommended,
        "assistant_rank": args.assistant_rank,
        "explicit_feedback": args.explicit_feedback,
        "context": json.loads(args.context_json) if args.context_json else None,
    }
    result = request_json("POST", "/content-intelligence/events", payload, core_url=args.core_url)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--core-url")
    sub = p.add_subparsers(dest="command", required=True)

    m = sub.add_parser("ingest-manifest")
    m.add_argument("--manifest", required=True)
    m.add_argument("--source-type", default="rss")
    m.set_defaults(func=cmd_ingest_manifest)

    e = sub.add_parser("event")
    e.add_argument("--item-id", required=True)
    e.add_argument("--event-type", required=True, choices=["shown", "selected", "deep_read", "liked", "disliked", "saved"])
    e.add_argument("--render-id")
    e.add_argument("--assistant-recommended", action="store_true")
    e.add_argument("--assistant-rank", type=int)
    e.add_argument("--explicit-feedback")
    e.add_argument("--context-json")
    e.set_defaults(func=cmd_event)
    return p


def main() -> int:
    args = build_parser().parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
