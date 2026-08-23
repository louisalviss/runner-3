#!/usr/bin/env python3

import argparse
import ipaddress
import json
import re
import socket
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from cloakbrowser import launch

SENSITIVE_QUERY_KEYS = {
    "access_token", "refresh_token", "auth_token", "api_key", "apikey",
    "client_secret", "password", "passwd", "session", "sessionid", "jwt",
    "token", "secret", "key",
}
BLOCKED_HOSTS = {"localhost", "localhost.localdomain", "metadata.google.internal"}
BLOCK_PAGE_MARKERS = (
    "blocked by network security",
    "you've been blocked by network security",
    "access denied",
    "request blocked",
)
MAX_URLS = 20


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def normalized_key(value):
    return re.sub(r"[^a-z0-9]+", "_", str(value).strip().lower()).strip("_")


def validate_url(url, allow_sensitive_query=False):
    if not isinstance(url, str):
        raise ValueError("every URL must be a string")
    p = urlparse(url)
    if p.scheme != "https":
        raise ValueError("Cloak fallback accepts HTTPS URLs only")
    if not p.hostname or p.username or p.password:
        raise ValueError("URL host is required and URL credentials are forbidden")
    host = p.hostname.lower().rstrip(".")
    if host in BLOCKED_HOSTS or host.endswith(".localhost"):
        raise ValueError(f"blocked host: {host}")
    if not allow_sensitive_query:
        for key, _ in parse_qsl(p.query, keep_blank_values=True):
            if normalized_key(key) in SENSITIVE_QUERY_KEYS:
                raise ValueError(f"sensitive query parameter is forbidden: {key}")
    try:
        literal = ipaddress.ip_address(host)
    except ValueError:
        literal = None
    if literal is not None and not literal.is_global:
        raise ValueError(f"non-public IP is forbidden: {host}")
    return p


def sanitize_url(url):
    p = urlparse(url)
    safe_query = [
        (key, value)
        for key, value in parse_qsl(p.query, keep_blank_values=True)
        if normalized_key(key) not in SENSITIVE_QUERY_KEYS
    ]
    return urlunparse(p._replace(query=urlencode(safe_query, doseq=True)))


def assert_public_dns(host):
    infos = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
    ips = sorted({item[4][0] for item in infos})
    if not ips:
        raise ValueError(f"DNS returned no address for {host}")
    for raw in ips:
        ip = ipaddress.ip_address(raw.split("%", 1)[0])
        if not ip.is_global:
            raise ValueError(f"DNS resolved {host} to non-public address {ip}")
    return ips


def load_job(path):
    job = json.loads(Path(path).read_text(encoding="utf-8"))
    if str(job.get("source_visibility", "")).lower() != "public":
        raise ValueError("source_visibility must be public")
    if str(job.get("mode", "read-only")).lower() != "read-only":
        raise ValueError("mode must be read-only")
    urls = job.get("urls")
    if not isinstance(urls, list) or not urls:
        raise ValueError("urls must be a non-empty array")
    if len(urls) > MAX_URLS:
        raise ValueError(f"at most {MAX_URLS} URLs per Cloak fallback job")
    timeout = int(job.get("timeout_seconds", 45))
    if not 10 <= timeout <= 90:
        raise ValueError("timeout_seconds must be between 10 and 90")
    settle_ms = int(job.get("settle_ms", 2500))
    if not 0 <= settle_ms <= 10000:
        raise ValueError("settle_ms must be between 0 and 10000")
    for url in urls:
        validate_url(url)
    return {
        "name": str(job.get("name", "cloak-fallback")),
        "urls": urls,
        "timeout": timeout,
        "settle_ms": settle_ms,
    }


def safe_dir(index, url):
    p = urlparse(url)
    host = re.sub(r"[^a-zA-Z0-9._-]+", "_", p.hostname or "host")[:80]
    return f"{index:03d}_{host}"


def detect_block(status, text):
    if status is not None and status >= 400:
        return f"http_{status}"
    lowered = text.lower()
    for marker in BLOCK_PAGE_MARKERS:
        if marker in lowered:
            return marker.replace(" ", "_")
    return None


