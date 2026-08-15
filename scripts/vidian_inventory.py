#!/usr/bin/env python3
import argparse
import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

import vidian_pipeline as vp


def last_page_reliable(slug):
    last_err = None
    for attempt in range(1, 5):
        try:
            n = vp.last_page(slug)
            if n > 0:
                return slug, n, None
            last_err = "no-pages"
        except Exception as e:
            last_err = f"{type(e).__name__}:{e}"
        try:
            vp._HTTP_LOCAL.session.close()
            del vp._HTTP_LOCAL.session
        except Exception:
            pass
        time.sleep(attempt * 2)
    return slug, 0, last_err or "no-pages"


def fetch_page(job):
    slug, page = job
    return vp.fetch_listing(slug, page)


def run(outdir, initial_workers=6, repair_rounds=6):
    out = Path(outdir)
    out.mkdir(parents=True, exist_ok=True)
    cats = vp.discover_categories()
    ranges = {}
    category_failures = []

    with ThreadPoolExecutor(max_workers=4) as ex:
        fs = {ex.submit(last_page_reliable, c): c for c in cats}
        for f in as_completed(fs):
            c, n, err = f.result()
            ranges[c] = n
            if err or n <= 0:
                category_failures.append({"category": c, "error": err or "no-pages"})

    if category_failures:
        print("CATEGORY_FAILURES", json.dumps(category_failures, ensure_ascii=False), flush=True)
        raise SystemExit(2)

    jobs = [(c, p) for c, n in ranges.items() for p in range(1, n + 1)]
    by = {}
    pending = []

    with ThreadPoolExecutor(max_workers=initial_workers) as ex:
        fs = [ex.submit(fetch_page, job) for job in jobs]
        for i, f in enumerate(as_completed(fs), 1):
            c, p, d, err = f.result()
            if err:
                pending.append((c, p, err))
            else:
                for u, t in d.items():
                    by[u] = max(by.get(u, ""), t, key=len)
            if i % 50 == 0 or i == len(jobs):
                print("LISTING", i, "/", len(jobs), "pending", len(pending), flush=True)

    for round_no in range(1, repair_rounds + 1):
        if not pending:
            break
        print("REPAIR_ROUND", round_no, "pages", len(pending), flush=True)
        time.sleep(round_no * 3)
        retry_jobs = [(c, p) for c, p, _ in pending]
        pending = []
        # A fresh executor gives repair requests fresh thread-local HTTP sessions.
        with ThreadPoolExecutor(max_workers=2) as ex:
            fs = [ex.submit(fetch_page, job) for job in retry_jobs]
            for f in as_completed(fs):
                c, p, d, err = f.result()
                if err:
                    pending.append((c, p, err))
                else:
                    for u, t in d.items():
                        by[u] = max(by.get(u, ""), t, key=len)
        print("REPAIR_REMAINING", len(pending), flush=True)

    failures = [
        {"category": c, "page": p, "error": err}
        for c, p, err in sorted(pending)
    ]
    rows = [
        {"url": u, "listing_title": t, "trusted": u not in vp.UNTRUSTED}
        for u, t in sorted(by.items())
    ]
    trusted = [r for r in rows if r["trusted"]]
    payload = {
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "categories": ranges,
        "page_failures": failures,
        "all_urls": len(rows),
        "trusted_urls": len(trusted),
        "known_untrusted": len([r for r in rows if not r["trusted"]]),
        "rows": rows,
    }
    (out / "vidian_inventory.json").write_text(
        json.dumps(payload, ensure_ascii=False), encoding="utf-8"
    )
    print(json.dumps({k: payload[k] for k in ("all_urls", "trusted_urls", "known_untrusted")}), flush=True)
    print("PAGE_FAILURES", len(failures), flush=True)
    if failures:
        for item in failures:
            print("PAGE_FAILURE", json.dumps(item, ensure_ascii=False), flush=True)
        raise SystemExit(3)
    if len(trusted) < 8500:
        raise SystemExit(f"inventory unexpectedly small: {len(trusted)}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="vidian_inventory")
    ap.add_argument("--initial-workers", type=int, default=6)
    ap.add_argument("--repair-rounds", type=int, default=6)
    args = ap.parse_args()
    run(args.out, args.initial_workers, args.repair_rounds)


if __name__ == "__main__":
    main()
