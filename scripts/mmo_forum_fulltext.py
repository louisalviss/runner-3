#!/usr/bin/env python3
import argparse
import hashlib
import json
import re
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36 runner-3-mmo-fulltext/1.0"
PREMIUM_MARKERS = ["premium content", "register and upgrade your account", "must first register and upgrade"]
BLOCK_MARKERS = ["checking your browser", "verify you are human", "attention required! | cloudflare", "temporarily blocked"]


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def thread_key(url):
    p = urlparse(url)
    m = re.search(r"(/(?:f/)?threads/[^/?#]+?\.(\d+))", p.path)
    if not m:
        return None
    return f"{p.scheme}://{p.netloc}{m.group(1)}/"


def thread_id(url):
    key = thread_key(url or "")
    if not key:
        return ""
    m = re.search(r"\.(\d+)/?$", key)
    return m.group(1) if m else ""


def clean_text(html):
    soup = BeautifulSoup(html or "", "html.parser")
    for tag in soup(["script", "style", "noscript", "svg", "template"]):
        tag.decompose()
    return "\n".join(x.strip() for x in soup.get_text("\n").splitlines() if x.strip())


def fetch(session, url, timeout):
    started = time.time()
    try:
        r = session.get(url, timeout=timeout, allow_redirects=True)
        text = clean_text(r.text)
        low = text[:6000].lower()
        blocked = r.status_code in {401, 403, 407, 429} or any(x in low for x in BLOCK_MARKERS)
        return {
            "requested_url": url,
            "final_url": r.url,
            "status": r.status_code,
            "ok": r.status_code < 400 and not blocked,
            "blocked": blocked,
            "html": r.text,
            "text": text,
            "elapsed_seconds": round(time.time() - started, 3),
        }
    except Exception as exc:
        return {
            "requested_url": url,
            "final_url": "",
            "status": None,
            "ok": False,
            "blocked": False,
            "html": "",
            "text": "",
            "error": f"{type(exc).__name__}: {exc}",
            "elapsed_seconds": round(time.time() - started, 3),
        }


def expand_urls(section):
    if section.get("urls"):
        return section["urls"]
    base = section["base"].rstrip("/") + "/"
    pages = int(section.get("pages", 1))
    return [base] + [base + f"page-{p}/" for p in range(2, pages + 1)]


def parse_listing(html, requested_url, source_name, section_name):
    soup = BeautifulSoup(html, "html.parser")
    rows = []
    for item in soup.select(".structItem.structItem--thread"):
        a = item.select_one('.structItem-title a[href*="/threads/"]')
        if not a:
            continue
        key = thread_key(urljoin(requested_url, a.get("href", "")))
        if not key:
            continue
        title = " ".join(a.get_text(" ", strip=True).split())
        listed_pages = [1]
        for x in item.find_all("a", href=True):
            m = re.search(r"/page-(\d+)", x.get("href", ""))
            if m:
                listed_pages.append(int(m.group(1)))
        rows.append({
            "source": source_name,
            "section": section_name,
            "url": key,
            "thread_id": thread_id(key),
            "title": title,
            "listed_pages": max(listed_pages),
        })
    return rows


def discover(config_path, output):
    cfg = json.loads(Path(config_path).read_text(encoding="utf-8"))
    out = Path(output)
    out.mkdir(parents=True, exist_ok=True)
    session = requests.Session()
    session.headers.update({"User-Agent": UA, "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"})
    manifest = []
    coverage = []
    for source in cfg["sources"]:
        by_url = {}
        listing_ok = 0
        listing_total = 0
        for section in source["sections"]:
            for url in expand_urls(section):
                listing_total += 1
                res = fetch(session, url, int(source.get("timeout_seconds", 35)))
                if res.get("ok"):
                    listing_ok += 1
                    for row in parse_listing(res["html"], url, source["name"], section["name"]):
                        old = by_url.get(row["url"])
                        if old is None:
                            by_url[row["url"]] = row
                        else:
                            old["listed_pages"] = max(old.get("listed_pages", 1), row.get("listed_pages", 1))
                time.sleep(float(source.get("delay_seconds", 0.02)))
        rows = sorted(by_url.values(), key=lambda x: (x["source"], int(x["thread_id"] or 0)))
        manifest.extend(rows)
        coverage.append({
            "source": source["name"],
            "listing_pages": listing_total,
            "listing_ok": listing_ok,
            "threads": len(rows),
        })
    (out / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
    (out / "coverage.json").write_text(json.dumps(coverage, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"coverage": coverage, "threads": len(manifest)}, ensure_ascii=False))


def detect_max_pages(first_html, listed_pages):
    nums = [1, int(listed_pages or 1)]
    soup = BeautifulSoup(first_html or "", "html.parser")
    for a in soup.find_all("a", href=True):
        m = re.search(r"/page-(\d+)", a.get("href", ""))
        if m:
            nums.append(int(m.group(1)))
    return max(nums)


def digest_text(text):
    raw = (text or "").encode("utf-8", errors="ignore")
    return hashlib.sha256(raw).hexdigest()


