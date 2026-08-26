#!/usr/bin/env python3
from __future__ import annotations

import csv
import json
import urllib.request
from datetime import datetime, timezone

import private_backtest_us60_robustness as base

STOOQ_URL = base.SPY_URL
YAHOO_URL = "https://query1.finance.yahoo.com/v8/finance/chart/SPY?period1=1577836800&period2=1787788800&interval=1d&events=history&includeAdjustedClose=true"
ORIGINAL_FETCH = base.fetch_spy_daily


def fetch_spy_daily_transport(out):
    try:
        rows = ORIGINAL_FETCH(out)
        base.SPY_URL = STOOQ_URL
        print(json.dumps({"benchmark_transport": "stooq", "rows": len(rows)}))
        return rows
    except Exception as stooq_error:
        req = urllib.request.Request(
            YAHOO_URL,
            headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json,text/plain,*/*"},
        )
        with urllib.request.urlopen(req, timeout=60) as r:
            payload = json.load(r)
        chart = (payload.get("chart") or {})
        if chart.get("error"):
            raise RuntimeError(f"Yahoo SPY transport error: {chart['error']}; Stooq={stooq_error}")
        results = chart.get("result") or []
        if not results:
            raise RuntimeError(f"Yahoo SPY result empty; Stooq={stooq_error}")
        result = results[0]
        timestamps = result.get("timestamp") or []
        quotes = (((result.get("indicators") or {}).get("quote") or [{}])[0].get("close") or [])
        rows = []
        for ts, close in zip(timestamps, quotes):
            if close is None:
                continue
            try:
                c = float(close)
            except (TypeError, ValueError):
                continue
            if c <= 0:
                continue
            d = datetime.fromtimestamp(int(ts), tz=timezone.utc).date()
            rows.append((d, c))
        rows.sort(key=lambda x: x[0])
        if len(rows) < 1000:
            raise RuntimeError(f"Yahoo SPY history too short rows={len(rows)}; Stooq={stooq_error}")
        with out.open("w", encoding="utf-8", newline="") as f:
            w = csv.writer(f)
            w.writerow(["Date", "Close"])
            for d, close in rows:
                w.writerow([d.isoformat(), repr(close)])
        base.SPY_URL = YAHOO_URL
        print(json.dumps({
            "benchmark_transport": "yahoo_fallback",
            "rows": len(rows),
            "stooq_error": str(stooq_error),
            "diagnostic_changes": "NONE"
        }))
        return rows


base.fetch_spy_daily = fetch_spy_daily_transport

if __name__ == "__main__":
    raise SystemExit(base.main())
