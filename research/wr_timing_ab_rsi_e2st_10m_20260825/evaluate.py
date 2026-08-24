#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import statistics
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

SEEN = {"AAPL", "AMZN", "MSFT", "NVDA", "TSLA"}
EXPECTED_ALL = set("AAPL ADBE ADI ADP ADSK AEP ALNY AMAT AMD AMGN AMZN AVGO BKR CDNS CMCSA COST CPRT CSCO CSGP CSX CTSH DXCM EA EXC FANG FTNT GILD GOOG GOOGL HON IDXX INTC INTU ISRG KHC LRCX MAR MCHP MDLZ META MPWR MRVL MSFT MU NFLX NVDA ODFL ORLY PANW PAYX PCAR PEP PLTR PYPL QCOM REGN ROST SBUX SNPS TMUS TSLA TTWO TXN VRTX WDAY WDC WMT ZS".split())
PRIMARY = EXPECTED_ALL - SEEN
RNG = np.random.default_rng(20260825)


def pf(vals):
    gp = sum(max(float(x), 0.0) for x in vals)
    gl = sum(max(-float(x), 0.0) for x in vals)
    if gl == 0:
        return 999.0 if gp > 0 else None
    return gp / gl


def met(rows, key):
    vals = [float(x[key]) for x in rows]
    return {
        "n": len(vals),
        "PF": pf(vals),
        "mean_bps": statistics.mean([v * 10000.0 for v in vals]) if vals else None,
        "median_bps": statistics.median([v * 10000.0 for v in vals]) if vals else None,
        "sum_return": sum(vals),
        "win_rate": 100.0 * sum(v > 0 for v in vals) / len(vals) if vals else None,
    }


def pseudo_dd(rows, key):
    eq = peak = 0.0
    dd = 0.0
    for x in sorted(rows, key=lambda z: (z["signal_entry"], z["symbol"])):
        eq += float(x[key])
        peak = max(peak, eq)
        dd = min(dd, eq - peak)
    return dd


def bootstrap_day_delta(rows, reps=2000):
    groups = defaultdict(list)
    for x in rows:
        ts = pd.Timestamp(x["signal_entry"])
        day = ts.tz_convert("America/New_York").date().isoformat()
        groups[day].append(float(x["delta_bps"]))
    days = sorted(groups)
    samples = []
    for _ in range(reps):
        picked = RNG.choice(days, size=len(days), replace=True)
        vals = []
        for d in picked:
            vals.extend(groups[str(d)])
        samples.append(float(np.mean(vals)))
    return {
        "reps": reps,
        "days": len(days),
        "mean_delta_bps": float(np.mean([float(x["delta_bps"]) for x in rows])),
        "p2_5_bps": float(np.percentile(samples, 2.5)),
        "p50_bps": float(np.percentile(samples, 50)),
        "p97_5_bps": float(np.percentile(samples, 97.5)),
    }


