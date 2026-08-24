#!/usr/bin/env python3
"""Deep-sweep a public subreddit into normalized SQL + raw evidence files.

Acquisition policy is deliberately cheap-first:
Reddit JSON -> old.reddit JSON. Browser/Cloak/VPN escalation remains outside
this collector and is only used when the public JSON lane is genuinely blocked.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import math
import pathlib
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict

UA = "runner3-reddit-deep-sweep/1.0 (+public read-only research)"
BASES = ("https://www.reddit.com", "https://old.reddit.com")

KEYWORDS = {
    "relative-strength": ("relative strength", "relative weakness", "rs/rw", "rs rw", "strong vs", "weak vs"),
    "scanner": ("scanner", "scan ", "stock screener", "screener"),
    "indicator": ("indicator", "pine script", "tradingview", "ema", "sma", "vwap"),
    "setup": ("setup", "entry", "breakout", "pullback", "reversal"),
    "trade-management": ("trade management", "position sizing", "stop loss", "stop-loss", "take profit", "exit"),
    "market-regime": ("market regime", "market condition", "spy", "qqq", "market trend"),
    "evidence": ("backtest", "statistics", "statistical", "expectancy", "sample size", "win rate", "profit factor"),
    "risk": ("risk management", "risk/reward", "r:r", "drawdown"),
}

NOISE_PATTERNS = (
    "daily live trading",
    "weekly live trading",
    "what are you trading",
    "off topic",
)


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def safe_name(value: str) -> str:
    value = re.sub(r"[^A-Za-z0-9_.-]+", "-", value.strip())
    return value.strip("-") or "unknown"


def request_json(path: str, query: dict[str, str | int] | None = None, tries: int = 3):
    suffix = path
    if query:
        suffix += ("&" if "?" in suffix else "?") + urllib.parse.urlencode(query)
    errors = []
    for base in BASES:
        url = base + suffix
        for attempt in range(1, tries + 1):
            req = urllib.request.Request(
                url,
                headers={
                    "User-Agent": UA,
                    "Accept": "application/json,text/plain;q=0.9,*/*;q=0.1",
                    "Cache-Control": "no-cache",
                },
            )
            try:
                with urllib.request.urlopen(req, timeout=35) as resp:
                    raw = resp.read()
                return json.loads(raw.decode("utf-8")), {
                    "url": url,
                    "bytes": len(raw),
                    "via": urllib.parse.urlsplit(base).netloc,
                }
            except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
                status = getattr(exc, "code", None)
                errors.append(f"{url} attempt={attempt} status={status} error={exc}")
                if status in (401, 403, 429):
                    break
                time.sleep(min(attempt, 2))
    raise RuntimeError(" | ".join(errors[-6:]))


def listing_specs(mode: str):
    if mode == "delta":
        return [
            ("new", None, 2),
            ("hot", None, 1),
            ("top-day", "day", 1),
            ("top-week", "week", 1),
        ]
    return [
        ("top-all", "all", 5),
        ("top-year", "year", 3),
        ("top-month", "month", 2),
        ("top-week", "week", 1),
        ("hot", None, 1),
        ("new", None, 2),
    ]


def fetch_listing(subreddit: str, label: str, period: str | None, pages: int):
    items = []
    raw_pages = []
    after = None
    endpoint = "top" if label.startswith("top-") else label
    for page_no in range(1, pages + 1):
        query = {"limit": 100, "raw_json": 1}
        if period:
            query["t"] = period
        if after:
            query["after"] = after
        payload, meta = request_json(f"/r/{urllib.parse.quote(subreddit)}/{endpoint}.json", query)
        children = (((payload or {}).get("data") or {}).get("children") or [])
        raw_pages.append({"page": page_no, "meta": meta, "payload": payload})
        if not children:
            break
        for child in children:
            if child.get("kind") == "t3" and isinstance(child.get("data"), dict):
                items.append(child["data"])
        after = ((payload or {}).get("data") or {}).get("after")
        if not after:
            break
        time.sleep(0.35)
    return items, raw_pages


def body_hash(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def tags_for(post: dict) -> dict[str, float]:
    text = f"{post.get('title','')}\n{post.get('selftext','')}".lower()
    tags = {}
    for tag, needles in KEYWORDS.items():
        hits = sum(1 for needle in needles if needle in text)
        if hits:
            tags[tag] = min(3.0, 1.0 + 0.5 * (hits - 1))
    return tags


def quality(post: dict) -> float:
    score = max(int(post.get("score") or 0), 0)
    comments = max(int(post.get("num_comments") or 0), 0)
    title = post.get("title") or ""
    body = post.get("selftext") or ""
    text = f"{title}\n{body}".lower()
    q = 1.35 * math.log1p(score) + 1.15 * math.log1p(comments)
    q += min(len(body), 10000) / 2500.0
    q += min(len(title), 180) / 180.0
    q += 1.1 * sum(tags_for(post).values())
    if any(pattern in text for pattern in NOISE_PATTERNS):
        q -= 5.0
    if body in ("[removed]", "[deleted]"):
        q -= 2.0
    return round(q, 4)


def comment_quality(comment: dict) -> float:
    score = max(int(comment.get("score") or 0), 0)
    body = comment.get("body") or ""
    q = math.log1p(score) + min(len(body), 5000) / 1600.0
    lower = body.lower()
    q += 0.45 * sum(
        1 for needles in KEYWORDS.values() for needle in needles if needle in lower
    )
    return round(q, 4)


def flatten_comments(node, post_id: str, depth: int = 0):
    out = []
    if isinstance(node, list):
        for item in node:
            out.extend(flatten_comments(item, post_id, depth))
        return out
    if not isinstance(node, dict):
        return out
    kind = node.get("kind")
    data = node.get("data") or {}
    if kind == "t1":
        row = {
            "comment_id": data.get("id"),
            "post_id": post_id,
            "parent_id": data.get("parent_id"),
            "author": data.get("author"),
            "depth": int(data.get("depth") if data.get("depth") is not None else depth),
            "body_text": data.get("body") or "",
            "score": int(data.get("score") or 0),
            "created_utc": int(data.get("created_utc") or 0),
        }
        if row["comment_id"]:
            row["body_hash"] = body_hash(row["body_text"])
            row["quality_score"] = comment_quality(data)
            out.append(row)
        replies = data.get("replies")
        if isinstance(replies, dict):
            children = ((replies.get("data") or {}).get("children") or [])
            out.extend(flatten_comments(children, post_id, depth + 1))
    elif kind == "Listing":
        out.extend(flatten_comments((data.get("children") or []), post_id, depth))
    return out


def fetch_thread(post_id: str):
    return request_json(
        f"/comments/{urllib.parse.quote(post_id)}.json",
        {"limit": 500, "depth": 10, "sort": "top", "raw_json": 1},
    )


def sql_quote(value):
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, (int, float)):
        if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
            return "NULL"
        return str(value)
    return "'" + str(value).replace("'", "''").replace("\x00", "") + "'"


def emit_post_sql(post: dict, sorts: list[str], raw_pointer: str | None, fetched: bool, comment_count: int):
    post_id = post["id"]
    canonical = "https://www.reddit.com" + (post.get("permalink") or f"/comments/{post_id}/")
    values = {
        "post_id": post_id,
        "subreddit": post.get("subreddit") or "",
        "canonical_url": canonical,
        "title": post.get("title") or "",
        "author": post.get("author"),
        "created_utc": int(post.get("created_utc") or 0),
        "score": int(post.get("score") or 0),
        "num_comments": int(post.get("num_comments") or 0),
        "body_text": post.get("selftext") or "",
        "body_hash": body_hash(post.get("selftext") or ""),
        "quality_score": quality(post),
        "status": "thread_fetched" if fetched else "indexed",
        "source_sorts": json.dumps(sorted(set(sorts)), separators=(",", ":")),
        "last_thread_fetch_at": utc_now() if fetched else None,
        "comments_snapshot_count": comment_count if fetched else 0,
        "raw_object_key": raw_pointer if fetched else None,
    }
    cols = list(values)
    quoted = ",".join(sql_quote(values[c]) for c in cols)
    update_cols = [c for c in cols if c != "post_id"]
    if not fetched:
        # A listing refresh must never erase a previously captured thread snapshot.
        update_cols = [
            c for c in update_cols
            if c not in ("status", "last_thread_fetch_at", "comments_snapshot_count", "raw_object_key")
        ]
    update = ",".join(f"{c}=excluded.{c}" for c in update_cols)
    if fetched:
        update += ",status='thread_fetched'"
    return (
        f"INSERT INTO reddit_posts ({','.join(cols)}) VALUES ({quoted}) "
        f"ON CONFLICT(post_id) DO UPDATE SET {update}, last_seen_at=CURRENT_TIMESTAMP;"
    )


def emit_comment_sql(c: dict):
    cols = [
        "comment_id", "post_id", "parent_id", "author", "depth", "body_text",
        "body_hash", "score", "created_utc", "quality_score"
    ]
    quoted = ",".join(sql_quote(c.get(k)) for k in cols)
    update = ",".join(
        f"{k}=excluded.{k}" for k in cols if k != "comment_id"
    )
    return (
        f"INSERT INTO reddit_comments ({','.join(cols)}) VALUES ({quoted}) "
        f"ON CONFLICT(comment_id) DO UPDATE SET {update}, last_seen_at=CURRENT_TIMESTAMP;"
    )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--subreddit", default="RealDayTrading")
    ap.add_argument("--mode", choices=("deep", "delta"), default="deep")
    ap.add_argument("--max-threads", type=int, default=60)
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--r2-key", required=True)
    ap.add_argument("--output-dir", required=True)
    ap.add_argument("--sql-dir", required=True)
    ap.add_argument("--manifest-out", required=True)
    args = ap.parse_args()

    started = utc_now()
    out_root = pathlib.Path(args.output_dir)
    listings_dir = out_root / "listings"
    threads_dir = out_root / "threads"
    listings_dir.mkdir(parents=True, exist_ok=True)
    threads_dir.mkdir(parents=True, exist_ok=True)

    posts: dict[str, dict] = {}
    post_sorts: dict[str, set[str]] = defaultdict(set)
    acquisition = []

    for label, period, pages in listing_specs(args.mode):
        items, raw_pages = fetch_listing(args.subreddit, label, period, pages)
        for page in raw_pages:
            p = listings_dir / f"{safe_name(label)}-{page['page']:02d}.json"
            p.write_text(json.dumps(page["payload"], ensure_ascii=False), encoding="utf-8")
            acquisition.append({
                "kind": "listing",
                "label": label,
                "page": page["page"],
                **page["meta"],
            })
        for post in items:
            pid = post.get("id")
            if not pid:
                continue
            prev = posts.get(pid)
            if prev is None or int(post.get("score") or 0) >= int(prev.get("score") or 0):
                posts[pid] = post
            post_sorts[pid].add(label)

    ranked = sorted(posts.values(), key=lambda p: (quality(p), int(p.get("score") or 0)), reverse=True)
    selected = ranked[: max(1, min(args.max_threads, 150))]

    all_comments = []
    fetched_ids = set()
    thread_errors = []
    thread_comment_counts = {}
    for post in selected:
        pid = post["id"]
        try:
            payload, meta = fetch_thread(pid)
            (threads_dir / f"{pid}.json").write_text(
                json.dumps(payload, ensure_ascii=False), encoding="utf-8"
            )
            acquisition.append({"kind": "thread", "post_id": pid, **meta})
            comments = []
            if isinstance(payload, list) and len(payload) >= 2:
                comments = flatten_comments(payload[1], pid)
                try:
                    thread_post = payload[0]["data"]["children"][0]["data"]
                    if isinstance(thread_post, dict):
                        posts[pid] = {**posts[pid], **thread_post}
                        post = posts[pid]
                except (KeyError, IndexError, TypeError):
                    pass
            dedup = {}
            for c in comments:
                dedup[c["comment_id"]] = c
            comments = list(dedup.values())
            all_comments.extend(comments)
            thread_comment_counts[pid] = len(comments)
            fetched_ids.add(pid)
        except Exception as exc:
            thread_errors.append({"post_id": pid, "error": str(exc)[:1000]})
        time.sleep(0.25)

    raw_pointer_prefix = f"{args.r2_key}#"
    sql = ["BEGIN;"]
    sql.append(
        "INSERT INTO reddit_scan_runs "
        "(run_id,subreddit,mode,status,started_at,posts_seen,threads_fetched,comments_seen,raw_object_key,error) VALUES "
        f"({sql_quote(args.run_id)},{sql_quote(args.subreddit)},{sql_quote(args.mode)},'running',"
        f"{sql_quote(started)},{len(posts)},{len(fetched_ids)},{len(all_comments)},"
        f"{sql_quote(args.r2_key)},{sql_quote(json.dumps(thread_errors, ensure_ascii=False) if thread_errors else None)}) "
        "ON CONFLICT(run_id) DO UPDATE SET status='running', posts_seen=excluded.posts_seen, "
        "threads_fetched=excluded.threads_fetched, comments_seen=excluded.comments_seen, "
        "raw_object_key=excluded.raw_object_key, error=excluded.error;"
    )

    for post in posts.values():
        pid = post["id"]
        fetched = pid in fetched_ids
        raw_pointer = raw_pointer_prefix + f"threads/{pid}.json" if fetched else None
        sql.append(
            emit_post_sql(
                post,
                sorted(post_sorts[pid]),
                raw_pointer,
                fetched,
                thread_comment_counts.get(pid, 0),
            )
        )
        for tag, weight in tags_for(post).items():
            sql.append(
                "INSERT INTO reddit_post_tags (post_id,tag,weight) VALUES "
                f"({sql_quote(pid)},{sql_quote(tag)},{sql_quote(weight)}) "
                "ON CONFLICT(post_id,tag) DO UPDATE SET weight=excluded.weight, updated_at=CURRENT_TIMESTAMP;"
            )

    for c in all_comments:
        sql.append(emit_comment_sql(c))

    sql.append(
        "UPDATE reddit_scan_runs SET status='success', finished_at=CURRENT_TIMESTAMP, "
        f"posts_seen={len(posts)}, threads_fetched={len(fetched_ids)}, comments_seen={len(all_comments)}, "
        f"raw_object_key={sql_quote(args.r2_key)}, error={sql_quote(json.dumps(thread_errors, ensure_ascii=False) if thread_errors else None)} "
        f"WHERE run_id={sql_quote(args.run_id)};"
    )
    sql.append("COMMIT;")

    sql_dir = pathlib.Path(args.sql_dir)
    sql_dir.mkdir(parents=True, exist_ok=True)
    start_stmt = sql[1]
    final_stmt = sql[-2]
    data_stmts = sql[2:-2]
    chunk_size = 200
    chunks = []
    chunks.append(("0000-start.sql", ["BEGIN;", start_stmt, "COMMIT;"]))
    for offset in range(0, len(data_stmts), chunk_size):
        payload = ["BEGIN;", *data_stmts[offset:offset + chunk_size], "COMMIT;"]
        chunks.append((f"{1 + offset // chunk_size:04d}-data.sql", payload))
    chunks.append((f"{1 + math.ceil(len(data_stmts) / chunk_size):04d}-finish.sql", ["BEGIN;", final_stmt, "COMMIT;"]))
    for name, payload in chunks:
        (sql_dir / name).write_text("\n".join(payload) + "\n", encoding="utf-8")

    top_preview = []
    for p in ranked[:25]:
        top_preview.append({
            "post_id": p["id"],
            "title": p.get("title") or "",
            "quality_score": quality(p),
            "score": int(p.get("score") or 0),
            "num_comments": int(p.get("num_comments") or 0),
            "tags": tags_for(p),
            "selected_for_thread": p["id"] in fetched_ids,
            "canonical_url": "https://www.reddit.com" + (p.get("permalink") or f"/comments/{p['id']}/"),
        })

    manifest = {
        "ok": True,
        "run_id": args.run_id,
        "subreddit": args.subreddit,
        "mode": args.mode,
        "started_at": started,
        "finished_at": utc_now(),
        "posts_seen": len(posts),
        "threads_requested": len(selected),
        "threads_fetched": len(fetched_ids),
        "thread_errors": thread_errors,
        "comments_seen": len(all_comments),
        "raw_object_key": args.r2_key,
        "listing_requests": len([x for x in acquisition if x["kind"] == "listing"),
        "thread_requests": len([x for x in acquisition if x["kind"] == "thread"),
        "acquisition_hosts": sorted({x.get("via") for x in acquisition if x.get("via")}),
        "top_candidates": top_preview,
    }
    pathlib.Path(args.manifest_out).write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({k: v for k, v in manifest.items() if k != "top_candidates"}, indent=2))

    if not posts:
        raise SystemExit("reddit_deep_sweep_no_posts")


if __name__ == "__main__":
    main()
