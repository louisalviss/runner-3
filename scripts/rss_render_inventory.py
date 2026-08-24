#!/usr/bin/env python3
import argparse
import json
from datetime import datetime, timedelta, timezone, date
from pathlib import Path

TZ_VN = timezone(timedelta(hours=7))
SOURCE_KEYS = [
    "tinhte", "genk", "vohoanghac", "fulcrum", "nghiencuuquocte",
    "noema", "gamek", "projectsyndicate", "economist", "theatlantic",
    "grimlogs", "scientificamerican", "quanta",
]
DIRECT_KEYS = ["hoquoctuan", "vnhacker"]


def parse_iso(value):
    if not value:
        return None
    value = str(value).strip()
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(value)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def window_for(day):
    start_local = datetime(day.year, day.month, day.day, tzinfo=TZ_VN)
    end_local = start_local + timedelta(days=1)
    return start_local.astimezone(timezone.utc), end_local.astimezone(timezone.utc)


def build_inventory(root, day):
    start_utc, end_utc = window_for(day)
    rows = []
    total_raw = 0
    problems = []

    for key in SOURCE_KEYS:
        path = root / "data" / "rss-reader" / "sources" / f"{key}.json"
        if not path.exists():
            rows.append({"sourceKey": key, "mode": "runner3", "status": "missing", "rawCount": None, "items": []})
            problems.append(f"missing mirror: {key}")
            continue
        try:
            obj = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            rows.append({"sourceKey": key, "mode": "runner3", "status": "invalid-json", "rawCount": None, "items": []})
            problems.append(f"invalid mirror {key}: {exc}")
            continue
        if obj.get("sourceKey") != key:
            problems.append(f"sourceKey mismatch: expected {key}, got {obj.get('sourceKey')}")
        in_window = []
        for item in obj.get("items") or []:
            dt = parse_iso(item.get("publishedAt"))
            if dt is None or not (start_utc <= dt < end_utc):
                continue
            in_window.append({
                "key": item.get("key"),
                "articleId": item.get("articleId"),
                "noteId": item.get("noteId"),
                "itemType": item.get("itemType"),
                "title": item.get("title"),
                "canonicalUrl": item.get("canonicalUrl"),
                "publishedAt": item.get("publishedAt"),
            })
        in_window.sort(key=lambda x: x.get("publishedAt") or "", reverse=True)
        total_raw += len(in_window)
        rows.append({
            "sourceKey": key,
            "mode": "runner3",
            "status": "ok",
            "mirrorCount": obj.get("count"),
            "newestPublishedAt": obj.get("newestPublishedAt"),
            "rawCount": len(in_window),
            "items": in_window,
        })

    for key in DIRECT_KEYS:
        rows.append({
            "sourceKey": key,
            "mode": "chatgpt-direct",
            "status": "requires-direct-verification",
            "rawCount": None,
            "items": [],
        })

    return {
        "version": 1,
        "scope": "rss-render-source-accounting",
        "timezone": "Asia/Ho_Chi_Minh",
        "date": day.isoformat(),
        "windowUtc": {"start": start_utc.isoformat().replace("+00:00", "Z"), "end": end_utc.isoformat().replace("+00:00", "Z")},
        "logicalSourceCount": 15,
        "runnerSourceCount": 13,
        "directSourceCount": 2,
        "runnerRawItemCount": total_raw,
        "sourceRows": rows,
        "problems": problems,
        "ok": not problems and len(rows) == 15,
        "renderContract": {
            "mustAccountAll15Sources": True,
            "mustRecordRawKeptFilteredPerSource": True,
            "manifestCountMustEqualSumKept": True,
            "rawPositiveKeptZeroRequiresFilterReason": True,
            "mismatchFailsClosed": True,
        },
    }


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
    print(json.dumps({"ok": inv["ok"], "date": inv["date"], "runnerRawItemCount": inv["runnerRawItemCount"], "out": str(out)}, ensure_ascii=False))
    raise SystemExit(0 if inv["ok"] else 2)


if __name__ == "__main__":
    main()
