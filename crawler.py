#!/usr/bin/env python3

import argparse
import hashlib
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qsl, urlparse

import requests
from bs4 import BeautifulSoup

DEFAULT_UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36 runner-3/1.1"
)

HARD_BLOCK_STATUSES = {401, 403, 407, 429}

RAW_CHALLENGE_MARKERS = [
    "cf-chl-",
    "/cdn-cgi/challenge-platform/",
    "challenges.cloudflare.com",
]

VISIBLE_CHALLENGE_MARKERS = [
    "cloudflare ray id",
    "checking your browser",
    "verify you are human",
    "attention required! | cloudflare",
    "temporarily blocked",
]

FORBIDDEN_JOB_KEYS = {
    "authorization",
    "cookie",
    "cookies",
    "password",
    "passwd",
    "secret",
    "secrets",
    "token",
    "access_token",
    "refresh_token",
    "api_key",
    "apikey",
    "client_secret",
    "private_key",
    "service_account",
    "credentials",
    "credential",
    "session",
    "sessionid",
}

FORBIDDEN_HEADER_NAMES = {
    "authorization",
    "cookie",
    "proxy-authorization",
    "x-api-key",
    "x-auth-token",
}

FORBIDDEN_QUERY_KEYS = {
    "access_token",
    "refresh_token",
    "auth_token",
    "api_key",
    "apikey",
    "client_secret",
    "password",
    "passwd",
    "session",
    "sessionid",
    "jwt",
}


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def normalized_key(value):
    return re.sub(r"[^a-z0-9]+", "_", str(value).strip().lower()).strip("_")


def validate_public_url(url):
    if not isinstance(url, str):
        raise ValueError("every job URL must be a string")
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("only http/https URLs are supported")
    if not parsed.netloc:
        raise ValueError("URL must contain a hostname")
    if parsed.username or parsed.password:
        raise ValueError("URL userinfo credentials are forbidden in this public repository")
    for key, _ in parse_qsl(parsed.query, keep_blank_values=True):
        if normalized_key(key) in FORBIDDEN_QUERY_KEYS:
            raise ValueError(f"sensitive query parameter is forbidden: {key}")


def scan_for_forbidden_keys(value, path="job"):
    if isinstance(value, dict):
        for key, child in value.items():
            nk = normalized_key(key)
            if nk in FORBIDDEN_JOB_KEYS:
                raise ValueError(f"sensitive field is forbidden in public job JSON: {path}.{key}")
            scan_for_forbidden_keys(child, f"{path}.{key}")
    elif isinstance(value, list):
        for i, child in enumerate(value):
            scan_for_forbidden_keys(child, f"{path}[{i}]")


