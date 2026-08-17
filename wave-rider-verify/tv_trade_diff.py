#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Both inputs must contain one row per CLOSED trade, ordered chronologically.
# Python input is the *_trades.csv emitted by wr_v2513_parity_pack.py.
# TradingView input may use canonical names below or common aliases.
ALIASES = {
    "signal_time": ["signal_time", "signal close", "signal_close", "signal_close_time", "signal utc", "signal_time_utc"],
    "side": ["side", "direction"],
    "entry_time": ["entry_time", "entry time", "entry_time_utc"],
    "exit_time": ["exit_time", "exit time", "exit_time_utc"],
    "entry": ["entry", "entry_price", "entry price", "planned_entry"],
    "stop": ["stop", "stop_price", "stop price"],
    "target": ["target", "target_price", "target price", "tp"],
    "exit_price": ["exit_price", "exit price"],
    "exit_reason": ["exit_reason", "exit reason", "reason"],
    "canon_r": ["canon_r", "r", "trade_r", "result_r", "total r"],
}

REQUIRED = [
    "signal_time", "side", "entry_time", "exit_time", "entry",
    "exit_price", "exit_reason", "canon_r",
]
OPTIONAL = ["stop", "target"]
TIME_FIELDS = {"signal_time", "entry_time", "exit_time"}
NUM_FIELDS = {"entry", "stop", "target", "exit_price", "canon_r"}


def norm_name(s: str) -> str:
    return " ".join(s.strip().lower().replace("_", " ").split())


def pick_columns(fieldnames: list[str], required: bool = True) -> dict[str, str]:
    normalized = {norm_name(x): x for x in fieldnames}
    out: dict[str, str] = {}
    for canonical, aliases in ALIASES.items():
        for a in aliases:
            hit = normalized.get(norm_name(a))
            if hit is not None:
                out[canonical] = hit
                break
    missing = [k for k in REQUIRED if k not in out]
    if required and missing:
        raise ValueError(
            "TradingView CSV is not normalized enough for exact parity. Missing columns: "
            + ", ".join(missing)
            + ". Required one-row-per-closed-trade schema: " + ", ".join(REQUIRED)
        )
    return out


def parse_time(v: str) -> int:
    s = v.strip()
    if not s:
        raise ValueError("empty timestamp")
    # Integer epoch milliseconds/seconds are accepted for lossless exports.
    if s.isdigit():
        n = int(s)
        return n if n > 10_000_000_000 else n * 1000
    s = s.replace(" UTC", "+00:00").replace("Z", "+00:00")
    d = datetime.fromisoformat(s)
    if d.tzinfo is None:
        d = d.replace(tzinfo=timezone.utc)
    return int(round(d.astimezone(timezone.utc).timestamp() * 1000))


def parse_num(v: str) -> float:
    s = v.strip().replace(",", "")
    if not s:
        raise ValueError("empty numeric field")
    return float(s)


def normalize_row(row: dict[str, str], cols: dict[str, str]) -> dict[str, Any]:
    x: dict[str, Any] = {}
    for k, col in cols.items():
        v = row.get(col, "")
        if k in TIME_FIELDS:
            x[k] = parse_time(v)
        elif k in NUM_FIELDS:
            x[k] = parse_num(v)
        elif k == "side":
            q = v.strip().upper()
            if q in {"BUY", "LONG", "L"}: q = "LONG"
            if q in {"SELL", "SHORT", "S"}: q = "SHORT"
            x[k] = q
        elif k == "exit_reason":
            x[k] = v.strip().upper().replace(" ", "_")
        else:
            x[k] = v.strip()
    return x


def load_csv(path: Path, *, tv: bool) -> list[dict[str, Any]]:
    with path.open(newline="", encoding="utf-8-sig") as f:
        r = csv.DictReader(f)
        if not r.fieldnames:
            raise ValueError(f"no CSV header: {path}")
        cols = pick_columns(r.fieldnames, required=True)
        rows = [normalize_row(row, cols) for row in r]
    # Never silently sort: ordering itself is part of parity. Assert monotonic signal times.
    for i in range(1, len(rows)):
        if rows[i]["signal_time"] < rows[i-1]["signal_time"]:
            raise ValueError(f"{path}: rows are not ordered by signal_time at row {i+1}")
    return rows


def near(a: float, b: float, tol: float) -> bool:
    return math.isclose(a, b, rel_tol=0.0, abs_tol=tol)


