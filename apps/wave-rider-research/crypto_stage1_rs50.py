#!/usr/bin/env python3
from __future__ import annotations

import csv
import io
import json
import os
import time
import zipfile
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import requests

TF_MS = 300_000
EMA_LEN = 50
BINANCE = "https://data.binance.vision"
SOURCE_ROOT = Path(os.getenv("SOURCE_ROOT", "/tmp/source"))
OUT = Path(os.getenv("OUT", "/tmp/out"))
MERGE_ROOT = Path(os.getenv("MERGE_ROOT", "/tmp/all"))
FINAL_OUT = Path(os.getenv("FINAL_OUT", "/tmp/final"))
SHARD = int(os.getenv("SHARD", "0"))
SHARDS = int(os.getenv("SHARDS", "8"))
EXPECTED_BASE_N = 359
EXPECTED_BASE_R6 = -91.2313


def sess():
    s = requests.Session()
    s.headers["User-Agent"] = "runner3-wr-stage1-rs50/1.0"
    return s


def get_zip(http, url):
    for k in range(3):
        try:
            r = http.get(url, timeout=45)
            if r.status_code == 404:
                return None
            r.raise_for_status()
            return r.content
        except Exception:
            if k == 2:
                raise
            time.sleep(0.4 * (k + 1))


def read_zip(data):
    if not data:
        return []
    out = []
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        text = z.read(z.namelist()[0]).decode()
    for row in csv.reader(io.StringIO(text)):
        if not row or not row[0].isdigit():
            continue
        out.append((int(row[0]), float(row[4])))
    return out


def month_iter():
    d = date(2024, 12, 1)
    end = date(2026, 7, 1)
    while d <= end:
        yield d.year, d.month
        d = (d.replace(day=28) + timedelta(days=4)).replace(day=1)


def load_symbol(http, sym):
    rows = []
    for y, m in month_iter():
        fn = f"{sym}-5m-{y:04d}-{m:02d}.zip"
        url = f"{BINANCE}/data/futures/um/monthly/klines/{sym}/5m/{fn}"
        rows.extend(read_zip(get_zip(http, url)))
    for d in range(1, 19):
        fn = f"{sym}-5m-2026-08-{d:02d}.zip"
        url = f"{BINANCE}/data/futures/um/daily/klines/{sym}/5m/{fn}"
        rows.extend(read_zip(get_zip(http, url)))
    ded = {ot: c for ot, c in rows}
    return [(ot, ded[ot]) for ot in sorted(ded)]


def load_source_trades():
    files = list(SOURCE_ROOT.rglob("trades.jsonl"))
    if len(files) != 1:
        raise SystemExit(f"SOURCE_TRADES_FILE_COUNT={len(files)}")
    out = []
    for ln in files[0].read_text().splitlines():
        if not ln.strip():
            continue
        t = json.loads(ln)
        if t.get("variant") == "canonical":
            out.append(t)
    if len(out) != EXPECTED_BASE_N:
        raise SystemExit(f"SOURCE_BASE_N_MISMATCH got={len(out)} expected={EXPECTED_BASE_N}")
    return out


def cost_r(t, bps):
    d = abs(float(t["e"]) - float(t["s"]))
    if d <= 0:
        return 0.0
    return (float(t["e"]) / d) * (bps / 10000.0)


def net_r(t, bps):
    return float(t["R"]) - cost_r(t, bps)


def ema50_gates(asset, btc):
    btc_map = dict(btc)
    alpha = 2.0 / (EMA_LEN + 1.0)
    prev = None
    gates = {}
    matched = 0
    for ot, ac in asset:
        bc = btc_map.get(ot)
        if bc in (None, 0):
            continue
        ratio = ac / bc
        cur = ratio if prev is None else alpha * ratio + (1.0 - alpha) * prev
        gates[ot] = bool(prev is not None and ratio > cur and cur > prev)
        prev = cur
        matched += 1
    return gates, matched


def metrics(trades, bps=6):
    vals = [net_r(t, bps) for t in trades]
    gp = sum(max(x, 0.0) for x in vals)
    gl = sum(max(-x, 0.0) for x in vals)
    return {
        "n": len(vals),
        "R": sum(vals),
        "avg_R": sum(vals) / len(vals) if vals else None,
        "PF": gp / gl if gl else None,
    }


def episode_metrics(trades):
    by_sig = defaultdict(list)
    by_day = defaultdict(list)
    for t in trades:
        r = net_r(t, 6)
        by_sig[int(t["signal"])].append(r)
        d = datetime.fromtimestamp(int(t["signal"]) / 1000, tz=timezone.utc).date().isoformat()
        by_day[d].append(r)
    eps = [sum(v) / len(v) for v in by_sig.values()]
    days = [sum(v) / len(v) for v in by_day.values()]
    return {
        "episode_count": len(eps),
        "episode_normalized_R": sum(eps),
        "daily_count": len(days),
        "daily_normalized_R": sum(days),
        "peak_same_signal": max((len(v) for v in by_sig.values()), default=0),
    }


def summarize(trades):
    return {
        "gross": metrics(trades, 0),
        "net_4bps": metrics(trades, 4),
        "net_6bps": metrics(trades, 6),
        "net_8bps": metrics(trades, 8),
        "long_6bps": metrics([t for t in trades if t["side"] == "L"], 6),
        "short_6bps": metrics([t for t in trades if t["side"] == "S"], 6),
        "by_year": {
            str(y): metrics([
                t for t in trades
                if datetime.fromtimestamp(int(t["signal"]) / 1000, tz=timezone.utc).year == y
            ], 6)
            for y in (2025, 2026)
        },
        "episode": episode_metrics(trades),
    }