def validate_job(job):
    if not isinstance(job, dict):
        raise ValueError("job JSON must be an object")

    scan_for_forbidden_keys(job)

    source_visibility = str(job.get("source_visibility", "")).strip().lower()
    if source_visibility != "public":
        raise ValueError(
            "runner-3 accepts only public Internet sources; set source_visibility to 'public'"
        )

    artifact_policy = str(job.get("artifact_policy", "none")).strip().lower()
    if artifact_policy not in {"none", "text", "raw"}:
        raise ValueError("artifact_policy must be one of: none, text, raw")

    urls = job.get("urls") or []
    if not isinstance(urls, list) or not urls:
        raise ValueError("job.urls must be a non-empty array")
    for url in urls:
        validate_public_url(url)

    custom_headers = job.get("headers") or {}
    if not isinstance(custom_headers, dict):
        raise ValueError("job.headers must be an object")
    for key in custom_headers:
        if normalized_key(key) in FORBIDDEN_HEADER_NAMES:
            raise ValueError(f"sensitive request header is forbidden: {key}")

    mode = str(job.get("mode", "auto")).lower()
    if mode not in {"http", "browser", "auto"}:
        raise ValueError("job.mode must be http, browser, or auto")

    timeout = int(job.get("timeout_seconds", 30))
    wait_ms = int(job.get("wait_after_load_ms", 1200))
    if not 1 <= timeout <= 120:
        raise ValueError("timeout_seconds must be between 1 and 120")
    if not 0 <= wait_ms <= 30000:
        raise ValueError("wait_after_load_ms must be between 0 and 30000")

    return {
        "source_visibility": source_visibility,
        "artifact_policy": artifact_policy,
        "mode": mode,
        "timeout": timeout,
        "wait_ms": wait_ms,
        "urls": urls,
        "custom_headers": custom_headers,
    }


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
    """Detect real access challenges without matching unrelated page content."""
    if status in HARD_BLOCK_STATUSES:
        return True

    visible = (text or "")[:8000].lower()
    visible_head = visible[:1200]

    if any(marker in visible for marker in VISIBLE_CHALLENGE_MARKERS):
        return True
    if visible_head.startswith("access denied") or "\naccess denied\n" in visible_head:
        return True

    text_len = len(text or "")

    # Successful pages with substantial visible content are not challenge
    # interstitials merely because a script/asset mentions Cloudflare tokens.
    if status is not None and 200 <= status < 300 and text_len >= 3000:
        return False

    raw_head = (html or "")[:60000].lower()
    if any(marker in raw_head for marker in RAW_CHALLENGE_MARKERS):
        return True

    # Generic CAPTCHA words are only meaningful on a short interstitial.
    if text_len < 3000 and "captcha" in visible_head:
        return True

    return False


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
        if response:
            try:
                content_type = response.all_headers().get("content-type", "")
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
            if mode == "http" or (
                not blocked and not too_thin and (result.get("status") or 0) < 400
            ):
                result["blocked_or_challenge"] = blocked
                result["fallback_used"] = False
                return result, errors
        except Exception as exc:
            errors.append(f"http: {type(exc).__name__}: {exc}")

    if mode in ("browser", "auto"):
        try:
            browser_result = browser_fetch(url, timeout, wait_ms, headers, user_agent)
            browser_result["blocked_or_challenge"] = looks_blocked(
                browser_result.get("status"),
                browser_result.get("html"),
                browser_result.get("text"),
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


def load_and_validate(job_file):
    job_path = Path(job_file)
    job = json.loads(job_path.read_text(encoding="utf-8"))
    policy = validate_job(job)
    return job_path, job, policy


def main():
    parser = argparse.ArgumentParser(description="Generic public-source targeted URL crawler")
    parser.add_argument("job_file")
    parser.add_argument("--output", default="crawl_output")
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()

    try:
        job_path, job, policy = load_and_validate(args.job_file)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(f"SECURITY_POLICY_ERROR: {exc}", file=sys.stderr)
        raise SystemExit(2)

    if args.validate_only:
        print(
            json.dumps(
                {
                    "job": job.get("name", job_path.stem),
                    "source_visibility": policy["source_visibility"],
                    "artifact_policy": policy["artifact_policy"],
                    "mode": policy["mode"],
                    "url_count": len(policy["urls"]),
                    "validated": True,
                },
                ensure_ascii=False,
            )
        )
        return

    mode = policy["mode"]
    timeout = policy["timeout"]
    wait_ms = policy["wait_ms"]
    urls = policy["urls"]
    artifact_policy = policy["artifact_policy"]
    user_agent = str(job.get("user_agent", DEFAULT_UA))

    headers = {
        "User-Agent": user_agent,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }
    headers.update({str(k): str(v) for k, v in policy["custom_headers"].items()})

    out_root = Path(args.output)
    out_root.mkdir(parents=True, exist_ok=True)

    manifest = {
        "job_name": job.get("name", job_path.stem),
        "job_file": str(job_path),
        "source_visibility": "public",
        "artifact_policy": artifact_policy,
        "response_headers_persisted": False,
        "mode": mode,
        "started_at": now_iso(),
        "url_count": len(urls),
        "results": [],
    }

    for index, url in enumerate(urls, start=1):
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
            (item_dir / "meta.json").write_text(
                json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8"
            )
            manifest["results"].append(meta)
            continue

        html = result.pop("html", "")
        text = result.pop("text", "")
        result.update(
            {
                "ok": bool(
                    result.get("status")
                    and result.get("status") < 400
                    and not result.get("blocked_or_challenge")
                ),
                "fetched_at": now_iso(),
                "html_bytes": len(html.encode("utf-8", errors="ignore")),
                "text_chars": len(text),
                "errors": errors,
                "output_dir": item_dir.name,
            }
        )

        if artifact_policy == "raw":
            (item_dir / "page.html").write_text(
                html, encoding="utf-8", errors="ignore"
            )
            (item_dir / "page.txt").write_text(
                text, encoding="utf-8", errors="ignore"
            )
        elif artifact_policy == "text":
            (item_dir / "page.txt").write_text(
                text, encoding="utf-8", errors="ignore"
            )

        (item_dir / "meta.json").write_text(
            json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        manifest["results"].append(result)

    manifest["finished_at"] = now_iso()
    manifest["ok_count"] = sum(1 for r in manifest["results"] if r.get("ok"))
    manifest["blocked_count"] = sum(
        1 for r in manifest["results"] if r.get("blocked_or_challenge")
    )
    manifest["failed_count"] = len(manifest["results"]) - manifest["ok_count"]

    (out_root / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    print(
        json.dumps(
            {
                "job": manifest["job_name"],
                "urls": manifest["url_count"],
                "ok": manifest["ok_count"],
                "blocked": manifest["blocked_count"],
                "failed": manifest["failed_count"],
                "artifact_policy": artifact_policy,
                "output": str(out_root),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