def audit_thread(session, row, source_cfg):
    base = row["url"]
    requested_id = row.get("thread_id") or thread_id(base)
    timeout = int(source_cfg.get("timeout_seconds", 35))
    delay = float(source_cfg.get("delay_seconds", 0.02))
    first = fetch(session, base, timeout)
    final_id = thread_id(first.get("final_url", ""))
    canonical_mismatch = bool(requested_id and final_id and requested_id != final_id)
    premium = any(x in first.get("text", "").lower() for x in PREMIUM_MARKERS)
    max_pages = 1
    if first.get("ok") and not canonical_mismatch:
        max_pages = detect_max_pages(first.get("html", ""), row.get("listed_pages", 1))
    pages = []
    total_chars = 0
    total_words = 0
    hashes = []

    def add_page(page_no, res, mismatch=False):
        nonlocal total_chars, total_words
        ok = bool(res.get("ok") and not mismatch)
        text = res.get("text", "") if ok else ""
        sha = digest_text(text) if ok else ""
        if ok:
            total_chars += len(text)
            total_words += len(text.split())
            hashes.append(sha)
        pages.append({
            "page": page_no,
            "status": res.get("status"),
            "ok": ok,
            "blocked": bool(res.get("blocked")),
            "canonical_mismatch": mismatch,
            "text_chars": len(text),
            "sha256": sha,
            "error": res.get("error", ""),
        })

    add_page(1, first, canonical_mismatch)
    if first.get("ok") and not canonical_mismatch and not premium:
        for p in range(2, max_pages + 1):
            url = base.rstrip("/") + f"/page-{p}/"
            res = fetch(session, url, timeout)
            pid = thread_id(res.get("final_url", ""))
            mismatch = bool(requested_id and pid and requested_id != pid)
            add_page(p, res, mismatch)
            time.sleep(delay)

    ok_pages = sum(1 for p in pages if p["ok"])
    if canonical_mismatch:
        qa = "FAIL_CANONICAL_MISMATCH"
    elif premium:
        qa = "PARTIAL_PREMIUM"
    elif ok_pages == max_pages and first.get("ok"):
        qa = "PASS"
    elif ok_pages > 0:
        qa = "PARTIAL"
    elif first.get("blocked"):
        qa = "FAIL_BLOCKED"
    else:
        qa = "FAIL"
    corpus_hash = hashlib.sha256("|".join(hashes).encode("ascii")).hexdigest() if hashes else ""
    return {
        **row,
        "final_url": first.get("final_url", ""),
        "max_pages_detected": max_pages,
        "pages_attempted": len(pages),
        "pages_ok": ok_pages,
        "premium_or_login_gate": premium,
        "canonical_mismatch": canonical_mismatch,
        "qa": qa,
        "total_chars_read": total_chars,
        "total_words_read": total_words,
        "corpus_sha256": corpus_hash,
        "pages": pages,
    }


def shard(config_path, manifest_path, output, source_name, shard_index, shard_total):
    cfg = json.loads(Path(config_path).read_text(encoding="utf-8"))
    source_cfg = next(x for x in cfg["sources"] if x["name"] == source_name)
    manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    rows = [x for x in manifest if x["source"] == source_name]
    rows = [row for i, row in enumerate(rows) if i % shard_total == shard_index]
    out = Path(output)
    out.mkdir(parents=True, exist_ok=True)
    session = requests.Session()
    session.headers.update({"User-Agent": UA, "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"})
    audits = []
    for i, row in enumerate(rows, 1):
        audit = audit_thread(session, row, source_cfg)
        audits.append(audit)
        print(json.dumps({"source": source_name, "shard": shard_index, "item": i, "total": len(rows), "thread_id": row.get("thread_id"), "qa": audit["qa"], "pages_ok": audit["pages_ok"], "pages": audit["max_pages_detected"]}, ensure_ascii=False), flush=True)
        time.sleep(float(source_cfg.get("delay_seconds", 0.02)))
    with (out / "audit.jsonl").open("w", encoding="utf-8") as fh:
        for row in audits:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    counts = Counter(x["qa"] for x in audits)
    summary = {
        "source": source_name,
        "shard_index": shard_index,
        "shard_total": shard_total,
        "threads_attempted": len(audits),
        "qa": dict(counts),
        "pages_attempted": sum(x["pages_attempted"] for x in audits),
        "pages_ok": sum(x["pages_ok"] for x in audits),
        "chars_read": sum(x["total_chars_read"] for x in audits),
        "words_read": sum(x["total_words_read"] for x in audits),
        "finished_at": now_iso(),
    }
    (out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False), flush=True)


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("discover")
    d.add_argument("config")
    d.add_argument("--output", required=True)
    s = sub.add_parser("shard")
    s.add_argument("config")
    s.add_argument("manifest")
    s.add_argument("--output", required=True)
    s.add_argument("--source", required=True)
    s.add_argument("--shard-index", type=int, required=True)
    s.add_argument("--shard-total", type=int, required=True)
    args = ap.parse_args()
    if args.cmd == "discover":
        discover(args.config, args.output)
    else:
        shard(args.config, args.manifest, args.output, args.source, args.shard_index, args.shard_total)


if __name__ == "__main__":
    main()
