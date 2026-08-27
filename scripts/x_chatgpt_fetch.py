#!/usr/bin/env python3
"""Fetch one or more public X/Twitter posts for the Runner-3 ChatGPT bridge."""
from __future__ import annotations

import argparse
import datetime as dt
import html as html_lib
import json
import re
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

UA = "runner3-x-chatgpt-bridge/1.0 (+https://github.com/louisalviss/runner-3)"
STATUS_RE = re.compile(r"/(?:i/web/)?status/(\d+)", re.I)


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def parse_x_url(url: str) -> tuple[str, str, str]:
    raw = (url or "").strip()
    p = urlparse(raw)
    host = p.netloc.lower().split(":", 1)[0]
    if host.startswith("www."):
        host = host[4:]
    if host not in {"x.com", "twitter.com", "mobile.twitter.com"}:
        raise ValueError("Only x.com/twitter.com status URLs are accepted")
    m = STATUS_RE.search(p.path)
    if not m:
        raise ValueError("URL does not contain a numeric /status/<id>")
    tweet_id = m.group(1)
    parts = [part for part in p.path.split("/") if part]
    username = ""
    if parts and parts[0].lower() not in {"i", "status"}:
        username = parts[0].lstrip("@").strip()
    canonical = f"https://x.com/{username}/status/{tweet_id}" if username else f"https://x.com/i/status/{tweet_id}"
    return username, tweet_id, canonical


def clean_author(author: Any) -> Any:
    if not isinstance(author, dict):
        return author
    keys = ("id", "name", "screen_name", "username", "avatar_url", "url", "verified", "followers")
    return {k: author.get(k) for k in keys if k in author}


def normalize_status(obj: Any, depth: int = 0) -> Any:
    if not isinstance(obj, dict):
        return obj
    if depth > 2:
        return {k: obj.get(k) for k in ("id", "url", "text") if k in obj}
    out: dict[str, Any] = {}
    for key in (
        "type", "id", "url", "text", "created_at", "created_timestamp", "likes", "reposts",
        "retweets", "quotes", "replies", "views", "bookmarks", "lang", "possibly_sensitive", "source",
    ):
        if key in obj:
            out[key] = obj.get(key)
    if "author" in obj:
        out["author"] = clean_author(obj.get("author"))
    if isinstance(obj.get("media"), dict):
        out["media"] = obj["media"]
    if isinstance(obj.get("poll"), dict):
        out["poll"] = obj["poll"]
    if isinstance(obj.get("quote"), dict):
        out["quote"] = normalize_status(obj["quote"], depth + 1)
    if isinstance(obj.get("replying_to"), dict):
        out["replying_to"] = obj["replying_to"]
    return out


def unwrap_fxtwitter(data: Any) -> tuple[Any, list[Any] | None, Any]:
    if not isinstance(data, dict):
        raise ValueError("FxTwitter returned non-object JSON")
    status = data.get("tweet") if isinstance(data.get("tweet"), dict) else data.get("status")
    if not isinstance(status, dict) and ("text" in data or "id" in data):
        status = data
    if not isinstance(status, dict):
        raise ValueError(f"FxTwitter JSON has no tweet/status object (code={data.get('code')!r})")
    thread = data.get("thread") if isinstance(data.get("thread"), list) else None
    author = data.get("author") if isinstance(data.get("author"), dict) else status.get("author")
    return status, thread, author


def fetch_fxtwitter(session: requests.Session, username: str, tweet_id: str) -> dict[str, Any]:
    if not username:
        raise ValueError("FxTwitter resolver requires username in URL")
    endpoint = f"https://api.fxtwitter.com/{username}/status/{tweet_id}"
    r = session.get(endpoint, timeout=20)
    r.raise_for_status()
    data = r.json()
    status, thread, author = unwrap_fxtwitter(data)
    return {
        "provider": "fxtwitter",
        "providerUrl": endpoint,
        "status": normalize_status(status),
        "thread": [normalize_status(x) for x in thread] if thread else [],
        "author": clean_author(author),
        "providerCode": data.get("code") if isinstance(data, dict) else None,
    }


def fetch_oembed(session: requests.Session, canonical: str) -> dict[str, Any]:
    endpoint = "https://publish.twitter.com/oembed"
    r = session.get(endpoint, params={"url": canonical, "omit_script": "1", "dnt": "1"}, timeout=20)
    r.raise_for_status()
    data = r.json()
    fragment = str(data.get("html") or "")
    text = BeautifulSoup(fragment, "html.parser").get_text(" ", strip=True)
    if not text:
        raise ValueError("oEmbed returned no post text")
    return {
        "provider": "twitter-oembed",
        "providerUrl": r.url,
        "status": {
            "url": canonical,
            "text": html_lib.unescape(text),
            "author": {"name": data.get("author_name"), "url": data.get("author_url")},
        },
        "thread": [],
        "author": {"name": data.get("author_name"), "url": data.get("author_url")},
    }


