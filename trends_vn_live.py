#!/usr/bin/env python3

import json
import re
from datetime import datetime, timezone
from pathlib import Path

from playwright.sync_api import sync_playwright

URL = "https://trends.google.com/trending?geo=VN&hl=vi"
OUT = Path("trends_vn_latest.json")


def clean(s):
    return re.sub(r"\s+", " ", (s or "")).strip()


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(
            viewport={"width": 1440, "height": 1200},
            locale="vi-VN",
            timezone_id="Asia/Ho_Chi_Minh",
        )
        page.goto(URL, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(5000)

        # Google has changed the Trending Now markup several times. Prefer
        # semantic table rows, then ARIA rows as a fallback.
        candidates = []
        for selector in ("tbody tr", "table tr", '[role="row"]'):
            rows = page.locator(selector)
            try:
                count = rows.count()
            except Exception:
                count = 0
            if count:
                for i in range(count):
                    try:
                        txt = clean(rows.nth(i).inner_text(timeout=3000))
                    except Exception:
                        continue
                    if txt and txt not in candidates:
                        candidates.append(txt)
                if len(candidates) >= 10:
                    break

        # Keep only rows that look like actual trends (have a search-volume
        # bucket and/or percentage increase), excluding header rows.
        trend_rows = []
        for txt in candidates:
            low = txt.lower()
            looks_volume = bool(re.search(r"\b\d+(?:[.,]\d+)?\s*(?:n\+|k\+|m\+|lượt tìm kiếm|searches)", txt, re.I))
            looks_pct = "%" in txt
            if (looks_volume or looks_pct) and "xu hướng tìm kiếm" not in low and "search volume" not in low:
                trend_rows.append(txt)
            if len(trend_rows) >= 10:
                break

        payload = {
            "captured_at": datetime.now(timezone.utc).isoformat(),
            "url": URL,
            "status": "HEALTHY" if len(trend_rows) == 10 else "DEGRADED",
            "top10_rows": trend_rows,
            "candidate_rows": candidates[:30],
            "page_title": page.title(),
        }
        OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({"status": payload["status"], "rows": len(trend_rows)}, ensure_ascii=False))
        browser.close()

    if len(trend_rows) != 10:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
