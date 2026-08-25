#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import os
import statistics
from pathlib import Path


def pf(vals):
    gp = sum(max(float(x), 0.0) for x in vals)
    gl = sum(max(-float(x), 0.0) for x in vals)
    return gp / gl if gl else (999.0 if gp > 0 else None)


def met(trades, key):
    vals = [float(x[key]) for x in trades]
    return {
        "n": len(vals),
        "PF": pf(vals),
        "mean_bps": statistics.mean([v * 10000 for v in vals]) if vals else None,
        "median_bps": statistics.median([v * 10000 for v in vals]) if vals else None,
        "sum_return": sum(vals),
        "win_rate": 100.0 * sum(v > 0 for v in vals) / len(vals) if vals else None,
    }


def main():
    ap = argparse.ArgumentParser(description="Evaluate merged Super RSI backtest artifacts")
    ap.add_argument("--profile", required=True)
    ap.add_argument("--input", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    profile = json.loads(Path(args.profile).read_text(encoding="utf-8"))
    root = Path(args.input)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    summaries, trades = [], []
    for p in root.rglob("summary-*.json"):
        try:
            summaries.append(json.loads(p.read_text(encoding="utf-8")))
        except Exception:
            pass

    for p in root.rglob("trades-*.jsonl"):
        for line in p.read_text(encoding="utf-8").splitlines():
            if line.strip():
                try:
                    trades.append(json.loads(line))
                except Exception:
                    pass

    summaries.sort(key=lambda x: x.get("symbol", ""))
    trades.sort(key=lambda x: (x.get("entry_time", ""), x.get("symbol", "")))

    expected = set(profile["universe"])
    excluded = set(profile.get("primary_exclude", []))
    primary_symbols = expected - excluded

    def group(symbols):
        ok = [s for s in summaries if s.get("symbol") in symbols and s.get("status") == "OK"]
        tt = [t for t in trades if t.get("symbol") in symbols]
        actual = met(tt, "actual_return")
        midpoint = met(tt, "mid_return")

        bysym = {}
        for sym in sorted(symbols):
            st = [t for t in tt if t["symbol"] == sym]
            if st:
                bysym[sym] = {
                    "actual": met(st, "actual_return"),
                    "midpoint": met(st, "mid_return"),
                }

        eligible_pf = [
            v["actual"]["PF"]
            for v in bysym.values()
            if v["actual"]["n"] >= 5 and v["actual"]["PF"] is not None
        ]
        positive = sum(v["actual"]["sum_return"] > 0 for v in bysym.values())

        return {
            "expected_symbols": len(symbols),
            "ok_symbols": len(ok),
            "actual": actual,
            "midpoint": midpoint,
            "positive_symbols": positive,
            "symbols_with_trades": len(bysym),
            "positive_symbol_fraction": positive / len(bysym) if bysym else 0.0,
            "median_symbol_PF_ge5": statistics.median(eligible_pf) if eligible_pf else None,
            "symbols": bysym,
        }

    primary = group(primary_symbols)
    all_symbols = group(expected)
    primary_trades = [t for t in trades if t["symbol"] in primary_symbols]

    start_year = int(profile["dates"]["report_start"][:4])
    end_year = int(profile["dates"]["end"][:4])
    years = {}
    for y in range(start_year, end_year + 1):
        yt = [t for t in primary_trades if int(t.get("entry_year", 0)) == y]
        years[str(y)] = {
            "actual": met(yt, "actual_return"),
            "midpoint": met(yt, "mid_return"),
        }

    pre_cutoff_year = int(profile.get("pre_cutoff_year", end_year - 1))
    pre = [t for t in primary_trades if int(t.get("entry_year", 0)) <= pre_cutoff_year]
    pre_actual = met(pre, "actual_return")

    recent_years = profile.get("recent_years", [max(start_year, end_year - 2), end_year - 1, end_year])
    recent_threshold = float(profile["gates"]["recent_year_pf_threshold"])
    positive_recent_years = sum(
        years.get(str(y), {}).get("actual", {}).get("PF") is not None
        and years[str(y)]["actual"]["PF"] > recent_threshold
        for y in recent_years
    )

    entry_sp = [
        float(t["entry_spread_bps"])
        for t in primary_trades
        if t.get("entry_spread_bps") is not None
    ]
    exit_sp = [
        float(t["exit_spread_bps"])
        for t in primary_trades
        if t.get("exit_spread_bps") is not None
    ]

    g = profile["gates"]
    flags = {
        "coverage": primary["ok_symbols"] >= int(g["coverage_min"]),
        "trades": primary["actual"]["n"] >= int(g["trades_min"]),
        "actual_pf": primary["actual"]["PF"] is not None and primary["actual"]["PF"] >= float(g["actual_pf_min"]),
        "actual_mean_bps": primary["actual"]["mean_bps"] is not None and primary["actual"]["mean_bps"] >= float(g["actual_mean_bps_min"]),
        "mid_pf": primary["midpoint"]["PF"] is not None and primary["midpoint"]["PF"] >= float(g["mid_pf_min"]),
        "mid_mean_positive": primary["midpoint"]["mean_bps"] is not None and primary["midpoint"]["mean_bps"] > 0,
        "positive_symbol_fraction": primary["positive_symbol_fraction"] >= float(g["positive_symbol_fraction_min"]),
        "median_symbol_pf": primary["median_symbol_PF_ge5"] is not None and primary["median_symbol_PF_ge5"] >= float(g["median_symbol_pf_min"]),
        "pre_cutoff_actual_pf": pre_actual["PF"] is not None and pre_actual["PF"] >= float(g["pre2026_actual_pf_min"]),
        "recent_positive_years": positive_recent_years >= int(g["recent_years_min"]),
    }
    passed = all(flags.values())

    report = {
        "status": "COMPLETE",
        "strategy_name": profile["strategy_name"],
        "profile": profile["name"],
        "profile_status": profile["status"],
        "asset_class": profile["asset_class"],
        "timeframe_minutes": profile["timeframe_minutes"],
        "git_sha": os.environ.get("GITHUB_SHA"),
        "strategy": profile["strategy"],
        "execution": profile["execution"],
        "primary_symbols": sorted(primary_symbols),
        "excluded_from_primary": sorted(excluded),
        "primary": primary,
        "all_universe": all_symbols,
        "years_primary": years,
        "pre_cutoff_year": pre_cutoff_year,
        "pre_cutoff_primary_actual": pre_actual,
        "recent_years": recent_years,
        "positive_recent_years": positive_recent_years,
        "median_entry_spread_bps": statistics.median(entry_sp) if entry_sp else None,
        "median_exit_spread_bps": statistics.median(exit_sp) if exit_sp else None,
        "gate_flags": flags,
        "PASS_PROFILE_GATES": passed,
        "lineage": profile.get("lineage", {}),
        "frozen_helper": profile.get("frozen_helper", {}),
    }

    (out / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    with (out / "trades.jsonl").open("w", encoding="utf-8") as f:
        for t in trades:
            f.write(json.dumps(t) + "\n")

    with (out / "symbol_summary.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["symbol", "status", "trades", "actual_pf", "actual_mean_bps", "mid_pf", "mid_mean_bps"])
        for s in summaries:
            w.writerow([
                s.get("symbol"), s.get("status"), s.get("trades"),
                s.get("actual_pf"), s.get("actual_mean_bps"),
                s.get("mid_pf"), s.get("mid_mean_bps"),
            ])

    with (out / "yearly_summary.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["year", "n", "actual_pf", "actual_mean_bps", "mid_pf", "mid_mean_bps"])
        for y in sorted(years):
            a, m = years[y]["actual"], years[y]["midpoint"]
            w.writerow([y, a["n"], a["PF"], a["mean_bps"], m["PF"], m["mean_bps"]])

    summary_md = [
        f"# {profile['strategy_name']} backtest",
        "",
        f"- Profile: `{profile['name']}`",
        f"- Asset class: `{profile['asset_class']}`",
        f"- Timeframe: `{profile['timeframe_minutes']}m`",
        f"- Primary symbols OK: **{primary['ok_symbols']}/{primary['expected_symbols']}**",
        f"- Primary trades: **{primary['actual']['n']}**",
        f"- Actual PF: **{primary['actual']['PF']}**",
        f"- Actual mean: **{primary['actual']['mean_bps']} bps/trade**",
        f"- Positive-symbol fraction: **{primary['positive_symbol_fraction']:.2%}**",
        f"- Median symbol PF: **{primary['median_symbol_PF_ge5']}**",
        f"- Median entry spread: **{report['median_entry_spread_bps']} bps**",
        f"- Median exit spread: **{report['median_exit_spread_bps']} bps**",
        f"- PASS_PROFILE_GATES: **{passed}**",
        "",
        "## Gate flags",
        "",
    ] + [f"- `{k}`: **{v}**" for k, v in flags.items()]
    (out / "SUMMARY.md").write_text("\n".join(summary_md) + "\n", encoding="utf-8")

    print(json.dumps({
        "profile": profile["name"],
        "primary_ok": primary["ok_symbols"],
        "primary_expected": primary["expected_symbols"],
        "trades": primary["actual"]["n"],
        "actual_pf": primary["actual"]["PF"],
        "actual_mean_bps": primary["actual"]["mean_bps"],
        "positive_symbol_fraction": primary["positive_symbol_fraction"],
        "PASS_PROFILE_GATES": passed,
    }, indent=2))


if __name__ == "__main__":
    main()
