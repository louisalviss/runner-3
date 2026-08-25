#!/usr/bin/env python3
"""Canonical one-URL Reddit read lane.

Thread-read and live-read are intentionally one workload: given a Reddit URL,
return the best current public snapshot available. The shared router attempts
live Reddit JSON first, then the Runner-3 bridge, then Arctic Shift.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import reddit_common as reddit


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", required=True)
    ap.add_argument("--raw-out", required=True)
    ap.add_argument("--summary-out", required=True)
    args = ap.parse_args()

    canonical, post_id, resolver, post, comments, meta = reddit.read_current_thread(args.url)
    top_level = [c for c in comments if c.get("parent_id") == "t3_" + post_id]
    max_depth = max((int(c.get("depth") or 0) for c in comments), default=0)
    reported = int(post.get("num_comments") or 0)

    raw = {
        "schema_version": 2,
        "lane": "reddit-read",
        "requested_url": args.url,
        "canonical_url": canonical,
        "post_id": post_id,
        "resolver": resolver,
        "acquisition": meta,
        "post": post,
        "comments": comments,
        "captured_at": reddit.utc_now(),
    }
    raw_path = Path(args.raw_out)
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    raw_bytes = (json.dumps(raw, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")
    raw_path.write_bytes(raw_bytes)

    acquisition_via = str(meta.get("via") or "")
    is_live = acquisition_via.startswith("reddit-json:") or acquisition_via.startswith("cloudflare-reddit-json:")
    summary = {
        "schema_version": 2,
        "ok": True,
        "lane": "reddit-read",
        "read_mode": "live-current" if is_live else "archive-fallback",
        "requested_url": args.url,
        "canonical_url": canonical,
        "post_id": post_id,
        "subreddit": post.get("subreddit"),
        "title": post.get("title"),
        "resolver_via": resolver.get("via"),
        "resolver_diagnostics": resolver.get("diagnostics") or [],
        "acquisition_via": acquisition_via,
        "source_url": meta.get("url"),
        "captured_comments": len(comments),
        "top_level_comments": len(top_level),
        "max_depth": max_depth,
        "reported_num_comments": reported if reported > 0 else None,
        "coverage_ratio": None,
        "coverage_basis": (
            "current/live public snapshot when available; otherwise Arctic Shift recursive tree snapshot; "
            "do not infer completeness from reported_num_comments"
        ),
        "raw_bytes": len(raw_bytes),
        "raw_sha256": hashlib.sha256(raw_bytes).hexdigest(),
        "finished_at": reddit.utc_now(),
    }
    summary_path = Path(args.summary_out)
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