def trade_key(x: dict[str, Any]) -> tuple[Any, Any]:
    return x.get("signal_time"), x.get("side")


def row_diff(py: dict[str, Any], tv: dict[str, Any], price_tol: float, r_tol: float) -> dict[str, Any]:
    diffs: dict[str, Any] = {}
    fields = REQUIRED + [k for k in OPTIONAL if k in py and k in tv]
    for k in fields:
        a, b = py.get(k), tv.get(k)
        if k in TIME_FIELDS:
            if a != b: diffs[k] = {"python": a, "tradingview": b, "delta_ms": (b-a) if a is not None and b is not None else None}
        elif k == "canon_r":
            if not near(float(a), float(b), r_tol): diffs[k] = {"python": a, "tradingview": b, "delta": float(b)-float(a)}
        elif k in NUM_FIELDS:
            if not near(float(a), float(b), price_tol): diffs[k] = {"python": a, "tradingview": b, "delta": float(b)-float(a)}
        else:
            if a != b: diffs[k] = {"python": a, "tradingview": b}
    return diffs


def context(rows: list[dict[str, Any]], i: int, radius: int = 2) -> list[dict[str, Any]]:
    a = max(0, i-radius); b = min(len(rows), i+radius+1)
    return [{"index": j, **rows[j]} for j in range(a, b)]


def compare(py: list[dict[str, Any]], tv: list[dict[str, Any]], price_tol: float, r_tol: float) -> dict[str, Any]:
    n = min(len(py), len(tv))
    for i in range(n):
        d = row_diff(py[i], tv[i], price_tol, r_tol)
        if d:
            kind = "FIELD_MISMATCH"
            # Diagnose the common sequence-shift case without hiding the first mismatch.
            if i+1 < len(py) and trade_key(py[i+1]) == trade_key(tv[i]):
                kind = "PYTHON_EXTRA_OR_TV_MISSING_TRADE"
            elif i+1 < len(tv) and trade_key(py[i]) == trade_key(tv[i+1]):
                kind = "TV_EXTRA_OR_PYTHON_MISSING_TRADE"
            return {
                "status": "FAIL",
                "reason": kind,
                "first_divergence_index_zero_based": i,
                "first_divergence_trade_number_one_based": i+1,
                "diff": d,
                "python_trade": py[i],
                "tradingview_trade": tv[i],
                "python_context": context(py, i),
                "tradingview_context": context(tv, i),
                "python_count": len(py),
                "tradingview_count": len(tv),
            }
    if len(py) != len(tv):
        i = n
        return {
            "status": "FAIL",
            "reason": "TRADE_COUNT_MISMATCH_AFTER_COMMON_PREFIX",
            "first_divergence_index_zero_based": i,
            "first_divergence_trade_number_one_based": i+1,
            "python_trade": py[i] if i < len(py) else None,
            "tradingview_trade": tv[i] if i < len(tv) else None,
            "python_context": context(py, min(i, max(len(py)-1, 0))) if py else [],
            "tradingview_context": context(tv, min(i, max(len(tv)-1, 0))) if tv else [],
            "python_count": len(py),
            "tradingview_count": len(tv),
        }
    return {
        "status": "PASS",
        "reason": "EXACT_ORDERED_TRADE_SEQUENCE_MATCH",
        "python_count": len(py),
        "tradingview_count": len(tv),
        "price_abs_tolerance": price_tol,
        "r_abs_tolerance": r_tol,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description="Find the first WR v2.5.13 Python-vs-TradingView trade divergence.")
    ap.add_argument("--python", dest="py", required=True, help="Exact-reference *_trades.csv")
    ap.add_argument("--tradingview", dest="tv", required=True, help="Normalized one-row-per-closed-trade TradingView CSV")
    ap.add_argument("--out", default="tv_trade_diff.json")
    ap.add_argument("--price-tol", type=float, default=1e-9)
    ap.add_argument("--r-tol", type=float, default=1e-9)
    args = ap.parse_args()

    py = load_csv(Path(args.py), tv=False)
    tv = load_csv(Path(args.tv), tv=True)
    result = compare(py, tv, args.price_tol, args.r_tol)
    Path(args.out).write_text(json.dumps(result, indent=2, sort_keys=False), encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=False))
    raise SystemExit(0 if result["status"] == "PASS" else 1)


if __name__ == "__main__":
    main()
