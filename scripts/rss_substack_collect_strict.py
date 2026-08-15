#!/usr/bin/env python3

import json
from pathlib import Path

import rss_substack_collect as collector

collector.SESSION.headers.update({
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9,vi;q=0.8",
    "Cache-Control": "no-cache",
})

collector.main()
health_path = Path(__file__).resolve().parents[1] / "data" / "rss-reader" / "substack-health.json"
health = json.loads(health_path.read_text(encoding="utf-8"))
raise SystemExit(0 if health.get("status") == "healthy" else 2)
