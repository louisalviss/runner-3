#!/usr/bin/env python3
from __future__ import annotations

import csv
import glob
import importlib.util
import io
import json
import math
import os
import sys
import time
import xml.etree.ElementTree as ET
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

HERE = Path(__file__).resolve().parent
OUT = Path(os.getenv("WR_OUT", "/tmp/wr"))
OUT.mkdir(parents=True, exist_ok=True)

REPORT_START = datetime(2025, 1, 1, tzinfo=timezone.utc)
REPORT_END = datetime(2026, 8, 15, tzinfo=timezone.utc)  # exclusive; signal time_close key
HISTORY_START = datetime(2024, 12, 1, tzinfo=timezone.utc)
LOAD_END = datetime(2026, 8, 19, tzinfo=timezone.utc)     # tail so pre-End signals can exit
TF_MIN = 5
TF_MS = TF_MIN * 60_000
COSTS_BPS = (4, 6, 8, 10, 12)

MONTHS = [(2024, 12)] + [(2025, m) for m in range(1, 13)] + [(2026, m) for m in range(1, 8)]
AUG_DAYS = range(1, 19)

BINANCE_S3 = "https://data.binance.vision"
LIST_ENDPOINT = "https://s3-ap-northeast-1.amazonaws.com/data.binance.vision"
PREFIX = "data/futures/um/monthly/klines/"


def load_modules():
    bspec = importlib.util.spec_from_file_location("wr_tv_base", HERE / "wr_tv_parity.py")
    base = importlib.util.module_from_spec(bspec)
    sys.modules[bspec.name] = base
    bspec.loader.exec_module(base)
    ref = base.load_ref()

    def pine_rightmost_pivots(v, left, right, high=True):
        out = [None] * len(v)
        ties = 0
        for conf in range(left + right, len(v)):
            c = conf - right
            x = v[c]
            L = v[c-left:c]
            R = v[c+1:c+right+1]
            if high:
                ok = all(x >= z for z in L) and all(x > z for z in R)
            else:
                ok = all(x <= z for z in L) and all(x < z for z in R)
            if ok:
                out[conf] = x
            elif x == (max(v[c-left:c+right+1]) if high else min(v[c-left:c+right+1])):
                ties += 1
        return [None] + out[:-1], ties

    ref.pivots = pine_rightmost_pivots
    base.TF = str(TF_MIN)
    base.TF_MS = TF_MS
    base.tv_tick = lambda info, vals: float(info["_tick"])
    return base, ref


def sess():
    s = requests.Session()
    s.headers["User-Agent"] = "runner3-wr2513-canonical-rerun/1.0"
    return s


def list_symbols(http: requests.Session):
    params = {"list-type": "2", "delimiter": "/", "prefix": PREFIX, "max-keys": "1000"}
    symbols = []
    nsx = {"s": "http://s3.amazonaws.com/doc/2006-03-01/"}
    while True:
        r = http.get(LIST_ENDPOINT, params=params, timeout=60)
        r.raise_for_status()
        root = ET.fromstring(r.content)
        for p in root.findall("s:CommonPrefixes/s:Prefix", nsx):
            x = p.text or ""
            if x.startswith(PREFIX):
                sym = x[len(PREFIX):].strip("/")
                if sym.endswith("USDT") and "_" not in sym:
                    symbols.append(sym)
        trunc = root.findtext("s:IsTruncated", default="false", namespaces=nsx) == "true"
        token = root.findtext("s:NextContinuationToken", default="", namespaces=nsx)
        if not trunc or not token:
            break
        params["continuation-token"] = token
    return sorted(set(symbols))


def get_zip(http: requests.Session, url: str):
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
            time.sleep(0.5 * (k + 1))
    return None


def read_zip(data, Bar):
    bars = []
    prices = []
    if not data:
        return bars, prices
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        text = z.read(z.namelist()[0]).decode()
    for row in csv.reader(io.StringIO(text)):
        if not row or not row[0].isdigit():
            continue
        ot = int(row[0]); ct = int(row[6])
        bars.append(Bar(ot, ct, float(row[1]), float(row[2]), float(row[3]), float(row[4])))
        if len(prices) < 12000:
            prices.extend(row[1:5])
    return bars, prices


def infer_tick(ref, prices):
    return float(ref.infer_tick(prices)) if prices else None