def meta_value(soup: BeautifulSoup, *names: str) -> str:
    for name in names:
        tag = soup.find("meta", attrs={"property": name}) or soup.find("meta", attrs={"name": name})
        if tag and tag.get("content"):
            return html_lib.unescape(str(tag.get("content")).strip())
    return ""


def fetch_fixupx(session: requests.Session, username: str, tweet_id: str, canonical: str) -> dict[str, Any]:
    if not username:
        raise ValueError("FixupX resolver requires username in URL")
    endpoint = f"https://fixupx.com/{username}/status/{tweet_id}"
    r = session.get(endpoint, timeout=20, allow_redirects=True)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    text = meta_value(soup, "og:description", "twitter:description", "description")
    title = meta_value(soup, "og:title", "twitter:title")
    image = meta_value(soup, "og:image", "twitter:image")
    if not text:
        raise ValueError("FixupX page has no description metadata")
    status: dict[str, Any] = {"url": canonical, "text": text}
    if title:
        status["title"] = title
    if image:
        status["media"] = {"preview_image": image}
    return {"provider": "fixupx-meta", "providerUrl": endpoint, "status": status, "thread": [], "author": None}


def fetch_one(url: str) -> dict[str, Any]:
    username, tweet_id, canonical = parse_x_url(url)
    session = requests.Session()
    session.headers.update({"User-Agent": UA, "Accept": "application/json,text/html;q=0.9,*/*;q=0.8"})
    attempts: list[dict[str, str]] = []
    resolvers = (
        ("fxtwitter", lambda: fetch_fxtwitter(session, username, tweet_id)),
        ("twitter-oembed", lambda: fetch_oembed(session, canonical)),
        ("fixupx-meta", lambda: fetch_fixupx(session, username, tweet_id, canonical)),
    )
    for name, fn in resolvers:
        try:
            payload = fn()
            payload.update({"ok": True, "inputUrl": url, "canonicalUrl": canonical, "tweetId": tweet_id, "username": username})
            if attempts:
                payload["failedFallbacks"] = attempts
            return payload
        except Exception as exc:
            attempts.append({"provider": name, "error": f"{type(exc).__name__}: {exc}"[:600]})
    return {
        "ok": False,
        "inputUrl": url,
        "canonicalUrl": canonical,
        "tweetId": tweet_id,
        "username": username,
        "error": "All public X resolvers failed",
        "attempts": attempts,
    }


def load_request(path: Path) -> dict[str, Any]:
    obj = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(obj, dict):
        raise ValueError("request must be a JSON object")
    if not isinstance(obj.get("url"), str) or not obj["url"].strip():
        raise ValueError("request.url is required")
    return obj


def request_id(path: Path, req: dict[str, Any]) -> str:
    raw = str(req.get("id") or path.stem)
    clean = re.sub(r"[^A-Za-z0-9._-]+", "-", raw).strip("-.")
    return (clean or path.stem)[:120]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("requests", nargs="+", help="request JSON paths")
    ap.add_argument("--output-dir", required=True)
    args = ap.parse_args()
    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    results = []
    failures = 0
    for raw_path in args.requests:
        path = Path(raw_path)
        try:
            req = load_request(path)
            rid = request_id(path, req)
            result = fetch_one(req["url"])
            result.update({"requestId": rid, "requestPath": str(path), "requestedAt": req.get("requestedAt"), "fetchedAt": utc_now()})
        except Exception as exc:
            rid = re.sub(r"[^A-Za-z0-9._-]+", "-", path.stem)[:120] or "request"
            result = {"ok": False, "requestId": rid, "requestPath": str(path), "fetchedAt": utc_now(), "error": f"{type(exc).__name__}: {exc}"[:1000]}
        (out_dir / f"{rid}.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        results.append({"requestId": rid, "ok": bool(result.get("ok")), "provider": result.get("provider"), "output": f"{rid}.json"})
        if not result.get("ok"):
            failures += 1
    print(json.dumps({"processed": len(results), "failures": failures, "results": results}, ensure_ascii=False))
    return 0 if failures == 0 else 2


if __name__ == "__main__":
    sys.exit(main())
