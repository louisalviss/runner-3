#!/usr/bin/env python3
import argparse
import json
import math
import re
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36 runner-3-mmo-sweep/1.0"
MONEY_RE = re.compile(r"(\$|profit|revenue|income|earning|money|roi|roas|mrr|sale|sold|client|agency|affiliate|e.?commerce|lead|saas|case study|journey|follow along|challenge|business|service|website|seo|ppc)", re.I)
NEG_RE = re.compile(r"(fail|failed|failure|loss|losing|broke|break.?even|mistake|struggle|problem|warning|scam|newbie|beginner)", re.I)
VENDOR_RE = re.compile(r"(case study|success story|partner.?s case|ready.?made bundle)", re.I)
PREMIUM_MARKERS = ["premium content", "register and upgrade your account", "must first register and upgrade"]
BLOCK_MARKERS = ["checking your browser", "verify you are human", "attention required! | cloudflare", "temporarily blocked"]


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def nval(value):
    s = str(value or "").strip().upper().replace(",", "")
    if not s:
        return 0.0
    mult = 1.0
    if s.endswith("K"):
        mult, s = 1_000.0, s[:-1]
    elif s.endswith("M"):
        mult, s = 1_000_000.0, s[:-1]
    try:
        return float(s) * mult
    except Exception:
        return 0.0


def text_from_html(html):
    soup = BeautifulSoup(html or "", "html.parser")
    title = soup.title.get_text(" ", strip=True) if soup.title else ""
    for tag in soup(["script", "style", "noscript", "svg", "template"]):
        tag.decompose()
    text = "\n".join(x.strip() for x in soup.get_text("\n").splitlines() if x.strip())
    return title, text


def fetch(session, url, timeout=35):
    started = time.time()
    try:
        r = session.get(url, timeout=timeout, allow_redirects=True)
        title, text = text_from_html(r.text)
        low = text[:5000].lower()
        blocked = r.status_code in {401, 403, 407, 429} or any(x in low for x in BLOCK_MARKERS)
        return {
            "requested_url": url,
            "final_url": r.url,
            "status": r.status_code,
            "ok": r.status_code < 400 and not blocked,
            "blocked": blocked,
            "title": title,
            "text": text,
            "html": r.text,
            "elapsed_seconds": round(time.time() - started, 3),
        }
    except Exception as exc:
        return {"requested_url": url, "final_url": "", "status": None, "ok": False, "blocked": False, "title": "", "text": "", "html": "", "error": f"{type(exc).__name__}: {exc}"}


def thread_key(url):
    p = urlparse(url)
    m = re.search(r"(/(?:f/)?threads/[^/?#]+?\.\d+)", p.path)
    if not m:
        return None
    return f"{p.scheme}://{p.netloc}{m.group(1)}/"


def thread_id(url):
    m = re.search(r"\.(\d+)/?$", thread_key(url) or "")
    return m.group(1) if m else ""


def page_urls(base, count):
    out = [base]
    stem = base.rstrip("/")
    for p in range(2, count + 1):
        out.append(f"{stem}/page-{p}/")
    return out


def parse_listing(html, requested_url, source_name, section):
    soup = BeautifulSoup(html, "html.parser")
    rows = []
    for item in soup.select(".structItem.structItem--thread"):
        a = item.select_one('.structItem-title a[href*="/threads/"]')
        if not a:
            continue
        raw = urljoin(requested_url, a.get("href", ""))
        key = thread_key(raw)
        if not key:
            continue
        title = " ".join(a.get_text(" ", strip=True).split())
        pairs = {}
        for pair in item.select(".pairs"):
            dt = pair.find("dt")
            dd = pair.find("dd")
            if dt and dd:
                pairs[dt.get_text(" ", strip=True)] = dd.get_text(" ", strip=True)
        user = item.select_one(".username")
        t = item.select_one("time")
        listed_pages = [1]
        for x in item.find_all("a", href=True):
            m = re.search(r"/page-(\d+)", x.get("href", ""))
            if m:
                listed_pages.append(int(m.group(1)))
        rows.append({
            "source": source_name,
            "section": section,
            "url": key,
            "thread_id": thread_id(key),
            "title": title,
            "author": user.get_text(strip=True) if user else "",
            "created": (t.get("datetime") or t.get_text(strip=True)) if t else "",
            "replies": pairs.get("Replies", ""),
            "views": pairs.get("Views", ""),
            "listed_pages": max(listed_pages),
        })
    return rows


