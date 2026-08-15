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

import vidian_pipeline as vp


def http_session():
    s = requests.Session()
    s.headers.update({
        "User-Agent": "Mozilla/5.0 (compatible; runner-3/VidianSnapshot/1.3)",
        "Accept-Language": "vi,en;q=0.8",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Connection": "close",
    })
    return s


def extract_article(root):
    try:
        return vp.extract(root)
    except ValueError as exc:
        if str(exc) != "article-region-too-short":
            raise

    # Some legitimate Vidian posts are genuinely very short. Preserve the
    # same h1->marker boundary as the canonical extractor, but relax only the
    # minimum-length gate for this explicit fallback case.
    h1s = root.xpath("//h1[1]")
    if not h1s:
        raise ValueError("missing-h1")
    h1 = h1s[0]
    paras = []
    buf = []
    last_parent = None

    def flush():
        nonlocal buf
        text = vp.clean(" ".join(buf))
        buf = []
        if len(text) >= 10:
            paras.append(text)

    for node in h1.xpath("following::text()"):
        parent = node.getparent()
        text = vp.clean(str(node))
        if not text:
            continue
        if vp.is_marker(text):
            flush()
            break
        if text.lower() in {"video", "rank", "tìm kiếm", "chat", "user"}:
            continue
        pid = id(parent)
        if last_parent is not None and pid != last_parent:
            flush()
        buf.append(text)
        last_parent = pid
    flush()

    if sum(map(len, paras)) < 20:
        raise ValueError("article-region-too-short")
    return paras


def fetch_article(s, row, timeout_sec):
    started = time.time()
    rec = {
        "url": row["url"],
        "listing_title": row.get("listing_title", ""),
        "status": "fetch-error",
        "http_status": 0,
        "retry_after": "",
        "title": "",
        "paragraphs": [],
        "paragraph_count": 0,
        "html_sha256": "",
        "clean_body_sha256": "",
        "source_prose_scope": "temporary-snapshot-only",
    }
    try:
        r = s.get(row["url"], timeout=(5, timeout_sec), allow_redirects=True)
        rec["http_status"] = r.status_code
        rec["retry_after"] = r.headers.get("Retry-After", "")
        rec["html_sha256"] = hashlib.sha256(r.content).hexdigest()
        if not r.ok:
            rec["status"] = f"http-{r.status_code}"
            return rec
        root = html.fromstring(r.content, base_url=r.url)
        paras = extract_article(root)
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


def load_existing(path):
    rows = {}
    p = Path(path)
    if not p.exists():
        return rows
    for line in p.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        rec = json.loads(line)
        rows[rec["url"]] = rec
    return rows


def save_checkpoint(path, selected, rows):
    p = Path(path)
    tmp = p.with_suffix(p.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        for src in selected:
            rec = rows.get(src["url"])
            if rec is not None:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    tmp.replace(p)


def cooldown_seconds(rec, default_sec):
    raw = str(rec.get("retry_after", "")).strip()
    if raw:
        try:
            return max(5.0, min(120.0, float(raw)))
        except ValueError:
            pass
    return default_sec


def run(inventory_path, outdir, index, count, passes, delay, timeout_sec, resume, allow_incomplete, cooldown_429, max_429_retries):
    inv = json.loads(Path(inventory_path).read_text(encoding="utf-8"))
    trusted = [r for r in inv["rows"] if r.get("trusted")]
    selected = [r for i, r in enumerate(trusted) if i % count == index]
    out = Path(outdir)
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"vidian_snapshot_chunk_{index:02d}.jsonl"
    rows = load_existing(resume or path)
    by_url = {r["url"]: r for r in selected}
    started = time.time()
    rate_limit_events = 0

    for attempt in range(1, passes + 1):
        pending = [u for u in by_url if rows.get(u, {}).get("status") != "fetched"]
        if not pending:
            break
        print(f"SNAPSHOT_PASS {attempt}/{passes} pending={len(pending)} timeout={timeout_sec}s", flush=True)
        s = http_session()
        for n, url in enumerate(pending, 1):
            rec = fetch_article(s, by_url[url], timeout_sec)
            retry_429 = 0
            while rec.get("status") == "http-429" and retry_429 < max_429_retries:
                retry_429 += 1
                rate_limit_events += 1
                rows[url] = rec
                save_checkpoint(path, selected, rows)
                pause = cooldown_seconds(rec, cooldown_429)
                print(
                    f"RATE_LIMIT chunk={index} item={n}/{len(pending)} retry={retry_429}/{max_429_retries} cooldown={pause:.1f}s",
                    flush=True,
                )
                time.sleep(pause)
                s.close()
                s = http_session()
                rec = fetch_article(s, by_url[url], timeout_sec)

            rows[url] = rec
            if n % 5 == 0 or n == len(pending):
                save_checkpoint(path, selected, rows)
                fetched = sum(rows.get(u, {}).get("status") == "fetched" for u in by_url)
                failed = sum(u in rows and rows[u].get("status") != "fetched" for u in by_url)
                print(
                    f"SNAPSHOT {index} pass={attempt} {n}/{len(pending)} fetched={fetched}/{len(selected)} failed_now={failed} rate_limits={rate_limit_events}",
                    flush=True,
                )
            if delay > 0:
                time.sleep(delay)
        s.close()
        if attempt < passes:
            left = sum(rows.get(u, {}).get("status") != "fetched" for u in by_url)
            if left:
                pause = min(20, 5 * attempt)
                print(f"SNAPSHOT_REPAIR_BACKOFF {pause}s failures={left}", flush=True)
                time.sleep(pause)

    save_checkpoint(path, selected, rows)
    ordered = [rows.get(r["url"], {"url": r["url"], "status": "missing"}) for r in selected]
    failures = [r for r in ordered if r.get("status") != "fetched"]
    status_counts = Counter(r.get("status", "missing") for r in ordered)
    summary = {
        "chunk": index,
        "chunks": count,
        "rows": len(ordered),
        "fetched": len(ordered) - len(failures),
        "failed": len(failures),
        "status_counts": dict(status_counts),
        "passes_this_step": passes,
        "request_delay_sec": delay,
        "read_timeout_sec": timeout_sec,
        "cooldown_429_sec": cooldown_429,
        "rate_limit_events": rate_limit_events,
        "elapsed_sec": round(time.time() - started, 3),
        "completed_utc": datetime.now(timezone.utc).isoformat(),
    }
    (out / f"snapshot_{index:02d}_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False), flush=True)
    if failures:
        sample = [{"url": r.get("url"), "status": r.get("status")} for r in failures[:10]]
        print("SNAPSHOT_FAILURE_SAMPLE", json.dumps(sample, ensure_ascii=False), flush=True)
        if not allow_incomplete:
            raise SystemExit(f"snapshot incomplete: {len(failures)} article failures")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--inventory", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--index", type=int, required=True)
    ap.add_argument("--count", type=int, default=64)
    ap.add_argument("--passes", type=int, default=1)
    ap.add_argument("--delay", type=float, default=0.4)
    ap.add_argument("--timeout", type=float, default=8.0)
    ap.add_argument("--resume", default="")
    ap.add_argument("--allow-incomplete", action="store_true")
    ap.add_argument("--cooldown-429", type=float, default=32.0)
    ap.add_argument("--max-429-retries", type=int, default=3)
    a = ap.parse_args()
    run(
        a.inventory, a.out, a.index, a.count, a.passes, a.delay,
        a.timeout, a.resume, a.allow_incomplete,
        a.cooldown_429, a.max_429_retries,
    )


if __name__ == "__main__":
    main()