def main():
    ap = argparse.ArgumentParser(description="Read-only CloakBrowser fallback for public HTTPS pages")
    ap.add_argument("job_file")
    ap.add_argument("--output", default="cloak_output")
    ap.add_argument("--validate-only", action="store_true")
    ap.add_argument("--browser-version", default="146.0.7680.177.5")
    args = ap.parse_args()

    cfg = load_job(args.job_file)
    if args.validate_only:
        for url in cfg["urls"]:
            p = validate_url(url)
            assert_public_dns(p.hostname)
        print(json.dumps({"valid": True, "urls": len(cfg["urls"]), "mode": "read-only"}))
        return 0

    outroot = Path(args.output)
    outroot.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    manifest = {
        "engine": "cloakbrowser-read-only",
        "job_name": cfg["name"],
        "job_file": args.job_file,
        "source_visibility": "public",
        "mode": "read-only",
        "browser_version": args.browser_version,
        "started_at": now_iso(),
        "results": [],
    }

    browser = launch(
        browser_version=args.browser_version,
        headless=False,
        humanize=True,
    )
    try:
        for i, url in enumerate(cfg["urls"], 1):
            rec = {"requested_url": url, "started_at": now_iso()}
            t0 = time.perf_counter()
            page = None
            try:
                parsed = validate_url(url)
                rec["resolved_ips"] = assert_public_dns(parsed.hostname)
                page = browser.new_page(viewport={"width": 1365, "height": 768})
                response = page.goto(url, wait_until="domcontentloaded", timeout=cfg["timeout"] * 1000)
                if cfg["settle_ms"]:
                    page.wait_for_timeout(cfg["settle_ms"])
                final = page.url
                final_parsed = validate_url(final, allow_sensitive_query=True)
                rec["final_resolved_ips"] = assert_public_dns(final_parsed.hostname)
                text = page.locator("body").inner_text(timeout=10000)
                status = response.status if response else None
                blocked_reason = detect_block(status, text)
                signals = page.evaluate("""() => ({
                    webdriver: navigator.webdriver,
                    userAgent: navigator.userAgent,
                    platform: navigator.platform,
                    languages: navigator.languages,
                    plugins: navigator.plugins.length,
                    hasChrome: !!window.chrome
                })""")
                d = outroot / safe_dir(i, url)
                d.mkdir(parents=True, exist_ok=True)
                (d / "page.txt").write_text(text, encoding="utf-8")
                rec.update({
                    "ok": blocked_reason is None and status is not None and 200 <= status < 400,
                    "status": status,
                    "final_url": sanitize_url(final),
                    "title": page.title(),
                    "text_chars": len(text),
                    "signals": signals,
                    "output_dir": d.name,
                })
                if blocked_reason:
                    rec["blocked_reason"] = blocked_reason
            except Exception as exc:
                rec.update({"ok": False, "error": f"{type(exc).__name__}: {exc}"})
            finally:
                if page is not None:
                    try:
                        page.close()
                    except Exception:
                        pass
            rec["elapsed_seconds"] = round(time.perf_counter() - t0, 3)
            manifest["results"].append(rec)
            print(json.dumps({
                "url": url,
                "ok": rec.get("ok"),
                "status": rec.get("status"),
                "blocked_reason": rec.get("blocked_reason"),
                "seconds": rec["elapsed_seconds"],
                "text_chars": rec.get("text_chars"),
            }, ensure_ascii=False), flush=True)
    finally:
        browser.close()

    manifest["finished_at"] = now_iso()
    manifest["wall_seconds"] = round(time.perf_counter() - started, 3)
    manifest["ok_count"] = sum(1 for x in manifest["results"] if x.get("ok"))
    manifest["failed_count"] = len(manifest["results"]) - manifest["ok_count"]
    (outroot / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "ok": manifest["ok_count"],
        "failed": manifest["failed_count"],
        "wall_seconds": manifest["wall_seconds"],
    }))
    return 0 if manifest["failed_count"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
