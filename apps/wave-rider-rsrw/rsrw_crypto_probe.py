#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import inspect
import json
import math
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

CANON_DIR = Path(os.getenv("WR_CANON_DIR", "/tmp/wr-canonical"))
OUT = Path(os.getenv("WR_RSRW_OUT", "apps/wave-rider-rsrw/output"))
SYMBOLS = [x.strip().upper() for x in os.getenv("WR_RSRW_SYMBOLS", "SOLUSDT,ETHUSDT,XRPUSDT").split(",") if x.strip()]
LENGTHS = [int(x) for x in os.getenv("WR_RSRW_LENGTHS", "10,21,50").split(",")]
USE_SLOPE = os.getenv("WR_RSRW_USE_SLOPE", "1") != "0"


def load_canonical():
    p = CANON_DIR / "wr_canonical_crypto_5m.py"
    if not p.exists():
        raise SystemExit(f"missing canonical engine: {p}")
    sys.path.insert(0, str(CANON_DIR))
    spec = importlib.util.spec_from_file_location("wr_crypto_canonical", p)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def ema_with_gates(asset_bars, btc_bars, length):
    btc = {b.ot: b.c for b in btc_bars}
    alpha = 2.0 / (length + 1.0)
    prev = None
    long_gate, short_gate, rows = {}, {}, {}
    matched = 0
    for b in asset_bars:
        bc = btc.get(b.ot)
        if bc in (None, 0):
            long_gate[b.ot] = False
            short_gate[b.ot] = False
            continue
        ratio = b.c / bc
        cur = ratio if prev is None else alpha * ratio + (1.0 - alpha) * prev
        slope_up = prev is not None and cur > prev
        slope_down = prev is not None and cur < prev
        lg = ratio > cur and ((not USE_SLOPE) or slope_up)
        sg = ratio < cur and ((not USE_SLOPE) or slope_down)
        long_gate[b.ot] = lg
        short_gate[b.ot] = sg
        rows[b.ot] = {"ratio": ratio, "ema": cur, "long": lg, "short": sg}
        prev = cur
        matched += 1
    return long_gate, short_gate, rows, matched


def patch_run_case(base):
    original = base.run_case
    src = inspect.getsource(original)
    long_old = "nl=allowed and safe and z['sra_ok'] and b.c>b.o and lr and b.c>z['res'] and b.l<=z['res']"
    short_old = "ns=allowed and safe and z['sra_ok'] and b.c<b.o and sr and b.c<z['sup'] and b.h>=z['sup']"
    long_new = long_old + " and RS_GATE_LONG.get(b.ot,False)"
    short_new = short_old + " and RS_GATE_SHORT.get(b.ot,False)"
    if src.count(long_old) != 1 or src.count(short_old) != 1:
        raise SystemExit("RS_PATCH_ANCHOR_MISMATCH")
    src = src.replace(long_old, long_new, 1).replace(short_old, short_new, 1)
    ns = base.__dict__
    exec(compile(src, "<rsrw_run_case>", "exec"), ns)
    patched = ns["run_case"]
    base.run_case = original
    return original, patched


def streak_and_dd(trades):
    cur_l = max_l = 0
    eq = peak = 0.0
    max_dd = 0.0
    for t in trades:
        r = float(t["R"])
        if r < 0:
            cur_l += 1
            max_l = max(max_l, cur_l)
        else:
            cur_l = 0
        eq += r
        peak = max(peak, eq)
        max_dd = max(max_dd, peak - eq)
    return max_l, max_dd


def summarize(canon, symbol, length, trades, matched_bars, total_bars):
    rs = [float(t["R"]) for t in trades]
    n = len(rs)
    gp = sum(max(r, 0.0) for r in rs)
    gl = sum(max(-r, 0.0) for r in rs)
    max_l, max_dd_r = streak_and_dd(trades)
    row = {
        "symbol": symbol,
        "ema_length": length,
        "use_slope": USE_SLOPE,
        "n": n,
        "total_r": sum(rs),
        "avg_r": (sum(rs) / n if n else None),
        "win_rate": (100.0 * sum(r > 0 for r in rs) / n if n else None),
        "pf_r": (gp / gl if gl else None),
        "max_losing_streak": max_l,
        "max_drawdown_r": max_dd_r,
        "net_r_6bps": sum(float(t["R"]) - canon.trade_cost_r(t, 6) for t in trades),
        "matched_ratio_bars": matched_bars,
        "asset_bars": total_bars,
    }
    for year in (2025, 2026):
        y = [t for t in trades if datetime.fromtimestamp(int(t["signal"]) / 1000, tz=timezone.utc).year == year]
        row[f"{year}_n"] = len(y)
        row[f"{year}_r"] = sum(float(t["R"]) for t in y)
    return row


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    canon = load_canonical()
    base, ref = canon.load_modules()
    original_run_case, rs_run_case = patch_run_case(base)
    http = canon.sess()

    print("LOAD BTCUSDT", flush=True)
    btc_bars, btc_tick = canon.load_symbol(http, ref, "BTCUSDT")
    if len(btc_bars) < 1000 or not btc_tick:
        raise SystemExit("BTC_DATA_FAIL")

    results, all_trades, errors = [], [], []
    for symbol in SYMBOLS:
        print("LOAD", symbol, flush=True)
        try:
            bars, tick = canon.load_symbol(http, ref, symbol)
            if len(bars) < 1000 or not tick:
                raise RuntimeError(f"insufficient data bars={len(bars)} tick={tick}")
            for length in LENGTHS:
                lg, sg, rs_rows, matched = ema_with_gates(bars, btc_bars, length)
                base.RS_GATE_LONG = lg
                base.RS_GATE_SHORT = sg
                base.run_case = rs_run_case
                trades, _ = canon.run_window(base, ref, bars, tick, canon.REPORT_START, canon.REPORT_END)
                row = summarize(canon, symbol, length, trades, matched, len(bars))
                results.append(row)
                for t in trades:
                    sig = int(t["signal"])
                    info = rs_rows.get(sig - (sig % canon.TF_MS)) or rs_rows.get(sig - canon.TF_MS + 1) or {}
                    all_trades.append({"symbol": symbol, "ema_length": length, **t, "rs_ratio": info.get("ratio"), "rs_ema": info.get("ema")})
                print("RESULT", json.dumps(row, separators=(",", ":")), flush=True)
        except Exception as e:
            errors.append({"symbol": symbol, "error": repr(e)})
            print("ERROR", symbol, repr(e), flush=True)
        finally:
            base.run_case = original_run_case

    payload = {
        "status": "COMPLETE" if not errors else "PARTIAL",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "strategy": "WR canonical crypto 5m + RS/BTC confirmation",
        "canonical_source_commit": "d1e7e6e5dcfdc3423860fdce7f1ad84f652fe1eb",
        "report_start_utc": canon.REPORT_START.isoformat(),
        "report_end_utc_exclusive": canon.REPORT_END.isoformat(),
        "benchmark": "BTCUSDT",
        "rule": "LONG: asset/BTC > EMA(asset/BTC) and EMA slope up; SHORT: asset/BTC < EMA(asset/BTC) and EMA slope down",
        "symbols": SYMBOLS,
        "ema_lengths": LENGTHS,
        "results": results,
        "errors": errors,
    }
    (OUT / "result.json").write_text(json.dumps(payload, indent=2) + "\n")
    with (OUT / "trades.jsonl").open("w") as f:
        for x in all_trades:
            f.write(json.dumps(x, separators=(",", ":")) + "\n")
    print(json.dumps(payload, indent=2), flush=True)
    if errors:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
