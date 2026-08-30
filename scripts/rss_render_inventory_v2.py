#!/usr/bin/env python3
"""Runner15 render inventory wrapper.

All 15 logical sources now have durable Runner mirrors. Hồ Quốc Tuấn and
vnhacker are no longer placeholder direct-verification rows.
"""

import argparse
import json
from datetime import datetime, timezone, timedelta, date
from pathlib import Path

import rss_render_inventory as legacy

SOURCE_KEYS = [
    "tinhte", "genk", "vohoanghac", "fulcrum", "nghiencuuquocte",
    "noema", "gamek", "projectsyndicate", "economist", "theatlantic",
    "grimlogs", "scientificamerican", "quanta", "hoquoctuan", "vnhacker",
]
TZ_VN = timezone(timedelta(hours=7))


def build_inventory(root, day):
    legacy.SOURCE_KEYS = list(SOURCE_KEYS)
    legacy.DIRECT_KEYS = []
    inv = legacy.build_inventory(root, day)
    inv["version"] = 2
    inv["scope"] = "rss-render-source-accounting-runner15"
    inv["logicalSourceCount"] = 15
    inv["runnerSourceCount"] = 15
    inv["directSourceCount"] = 0
    inv["directVerificationPending"] = []
    inv["ok"] = (
        not (inv.get("problems") or [])
        and len(inv.get("sourceRows") or []) == 15
        and all(row.get("status") == "ok" for row in inv.get("sourceRows") or [])
        and all(row.get("rawCount") is not None for row in inv.get("sourceRows") or [])
    )
    contract = dict(inv.get("renderContract") or {})
    contract.update({
        "mustAccountAll15Sources": True,
        "all15BackedByRunnerMirrors": True,
        "directVerificationRequired": False,
        "missingSourceFailsClosed": True,
    })
    inv["renderContract"] = contract
    return inv


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    ap.add_argument("--date", help="YYYY-MM-DD; default today in UTC+7")
    ap.add_argument("--out", help="output JSON path")
    args = ap.parse_args()
    root = Path(args.root).resolve()
    day = date.fromisoformat(args.date) if args.date else datetime.now(TZ_VN).date()
    inv = build_inventory(root, day)
    out = Path(args.out) if args.out else root / "data" / "rss-reader" / f"render-inventory-{day.isoformat()}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(inv, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "ok": inv["ok"],
        "date": inv["date"],
        "runnerRawItemCount": inv["runnerRawItemCount"],
        "runnerSourceCount": inv["runnerSourceCount"],
        "out": str(out),
    }, ensure_ascii=False))
    return 0 if inv["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
