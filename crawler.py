#!/usr/bin/env python3

import argparse
import hashlib
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

DEFAULT_UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36 runner-3/1.0"
)

BLOCK_MARKERS = [
    "cf-chl-",
    "cloudflare ray id",
    "checking your browser",
    "verify you are human",
    "captcha",
    "access denied",
    "attention required",
    "temporarily blocked",
]


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def safe_name(url: str, index: int) -> str:
    parsed = urlparse(url)
    host = re.sub(r"[^a-zA-Z0-9._-]+", "_", parsed.netloc)[:60] or "url"
    path = re.sub(r"[^a-zA-Z0-9._-]+", "_", parsed.path.strip("/"))[:80] or "root"
    digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:10]
    return f"{index:03d}_{host}_{path}_{digest}"


def extract_text(html: str):
    soup = BeautifulSoup(html or "", "html.parser")
    title = soup.title.get_text(" ", strip=True) if soup.title else ""
    for tag in soup(["script", "style", "noscript", "svg", "template"]):
        tag.decompose()
    text = "\n".join(
        line.strip() for line in soup.get_text("\n").splitlines() if line.strip()
    )
    return title, text


def looks_blocked(status, html, text):
    sample = ((html or "") + "\n" + (text or ""))[:200000].lower()
    if status in (401, 403, 407, 429, 503):
        return True
    return any(marker in sample for marker in BLOCK_MARKERS)


def http_fetch(url, timeout, headers):
    started = time.time()
    r = requests.get(
        url,
        timeout=timeout,
        headers=headers,
        allow_redirects=True,
    )
    html = r.text
    title, text = extract_text(html)
    return {
        "engine": "http",
        "requested_url": url,
        "final_url": r.url,
        "status": r.status_code,
        "content_type": r.headers.get("content-type", ""),
        "headers": dict(r.headers),
        "html": html,
        "title": title,
        "text": text,
        "elapsed_seconds": round(time.time() - started, 3),
    }


def browser_fetch(url, timeout, wait_ms, headers, user_agent):
    from playwright.sync_api import sync_playwright

    started = time.time()
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(user_agent=user_agent)
        if headers:
            context.set_extra_http_headers(headers)
        page = context.new_page()
        response = page.goto(url, wait_until="domcontentloaded", timeout=timeout * 1000)
        if wait_ms > 0:
            page.wait_for_timeout(wait_ms)
        html = page.content()
        final_url = page.url
        status = response.status if response else None
        content_type = ""
        response_headers = {}
        if response:
            try:
                response_headers = response.all_headers()
                content_type = response_headers.get("content-type", "")
            except Exception:
                pass
        title, text = extract_text(html)
        context.close()
        browser.close()
    return {
        "engine": "browser",
        "requested_url": url,
        "final_url": final_url,
        "status": status,
        "content_type": content_type,
        "headers": response_headers,
        "html": html,
        "title": title,
        "text": text,
        "elapsed_seconds": round(time.time() - started, 3),
    }


def crawl_one(url, mode, timeout, wait_ms, headers, user_agent):
    errors = []
    result = None

    if mode in ("http", "auto"):
        try:
            result = http_fetch(url, timeout, headers)
            blocked = looks_blocked(result.get("status"), result.get("html"), result.get("text"))
            too_thin = len(result.get("text") or "") < 300
            if mode == "http" or (not blocked and not too_thin and (result.get("status") or 0) < 400):
                result["blocked_or_challenge"] = blocked
                result["fallback_used"] = False
                return result, errors
        except Exception as exc:
            errors.append(f"http: {type(exc).__name__}: {exc}")

    if mode in ("browser", "auto"):
        try:
            browser_result = browser_fetch(url, timeout, wait_ms, headers, user_agent)
            browser_result["blocked_or_challenge"] = looks_blocked(
                browser_result.get("status"), browser_result.get("html"), browser_result.get("text")
            )
            browser_result["fallback_used"] = mode == "auto"
            return browser_result, errors
        except Exception as exc:
            errors.append(f"browser: {type(exc).__name__}: {exc}")

    if result is not None:
        result["blocked_or_challenge"] = looks_blocked(
            result.get("status"), result.get("html"), result.get("text")
        )
        result["fallback_used"] = False
        return result, errors

    return None, errors


def main():
    parser = argparse.ArgumentParser(description="Generic targeted URL crawler")
    parser.add_argument("job_file")
    parser.add_argument("--output", default="crawl_output")
    args = parser.parse_args()

    job_path = Path(args.job_file)
    job = json.loads(job_path.read_text(encoding="utf-8"))

    urls = job.get("urls") or []
    if not isinstance(urls, list) or not urls:
        raise SystemExit("job.urls must be a non-empty array")

    mode = str(job.get("mode", "auto")).lower()
    if mode not in {"http", "browser", "auto"}:
        raise SystemExit("job.mode must be http, browser, or auto")

    timeout = int(job.get("timeout_seconds", 30))
    wait_ms = int(job.get("wait_after_load_ms", 1200))
    user_agent = str(job.get("user_agent", DEFAULT_UA))
    custom_headers = job.get("headers") or {}
    if not isinstance(custom_headers, dict):
        raise SystemExit("job.headers must be an object")

    headers = {"User-Agent": user_agent, "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"}
    headers.update({str(k): str(v) for k, v in custom_headers.items()})

    out_root = Path(args.output)
    out_root.mkdir(parents=True, exist_ok=True)

    manifest = {
        "job_name": job.get("name", job_path.stem),
        "job_file": str(job_path),
        "mode": mode,
        "started_at": now_iso(),
        "url_count": len(urls),
        "results": [],
    }

    for index, url in enumerate(urls, start=1):
        if not isinstance(url, str) or not url.startswith(("http://", "https://")):
            manifest["results"].append({
                "requested_url": url,
                "ok": False,
                "errors": ["invalid URL: only http/https URLs are supported"],
            })
            continue

        item_dir = out_root / safe_name(url, index)
        item_dir.mkdir(parents=True, exist_ok=True)

        result, errors = crawl_one(url, mode, timeout, wait_ms, headers, user_agent)
        if result is None:
            meta = {
                "requested_url": url,
                "ok": False,
                "fetched_at": now_iso(),
                "errors": errors,
            }
            (item_dir / "meta.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
            manifest["results"].append(meta)
            continue

        html = result.pop("html", "")
        text = result.pop("text", "")
        result.update({
            "ok": bool(result.get("status") and result.get("status") < 400 and not result.get("blocked_or_challenge")),
            "fetched_at": now_iso(),
            "html_bytes": len(html.encode("utf-8", errors="ignore")),
            "text_chars": len(text),
            "errors": errors,
            "output_dir": item_dir.name,
        })

        (item_dir / "page.html").write_text(html, encoding="utf-8", errors="ignore")
        (item_dir / "page.txt").write_text(text, encoding="utf-8", errors="ignore")
        (item_dir / "meta.json").write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
        manifest["results"].append(result)

    manifest["finished_at"] = now_iso()
    manifest["ok_count"] = sum(1 for r in manifest["results"] if r.get("ok"))
    manifest["blocked_count"] = sum(1 for r in manifest["results"] if r.get("blocked_or_challenge"))
    manifest["failed_count"] = len(manifest["results"]) - manifest["ok_count"]

    (out_root / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    print(json.dumps({
        "job": manifest["job_name"],
        "urls": manifest["url_count"],
        "ok": manifest["ok_count"],
        "blocked": manifest["blocked_count"],
        "failed": manifest["failed_count"],
        "output": str(out_root),
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
