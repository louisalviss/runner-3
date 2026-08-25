#!/usr/bin/env python3
"""Run Reddit deep-sweep using the shared Reddit acquisition layer.

Generic Reddit access is owned by reddit_common.py. This wrapper only adds the
RealDayTrading wiki bootstrap/refresh required by the deep research workload.
"""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import time
import urllib.parse
import urllib.request

import reddit_common as reddit

COLLECTOR = Path(__file__).with_name("reddit_deep_sweep.py")
UA = "runner3-reddit-deep-sweep/4.0 (+public read-only research)"
JINA_BASE = "https://r.jina.ai/https://www.reddit.com"
WIKI_EXPORT_REPO = "https://github.com/RichVarney/RealDayTrading_Wiki"
WIKI_RE = re.compile(r"^/r/([A-Za-z0-9_]+)/wiki/([A-Za-z0-9_.-]+)\.json$")
ORIGINAL_POST_RE = re.compile(
    r"Original post:\s*\[[^\]]*\]\((https?://(?:www\.)?reddit\.com/r/[^)\s]+/comments/[A-Za-z0-9]+/[^)]*)\)",
    re.I,
)


def load_collector():
    spec = importlib.util.spec_from_file_location("runner3_reddit_deep_sweep", COLLECTOR)
    if spec is None or spec.loader is None:
        raise RuntimeError("unable_to_load_reddit_collector")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def jina_wiki(path: str):
    match = WIKI_RE.match(path)
    if not match:
        raise RuntimeError("jina_wiki_path_not_supported")
    subreddit, page = match.groups()
    source_url = f"https://www.reddit.com/r/{subreddit}/wiki/{page}/"
    url = f"{JINA_BASE}/r/{subreddit}/wiki/{page}/"
    errors = []
    for attempt in range(1, 4):
        req = urllib.request.Request(
            url,
            headers={"User-Agent": UA, "Accept": "text/plain,text/markdown,*/*;q=0.1"},
        )
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                raw = resp.read()
                status = resp.status
            if status != 200:
                raise RuntimeError(f"jina_http_{status}")
            text = raw.decode("utf-8", "replace").strip()
            if len(text) < 100:
                raise RuntimeError("jina_wiki_too_short")
            payload = {
                "kind": "wikipage",
                "data": {
                    "content_md": text,
                    "content_html": "",
                    "revision_date": None,
                },
                "_runner3_mirror": {
                    "source_url": source_url,
                    "reader_url": url,
                },
            }
            return payload, {
                "url": source_url,
                "bytes": len(raw),
                "via": "jina-reader",
            }
        except Exception as exc:
            errors.append(f"attempt={attempt}:{type(exc).__name__}:{exc}")
            if attempt < 3:
                time.sleep(attempt)
    raise RuntimeError("jina_wiki_failed:" + " | ".join(errors[-3:]))


def ensure_wiki_export_dir() -> Path:
    configured = os.environ.get("RDT_WIKI_EXPORT_DIR", "").strip()
    if configured:
        path = Path(configured)
        if (path / "posts").is_dir():
            return path
        raise RuntimeError(f"rdt_wiki_export_dir_invalid:{path}")

    target = Path(tempfile.gettempdir()) / "rdt-wiki-export"
    if target.exists():
        shutil.rmtree(target)
    clone_url = WIKI_EXPORT_REPO + ".git"
    subprocess.run(
        ["git", "clone", "--depth", "1", "--filter=blob:none", "--sparse", clone_url, str(target)],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        timeout=120,
    )
    subprocess.run(
        ["git", "-C", str(target), "sparse-checkout", "set", "posts"],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        timeout=120,
    )
    commit = subprocess.check_output(
        ["git", "-C", str(target), "rev-parse", "HEAD"],
        text=True,
        timeout=20,
    ).strip()
    os.environ["RDT_WIKI_EXPORT_DIR"] = str(target)
    os.environ["RDT_WIKI_EXPORT_COMMIT"] = commit
    return target