def load_symbol(http, ref, sym):
    bars = []
    prices = []
    for y, m in MONTHS:
        fn = f"{sym}-5m-{y:04d}-{m:02d}.zip"
        url = f"{BINANCE_S3}/data/futures/um/monthly/klines/{sym}/5m/{fn}"
        try:
            b, p = read_zip(get_zip(http, url), ref.Bar)
            bars.extend(b)
            if len(prices) < 12000:
                prices.extend(p[:12000-len(prices)])
        except Exception as e:
            print("MONTH_ERR", sym, y, m, repr(e), flush=True)
    for d in AUG_DAYS:
        fn = f"{sym}-5m-2026-08-{d:02d}.zip"
        url = f"{BINANCE_S3}/data/futures/um/daily/klines/{sym}/5m/{fn}"
        try:
            b, p = read_zip(get_zip(http, url), ref.Bar)
            bars.extend(b)
            if len(prices) < 12000:
                prices.extend(p[:12000-len(prices)])
        except Exception as e:
            print("DAY_ERR", sym, d, repr(e), flush=True)
    lo = int(HISTORY_START.timestamp() * 1000)
    hi = int(LOAD_END.timestamp() * 1000)
    ded = {b.ot: b for b in bars if lo <= b.ot < hi}
    bars = [ded[k] for k in sorted(ded)]
    tick = infer_tick(ref, prices)
    return bars, tick


def info_for_tick(tick):
    return {
        "timezone": "Etc/UTC",
        "exchange_timezone": "Etc/UTC",
        "session": "0000-0000:1234567",
        "subsessions": [{"id": "regular", "session": "0000-0000:1234567"}],
        "_tick": tick,
    }


def run_window(base, ref, bars, tick, start, end):
    base.START = start
    base.END = end
    trades, met = base.run_case(ref, bars, info_for_tick(tick), HISTORY_START, "start", True)
    return trades, met


def trade_cost_r(t, bps):
    dist = abs(float(t["e"]) - float(t["s"]))
    if dist <= 0:
        return 0.0
    return (float(t["e"]) / dist) * (bps / 10000.0)


def summarize(sym, bars, tick, trades):
    rs = [float(t["R"]) for t in trades]
    n = len(rs)
    gp = sum(max(r, 0.0) for r in rs)
    gl = sum(max(-r, 0.0) for r in rs)
    row = {
        "symbol": sym,
        "tf": TF_MIN,
        "bars": len(bars),
        "tick": tick,
        "n": n,
        "total_r": sum(rs),
        "avg_r": (sum(rs) / n if n else None),
        "win_rate": (100.0 * sum(r > 0 for r in rs) / n if n else None),
        "pf_r": (gp / gl if gl else None),
    }
    for bps in COSTS_BPS:
        row[f"net_r_{bps}bps"] = sum(float(t["R"]) - trade_cost_r(t, bps) for t in trades)
    by_year = {}
    for year in (2025, 2026):
        yr = [t for t in trades if datetime.fromtimestamp(int(t["signal"]) / 1000, tz=timezone.utc).year == year]
        by_year[str(year)] = {
            "n": len(yr),
            "total_r": sum(float(t["R"]) for t in yr),
            **{f"net_r_{bps}bps": sum(float(t["R"]) - trade_cost_r(t, bps) for t in yr) for bps in COSTS_BPS},
        }
    row["by_year"] = by_year
    return row


def oracle():
    base, ref = load_modules()
    http = sess()
    vn = timezone(timedelta(hours=7))
    def vn_dt(s): return datetime.fromisoformat(s).replace(tzinfo=vn).astimezone(timezone.utc)
    expected = {
        ("BNBUSDT", "W1"): (5, 3.420895522388),
        ("TRXUSDT", "W1"): (4, 2.6),
        ("BNBUSDT", "W2"): (3, 6.9),
        ("TRXUSDT", "W2"): (2, -2.0),
    }
    windows = {
        "W1": (vn_dt("2026-08-05T00:00:00"), vn_dt("2026-08-10T00:00:00")),
        "W2": (vn_dt("2026-08-10T00:00:00"), vn_dt("2026-08-16T00:00:00")),
    }
    # Recent oracle needs July warmup, so fetch 2026-07 monthly + Aug daily directly.
    global MONTHS, HISTORY_START
    old_months, old_hist = MONTHS, HISTORY_START
    MONTHS = [(2026, 7)]
    HISTORY_START = datetime(2026, 7, 20, tzinfo=timezone.utc)
    rows = []
    try:
        for sym in ("BNBUSDT", "TRXUSDT"):
            bars, tick = load_symbol(http, ref, sym)
            if not bars or not tick:
                raise SystemExit(f"ORACLE_DATA_FAIL {sym}")
            for label, (st, en) in windows.items():
                tr, _ = run_window(base, ref, bars, tick, st, en)
                got = (len(tr), sum(float(x["R"]) for x in tr))
                want = expected[(sym, label)]
                ok = got[0] == want[0] and abs(got[1] - want[1]) <= 0.02
                row = {"symbol": sym, "window": label, "n": got[0], "R": got[1], "expected_n": want[0], "expected_R": want[1], "pass": ok}
                rows.append(row)
                print("ORACLE", row, flush=True)
                if not ok:
                    raise SystemExit(7)
    finally:
        MONTHS, HISTORY_START = old_months, old_hist
    (OUT / "oracle.json").write_text(json.dumps(rows, indent=2))
    print("PARITY_4_WINDOWS=PASS", flush=True)


