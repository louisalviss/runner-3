#!/usr/bin/env python3

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse

from bs4 import BeautifulSoup

import forum_signal_rank as rank


ORIGINAL_EXTRACT_POSTS = rank.base.extract_posts
ORIGINAL_FETCH = rank.base.fetch
COMMENT_WORD_RE = re.compile(r"comment|reply|discussion|response|phan.?hoi|binh.?luan", re.I)
TINHTE_TZ = timezone(timedelta(hours=7))
TINHTE_DATE_RE = re.compile(r"\b(\d{1,2})/(\d{1,2})/(\d{4})(?:\s+(\d{1,2}):(\d{2}))?\b")
TINHTE_REL_RE = re.compile(r"\b(\d+)\s*(phút|giờ|ngày)\s*(?:trước)?\b", re.I)


def clean_text(value):
    if value is None:
        return ""
    if isinstance(value, str):
        text = BeautifulSoup(value, "html.parser").get_text("\n", strip=True)
    else:
        text = str(value)
    return "\n".join(x.strip() for x in text.splitlines() if x.strip())


def is_tinhte_url(url):
    host = (urlparse(url).hostname or "").lower()
    return host == "tinhte.vn" or host.endswith(".tinhte.vn")


def fingerprint_row(row):
    post_id = clean_text(row.get("post_id", ""))
    thread_key = clean_text(row.get("thread_key", ""))
    if post_id:
        raw = f"{thread_key}|id|{post_id}"
    else:
        text = rank.base.normalize_text(row.get("text", ""))
        author = rank.base.normalize_text(row.get("author", ""))
        timestamp = clean_text(row.get("timestamp", ""))
        raw = f"{thread_key}|text|{author}|{timestamp}|{text}"
    return hashlib.sha1(raw.encode("utf-8", errors="ignore")).hexdigest()


def first_value(obj, names):
    if not isinstance(obj, dict):
        return None
    lowered = {str(k).lower(): k for k in obj.keys()}
    for name in names:
        key = lowered.get(name.lower())
        if key is not None:
            return obj.get(key)
    return None


def author_from_value(value):
    if isinstance(value, dict):
        for key in ("name", "username", "displayName", "fullName", "nick", "nickname"):
            v = first_value(value, [key])
            if v:
                return clean_text(v)
        return ""
    return clean_text(value)


def walk_comment_json(value, path=()):
    rows = []
    if isinstance(value, dict):
        path_text = "/".join(str(p).lower() for p in path)
        node_type = clean_text(first_value(value, ["@type", "type", "__typename"]) or "").lower()
        is_comment_path = bool(COMMENT_WORD_RE.search(path_text)) or node_type in {
            "comment", "reply", "postcomment", "discussioncomment"
        }
        text_value = first_value(value, ["content", "body", "message", "text", "html", "comment"])
        comment_id = first_value(value, ["commentId", "comment_id", "replyId", "reply_id", "postId", "post_id", "id"])
        author_value = first_value(value, ["author", "user", "username", "member", "creator", "createdBy", "created_by"])
        timestamp = first_value(value, ["createdAt", "created_at", "publishedAt", "published_at", "date", "time", "timestamp"])
        text = clean_text(text_value)
        comment_shape = (
            20 <= len(text) <= 12000
            and comment_id is not None
            and author_value is not None
            and timestamp is not None
        )
        if (is_comment_path or comment_shape) and 20 <= len(text) <= 12000 and (comment_id is not None or author_value is not None):
            rows.append({
                "post_id": clean_text(comment_id),
                "author": author_from_value(author_value),
                "timestamp": clean_text(timestamp),
                "text": text,
                "text_chars": len(text),
                "extraction": "structured_post",
            })
        for key, child in value.items():
            rows.extend(walk_comment_json(child, path + (key,)))
    elif isinstance(value, list):
        for idx, child in enumerate(value):
            rows.extend(walk_comment_json(child, path + (idx,)))
    return rows


def extract_tinhte_json_comments(soup):
    rows = []
    for script in soup.find_all("script"):
        raw = script.string or script.get_text("", strip=False)
        if not raw or len(raw) < 20:
            continue
        stype = (script.get("type") or "").lower()
        sid = (script.get("id") or "").lower()
        looks_json = "json" in stype or sid in {"__next_data__", "__nuxt_data__"}
        if not looks_json:
            continue
        try:
            payload = json.loads(raw)
        except Exception:
            continue
        rows.extend(walk_comment_json(payload, (sid or "script",)))
    return rows


def parse_tinhte_timestamp(value):
    raw = " ".join(str(value or "").split())
    if not raw:
        return ""
    m = TINHTE_DATE_RE.search(raw)
    if m:
        day, month, year = map(int, m.group(1, 2, 3))
        hour = int(m.group(4) or 0)
        minute = int(m.group(5) or 0)
        try:
            return datetime(year, month, day, hour, minute, tzinfo=TINHTE_TZ).isoformat()
        except ValueError:
            return ""
    lowered = raw.lower()
    now = datetime.now(TINHTE_TZ)
    if "vừa xong" in lowered or "vừa mới" in lowered:
        return now.isoformat()
    if "hôm qua" in lowered:
        return (now - timedelta(days=1)).isoformat()
    m = TINHTE_REL_RE.search(lowered)
    if m:
        amount = int(m.group(1))
        unit = m.group(2).lower()
        if unit == "phút":
            dt = now - timedelta(minutes=amount)
        elif unit == "giờ":
            dt = now - timedelta(hours=amount)
        else:
            dt = now - timedelta(days=amount)
        return dt.isoformat()
    return ""