def score_thread(row):
    replies = nval(row.get("replies"))
    views = nval(row.get("views"))
    title = row.get("title", "")
    score = 2.0 * min(replies, 250) / 250 + 1.2 * min(views, 50000) / 50000
    if MONEY_RE.search(title):
        score += 2.0
    if NEG_RE.search(title):
        score += 0.9
    if row.get("section") in {"case_studies", "laboratory", "education"}:
        score += 0.7
    if VENDOR_RE.search(title):
        score += 0.2
    return round(score, 4)


def select_threads(rows, limit):
    for row in rows:
        row["score"] = score_thread(row)
    ranked = sorted(rows, key=lambda x: (x["score"], nval(x.get("replies")), nval(x.get("views"))), reverse=True)
    base = ranked[: max(0, limit - max(5, limit // 5))]
    picked = {x["url"]: x for x in base}
    negatives = [x for x in ranked if NEG_RE.search(x.get("title", "")) and x["url"] not in picked]
    for x in negatives[: max(5, limit // 5)]:
        picked[x["url"]] = x
    return sorted(picked.values(), key=lambda x: x["score"], reverse=True)[:limit]


def discover_source(session, source, out_dir):
    rows_by_url = {}
    listing_audit = []
    for section in source["sections"]:
        for url in section["urls"]:
            res = fetch(session, url, source.get("timeout_seconds", 35))
            listing_audit.append({k: v for k, v in res.items() if k not in {"html", "text"}} | {"section": section["name"], "text_chars": len(res.get("text", ""))})
            if not res.get("ok"):
                continue
            for row in parse_listing(res["html"], url, source["name"], section["name"]):
                old = rows_by_url.get(row["url"])
                if old is None:
                    rows_by_url[row["url"]] = row
                else:
                    old["listed_pages"] = max(old.get("listed_pages", 1), row.get("listed_pages", 1))
                    if nval(row.get("replies")) > nval(old.get("replies")):
                        old.update({k: row[k] for k in ["replies", "views", "author", "created"]})
            time.sleep(source.get("delay_seconds", 0.03))
    discovered = list(rows_by_url.values())
    selected = select_threads(discovered, source.get("select_threads", 40))
    src_dir = out_dir / source["name"]
    src_dir.mkdir(parents=True, exist_ok=True)
    (src_dir / "discovery.json").write_text(json.dumps(discovered, ensure_ascii=False, indent=2), encoding="utf-8")
    (src_dir / "listing_audit.json").write_text(json.dumps(listing_audit, ensure_ascii=False, indent=2), encoding="utf-8")
    (src_dir / "selected_threads.json").write_text(json.dumps(selected, ensure_ascii=False, indent=2), encoding="utf-8")
    return discovered, selected, listing_audit


def fullread_source(session, source, selected, out_dir):
    audits = []
    src_dir = out_dir / source["name"] / "fullread"
    src_dir.mkdir(parents=True, exist_ok=True)
    for row in selected:
        base = row["url"]
        first = fetch(session, base, source.get("timeout_seconds", 35))
        requested_id = row.get("thread_id") or thread_id(base)
        final_id = thread_id(first.get("final_url", ""))
        canonical_mismatch = bool(requested_id and final_id and requested_id != final_id)
        premium = any(x in first.get("text", "").lower() for x in PREMIUM_MARKERS)
        max_pages = 1
        if first.get("ok") and not canonical_mismatch:
            soup = BeautifulSoup(first.get("html", ""), "html.parser")
            nums = [1]
            for a in soup.find_all("a", href=True):
                m = re.search(r"/page-(\d+)", a.get("href", ""))
                if m:
                    nums.append(int(m.group(1)))
            max_pages = min(max(nums), source.get("max_thread_pages", 30))
            max_pages = max(max_pages, min(row.get("listed_pages", 1), source.get("max_thread_pages", 30)))
        pages = []
        thread_dir = src_dir / (requested_id or re.sub(r"\W+", "_", row.get("title", ""))[:60])
        thread_dir.mkdir(parents=True, exist_ok=True)
        if first.get("ok") and not canonical_mismatch:
            first_text = first.get("text", "")
            (thread_dir / "page-1.txt").write_text(first_text, encoding="utf-8", errors="ignore")
            pages.append({"page": 1, "url": base, "status": first.get("status"), "ok": True, "text_chars": len(first_text)})
        else:
            pages.append({"page": 1, "url": base, "status": first.get("status"), "ok": False, "text_chars": len(first.get("text", "")), "error": first.get("error", ""), "canonical_mismatch": canonical_mismatch})
        if first.get("ok") and not canonical_mismatch and not premium:
            for p in range(2, max_pages + 1):
                url = base.rstrip("/") + f"/page-{p}/"
                res = fetch(session, url, source.get("timeout_seconds", 35))
                final_pid = thread_id(res.get("final_url", ""))
                mismatch = bool(requested_id and final_pid and requested_id != final_pid)
                ok = bool(res.get("ok") and not mismatch)
                if ok:
                    (thread_dir / f"page-{p}.txt").write_text(res.get("text", ""), encoding="utf-8", errors="ignore")
                pages.append({"page": p, "url": url, "status": res.get("status"), "ok": ok, "text_chars": len(res.get("text", "")), "canonical_mismatch": mismatch, "error": res.get("error", "")})
                time.sleep(source.get("delay_seconds", 0.03))
        ok_pages = sum(1 for x in pages if x["ok"])
        if canonical_mismatch:
            qa = "FAIL_CANONICAL_MISMATCH"
        elif premium:
            qa = "PARTIAL_PREMIUM"
        elif ok_pages == max_pages and first.get("ok"):
            qa = "PASS"
        elif ok_pages > 0:
            qa = "PARTIAL"
        else:
            qa = "FAIL"
        audit = row | {
            "final_url": first.get("final_url", ""),
            "max_pages_detected": max_pages,
            "pages_ok": ok_pages,
            "pages_attempted": len(pages),
            "premium_or_login_gate": premium,
            "canonical_mismatch": canonical_mismatch,
            "qa": qa,
            "pages": pages,
        }
        audits.append(audit)
        (thread_dir / "audit.json").write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
    (out_dir / source["name"] / "fullread_audit.json").write_text(json.dumps(audits, ensure_ascii=False, indent=2), encoding="utf-8")
    return audits


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("config")
    ap.add_argument("--output", default="mmo_sweep_output")
    args = ap.parse_args()
    cfg = json.loads(Path(args.config).read_text(encoding="utf-8"))
    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)
    session = requests.Session()
    session.headers.update({"User-Agent": UA, "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"})
    summary = {"started_at": now_iso(), "sources": {}}
    for source in cfg["sources"]:
        discovered, selected, listing_audit = discover_source(session, source, out)
        audits = fullread_source(session, source, selected, out)
        c = Counter(x["qa"] for x in audits)
        summary["sources"][source["name"]] = {
            "listing_pages": len(listing_audit),
            "listing_ok": sum(1 for x in listing_audit if x.get("ok")),
            "discovered_threads": len(discovered),
            "selected_threads": len(selected),
            "fullread_qa": dict(c),
        }
    summary["finished_at"] = now_iso()
    (out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