def export_wiki_snapshot(collector, subreddit: str, live_fetch_wiki):
    export_dir = ensure_wiki_export_dir()
    posts_dir = export_dir / "posts"
    files = sorted(posts_dir.glob("*.md"))
    if not files:
        raise RuntimeError(f"rdt_wiki_export_posts_missing:{posts_dir}")

    canonical_links = []
    external_links = []
    canonical_seen = set()
    external_seen = set()
    chunks = [
        "# RealDayTrading Wiki export snapshot",
        "",
        f"Source: {WIKI_EXPORT_REPO}",
        f"Snapshot commit: {os.environ.get('RDT_WIKI_EXPORT_COMMIT') or 'unknown'}",
        "",
    ]
    total_bytes = 0

    for path in files:
        text = path.read_text(encoding="utf-8", errors="replace")
        total_bytes += len(text.encode("utf-8"))
        chunks.extend([f"\n\n<!-- source-file: {path.name} -->\n", text])

        match = ORIGINAL_POST_RE.search(text)
        if match:
            url = collector.normalize_wiki_url(match.group(1), subreddit)
            if url:
                parts = urllib.parse.urlsplit(url)
                pid_match = collector.POST_ID_RE.search(parts.path)
                pid = pid_match.group(1) if pid_match else None
                if pid and pid not in canonical_seen:
                    canonical_seen.add(pid)
                    canonical_links.append({
                        "ordinal": len(canonical_links) + 1,
                        "label": path.stem[:500],
                        "url": url,
                        "host": parts.netloc.lower(),
                        "kind": "reddit-thread",
                        "post_id": pid,
                        "wiki_source": "github-export",
                    })

        for link in collector.extract_wiki_links(text, subreddit):
            if link.get("kind") != "external":
                continue
            url = link.get("url")
            if not url or url in external_seen:
                continue
            external_seen.add(url)
            item = dict(link)
            item["wiki_source"] = "github-export"
            external_links.append(item)

    if len(canonical_links) < 50:
        raise RuntimeError(f"rdt_wiki_export_too_small:reddit_threads={len(canonical_links)}")

    live_valid = False
    live_error = None
    live_links = []
    live_markdown = ""
    try:
        _live_payload, live_markdown, candidate_links, _live_meta = live_fetch_wiki(subreddit)
        live_reddit_ids = {x.get("post_id") for x in candidate_links if x.get("post_id")}
        if len(candidate_links) >= 50 and len(live_reddit_ids) >= 50:
            live_valid = True
            live_links = candidate_links
        else:
            live_error = (
                f"live_wiki_rejected:links={len(candidate_links)}:"
                f"reddit_threads={len(live_reddit_ids)}"
            )
    except Exception as exc:
        live_error = f"{type(exc).__name__}:{exc}"

    links = list(canonical_links)
    seen_urls = {x["url"] for x in links}
    for link in external_links:
        if link.get("url") not in seen_urls:
            links.append(link)
            seen_urls.add(link["url"])
    if live_valid:
        for link in live_links:
            if link.get("url") not in seen_urls:
                item = dict(link)
                item["wiki_source"] = "live-refresh"
                links.append(item)
                seen_urls.add(item["url"])

    combined = "\n".join(chunks)
    if live_valid and live_markdown:
        combined += "\n\n# Live wiki refresh\n\n" + live_markdown

    payload = {
        "kind": "wiki-export",
        "data": {
            "source_repo": WIKI_EXPORT_REPO,
            "snapshot_commit": os.environ.get("RDT_WIKI_EXPORT_COMMIT"),
            "post_files": len(files),
            "canonical_reddit_threads": len(canonical_links),
            "live_refresh_valid": live_valid,
            "live_refresh_error": live_error,
        },
    }
    meta = {
        "url": WIKI_EXPORT_REPO,
        "bytes": total_bytes,
        "via": "github-wiki-export+live" if live_valid else "github-wiki-export",
        "snapshot_commit": os.environ.get("RDT_WIKI_EXPORT_COMMIT"),
        "post_files": len(files),
        "canonical_reddit_threads": len(canonical_links),
        "live_refresh_valid": live_valid,
        "live_refresh_error": live_error,
    }
    return payload, combined, links, meta


def main():
    collector = load_collector()
    original_fetch_wiki = collector.fetch_wiki

    def request_json(path: str, query=None, tries: int = 3):
        if WIKI_RE.match(path):
            return jina_wiki(path)
        return reddit.resilient_request_json(path, query, min(max(int(tries), 1), 3))

    collector.request_json = request_json
    collector.fetch_wiki = lambda subreddit: export_wiki_snapshot(
        collector,
        subreddit,
        original_fetch_wiki,
    )
    collector.main()


if __name__ == "__main__":
    main()