def strip_tinhte_author_meta(value):
    text = " ".join(str(value or "").split())
    text = TINHTE_DATE_RE.sub("", text)
    text = TINHTE_REL_RE.sub("", text)
    text = re.sub(r"\b(?:hôm qua|vừa xong|vừa mới)\b", "", text, flags=re.I)
    text = re.sub(r"\bĐề xuất ra trang chủ\b", "", text, flags=re.I)
    return " ".join(text.split()).strip(" -·|")


def extract_tinhte_dom_comments(soup):
    selectors = [
        "div.post-item__container",
        "[class*='post-item__container']",
        "[data-comment-id]",
        "[data-reply-id]",
        "[data-post-id]",
        "[id^='comment-']",
        "[id^='reply-']",
        ".comment-item",
        ".commentItem",
        "[class*='comment-item']",
        "[class*='reply-item']",
        "article[class*='comment']",
        "li[class*='comment']",
    ]
    nodes = []
    seen_nodes = set()
    for selector in selectors:
        try:
            matches = soup.select(selector)
        except Exception:
            continue
        for node in matches:
            marker = id(node)
            if marker in seen_nodes:
                continue
            seen_nodes.add(marker)
            nodes.append(node)

    rows = []
    seen_text = set()
    for node in nodes:
        body = node.select_one(
            ".post-body, [class*='post-body'], [class*='postBody'], "
            ".comment-content, .commentContent, [class*='comment-content'], "
            "[class*='commentContent'], [class*='reply-content'], [class*='replyContent']"
        )
        if body is None:
            continue
        clone = BeautifulSoup(str(body), "html.parser")
        for bad in clone.select("script, style, button, nav, footer, form, svg, blockquote, .quote, .post-quote"):
            bad.decompose()
        text = clean_text(clone.get_text("\n", strip=True))
        if not (20 <= len(text) <= 12000):
            continue
        fp = hashlib.sha1(rank.base.normalize_text(text).encode("utf-8", errors="ignore")).hexdigest()
        if fp in seen_text:
            continue
        seen_text.add(fp)

        post_id = (
            node.get("data-comment-id")
            or node.get("data-reply-id")
            or node.get("data-post-id")
            or node.get("data-id")
            or node.get("id")
            or ""
        )
        author_node = node.select_one(
            ".author-info, .author, [class*='author-info'], [class*='username'], "
            "[class*='user-name'], [class*='userName'], a[href*='/members/'], a[href*='/user/']"
        )
        author_raw = clean_text(author_node.get_text(" ", strip=True)) if author_node else ""
        name_node = author_node.select_one("a[href]") if author_node else None
        author = clean_text(name_node.get_text(" ", strip=True)) if name_node else strip_tinhte_author_meta(author_raw)

        time_node = node.select_one("time, [class*='time'], [class*='date']")
        timestamp = ""
        if time_node:
            timestamp = time_node.get("datetime") or time_node.get("title") or clean_text(time_node.get_text(" ", strip=True))
        timestamp = parse_tinhte_timestamp(timestamp or author_raw)

        rows.append({
            "post_id": clean_text(post_id),
            "author": author,
            "timestamp": clean_text(timestamp),
            "text": text,
            "text_chars": len(text),
            "extraction": "structured_post",
        })
    return rows


def enhanced_extract_posts(html, url, max_posts):
    if not is_tinhte_url(url):
        return ORIGINAL_EXTRACT_POSTS(html, url, max_posts)

    soup = BeautifulSoup(html or "", "html.parser")
    title_node = soup.select_one("h1, [class*='thread-title'], [class*='threadTitle']")
    title = clean_text(title_node.get_text(" ", strip=True)) if title_node else ""
    if not title and soup.title:
        title = clean_text(soup.title.get_text(" ", strip=True))

    rows = extract_tinhte_dom_comments(soup)
    if not rows:
        rows = extract_tinhte_json_comments(soup)

    if rows:
        deduped = []
        seen = set()
        for row in rows:
            key = row.get("post_id") or hashlib.sha1(
                (
                    rank.base.normalize_text(row.get("author", ""))
                    + "|"
                    + rank.base.normalize_text(row.get("timestamp", ""))
                    + "|"
                    + rank.base.normalize_text(row.get("text", ""))
                ).encode("utf-8", errors="ignore")
            ).hexdigest()
            if key in seen:
                continue
            seen.add(key)
            deduped.append(row)
        return title, deduped[-max_posts:]

    return ORIGINAL_EXTRACT_POSTS(html, url, max_posts)


