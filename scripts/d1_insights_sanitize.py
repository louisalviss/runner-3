#!/usr/bin/env python3
"""Print bounded D1 SQL Insights metrics without logging raw query strings."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

MAX_INPUT_BYTES = 2_000_000
MAX_QUERIES = 20
METRICS = (
    "numberOfTimesRun",
    "totalRowsRead",
    "totalRowsWritten",
    "avgRowsRead",
    "avgRowsWritten",
    "avgDurationMs",
)
SQL_OPERATION = re.compile(r"^\s*([a-zA-Z]+)")
SQL_TABLE = re.compile(r'\b(?:FROM|JOIN|UPDATE|INTO)\s+["\x60]?([a-zA-Z_][a-zA-Z_0-9]*)', re.I)


def sanitize(payload: object) -> list[dict]:
    if not isinstance(payload, list) or len(payload) > MAX_QUERIES:
        raise ValueError("insights_shape_or_limit")
    summary = []
    for item in payload:
        if not isinstance(item, dict):
            raise ValueError("insights_entry_shape")
        query = item.get("query")
        if not isinstance(query, str) or not query or len(query) > 100_000:
            raise ValueError("insights_query_shape")
        operation = SQL_OPERATION.match(query)
        row = {
            "query_sha16": hashlib.sha256(query.encode("utf-8")).hexdigest()[:16],
            "operation": operation.group(1).upper() if operation else "UNKNOWN",
            "tables": sorted(set(SQL_TABLE.findall(query))),
        }
        for metric in METRICS:
            value = item.get(metric)
            if value is not None and (isinstance(value, bool) or not isinstance(value, (float, int))):
                raise ValueError("insights_metric_shape")
            row[metric] = value
        summary.append(row)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--kind", choices=("reads", "writes"), required=True)
    args = parser.parse_args()
    try:
        if args.input.stat().st_size > MAX_INPUT_BYTES:
            raise ValueError("insights_input_too_large")
        payload = json.loads(args.input.read_text(encoding="utf-8"))
        result = sanitize(payload)
    except (ValueError, OSError):
        # Errors must not echo raw CLI output or query contents.
        raise SystemExit("D1_INSIGHTS_SANITIZE_FAILED")
    print("D1_INSIGHTS_SANITIZED_" + args.kind.upper() + "=" + json.dumps(result, separators=(",", ":")))


if __name__ == "__main__":
    main()
