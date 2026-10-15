#!/usr/bin/env python3
"""Offline QA for native Gate-first R7 archival evidence. No network/order side effects."""
import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
revisions = json.loads((ROOT / "gatefirst_revision_extra_10_originals.json").read_text(encoding="utf-8"))
assert len(revisions) == 10 and len({r["revision_id"] for r in revisions}) == 10
assert all("error" not in r for r in revisions)
r282 = next(r for r in revisions if r["revision_id"] == "282")
lhx = next(c for c in r282["selected"] if c["Symbol"] == "LHX")
assert lhx["Entry Status"] == "ENTRY_READY"
assert lhx["Execution Signal"] == "NONE"
assert "market is closed" in lhx["Signal Gate Note"]
assert "delayed" in lhx["Signal Gate Note"]
rows = list(csv.DictReader((ROOT / "entry_ready_unissued_next_session_7.csv").open(encoding="utf-8")))
assert len(rows) == 7
miss = [r for r in rows if r["classification"] == "POTENTIAL_UNISSUED_RECHECK"]
assert len(miss) == 1
case = miss[0]
assert (case["symbol"], case["NYSE_session"]) == ("LHX", "2026-09-14")
assert 245 <= float(case["regular_session_open"]) <= 250
assert float(case["low"]) <= 250
assert case["actual_BUY_SIGNAL_before_open"] == "False"
assert case["original_broker_order_proven"] == "False"
assert abs(float(case["price_only_net_5D_pct"]) + 0.7098) < 0.001
assert abs(float(case["price_only_net_20D_pct"]) + 4.8743) < 0.001
assert all(r["actual_BUY_SIGNAL_before_open"] == "False" for r in rows)
summary = json.loads((ROOT / "QA_REVISION_R7.json").read_text(encoding="utf-8"))
assert summary["union_distinct_revision_bodies"] == 20
assert summary["no_new_historical_BUY_discovered"] is True
assert 2.23 < summary["LHX_2026_09_14_old_bull_bear_math_RR_50bps"] < 2.24
print("R7_OFFLINE_QA_PASS")