def enhanced_fetch(url, policy, headers, user_agent):
    if not is_tinhte_url(url):
        return ORIGINAL_FETCH(url, policy, headers, user_agent)

    rendered_policy = dict(policy)
    rendered_policy["mode"] = "browser"
    rendered_policy["wait_ms"] = max(int(policy.get("wait_ms", 0)), 3000)
    result, errors = ORIGINAL_FETCH(url, rendered_policy, headers, user_agent)

    if result is None or not result.get("ok"):
        http_policy = dict(policy)
        http_policy["mode"] = "http"
        fallback, fallback_errors = ORIGINAL_FETCH(url, http_policy, headers, user_agent)
        errors = list(errors or []) + [f"browser_fallback: {e}" for e in (fallback_errors or [])]
        if fallback is not None:
            return fallback, errors
    return result, errors


def load_state(path):
    if not path.exists():
        return {"version": 1, "threads": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or not isinstance(data.get("threads", {}), dict):
            raise ValueError("invalid state")
        data.setdefault("version", 1)
        data.setdefault("threads", {})
        return data
    except Exception:
        return {"version": 1, "threads": {}}


def save_state(path, state):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def run_ranker(job_file, output, validate_only=False):
    old_argv = sys.argv[:]
    rank.base.extract_posts = enhanced_extract_posts
    rank.base.fetch = enhanced_fetch
    try:
        argv = ["forum_signal_rank.py", job_file, "--output", str(output)]
        if validate_only:
            argv.append("--validate-only")
        sys.argv = argv
        rank.main()
    finally:
        sys.argv = old_argv
        rank.base.extract_posts = ORIGINAL_EXTRACT_POSTS
        rank.base.fetch = ORIGINAL_FETCH


def main():
    parser = argparse.ArgumentParser(description="Forum signal ranker with Tinhte rendered comments and persistent delta state")
    parser.add_argument("job_file")
    parser.add_argument("--output", default="crawl_output")
    parser.add_argument("--state-file", default=".forum-state/state.json")
    parser.add_argument("--state-history", type=int, default=160)
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()

    if not 20 <= args.state_history <= 1000:
        print("SECURITY_POLICY_ERROR: state-history must be 20..1000", file=sys.stderr)
        raise SystemExit(2)

    if args.validate_only:
        run_ranker(args.job_file, args.output, validate_only=True)
        print(json.dumps({
            "runner": "forum_signal_delta",
            "state_file": args.state_file,
            "state_history": args.state_history,
            "tinhte_rendered_fetch": True,
            "validated": True,
        }, ensure_ascii=False))
        return

    out_root = Path(args.output)
    out_root.mkdir(parents=True, exist_ok=True)
    run_ranker(args.job_file, out_root, validate_only=False)

    snapshot_path = out_root / "forum_signal.jsonl"
    snapshot_rows = []
    if snapshot_path.exists():
        for line in snapshot_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                snapshot_rows.append(json.loads(line))

    state_path = Path(args.state_file)
    state = load_state(state_path)
    previous_threads = len(state.get("threads", {}))
    new_rows = []
    seen_now = {}

    for row in snapshot_rows:
        thread_key = clean_text(row.get("thread_key", ""))
        fp = fingerprint_row(row)
        row["fingerprint"] = fp
        prior = set(state.get("threads", {}).get(thread_key, []))
        row["is_new"] = fp not in prior
        if row["is_new"]:
            new_rows.append(row)
        seen_now.setdefault(thread_key, []).append(fp)

    for thread_key, fresh_fps in seen_now.items():
        prior = list(state.get("threads", {}).get(thread_key, []))
        merged = []
        seen = set()
        for fp in prior + fresh_fps:
            if fp in seen:
                continue
            seen.add(fp)
            merged.append(fp)
        state.setdefault("threads", {})[thread_key] = merged[-args.state_history:]

    state["version"] = 1
    state["last_snapshot_rows"] = len(snapshot_rows)
    state["last_delta_rows"] = len(new_rows)
    save_state(state_path, state)

    snapshot_audit_path = out_root / "forum_signal_snapshot.jsonl"
    snapshot_path.replace(snapshot_audit_path)
    with snapshot_path.open("w", encoding="utf-8") as f:
        for row in new_rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    manifest_path = out_root / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {}
    manifest["runner"] = "forum_signal_delta"
    manifest["snapshot_rows"] = len(snapshot_rows)
    manifest["delta_rows"] = len(new_rows)
    manifest["state_threads_before"] = previous_threads
    manifest["state_threads_after"] = len(state.get("threads", {}))
    manifest["state_history_per_thread"] = args.state_history
    manifest["delta_output"] = "forum_signal.jsonl"
    manifest["snapshot_audit_output"] = "forum_signal_snapshot.jsonl"
    manifest["tinhte_rendered_fetch"] = True
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps({
        "job": manifest.get("job_name"),
        "runner": "forum_signal_delta",
        "snapshot_rows": len(snapshot_rows),
        "delta_rows": len(new_rows),
        "state_threads": len(state.get("threads", {})),
        "tinhte_rendered_fetch": True,
        "output": str(out_root),
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
