#!/usr/bin/env python3
"""Durable D1 state for Vietnam News Radar.

This is deliberately a small control-plane ledger. It stores only bounded
story/thread identities and development hashes in Runner3 Core D1; article
content and reports stay in their existing stores.

Story semantics:
- unseen cluster => NEW
- same cluster + same development hash => DUPLICATE
- same cluster + changed development hash => UPDATE

F33 is a coverage exception: classification never suppresses a page-1 thread.
Every F33 result includes render_required=true.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CORE_HELPERS = ROOT / ".github" / "scripts"
if str(CORE_HELPERS) not in sys.path:
    sys.path.insert(0, str(CORE_HELPERS))

from runner3_core import get_checkpoint, save_checkpoint, save_state  # noqa: E402

PROJECT = "vietnam-news-radar"
SOURCE = "vietnam-news-radar"
STORY_SCOPE = "story-ledger"
F33_SCOPE = "f33-ledger"
DEFAULT_MAX_STORIES = 500
DEFAULT_MAX_F33_THREADS = 200


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def empty_ledger(kind: str) -> dict[str, Any]:
    key = "stories" if kind == "story" else "threads"
    return {"version": 1, key: {}}


def checkpoint_position(checkpoint: dict[str, Any] | None, kind: str) -> dict[str, Any]:
    if not checkpoint:
        return empty_ledger(kind)
    position = checkpoint.get("position")
    if not isinstance(position, dict):
        return empty_ledger(kind)
    key = "stories" if kind == "story" else "threads"
    if not isinstance(position.get(key), dict):
        return empty_ledger(kind)
    return position


def classify_story(ledger: dict[str, Any], cluster_id: str, development_hash: str) -> str:
    prior = ledger.get("stories", {}).get(cluster_id)
    if not prior:
        return "NEW"
    if prior.get("development_hash") == development_hash:
        return "DUPLICATE"
    return "UPDATE"


def classify_f33(ledger: dict[str, Any], thread_id: str, development_hash: str | None) -> str:
    prior = ledger.get("threads", {}).get(thread_id)
    if not prior:
        return "NEW"
    if development_hash and prior.get("development_hash") != development_hash:
        return "UPDATE"
    return "SEEN_OR_BUMPED"


def _prune(entries: dict[str, Any], max_entries: int) -> dict[str, Any]:
    if len(entries) <= max_entries:
        return entries
    ordered = sorted(
        entries.items(),
        key=lambda kv: (
            str(kv[1].get("last_seen_at") or kv[1].get("last_seen_page1_at") or ""),
            str(kv[1].get("last_rendered_at") or ""),
            kv[0],
        ),
        reverse=True,
    )
    return dict(ordered[:max_entries])


def update_story_ledger(
    ledger: dict[str, Any],
    *,
    cluster_id: str,
    development_hash: str,
    headline: str | None,
    rendered: bool,
    timestamp: str,
    max_entries: int,
) -> tuple[dict[str, Any], str]:
    stories = dict(ledger.get("stories") or {})
    action = classify_story({"stories": stories}, cluster_id, development_hash)
    prior = dict(stories.get(cluster_id) or {})
    first_seen = prior.get("first_seen_at") or timestamp
    prior_hash = prior.get("development_hash")
    update_count = int(prior.get("update_count") or 0)
    if prior and prior_hash != development_hash:
        update_count += 1
    item = {
        **prior,
        "development_hash": development_hash,
        "first_seen_at": first_seen,
        "last_seen_at": timestamp,
        "update_count": update_count,
    }
    if headline:
        item["headline"] = headline
    if rendered:
        item["last_rendered_at"] = timestamp
    stories[cluster_id] = item
    stories = _prune(stories, max_entries)
    return {"version": 1, "stories": stories}, action


def update_f33_ledger(
    ledger: dict[str, Any],
    *,
    thread_id: str,
    development_hash: str | None,
    thread_created_at: str | None,
    full_crawl_run: str | None,
    timestamp: str,
    max_entries: int,
) -> tuple[dict[str, Any], str]:
    threads = dict(ledger.get("threads") or {})
    action = classify_f33({"threads": threads}, thread_id, development_hash)
    prior = dict(threads.get(thread_id) or {})
    item = {
        **prior,
        "first_seen_at": prior.get("first_seen_at") or timestamp,
        "last_seen_page1_at": timestamp,
    }
    if development_hash:
        item["development_hash"] = development_hash
    if thread_created_at:
        item["thread_created_at"] = thread_created_at
    if full_crawl_run:
        item["last_full_crawl_run"] = full_crawl_run
    threads[thread_id] = item
    threads = _prune(threads, max_entries)
    return {"version": 1, "threads": threads}, action


def emit(obj: dict[str, Any]) -> None:
    print(json.dumps(obj, ensure_ascii=False, sort_keys=True))


def cmd_story(args: argparse.Namespace) -> int:
    checkpoint = get_checkpoint(PROJECT, STORY_SCOPE, core_url=args.core_url)
    ledger = checkpoint_position(checkpoint, "story")
    timestamp = args.at or now_iso()
    updated, action = update_story_ledger(
        ledger,
        cluster_id=args.cluster_id,
        development_hash=args.development_hash,
        headline=args.headline,
        rendered=args.rendered,
        timestamp=timestamp,
        max_entries=args.max_entries,
    )
    if args.commit:
        saved = save_checkpoint(
            PROJECT,
            SOURCE,
            scope=STORY_SCOPE,
            status="success",
            position=updated,
            core_url=args.core_url,
        )
    else:
        saved = None
    emit({
        "ok": True,
        "cluster_id": args.cluster_id,
        "action": action,
        "render_candidate": action in {"NEW", "UPDATE"},
        "committed": bool(args.commit),
        "checkpoint_updated_at": (saved or {}).get("updated_at"),
    })
    return 0


def cmd_f33(args: argparse.Namespace) -> int:
    checkpoint = get_checkpoint(PROJECT, F33_SCOPE, core_url=args.core_url)
    ledger = checkpoint_position(checkpoint, "f33")
    timestamp = args.at or now_iso()
    updated, action = update_f33_ledger(
        ledger,
        thread_id=args.thread_id,
        development_hash=args.development_hash,
        thread_created_at=args.thread_created_at,
        full_crawl_run=args.full_crawl_run,
        timestamp=timestamp,
        max_entries=args.max_entries,
    )
    if args.commit:
        saved = save_checkpoint(
            PROJECT,
            SOURCE,
            scope=F33_SCOPE,
            status="success",
            position=updated,
            core_url=args.core_url,
        )
    else:
        saved = None
    emit({
        "ok": True,
        "thread_id": args.thread_id,
        "action": action,
        "render_required": True,
        "committed": bool(args.commit),
        "checkpoint_updated_at": (saved or {}).get("updated_at"),
    })
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    detail = {
        "last_success_at": args.last_success_at,
        "trends_snapshot_at": args.trends_snapshot_at,
        "f33_run_id": args.f33_run_id,
        "forum_signal_run_id": args.forum_signal_run_id,
    }
    detail = {k: v for k, v in detail.items() if v is not None}
    state = save_state(
        SOURCE,
        status=args.status,
        run_id=args.run_id,
        detail=detail,
        core_url=args.core_url,
    )
    emit({"ok": True, "state": state})
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--core-url", default=os.environ.get("RUNNER3_CORE_URL"))
    sub = p.add_subparsers(dest="command", required=True)

    s = sub.add_parser("story", help="classify/optionally commit a normalized story cluster")
    s.add_argument("--cluster-id", required=True)
    s.add_argument("--development-hash", required=True)
    s.add_argument("--headline")
    s.add_argument("--at")
    s.add_argument("--rendered", action="store_true")
    s.add_argument("--commit", action="store_true")
    s.add_argument("--max-entries", type=int, default=DEFAULT_MAX_STORIES)
    s.set_defaults(func=cmd_story)

    f = sub.add_parser("f33", help="track F33 page-1 thread without suppressing rendering")
    f.add_argument("--thread-id", required=True)
    f.add_argument("--development-hash")
    f.add_argument("--thread-created-at")
    f.add_argument("--full-crawl-run")
    f.add_argument("--at")
    f.add_argument("--commit", action="store_true")
    f.add_argument("--max-entries", type=int, default=DEFAULT_MAX_F33_THREADS)
    f.set_defaults(func=cmd_f33)

    r = sub.add_parser("run", help="persist Radar run-level state")
    r.add_argument("--status", required=True, choices=["running", "success", "failed", "degraded"])
    r.add_argument("--run-id")
    r.add_argument("--last-success-at")
    r.add_argument("--trends-snapshot-at")
    r.add_argument("--f33-run-id")
    r.add_argument("--forum-signal-run-id")
    r.set_defaults(func=cmd_run)
    return p


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    if hasattr(args, "max_entries") and args.max_entries < 1:
        parser.error("--max-entries must be >= 1")
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