def shard():
    base, ref = load_modules()
    http = sess()
    shard_no = int(os.getenv("SHARD", "0"))
    shards = int(os.getenv("SHARDS", "8"))
    symbols = list_symbols(http)
    mine = [s for i, s in enumerate(symbols) if i % shards == shard_no]
    print("UNIVERSE", len(symbols), "SHARD", shard_no, len(mine), flush=True)
    sums, errors = [], []
    trades_path = OUT / f"trades-{shard_no}.jsonl"
    with trades_path.open("w") as tf:
        for j, sym in enumerate(mine, 1):
            try:
                bars, tick = load_symbol(http, ref, sym)
                if len(bars) < 100 or not tick:
                    print("SKIP", sym, len(bars), tick, flush=True)
                    continue
                tr, _ = run_window(base, ref, bars, tick, REPORT_START, REPORT_END)
                row = summarize(sym, bars, tick, tr)
                sums.append(row)
                for t in tr:
                    rec = {"symbol": sym, "tf": TF_MIN, **t}
                    rec["stop_pct"] = abs(float(t["e"]) - float(t["s"])) / float(t["e"]) * 100.0 if float(t["e"]) else None
                    tf.write(json.dumps(rec) + "\n")
                print(f"[{shard_no}] {j}/{len(mine)} {sym} bars={len(bars)} tick={tick} n={row['n']} R={row['total_r']:.3f}", flush=True)
            except Exception as e:
                errors.append({"symbol": sym, "error": repr(e)})
                print("ERROR", sym, repr(e), flush=True)
    (OUT / f"summary-{shard_no}.json").write_text(json.dumps(sums, indent=2))
    (OUT / f"errors-{shard_no}.json").write_text(json.dumps(errors, indent=2))
    (OUT / f"meta-{shard_no}.json").write_text(json.dumps({"shard": shard_no, "symbols_total": len(symbols), "symbols_assigned": len(mine), "completed": len(sums), "errors": len(errors)}, indent=2))


def merge():
    root = Path(os.getenv("MERGE_ROOT", "/tmp/all"))
    final = Path(os.getenv("FINAL_OUT", "/tmp/final"))
    final.mkdir(parents=True, exist_ok=True)
    rows, errors = [], []
    for p in root.rglob("summary-*.json"):
        rows += json.loads(p.read_text())
    for p in root.rglob("errors-*.json"):
        errors += json.loads(p.read_text())
    rows.sort(key=lambda x: (-(x.get("net_r_6bps") if x.get("net_r_6bps") is not None else -1e99), x["symbol"]))
    (final / "summary.json").write_text(json.dumps(rows, indent=2))
    (final / "errors.json").write_text(json.dumps(errors, indent=2))
    fields = ["symbol", "tf", "bars", "tick", "n", "total_r", "avg_r", "win_rate", "pf_r"] + [f"net_r_{b}bps" for b in COSTS_BPS]
    with (final / "summary.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k) for k in fields})
    with (final / "trades.jsonl").open("w") as dst:
        for p in root.rglob("trades-*.jsonl"):
            dst.write(p.read_text())
    elig = [r for r in rows if r["n"] >= 100]
    report = {
        "strategy": "WR 2.5.13 WIN canonical",
        "timeframe": "5m",
        "report_key": "signal candle close time [Start, End)",
        "report_start_utc": REPORT_START.isoformat(),
        "report_end_utc_exclusive": REPORT_END.isoformat(),
        "engine": "rightmost-tie pivots; <=1.5 ATR; embedded late-2025 news; Binance regular daily session guard; tick-aware fills; conservative same-bar",
        "symbols_completed": len(rows),
        "errors": len(errors),
        "symbols_n_ge_100": len(elig),
        "gross_positive_n_ge_100": sum((r.get("total_r") or 0) > 0 for r in elig),
        "net6_positive_n_ge_100": sum((r.get("net_r_6bps") or 0) > 0 for r in elig),
        "total_trades": sum(r["n"] for r in rows),
        "aggregate_gross_r": sum(r["total_r"] for r in rows),
        **{f"aggregate_net_r_{b}bps": sum(r[f"net_r_{b}bps"] for r in rows) for b in COSTS_BPS},
        "top20_net6": [{k: r.get(k) for k in ("symbol", "n", "total_r", "net_r_6bps")} for r in rows[:20]],
    }
    (final / "report.json").write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2), flush=True)


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "shard"
    if mode == "oracle":
        oracle()
    elif mode == "shard":
        shard()
    elif mode == "merge":
        merge()
    else:
        raise SystemExit(f"unknown mode {mode}")


if __name__ == "__main__":
    main()
