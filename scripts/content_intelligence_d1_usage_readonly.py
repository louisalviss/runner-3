#!/usr/bin/env python3
"""Read-only D1 query-cost diagnosis; never runs SQL against a D1 database.

This replaces correlated per-item COUNT/EXISTS inventory queries that can
consume millions of D1 rows just to inspect a data pipeline.
"""
import argparse
import json
import subprocess
import sys


def load_insights(database, period, limit):
    cmd = ["wrangler", "d1", "insights", database,
           "--sort-by=reads", "--sort-type=sum", "--sort-direction=DESC",
           "--time-period=" + period, "--limit=" + str(limit), "--json"]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=40, check=False)
    if result.returncode:
        raise RuntimeError("D1 Insights unavailable (no SQL was run): " +
                           result.stderr[-400:])
    records = json.loads(result.stdout)
    if not isinstance(records, list):
        raise RuntimeError("Unexpected D1 Insights response")
    return records


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", default="runner3-content-intelligence")
    parser.add_argument("--period", choices=("1d", "7d"), default="1d")
    parser.add_argument("--limit", type=int, default=30)
    args = parser.parse_args()
    if args.limit < 1 or args.limit > 100:
        parser.error("--limit must be between 1 and 100")
    if args.database != "runner3-content-intelligence":
        parser.error("Only the canonical Content Intelligence database is allowed")
    records = load_insights(args.database, args.period, args.limit)
    report = {
        "mode": "D1_INSIGHTS_ONLY_NO_SQL", "database": args.database,
        "period": args.period, "reported_query_count": len(records),
        "reported_rows_read": sum(int(r.get("totalRowsRead") or 0) for r in records),
        "note": "Rows reflect grouped query insights for the requested rolling window; not an account-wide billing total",
        "top_queries": [
            {"sql_prefix": " ".join(str(r.get("query") or "").split())[:170],
             "executions": int(r.get("numberOfTimesRun") or 0),
             "rows_read": int(r.get("totalRowsRead") or 0)}
            for r in records[:min(15, len(records))]
        ]
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
