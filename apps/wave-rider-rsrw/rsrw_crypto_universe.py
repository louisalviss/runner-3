#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import inspect
import json
import math
import os
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

CANON_DIR = Path(os.getenv("WR_CANON_DIR", "/tmp/wr-canonical"))
OUT = Path(os.getenv("WR_RSRW_OUT", "apps/wave-rider-rsrw/universe-output"))
LENGTHS = [int(x) for x in os.getenv("WR_RSRW_LENGTHS", "10,21,50").split(",") if x.strip()]
USE_SLOPE = os.getenv("WR_RSRW_USE_SLOPE", "1") != "0"
SHARD = int(os.getenv("WR_RSRW_SHARD", "0"))
SHARDS = int(os.getenv("WR_RSRW_SHARDS", "8"))
BENCHMARK = "BTCUSDT"


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
    exec(compile(src, "<rsrw_universe_run_case>", "exec"), ns)
    patched = ns["run_case"]
    base.run_case = original
    return original, patched


def streak_and_dd(trades):
    cur_l = max_l = 0
    eq = peak = 0.0
    max_dd = 0.0
    for t in sorted(trades, key=lambda x: (int(x["signal"]), x.get("symbol", ""))):
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


def summarize(canon, symbol, variant, trades, matched_bars=None, total_bars=None):
    rs = [float(t["R"]) for t in trades]
    n = len(rs)
    gp = sum(max(r, 0.0) for r in rs)
    gl = sum(max(-r, 0.0) for r in rs)
    max_l, max_dd_r = streak_and_dd(trades)
    row = {
        "symbol": symbol,
        "variant": variant,
        "ema_length": None if variant == "BASE" else int(variant.replace("EMA", "")),
        "use_slope": USE_SLOPE if variant != "BASE" else None,
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
        row[f"{year}_net_r_6bps"] = sum(float(t["R"]) - canon.trade_cost_r(t, 6) for t in y)
    return row


def run_shard():
    OUT.mkdir(parents=True, exist_ok=True)
    canon = load_canonical()
    base, ref = canon.load_modules()
    original_run_case, rs_run_case = patch_run_case(base)
    http = canon.sess()

    print("LOAD BENCHMARK", BENCHMARK, flush=True)
    btc_bars, btc_tick = canon.load_symbol(http, ref, BENCHMARK)
    if len(btc_bars) < 1000 or not btc_tick:
        raise SystemExit("BTC_DATA_FAIL")

    universe = [s for s in canon.list_symbols(http) if s != BENCHMARK]
    mine = [s for i, s in enumerate(universe) if i % SHARDS == SHARD]
    print("UNIVERSE", len(universe), "SHARD", SHARD, "ASSIGNED", len(mine), flush=True)

    results, all_trades, errors, skips = [], [], [], []
    for idx, symbol in enumerate(mine, 1):
        print(f"[{SHARD}] {idx}/{len(mine)} LOAD {symbol}", flush=True)
        try:
            bars, tick = canon.load_symbol(http, ref, symbol)
            if len(bars) < 1000 or not tick:
                skips.append({"symbol": symbol, "reason": f"insufficient_data bars={len(bars)} tick={tick}"})
                print("SKIP", symbol, skips[-1]["reason"], flush=True)
                continue

            base.run_case = original_run_case
            base_trades, _ = canon.run_window(base, ref, bars, tick, canon.REPORT_START, canon.REPORT_END)
            base_row = summarize(canon, symbol, "BASE", base_trades, None, len(bars))
            results.append(base_row)
            for t in base_trades:
                all_trades.append({"symbol": symbol, "variant": "BASE", **t})

            for length in LENGTHS:
                lg, sg, rs_rows, matched = ema_with_gates(bars, btc_bars, length)
                base.RS_GATE_LONG = lg
                base.RS_GATE_SHORT = sg
                base.run_case = rs_run_case
                trades, _ = canon.run_window(base, ref, bars, tick, canon.REPORT_START, canon.REPORT_END)
                variant = f"EMA{length}"
                row = summarize(canon, symbol, variant, trades, matched, len(bars))
                results.append(row)
                for t in trades:
                    sig = int(t["signal"])
                    ot = sig - canon.TF_MS + 1
                    info = rs_rows.get(ot, {})
                    all_trades.append({"symbol": symbol, "variant": variant, **t, "rs_ratio": info.get("ratio"), "rs_ema": info.get("ema")})
                print("RESULT", json.dumps(row, separators=(",", ":")), flush=True)
        except Exception as e:
            errors.append({"symbol": symbol, "error": repr(e)})
            print("ERROR", symbol, repr(e), flush=True)
        finally:
            base.run_case = original_run_case

    payload = {
        "status": "COMPLETE" if not errors else "PARTIAL",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "strategy": "WR canonical crypto 5m + RS/BTC full-universe confirmation",
        "canonical_source_commit": "d1e7e6e5dcfdc3423860fdce7f1ad84f652fe1eb",
        "report_start_utc": canon.REPORT_START.isoformat(),
        "report_end_utc_exclusive": canon.REPORT_END.isoformat(),
        "benchmark": BENCHMARK,
        "rule": "LONG: asset/BTC > EMA(asset/BTC) and EMA slope up; SHORT: asset/BTC < EMA(asset/BTC) and EMA slope down",
        "ema_lengths": LENGTHS,
        "universe_symbols_ex_btc": len(universe),
        "shard": SHARD,
        "shards": SHARDS,
        "assigned": len(mine),
        "symbols_with_results": len({r['symbol'] for r in results}),
        "results": results,
        "skips": skips,
        "errors": errors,
    }
    (OUT / f"result-{SHARD}.json").write_text(json.dumps(payload, indent=2) + "\n")
    with (OUT / f"trades-{SHARD}.jsonl").open("w") as f:
        for x in all_trades:
            f.write(json.dumps(x, separators=(",", ":")) + "\n")
    print(json.dumps({k: payload[k] for k in ("status", "shard", "assigned", "symbols_with_results")}, indent=2), flush=True)


def aggregate_rows(rows):
    out = {}
    for variant, vr in sorted(rows.items()):
        n = sum(int(r["n"]) for r in vr)
        total = sum(float(r["total_r"]) for r in vr)
        wins = sum((float(r["win_rate"]) / 100.0) * int(r["n"]) for r in vr if r.get("win_rate") is not None)
        out[variant] = {
            "symbols": len(vr),
            "symbols_with_trades": sum(int(r["n"]) > 0 for r in vr),
            "n": n,
            "total_r": total,
            "avg_r": total / n if n else None,
            "win_rate": 100.0 * wins / n if n else None,
            "net_r_6bps": sum(float(r["net_r_6bps"]) for r in vr),
            "2025_n": sum(int(r["2025_n"]) for r in vr),
            "2025_r": sum(float(r["2025_r"]) for r in vr),
            "2025_net_r_6bps": sum(float(r["2025_net_r_6bps"]) for r in vr),
            "2026_n": sum(int(r["2026_n"]) for r in vr),
            "2026_r": sum(float(r["2026_r"]) for r in vr),
            "2026_net_r_6bps": sum(float(r["2026_net_r_6bps"]) for r in vr),
        }
    base = out.get("BASE")
    if base:
        for variant, z in out.items():
            if variant == "BASE":
                continue
            z["delta_n_vs_base"] = z["n"] - base["n"]
            z["retained_trade_pct"] = 100.0 * z["n"] / base["n"] if base["n"] else None
            z["delta_total_r_vs_base"] = z["total_r"] - base["total_r"]
            z["delta_avg_r_vs_base"] = z["avg_r"] - base["avg_r"] if z["avg_r"] is not None and base["avg_r"] is not None else None
            z["delta_net_r_6bps_vs_base"] = z["net_r_6bps"] - base["net_r_6bps"]
    return out


def run_merge():
    root = Path(os.getenv("WR_RSRW_MERGE_ROOT", "/tmp/all"))
    final = Path(os.getenv("WR_RSRW_FINAL_OUT", "/tmp/final"))
    final.mkdir(parents=True, exist_ok=True)
    payloads, results, skips, errors, trades = [], [], [], [], []
    for p in root.rglob("result-*.json"):
        try:
            x = json.loads(p.read_text())
            payloads.append(x)
            results.extend(x.get("results", []))
            skips.extend(x.get("skips", []))
            errors.extend(x.get("errors", []))
        except Exception as e:
            errors.append({"file": str(p), "error": repr(e)})
    for p in root.rglob("trades-*.jsonl"):
        for line in p.read_text().splitlines():
            try:
                trades.append(json.loads(line))
            except Exception:
                pass

    by_variant = defaultdict(list)
    by_symbol = defaultdict(dict)
    for r in results:
        by_variant[r["variant"]].append(r)
        by_symbol[r["symbol"]][r["variant"]] = r
    aggregate = aggregate_rows(by_variant)

    comparisons = []
    for symbol, variants in sorted(by_symbol.items()):
        b = variants.get("BASE")
        if not b:
            continue
        for length in LENGTHS:
            v = variants.get(f"EMA{length}")
            if not v:
                continue
            comparisons.append({
                "symbol": symbol,
                "ema_length": length,
                "base_n": b["n"],
                "filter_n": v["n"],
                "retained_trade_pct": 100.0 * v["n"] / b["n"] if b["n"] else None,
                "base_total_r": b["total_r"],
                "filter_total_r": v["total_r"],
                "delta_total_r": v["total_r"] - b["total_r"],
                "base_avg_r": b["avg_r"],
                "filter_avg_r": v["avg_r"],
                "delta_avg_r": (v["avg_r"] - b["avg_r"]) if v["avg_r"] is not None and b["avg_r"] is not None else None,
                "base_net_r_6bps": b["net_r_6bps"],
                "filter_net_r_6bps": v["net_r_6bps"],
                "delta_net_r_6bps": v["net_r_6bps"] - b["net_r_6bps"],
            })

    top = {}
    for length in LENGTHS:
        xs = [x for x in comparisons if x["ema_length"] == length]
        top[f"EMA{length}"] = {
            "top_improvers_total_r": sorted(xs, key=lambda x: x["delta_total_r"], reverse=True)[:25],
            "top_degraders_total_r": sorted(xs, key=lambda x: x["delta_total_r"])[:25],
            "symbols_total_r_improved": sum(x["delta_total_r"] > 0 for x in xs),
            "symbols_avg_r_improved": sum((x["delta_avg_r"] or 0) > 0 for x in xs if x["delta_avg_r"] is not None),
            "symbols_net6_improved": sum(x["delta_net_r_6bps"] > 0 for x in xs),
            "symbols_compared": len(xs),
        }

    report = {
        "status": "COMPLETE" if len(payloads) == SHARDS and not errors else "PARTIAL",
        "strategy": "WR canonical crypto 5m + RS/BTC full-universe confirmation",
        "canonical_source_commit": "d1e7e6e5dcfdc3423860fdce7f1ad84f652fe1eb",
        "benchmark": BENCHMARK,
        "ema_lengths": LENGTHS,
        "shards_found": len(payloads),
        "symbols_discovered_ex_btc": max((x.get("universe_symbols_ex_btc", 0) for x in payloads), default=0),
        "symbols_with_results": len(by_symbol),
        "skips": skips,
        "errors": errors,
        "aggregate": aggregate,
        "comparison_summary": top,
        "per_symbol_comparisons": comparisons,
    }
    (final / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    (final / "per-symbol.json").write_text(json.dumps(results, indent=2) + "\n")
    with (final / "trades.jsonl").open("w") as f:
        for x in trades:
            f.write(json.dumps(x, separators=(",", ":")) + "\n")
    print(json.dumps({
        "status": report["status"],
        "shards_found": report["shards_found"],
        "symbols_discovered_ex_btc": report["symbols_discovered_ex_btc"],
        "symbols_with_results": report["symbols_with_results"],
        "aggregate": aggregate,
    }, indent=2), flush=True)


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "shard"
    if mode == "shard":
        run_shard()
    elif mode == "merge":
        run_merge()
    else:
        raise SystemExit(f"unknown mode: {mode}")


if __name__ == "__main__":
    main()