def shard():
    OUT.mkdir(parents=True, exist_ok=True)
    all_trades = load_source_trades()
    symbols = sorted({t["symbol"] for t in all_trades})
    mine = [s for i, s in enumerate(symbols) if i % SHARDS == SHARD]
    mine_set = set(mine)
    base = [t for t in all_trades if t["symbol"] in mine_set]
    http = sess()
    btc = load_symbol(http, "BTCUSDT")
    if len(btc) < 1000:
        raise SystemExit("BTC_DATA_FAIL")

    gates_by_symbol = {}
    coverage = {}
    for sym in mine:
        longs = [t for t in base if t["symbol"] == sym and t["side"] == "L"]
        if not longs:
            continue
        asset = load_symbol(http, sym)
        if len(asset) < 1000:
            raise SystemExit(f"ASSET_DATA_FAIL {sym} bars={len(asset)}")
        gates, matched = ema50_gates(asset, btc)
        missing = []
        for t in longs:
            feature_ot = int(t["signal"]) - TF_MS + 1
            if feature_ot not in gates:
                missing.append(feature_ot)
        if missing:
            raise SystemExit(f"RS_GATE_MISSING {sym} n={len(missing)} sample={missing[:3]}")
        gates_by_symbol[sym] = gates
        coverage[sym] = {"asset_bars": len(asset), "matched_ratio_bars": matched, "long_trades": len(longs)}

    filtered = []
    decisions = []
    for t in base:
        keep = True
        if t["side"] == "L":
            feature_ot = int(t["signal"]) - TF_MS + 1
            keep = gates_by_symbol[t["symbol"]][feature_ot]
            decisions.append({
                "symbol": t["symbol"],
                "signal": int(t["signal"]),
                "feature_ot": feature_ot,
                "keep": keep,
            })
        if keep:
            filtered.append(t)

    payload = {
        "status": "COMPLETE",
        "shard": SHARD,
        "shards": SHARDS,
        "symbols_total": len(symbols),
        "symbols_assigned": mine,
        "rule": "LONG only: asset/BTC close > EMA50(asset/BTC) and EMA50 slope up at canonical signal bar close; SHORT unchanged",
        "source": "historical causal Stage1 canonical trades from corrected artifact run 32618199814",
        "base": summarize(base),
        "rs50": summarize(filtered),
        "coverage": coverage,
        "decisions": decisions,
    }
    (OUT / f"result-{SHARD}.json").write_text(json.dumps(payload, indent=2) + "\n")
    with (OUT / f"base-{SHARD}.jsonl").open("w") as f:
        for t in base:
            f.write(json.dumps(t, separators=(",", ":")) + "\n")
    with (OUT / f"rs50-{SHARD}.jsonl").open("w") as f:
        for t in filtered:
            f.write(json.dumps(t, separators=(",", ":")) + "\n")
    print(json.dumps({"shard": SHARD, "base": payload["base"]["net_6bps"], "rs50": payload["rs50"]["net_6bps"]}, indent=2), flush=True)


def read_jsonl(pattern):
    out = []
    for p in MERGE_ROOT.rglob(pattern):
        for ln in p.read_text().splitlines():
            if ln.strip():
                out.append(json.loads(ln))
    return out


def merge():
    FINAL_OUT.mkdir(parents=True, exist_ok=True)
    result_files = list(MERGE_ROOT.rglob("result-*.json"))
    if len(result_files) != SHARDS:
        raise SystemExit(f"SHARD_COUNT_MISMATCH got={len(result_files)} expected={SHARDS}")
    base = read_jsonl("base-*.jsonl")
    rs50 = read_jsonl("rs50-*.jsonl")
    b = summarize(base)
    r = summarize(rs50)
    got_n = b["net_6bps"]["n"]
    got_r = b["net_6bps"]["R"]
    if got_n != EXPECTED_BASE_N or abs(got_r - EXPECTED_BASE_R6) > 5e-4:
        raise SystemExit(f"BASELINE_PARITY_FAIL n={got_n} R6={got_r}")

    report = {
        "status": "COMPLETE",
        "research_question": "On causally reconstructed historical Crypto Stage1 canonical WR trades, does frozen RS50 Long-only confirmation create a robust edge?",
        "rule": "LONG: asset/BTC close > EMA50(asset/BTC) AND EMA50 slope up at signal-bar close; SHORT unchanged",
        "no_parameter_sweep": True,
        "baseline_parity": {"expected_n": EXPECTED_BASE_N, "expected_R6": EXPECTED_BASE_R6, "actual_n": got_n, "actual_R6": got_r, "pass": True},
        "baseline": b,
        "rs50": r,
        "delta_rs50_minus_baseline_6bps": {
            "R": r["net_6bps"]["R"] - b["net_6bps"]["R"],
            "n": r["net_6bps"]["n"] - b["net_6bps"]["n"],
            "avg_R": r["net_6bps"]["avg_R"] - b["net_6bps"]["avg_R"],
        },
        "guardrails": [
            "Historical Stage1 membership and canonical WR trades are reused, not re-fit",
            "EMA length fixed at 50 before this run",
            "Only Long side receives RS50 gate; Short is unchanged",
            "Signal-bar close is used causally; no future bar data",
            "4/6/8bps and episode/day normalization are reported",
            "No post-hoc symbol whitelist or threshold rescue",
        ],
    }
    (FINAL_OUT / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    with (FINAL_OUT / "rs50-trades.jsonl").open("w") as f:
        for t in rs50:
            f.write(json.dumps(t, separators=(",", ":")) + "\n")
    print(json.dumps(report, indent=2), flush=True)


if __name__ == "__main__":
    mode = os.getenv("MODE", "shard")
    shard() if mode == "shard" else merge()
