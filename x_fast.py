#!/usr/bin/env python3

import argparse
import hashlib
import json
import re
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import parse_qsl, urlparse

UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)

BLOCK_TAGS = {
    "address", "article", "aside", "blockquote", "br", "div", "dl", "dt", "dd",
    "fieldset", "figcaption", "figure", "footer", "form", "h1", "h2", "h3", "h4",
    "h5", "h6", "header", "hr", "li", "main", "nav", "ol", "p", "pre", "section",
    "table", "tbody", "td", "tfoot", "th", "thead", "tr", "ul"
}
SKIP_TAGS = {"script", "style", "noscript", "svg", "template"}
SENSITIVE_QUERY_KEYS = {
    "access_token", "refresh_token", "auth_token", "api_key", "apikey", "client_secret",
    "password", "passwd", "session", "sessionid", "jwt"
}
ALLOWED_HOSTS = {"x.com", "www.x.com", "twitter.com", "www.twitter.com"}
X_ERROR_MARKERS = (
    "something went wrong, but don’t fret",
    "something went wrong, but don't fret",
    "some privacy related extensions may cause issues on x.com",
)


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def normalized_key(value):
    return re.sub(r"[^a-z0-9]+", "_", str(value).strip().lower()).strip("_")


def validate_url(url):
    if not isinstance(url, str):
        raise ValueError("every URL must be a string")
    p = urlparse(url)
    if p.scheme != "https":
        raise ValueError("X Fast accepts HTTPS URLs only")
    if p.netloc.lower() not in ALLOWED_HOSTS:
        raise ValueError(f"X Fast accepts only x.com/twitter.com URLs: {p.netloc}")
    if p.username or p.password:
        raise ValueError("URL credentials are forbidden")
    for key, _ in parse_qsl(p.query, keep_blank_values=True):
        if normalized_key(key) in SENSITIVE_QUERY_KEYS:
            raise ValueError(f"sensitive query parameter is forbidden: {key}")


def validate_job(job):
    if not isinstance(job, dict):
        raise ValueError("job JSON must be an object")
    if str(job.get("source_visibility", "")).lower() != "public":
        raise ValueError("source_visibility must be public")

    artifact_policy = str(job.get("artifact_policy", "text")).lower()
    if artifact_policy not in {"none", "text", "raw"}:
        raise ValueError("artifact_policy must be none, text, or raw")

    urls = job.get("urls")
    if not isinstance(urls, list) or not urls:
        raise ValueError("urls must be a non-empty array")
    if len(urls) > 500:
        raise ValueError("X Fast supports at most 500 URLs per job")
    for url in urls:
        validate_url(url)

    timeout = int(job.get("timeout_seconds", 12))
    workers = int(job.get("max_workers", min(12, len(urls))))
    if not 2 <= timeout <= 60:
        raise ValueError("timeout_seconds must be between 2 and 60")
    if not 1 <= workers <= 24:
        raise ValueError("max_workers must be between 1 and 24")

    return {
        "name": str(job.get("name", "x-fast")),
        "artifact_policy": artifact_policy,
        "urls": urls,
        "timeout": timeout,
        "workers": workers,
    }


class PageParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.skip_depth = 0
        self.title_depth = 0
        self.title_parts = []
        self.meta = {}
        self.canonical = ""

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        attrs = dict(attrs)
        if tag in SKIP_TAGS:
            self.skip_depth += 1
            return
        if self.skip_depth:
            return
        if tag == "title":
            self.title_depth += 1
        if tag in BLOCK_TAGS:
            self.parts.append("\n")
        if tag == "meta":
            key = attrs.get("property") or attrs.get("name")
            content = attrs.get("content")
            if key and content:
                self.meta[str(key).lower()] = str(content)
        if tag == "link":
            rel = str(attrs.get("rel", "")).lower()
            if "canonical" in rel and attrs.get("href"):
                self.canonical = str(attrs["href"])

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        self.handle_endtag(tag)

    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag in SKIP_TAGS:
            if self.skip_depth:
                self.skip_depth -= 1
            return
        if self.skip_depth:
            return
        if tag == "title" and self.title_depth:
            self.title_depth -= 1
        if tag in BLOCK_TAGS:
            self.parts.append("\n")

    def handle_data(self, data):
        if self.skip_depth:
            return
        if self.title_depth:
            self.title_parts.append(data)
        if data and data.strip():
            self.parts.append(data)

    def result(self):
        raw = "".join(self.parts)
        lines = []
        for line in raw.splitlines():
            line = re.sub(r"[ \t\r\f\v]+", " ", line).strip()
            if line:
                lines.append(line)
        title = re.sub(r"\s+", " ", " ".join(self.title_parts)).strip()
        return title, "\n".join(lines), self.meta, self.canonical