def group_report(rows):
    a = met(rows, "a_return")
    b = met(rows, "b_return")
    executed = [x for x in rows if x["b_executed"]]
    b_exec = met(executed, "b_return")
    improvements = [float(x["entry_improvement_bps"]) for x in executed if x.get("entry_improvement_bps") is not None]
    delays = [float(x["entry_delay_vs_A_min"]) for x in executed if x.get("entry_delay_vs_A_min") is not None]
    return {
        "opportunities": len(rows),
        "A": a,
        "B_per_opportunity": b,
        "B_executed_only": b_exec,
        "delta_mean_bps_per_opportunity": b["mean_bps"] - a["mean_bps"] if rows else None,
        "executed": len(executed),
        "execution_rate": len(executed) / len(rows) if rows else 0.0,
        "missed_rate": 1.0 - len(executed) / len(rows) if rows else 1.0,
        "median_entry_improvement_bps": statistics.median(improvements) if improvements else None,
        "mean_entry_improvement_bps": statistics.mean(improvements) if improvements else None,
        "median_entry_delay_vs_A_min": statistics.median(delays) if delays else None,
        "pseudo_sequence_dd_A_sum_return": pseudo_dd(rows, "a_return"),
        "pseudo_sequence_dd_B_sum_return": pseudo_dd(rows, "b_return"),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    root = Path(args.input)
    out = Path(args.out); out.mkdir(parents=True, exist_ok=True)

    summaries = []
    rows = []
    for p in root.rglob("summary-*.json"):
        summaries.append(json.loads(p.read_text(encoding="utf-8")))
    for p in root.rglob("opportunities-*.jsonl"):
        for line in p.read_text(encoding="utf-8").splitlines():
            if line.strip():
                rows.append(json.loads(line))
    summaries.sort(key=lambda x: x.get("symbol", ""))
    rows.sort(key=lambda x: (x["signal_entry"], x["symbol"]))

    ok_symbols = {x["symbol"] for x in summaries if x.get("status") == "OK"}
    if ok_symbols != EXPECTED_ALL:
        missing = sorted(EXPECTED_ALL - ok_symbols)
        extra = sorted(ok_symbols - EXPECTED_ALL)
        raise SystemExit(f"WR 10m data coverage invalid; missing={missing} extra={extra}")

    primary = [x for x in rows if x["symbol"] in PRIMARY]
    all68 = [x for x in rows if x["symbol"] in EXPECTED_ALL]
    if len(primary) != 4023:
        raise SystemExit(f"frozen primary opportunity count mismatch: {len(primary)} != 4023")
    if len(all68) != 4356:
        raise SystemExit(f"frozen all68 opportunity count mismatch: {len(all68)} != 4356")

    primary_report = group_report(primary)
    all68_report = group_report(all68)

    years = {}
    for y in range(2022, 2027):
        yy = [x for x in primary if int(x["entry_year"]) == y]
        years[str(y)] = group_report(yy)
    pre = [x for x in primary if int(x["entry_year"]) <= 2025]
    pre_report = group_report(pre)

    symbol_stats = {}
    ge = 0
    symbol_deltas = []
    for sym in sorted(PRIMARY):
        ss = [x for x in primary if x["symbol"] == sym]
        r = group_report(ss)
        delta = r["delta_mean_bps_per_opportunity"]
        a_sum = r["A"]["sum_return"]
        b_sum = r["B_per_opportunity"]["sum_return"]
        b_ge_a = b_sum >= a_sum
        ge += int(b_ge_a)
        symbol_deltas.append(delta)
        symbol_stats[sym] = {**r, "B_cumulative_ge_A": b_ge_a}
    breadth_fraction = ge / len(PRIMARY)
    median_symbol_delta = statistics.median(symbol_deltas)

    boot = bootstrap_day_delta(primary, 2000)
    recent_wins = sum(
        years[str(y)]["B_per_opportunity"]["mean_bps"] > years[str(y)]["A"]["mean_bps"]
        for y in (2024, 2025, 2026)
    )

    a_pf = primary_report["A"]["PF"]
    b_pf = primary_report["B_executed_only"]["PF"]
    flags = {
        "matched_opportunities_eq_4023": len(primary) == 4023,
        "B_mean_ge_A_plus_10bps": primary_report["B_per_opportunity"]["mean_bps"] >= primary_report["A"]["mean_bps"] + 10.0,
        "B_exec_PF_ge_A_plus_0_05": b_pf is not None and a_pf is not None and b_pf >= a_pf + 0.05,
        "median_entry_improvement_positive": primary_report["median_entry_improvement_bps"] is not None and primary_report["median_entry_improvement_bps"] > 0.0,
        "execution_rate_ge_20pct": primary_report["execution_rate"] >= 0.20,
        "pre2026_B_mean_ge_A": pre_report["B_per_opportunity"]["mean_bps"] >= pre_report["A"]["mean_bps"],
        "recent_years_B_beats_A_ge_2": recent_wins >= 2,
        "bootstrap_95pct_lower_delta_positive": boot["p2_5_bps"] > 0.0,
        "symbol_breadth_or_median_delta_pass": breadth_fraction >= 0.55 or median_symbol_delta > 0.0,
    }
    passed = all(flags.values())

    report = {
        "status": "COMPLETE",
        "lineage": "RSI E2+ST external alpha -> WR 10m timing/execution matched A/B",
        "preregistration_commit": "4891b76fc1072dead7a5759b3fca7f330145bc8a",
        "parent_external_alpha_run": 32772722993,
        "parent_external_alpha_artifact": 9537584643,
        "parent_external_alpha_result_commit": "70652643f8ac5ed80a9b0cc419f295d35f1ad268",
        "design": {
            "A": "frozen parent actual ASK entry / BID SuperTrend exit",
            "B": "same opportunity and exit; first filled canonical WR 2.5.13 10m LONG stop-entry within 60m; miss=0",
            "WR_reference_commit": "27797cf9c4ea0a91b1bc8d62059d052c2c843eb5",
            "timing_window_minutes": 60,
            "target_timeframe_minutes": 10,
            "source": "paired Dukascopy M5 BID/ASK -> timestamp midpoint -> 10m regular-session bars",
        },
        "coverage": {
            "expected_symbols": 68,
            "ok_symbols": len(ok_symbols),
            "primary_symbols": 63,
            "primary_opportunities": len(primary),
            "all68_opportunities": len(all68),
        },
        "primary": primary_report,
        "secondary_all68": all68_report,
        "years_primary": years,
        "pre2026_primary": pre_report,
        "paired_day_block_bootstrap": boot,
        "symbol_comparison": {
            "B_cumulative_ge_A_symbols": ge,
            "fraction": breadth_fraction,
            "median_symbol_delta_mean_bps": median_symbol_delta,
            "symbols": symbol_stats,
        },
        "recent_years_B_beats_A": recent_wins,
        "gate_flags": flags,
        "PASS_WR_TIMING_INCREMENTAL": passed,
        "interpretation_if_pass": "WR may be retained only as INCREMENTAL_TIMING_EXECUTION_LAYER for this external alpha; WR standalone remains closed.",
        "interpretation_if_fail": "Keep external alpha without WR timing; no rescue tuning of this lineage.",
        "raw_symbol_summaries": summaries,
    }
    (out / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    with (out / "opportunities.jsonl").open("w", encoding="utf-8") as f:
        for x in rows:
            f.write(json.dumps(x) + "\n")

    print("PRIMARY", json.dumps({k: v for k, v in primary_report.items() if k not in ()}, indent=2))
    print("PRE2026", json.dumps(pre_report, indent=2))
    print("RECENT_WINS", recent_wins)
    print("BOOTSTRAP", json.dumps(boot, indent=2))
    print("BREADTH", ge, "/", len(PRIMARY), breadth_fraction, "MEDIAN_SYMBOL_DELTA", median_symbol_delta)
    print("FLAGS", json.dumps(flags, indent=2))
    print("PASS_WR_TIMING_INCREMENTAL", passed)


if __name__ == "__main__":
    main()
