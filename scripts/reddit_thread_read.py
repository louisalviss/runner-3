#!/usr/bin/env python3
"""Read one public Reddit thread through the resilient Runner-3 path.

Canonical path for Reddit share links:
1. If URL is already canonical /comments/<id>/, use it directly.
2. Resolve Reddit /s/ links through rxddit's redirect only (no page scrape).
3. Fetch the post + recursive comment tree through the existing Arctic Shift
   implementation in reddit_deep_sweep_cloudflare.py.

This intentionally does not compute a coverage ratio from Reddit/Arctic Shift
`num_comments`: that metadata can be 0 or stale while the archive tree contains
many comments. The durable evidence is the captured tree snapshot count.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import urllib.error
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
DEEP = Path(__file__).with_name("reddit_deep_sweep_cloudflare.py")
UA = "runner3-reddit-thread-read/1.0 (+public read-only research)"
POST_RE = re.compile(r"/comments/([A-Za-z0-9]+)/", re.I)


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def canonical_from_url(value: str) -> tuple[str | None, str | None]:
    value = (value or "").strip()
    try:
        parts = urllib.parse.urlsplit(value)
    except ValueError:
        return None, None
    match = POST_RE.search(parts.path or "")
    if not match:
        return None, None
    pid = match.group(1)
    path = parts.path
    canonical = urllib.parse.urlunsplit(("https", "www.reddit.com", path, "", ""))
    return canonical.rstrip("/") + "/", pid


def resolve_rxddit(url: str) -> tuple[str, str, list[str]]:
    canonical, pid = canonical_from_url(url)
    if canonical and pid:
        return canonical, pid, ["already-canonical"]

    parts = urllib.parse.urlsplit(url)
    host = (parts.hostname or "").lower()
    if not (host == "reddit.com" or host.endswith(".reddit.com")) or "/s/" not in parts.path:
        raise RuntimeError("unsupported_reddit_url: expected canonical /comments/ URL or Reddit /s/ share URL")

    target = urllib.parse.urlunsplit(("https", "rxddit.com", parts.path, parts.query, ""))
    req = urllib.request.Request(
        target,
        headers={
            "User-Agent": UA,
            "Accept": "text/html,application/xhtml+xml,*/*;q=0.1",
            "Accept-Language": "en-US,en;q=0.5",
        },
    )
    opener = urllib.request.build_opener(NoRedirect)
    status = None
    location = ""
    body = ""
    try:
        with opener.open(req, timeout=45) as resp:
            status = resp.status
            location = resp.headers.get("Location", "")
            body = resp.read(200_000).decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        status = exc.code
        location = exc.headers.get("Location", "")
        try:
            body = exc.read(200_000).decode("utf-8", "replace")
        except Exception:
            body = ""

    diagnostics = [f"rxddit:{status}:{'location' if location else 'no-location'}:{len(body)}"]
    candidates = []
    if location:
        candidates.append(urllib.parse.urljoin(target, location))
    candidates.extend(re.findall(r"https?://[^\s\"'<>]+/comments/[A-Za-z0-9]+/[^\s\"'<>]*", body, re.I))

    for candidate in candidates:
        cparts = urllib.parse.urlsplit(candidate)
        if (cparts.hostname or "").lower() in {"rxddit.com", "www.rxddit.com"}:
            candidate = urllib.parse.urlunsplit(("https", "www.reddit.com", cparts.path, "", ""))
        canonical, pid = canonical_from_url(candidate)
        if canonical and pid:
            return canonical, pid, diagnostics

    raise RuntimeError("reddit_shortlink_unresolved:" + ";".join(diagnostics))


def load_deep_module():
    spec = importlib.util.spec_from_file_location("runner3_reddit_deep_single", DEEP)
    if spec is None or spec.loader is None:
        raise RuntimeError("unable_to_load_reddit_deep_sweep_cloudflare")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", required=True)
    ap.add_argument("--raw-out", required=True)
    ap.add_argument("--summary-out", required=True)
    args = ap.parse_args()

    canonical, post_id, resolver_diag = resolve_rxddit(args.url)
    deep = load_deep_module()
    payload, meta = deep.archive_thread(
        f"/comments/{post_id}.json",
        {"limit": 9999, "depth": 10, "sort": "top", "raw_json": 1},
    )

    post = payload[0]["data"]["children"][0]["data"]
    comments = [
        child.get("data") or {}
        for child in payload[1]["data"].get("children", [])
        if child.get("kind") == "t1"
    ]
    top_level = [c for c in comments if c.get("parent_id") == "t3_" + post_id]
    max_depth = max((int(c.get("depth") or 0) for c in comments), default=0)
    reported = int(post.get("num_comments") or 0)

    raw = {
        "schema_version": 1,
        "requested_url": args.url,
        "canonical_url": canonical,
        "post_id": post_id,
        "resolver": {"via": "rxddit" if resolver_diag != ["already-canonical"] else "canonical", "diagnostics": resolver_diag},
        "acquisition": meta,
        "post": post,
        "comments": comments,
        "captured_at": utc_now(),
    }
    raw_path = Path(args.raw_out)
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    raw_bytes = (json.dumps(raw, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")
    raw_path.write_bytes(raw_bytes)

    summary = {
        "schema_version": 1,
        "ok": True,
        "requested_url": args.url,
        "canonical_url": canonical,
        "post_id": post_id,
        "subreddit": post.get("subreddit"),
        "title": post.get("title"),
        "resolver_via": raw["resolver"]["via"],
        "resolver_diagnostics": resolver_diag,
        "acquisition_via": meta.get("via"),
        "source_url": meta.get("url"),
        "captured_comments": len(comments),
        "top_level_comments": len(top_level),
        "max_depth": max_depth,
        "reported_num_comments": reported if reported > 0 else None,
        "coverage_ratio": None,
        "coverage_basis": "arctic-shift recursive tree snapshot; do not infer completeness from reported_num_comments",
        "raw_bytes": len(raw_bytes),
        "raw_sha256": hashlib.sha256(raw_bytes).hexdigest(),
        "finished_at": utc_now(),
    }
    summary_path = Path(args.summary_out)
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