def status_identity(url):
    p = urlparse(url)
    m = re.search(r"/([^/]+)/status/(\d+)", p.path)
    if not m:
        return {"author_handle": None, "post_id": None}
    return {"author_handle": m.group(1), "post_id": m.group(2)}


def classify_surface(url, post_id):
    path = urlparse(url).path.rstrip("/")
    if post_id:
        return "status"
    if path == "/search":
        return "search"
    if re.fullmatch(r"/[A-Za-z0-9_]{1,30}", path or ""):
        return "profile"
    return "other"


def safe_name(url, index):
    p = urlparse(url)
    path = re.sub(r"[^a-zA-Z0-9._-]+", "_", p.path.strip("/"))[:100] or "root"
    digest = hashlib.sha256(url.encode()).hexdigest()[:10]
    return f"{index:03d}_{path}_{digest}"


def fetch_one(index, url, timeout, artifact_policy, output_root):
    started = time.time()
    dirname = safe_name(url, index)
    outdir = output_root / dirname
    outdir.mkdir(parents=True, exist_ok=True)
    body_path = outdir / "page.html.tmp"

    fmt = "%{http_code}\n%{url_effective}\n%{time_total}\n%{content_type}"
    cmd = [
        "curl", "--location", "--compressed", "--silent", "--show-error",
        "--connect-timeout", str(min(timeout, 10)), "--max-time", str(timeout),
        "--user-agent", UA,
        "--header", "Accept-Language: en-US,en;q=0.9",
        "--output", str(body_path), "--write-out", fmt, url,
    ]

    proc = subprocess.run(cmd, capture_output=True, text=True)
    curl_meta = (proc.stdout or "").splitlines()
    status = int(curl_meta[0]) if curl_meta and curl_meta[0].isdigit() else None
    final_url = curl_meta[1] if len(curl_meta) > 1 else url
    curl_seconds = float(curl_meta[2]) if len(curl_meta) > 2 else None
    content_type = curl_meta[3] if len(curl_meta) > 3 else ""

    body = body_path.read_bytes() if body_path.exists() else b""
    html = body.decode("utf-8", errors="replace")
    parser = PageParser()
    try:
        parser.feed(html)
        title, text, meta_tags, canonical = parser.result()
    except Exception as exc:
        title, text, meta_tags, canonical = "", "", {}, ""
        parse_error = str(exc)
    else:
        parse_error = None

    identity = status_identity(final_url or url)
    surface = classify_surface(final_url or url, identity["post_id"])
    description = (
        meta_tags.get("og:description")
        or meta_tags.get("twitter:description")
        or meta_tags.get("description")
        or ""
    )
    image = meta_tags.get("og:image") or meta_tags.get("twitter:image") or ""
    lower_text = text.lower()
    search_error_present = any(marker in lower_text for marker in X_ERROR_MARKERS)
    login_wall_present = "log in or sign up for x" in lower_text
    comment_scope = None
    if identity["post_id"]:
        comment_scope = "sample_only" if login_wall_present else "unknown"

    structured = {
        **identity,
        "surface": surface,
        "canonical_url": canonical or (final_url.split("?", 1)[0] if final_url else url.split("?", 1)[0]),
        "description": description,
        "image": image,
        "og_title": meta_tags.get("og:title", ""),
        "twitter_title": meta_tags.get("twitter:title", ""),
        "login_wall_present": login_wall_present,
        "search_error_present": search_error_present,
        "comment_scope": comment_scope,
    }

    elapsed = round(time.time() - started, 3)
    ok = bool(
        proc.returncode == 0
        and status is not None
        and 200 <= status < 300
        and len(text) >= 300
        and not search_error_present
    )
    errors = []
    if proc.returncode != 0:
        errors.append((proc.stderr or f"curl exit {proc.returncode}").strip())
    if parse_error:
        errors.append(f"parse: {parse_error}")
    if search_error_present:
        errors.append("X returned an anonymous search/error shell instead of usable results")
    elif status is not None and 200 <= status < 300 and len(text) < 300:
        errors.append("X returned too little visible text to treat as usable content")

    record = {
        "engine": "x-fast-http",
        "requested_url": url,
        "final_url": final_url,
        "status": status,
        "content_type": content_type,
        "title": title,
        "elapsed_seconds": elapsed,
        "curl_seconds": curl_seconds,
        "ok": ok,
        "fetched_at": now_iso(),
        "html_bytes": len(body),
        "text_chars": len(text),
        "errors": errors,
        "output_dir": dirname,
        **structured,
    }

    if artifact_policy != "none":
        (outdir / "page.txt").write_text(text, encoding="utf-8")
        (outdir / "meta.json").write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
        (outdir / "structured.json").write_text(
            json.dumps({"meta_tags": meta_tags, **structured}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    if artifact_policy == "raw":
        final_html = outdir / "page.html"
        body_path.replace(final_html)
    else:
        body_path.unlink(missing_ok=True)

    return index, record


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("job_file")
    ap.add_argument("--output", default="crawl_output")
    ap.add_argument("--validate-only", action="store_true")
    args = ap.parse_args()

    job_path = Path(args.job_file)
    job = json.loads(job_path.read_text(encoding="utf-8"))
    cfg = validate_job(job)
    if args.validate_only:
        print(f"valid X Fast job: {len(cfg['urls'])} URLs, workers={cfg['workers']}")
        return 0

    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)
    started_at = now_iso()
    wall_started = time.time()
    results = [None] * len(cfg["urls"])

    with ThreadPoolExecutor(max_workers=cfg["workers"]) as pool:
        futures = {
            pool.submit(fetch_one, i + 1, url, cfg["timeout"], cfg["artifact_policy"], out): i
            for i, url in enumerate(cfg["urls"])
        }
        for fut in as_completed(futures):
            i = futures[fut]
            try:
                _, record = fut.result()
            except Exception as exc:
                record = {
                    "engine": "x-fast-http",
                    "requested_url": cfg["urls"][i],
                    "status": None,
                    "ok": False,
                    "elapsed_seconds": None,
                    "errors": [str(exc)],
                    "fetched_at": now_iso(),
                }
            results[i] = record
            print(json.dumps({
                "url": record.get("requested_url"),
                "surface": record.get("surface"),
                "status": record.get("status"),
                "ok": record.get("ok"),
                "seconds": record.get("elapsed_seconds"),
                "text_chars": record.get("text_chars"),
            }, ensure_ascii=False), flush=True)

    manifest = {
        "job_name": cfg["name"],
        "job_file": str(job_path),
        "source_visibility": "public",
        "artifact_policy": cfg["artifact_policy"],
        "engine": "x-fast-http",
        "max_workers": cfg["workers"],
        "started_at": started_at,
        "finished_at": now_iso(),
        "wall_seconds": round(time.time() - wall_started, 3),
        "url_count": len(results),
        "ok_count": sum(1 for r in results if r and r.get("ok")),
        "failed_count": sum(1 for r in results if not r or not r.get("ok")),
        "results": results,
        "note": "Status/profile pages are anonymous public snapshots. Status pages may expose only a sample of replies; full comment threads are not guaranteed. Anonymous X search can return an unusable error shell and is marked failed.",
    }
    if cfg["artifact_policy"] != "none":
        (out / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "ok": manifest["ok_count"],
        "failed": manifest["failed_count"],
        "wall_seconds": manifest["wall_seconds"],
    }))
    return 0 if manifest["failed_count"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
