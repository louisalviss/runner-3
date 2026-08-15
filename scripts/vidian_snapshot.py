#!/usr/bin/env python3
import argparse
import hashlib
import json
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import requests
from lxml import html
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

import vidian_pipeline as vp


def http_session():
    s = requests.Session()
    s.headers.update({
        "User-Agent": "Mozilla/5.0 (compatible; runner-3/VidianSnapshot/1.0)",
        "Accept-Language": "vi,en;q=0.8",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    })
    retry = Retry(
        total=2,
        connect=2,
        read=2,
        status=2,
        backoff_factor=1.0,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset(["GET"]),
        respect_retry_after_header=True,
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry, pool_connections=1, pool_maxsize=1)
    s.mount("https://", adapter)
    s.mount("http://", adapter)
    return s


def fetch_article(s, row):
    started = time.time()
    rec = {
        "url": row["url"],
        "listing_title": row.get("listing_title", ""),
        "status": "fetch-error",
        "http_status": 0,
        "title": "",
        "paragraphs": [],
        "paragraph_count": 0,
        "html_sha256": "",
        "clean_body_sha256": "",
        "source_prose_scope": "temporary-snapshot-only",
    }
    try:
        r = s.get(row["url"], timeout=(8, 30), allow_redirects=True)
        rec["http_status"] = r.status_code
        rec["html_sha256"] = hashlib.sha256(r.content).hexdigest()
        if not r.ok:
            rec["status"] = f"http-{r.status_code}"
            return rec
        root = html.fromstring(r.content, base_url=r.url)
        paras = vp.extract(root)
        full = vp.clean(" ".join(paras))
        title = root.xpath('//meta[@property="og:title"]/@content') or root.xpath('//h1[1]//text()') or root.xpath('//title/text()')
        rec.update({
            "status": "fetched",
            "title": vp.clean(title[0]) if title else "",
            "paragraphs": paras,
            "paragraph_count": len(paras),
            "clean_body_sha256": hashlib.sha256(full.encode()).hexdigest(),
        })
    except Exception as exc:
        rec["status"] = f"error:{type(exc).__name__}:{str(exc)[:140]}"
    finally:
        rec["fetch_elapsed_sec"] = round(time.time() - started, 3)
    return rec


def run(inventory_path, outdir, index, count, passes, delay):
    inv = json.loads(Path(inventory_path).read_text(encoding="utf-8"))
    trusted = [r for r in inv["rows"] if r.get("trusted")]
    selected = [r for i, r in enumerate(trusted) if i % count == index]
    out = Path(outdir)
    out.mkdir(parents=True, exist_ok=True)
    rows = {r["url"]: None for r in selected}
    by_url = {r["url"]: r for r in selected}
    pending = list(rows)
    s = http_session()
    started = time.time()

    for attempt in range(1, passes + 1):
        if not pending:
            break
        current = pending
        pending = []
        print(f"SNAPSHOT_PASS {attempt}/{passes} pending={len(current)}", flush=True)
        for n, url in enumerate(current, 1):
            rec = fetch_article(s, by_url[url])
            rows[url] = rec
            if rec["status"] != "fetched":
                pending.append(url)
            if n % 25 == 0 or n == len(current):
                counts = Counter((rows[u] or {}).get("status", "pending") for u in rows)
                print(f"SNAPSHOT {index} pass={attempt} {n}/{len(current)} fetched={counts.get('fetched', 0)} retry={len(pending)}", flush=True)
            if delay > 0:
                time.sleep(delay)
        if pending and attempt < passes:
            pause = min(30, 2 ** attempt * 2)
            print(f"SNAPSHOT_BACKOFF {pause}s failures={len(pending)}", flush=True)
            time.sleep(pause)

    ordered = [rows[r["url"]] for r in selected]
    path = out / f"vidian_snapshot_chunk_{index:02d}.jsonl"
    with path.open("w", encoding="utf-8", buffering=1) as f:
        for rec in ordered:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    failures = [r for r in ordered if not r or r.get("status") != "fetched"]
    status_counts = Counter((r or {}).get("status", "missing") for r in ordered)
    summary = {
        "chunk": index,
        "chunks": count,
        "rows": len(ordered),
        "fetched": len(ordered) - len(failures),
        "failed": len(failures),
        "status_counts": dict(status_counts),
        "passes": passes,
        "request_delay_sec": delay,
        "elapsed_sec": round(time.time() - started, 3),
        "completed_utc": datetime.now(timezone.utc).isoformat(),
    }
    (out / f"snapshot_{index:02d}_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False), flush=True)
    if failures:
        sample = [{"url": r.get("url"), "status": r.get("status")} for r in failures[:10]]
        print("SNAPSHOT_FAILURE_SAMPLE", json.dumps(sample, ensure_ascii=False), flush=True)
        raise SystemExit(f"snapshot incomplete: {len(failures)} article failures")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--inventory", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--index", type=int, required=True)
    ap.add_argument("--count", type=int, default=32)
    ap.add_argument("--passes", type=int, default=5)
    ap.add_argument("--delay", type=float, default=0.6)
    a = ap.parse_args()
    run(a.inventory, a.out, a.index, a.count, a.passes, a.delay)


if __name__ == "__main__":
    main()
