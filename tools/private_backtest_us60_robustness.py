#!/usr/bin/env python3
from __future__ import annotations

import argparse
import bisect
import csv
import io
import json
import math
import statistics
import tempfile
import urllib.request
from collections import defaultdict
from datetime import date, datetime, timezone
from pathlib import Path

import private_backtest_worker_v2 as core
import private_backtest_concentration as concentration

PROJECT = "private-backtest"
SPY_URL = "https://stooq.com/q/d/l/?s=spy.us&i=d&d1=20200101&d2=20260825"


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def parse_dt(v):
    s = str(v).strip()
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def pf(vals):
    gp = sum(x for x in vals if x > 0)
    gl = -sum(x for x in vals if x < 0)
    if gl > 0:
        return gp / gl
    return 999.0 if gp > 0 else None


def metrics(vals):
    vals = list(vals)
    if not vals:
        return {"n": 0, "pf": None, "mean_bps": None, "median_bps": None, "win_rate_pct": None, "sum_bps": 0.0}
    return {
        "n": len(vals),
        "pf": pf(vals),
        "mean_bps": statistics.fmean(vals),
        "median_bps": statistics.median(vals),
        "win_rate_pct": 100.0 * sum(x > 0 for x in vals) / len(vals),
        "sum_bps": sum(vals),
    }


def weighted_metrics(rows, weights):
    if len(rows) != len(weights) or not rows:
        raise RuntimeError("weighted_metrics input mismatch")
    total_w = sum(weights)
    gp = sum(w * r["bps"] for r, w in zip(rows, weights) if r["bps"] > 0)
    gl = -sum(w * r["bps"] for r, w in zip(rows, weights) if r["bps"] < 0)
    mean = sum(w * r["bps"] for r, w in zip(rows, weights)) / total_w
    return {
        "n": len(rows),
        "pf": gp / gl if gl > 0 else (999.0 if gp > 0 else None),
        "weighted_mean_bps": mean,
        "weight_sum": total_w,
    }


def gt(v, threshold):
    return v is not None and v > threshold


def ge(v, threshold):
    return v is not None and v >= threshold


def quarter_key(dt):
    q = (dt.month - 1) // 3 + 1
    return f"{dt.year}-Q{q}"


def quarter_index(key):
    y, q = key.split("-Q")
    return int(y) * 4 + int(q) - 1


def fetch_spy_daily(out: Path):
    req = urllib.request.Request(SPY_URL, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=60) as r:
        data = r.read()
    if len(data) < 10000 or b"Date" not in data[:200]:
        raise RuntimeError(f"unexpected SPY payload size={len(data)}")
    out.write_bytes(data)
    text = data.decode("utf-8-sig")
    rows = []
    for row in csv.DictReader(io.StringIO(text)):
        try:
            d = date.fromisoformat(row["Date"])
            close = float(row["Close"])
        except Exception:
            continue
        if close > 0:
            rows.append((d, close))
    rows.sort(key=lambda x: x[0])
    if len(rows) < 1000:
        raise RuntimeError(f"SPY history too short rows={len(rows)}")
    return rows


def build_spy_states(rows):
    dates = [d for d, _ in rows]
    closes = [c for _, c in rows]
    logrets = [None]
    for i in range(1, len(closes)):
        logrets.append(math.log(closes[i] / closes[i - 1]))
    states = {}
    for i, (d, close) in enumerate(rows):
        if i < 199:
            continue
        sma200 = statistics.fmean(closes[i - 199:i + 1])
        if i < 20:
            continue
        rr = [x for x in logrets[i - 19:i + 1] if x is not None]
        if len(rr) != 20:
            continue
        # population stdev is deterministic and appropriate for descriptive regime labeling.
        vol20 = statistics.pstdev(rr) * math.sqrt(252.0)
        states[d] = {
            "close": close,
            "sma200": sma200,
            "vol20_ann": vol20,
            "trend": "bull" if close >= sma200 else "bear",
            "vol": "high_vol" if vol20 >= 0.20 else "low_vol",
        }
    return dates, states


def previous_state(trade_date, dates, states):
    i = bisect.bisect_left(dates, trade_date) - 1
    while i >= 0:
        d = dates[i]
        if d in states:
            return d, states[d]
        i -= 1
    return None, None


def rows_to_csv(path: Path, rows, fields):
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for row in rows:
            w.writerow({k: row.get(k) for k in fields})


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    args = ap.parse_args()
    c = read_json(Path(args.config))
    source_scope = c["source_scope"]
    out_scope = c["scope"]
    work = Path(tempfile.mkdtemp(prefix="us60-robustness-"))

    report_path = work / "report.json"
    trades_path = work / "trades.jsonl"
    core.download_artifact(PROJECT, source_scope, "final/report.json", report_path)
    core.download_artifact(PROJECT, source_scope, "final/trades.jsonl", trades_path)
    report = read_json(report_path)

    symbols = [str(x).upper() for x in report.get("primary_symbols", [])]
    if len(symbols) != int(c["expected_symbols"]):
        raise RuntimeError(f"symbol parity failed {len(symbols)} != {c['expected_symbols']}")
    symbol_set = set(symbols)
    raw_all = [json.loads(x) for x in trades_path.read_text(encoding="utf-8").splitlines() if x.strip()]
    raw = [r for r in raw_all if str(r.get("symbol", "")).upper() in symbol_set]
    if len(raw) != int(c["expected_trades"]):
        raise RuntimeError(f"trade parity failed {len(raw)} != {c['expected_trades']}")
    if not raw or "actual_return_bps" not in raw[0] or "entry_time" not in raw[0]:
        raise RuntimeError(f"required trade fields unavailable keys={sorted(raw[0].keys()) if raw else []}")

    trades = []
    for i, r in enumerate(raw):
        trades.append({
            "idx": i,
            "symbol": str(r["symbol"]).upper(),
            "entry": parse_dt(r["entry_time"]),
            "bps": float(r["actual_return_bps"]),
        })
    base = metrics(t["bps"] for t in trades)
    target = report["primary"]["actual"]
    if abs(base["pf"] - float(target["PF"])) > 1e-8:
        raise RuntimeError(f"baseline PF parity failed {base['pf']} vs {target['PF']}")
    if abs(base["mean_bps"] - float(target["mean_bps"])) > 1e-6:
        raise RuntimeError(f"baseline mean parity failed {base['mean_bps']} vs {target['mean_bps']}")

    # Sector mapping uses the exact same helper as the already-completed concentration diagnostic.
    sector_meta = concentration.fetch_sector_map(symbols)
    for t in trades:
        t["sector"] = sector_meta[t["symbol"]]["sector"]
    sectors = sorted(set(t["sector"] for t in trades))

    thresholds = c["diagnostic_thresholds"]

    # Leave-one-symbol-out.
    loso = []
    for s in symbols:
        m = metrics(t["bps"] for t in trades if t["symbol"] != s)
        loso.append({"excluded_symbol": s, **m, "pf_delta_vs_baseline": m["pf"] - base["pf"] if m["pf"] is not None else None})
    loso.sort(key=lambda x: (999 if x["pf"] is None else x["pf"], x["excluded_symbol"]))

    # Leave-one-sector-out.
    losector = []
    for sec in sectors:
        excluded_symbols = sorted({t["symbol"] for t in trades if t["sector"] == sec})
        m = metrics(t["bps"] for t in trades if t["sector"] != sec)
        losector.append({
            "excluded_sector": sec,
            "excluded_symbol_count": len(excluded_symbols),
            "excluded_symbols": excluded_symbols,
            **m,
            "pf_delta_vs_baseline": m["pf"] - base["pf"] if m["pf"] is not None else None,
        })
    losector.sort(key=lambda x: (999 if x["pf"] is None else x["pf"], x["excluded_sector"]))

    # Positive-contributor removal. Ranking is full-sample net bps contribution, descending.
    by_symbol = defaultdict(list)
    for t in trades:
        by_symbol[t["symbol"]].append(t["bps"])
    contrib = sorted(
        ({"symbol": s, "sum_bps": sum(by_symbol[s]), "pf": pf(by_symbol[s]), "mean_bps": statistics.fmean(by_symbol[s]), "n": len(by_symbol[s])} for s in symbols),
        key=lambda x: (x["sum_bps"], x["symbol"]),
        reverse=True,
    )
    positive_rank = [x for x in contrib if x["sum_bps"] > 0]
    top_removal = []
    for n in c["new_diagnostics_preregistered_before_outcome"]["remove_top_positive_contributors"]:
        removed = [x["symbol"] for x in positive_rank[:int(n)]]
        m = metrics(t["bps"] for t in trades if t["symbol"] not in set(removed))
        top_removal.append({"top_n": int(n), "removed_symbols": removed, **m})

    # Equal-symbol weighting: every symbol gets equal total weight regardless of trade frequency.
    counts = {s: len(by_symbol[s]) for s in symbols}
    eq_weights = [1.0 / counts[t["symbol"]] for t in trades]
    equal_symbol = weighted_metrics(trades, eq_weights)
    equal_symbol["interpretation"] = "each symbol has equal total weight; within-symbol trades equally weighted"

    # Calendar and rolling time stability, assigned by entry timestamp.
    by_year = defaultdict(list)
    by_q = defaultdict(list)
    for t in trades:
        by_year[str(t["entry"].year)].append(t["bps"])
        by_q[quarter_key(t["entry"])].append(t["bps"])
    years = [{"period": k, **metrics(v)} for k, v in sorted(by_year.items())]
    quarters = [{"period": k, **metrics(v)} for k, v in sorted(by_q.items(), key=lambda kv: quarter_index(kv[0]))]
    quarter_keys = [x["period"] for x in quarters]
    rolling4 = []
    for i in range(len(quarter_keys) - 3):
        ks = quarter_keys[i:i + 4]
        if quarter_index(ks[-1]) - quarter_index(ks[0]) != 3:
            continue
        vals = []
        for k in ks:
            vals.extend(by_q[k])
        rolling4.append({"start": ks[0], "end": ks[-1], **metrics(vals)})

    # Deterministic friction validation grid on canonical actual returns.
    friction = []
    for extra in c["friction_validation_grid_extra_roundtrip_bps"]:
        m = metrics(t["bps"] - float(extra) for t in trades)
        friction.append({"extra_roundtrip_bps": float(extra), **m})

    # External market regimes from prior-day SPY only; no same-day close lookahead.
    spy_path = work / "spy-stooq-daily.csv"
    spy_rows = fetch_spy_daily(spy_path)
    spy_dates, spy_states = build_spy_states(spy_rows)
    regime_rows = defaultdict(list)
    combined_rows = defaultdict(list)
    unmapped = []
    for t in trades:
        state_date, state = previous_state(t["entry"].date(), spy_dates, spy_states)
        if state is None:
            unmapped.append(t["idx"])
            continue
        regime_rows[state["trend"]].append(t["bps"])
        regime_rows[state["vol"]].append(t["bps"])
        combined_rows[f"{state['trend']}__{state['vol']}"] .append(t["bps"])
    if unmapped:
        raise RuntimeError(f"SPY regime mapping incomplete count={len(unmapped)}")
    regimes = {k: metrics(v) for k, v in sorted(regime_rows.items())}
    combined_regimes = {k: metrics(v) for k, v in sorted(combined_rows.items())}

    year_pf_frac = sum(gt(x["pf"], 1.0) for x in years) / len(years)
    quarter_pf_frac = sum(gt(x["pf"], 1.0) for x in quarters) / len(quarters)
    quarter_mean_frac = sum(gt(x["mean_bps"], 0.0) for x in quarters) / len(quarters)
    rolling4_pf_frac = sum(gt(x["pf"], 1.0) for x in rolling4) / len(rolling4) if rolling4 else 0.0

    flags = {
        "leave_one_symbol_no_reversal": all(gt(x["pf"], thresholds["leave_one_symbol_no_reversal_pf_min_exclusive"]) for x in loso),
        "leave_one_symbol_strong": all(ge(x["pf"], thresholds["leave_one_symbol_strong_pf_min"]) for x in loso),
        "leave_one_sector_no_reversal": all(gt(x["pf"], thresholds["leave_one_sector_no_reversal_pf_min_exclusive"]) for x in losector),
        "leave_one_sector_robust": all(ge(x["pf"], thresholds["leave_one_sector_robust_pf_min"]) for x in losector),
        "top5_removed_no_reversal": gt(next(x for x in top_removal if x["top_n"] == 5)["pf"], thresholds["top5_removed_pf_min_exclusive"]),
        "equal_symbol_weighted": ge(equal_symbol["pf"], thresholds["equal_symbol_weighted_pf_min"]),
        "calendar_year_consistency": year_pf_frac >= thresholds["calendar_year_fraction_pf_gt_1_min"],
        "calendar_quarter_pf_consistency": quarter_pf_frac >= thresholds["calendar_quarter_fraction_pf_gt_1_min"],
        "calendar_quarter_mean_consistency": quarter_mean_frac >= thresholds["calendar_quarter_fraction_mean_positive_min"],
        "rolling_4q_consistency": rolling4_pf_frac >= thresholds["rolling_4q_fraction_pf_gt_1_min"],
        "regime_sample_adequacy": all(regimes.get(k, {}).get("n", 0) >= thresholds["regime_min_trades"] for k in ["bull", "bear", "high_vol", "low_vol"]),
        "regime_no_reversal": all(gt(regimes.get(k, {}).get("pf"), thresholds["regime_each_pf_min_exclusive"]) for k in ["bull", "bear", "high_vol", "low_vol"]),
    }
    # Overall robustness is intentionally strict and uses only preregistered NEW diagnostics.
    overall_pass = all(flags.values())

    result = {
        "schema": 1,
        "source_scope": source_scope,
        "scope": out_scope,
        "strategy_changes": "NONE",
        "baseline_parity": base,
        "known_validation": {
            "friction_grid": friction,
            "note": "0/10/20/25/30bps overlap earlier known diagnostics; they are reproducibility checks, not new evidence",
        },
        "new_robustness": {
            "leave_one_symbol_out": {
                "worst": loso[0],
                "best": loso[-1],
                "all": loso,
            },
            "leave_one_sector_out": {
                "worst": losector[0],
                "best": losector[-1],
                "all": losector,
            },
            "positive_contributor_ranking": positive_rank,
            "top_positive_contributor_removal": top_removal,
            "equal_symbol_weighted": equal_symbol,
            "calendar_year": years,
            "calendar_quarter": quarters,
            "rolling_four_quarter": rolling4,
            "consistency": {
                "year_fraction_pf_gt_1": year_pf_frac,
                "quarter_fraction_pf_gt_1": quarter_pf_frac,
                "quarter_fraction_mean_positive": quarter_mean_frac,
                "rolling4_fraction_pf_gt_1": rolling4_pf_frac,
            },
            "market_regime": {
                "benchmark": "SPY",
                "source": SPY_URL,
                "source_sha256": core.sha256_file(spy_path),
                "assignment": "strict previous trading day",
                "trend_rule": "prior SPY close >= prior SMA200 => bull; else bear",
                "vol_rule": "prior 20d log-return realized vol annualized >= 20% => high_vol; else low_vol",
                "marginal": regimes,
                "combined": combined_regimes,
            },
        },
        "thresholds": thresholds,
        "flags": flags,
        "robustness_pass": overall_pass,
        "discipline": c["discipline"],
    }

    result_path = work / "us60-robustness-v1.json"
    write_json(result_path, result)
    loso_csv = work / "leave-one-symbol-out.csv"
    losector_csv = work / "leave-one-sector-out.csv"
    time_csv = work / "calendar-quarter.csv"
    rows_to_csv(loso_csv, loso, ["excluded_symbol", "n", "pf", "mean_bps", "median_bps", "win_rate_pct", "sum_bps", "pf_delta_vs_baseline"])
    rows_to_csv(losector_csv, losector, ["excluded_sector", "excluded_symbol_count", "n", "pf", "mean_bps", "median_bps", "win_rate_pct", "sum_bps", "pf_delta_vs_baseline"])
    rows_to_csv(time_csv, quarters, ["period", "n", "pf", "mean_bps", "median_bps", "win_rate_pct", "sum_bps"])

    prereg_copy = work / "preregistration.json"
    write_json(prereg_copy, c)
    for name, path, ct in [
        ("research/us60-robustness-v1.json", result_path, "application/json; charset=utf-8"),
        ("research/us60-robustness-v1-preregistration.json", prereg_copy, "application/json; charset=utf-8"),
        ("research/us60-robustness-leave-one-symbol.csv", loso_csv, "text/csv; charset=utf-8"),
        ("research/us60-robustness-leave-one-sector.csv", losector_csv, "text/csv; charset=utf-8"),
        ("research/us60-robustness-calendar-quarter.csv", time_csv, "text/csv; charset=utf-8"),
        ("research/us60-robustness-spy-source.csv", spy_path, "text/csv; charset=utf-8"),
    ]:
        core.upload_artifact(PROJECT, out_scope, name, path, ct)

    checkpoint = {
        "source": core.SOURCE,
        "status": "complete",
        "position": {
            "phase": "us60_robustness_v1",
            "source_scope": source_scope,
            "scope": out_scope,
            "robustness_pass": overall_pass,
            "flags": flags,
            "worst_leave_one_symbol": loso[0],
            "worst_leave_one_sector": losector[0],
            "top5_removed": next(x for x in top_removal if x["top_n"] == 5),
            "equal_symbol": equal_symbol,
            "regimes": regimes,
        },
        "dropbox_path": None,
        "last_error": None,
    }
    core.put_json("/checkpoints/super-rsi/us60-robustness-v1", checkpoint)

    print(json.dumps({
        "scope": out_scope,
        "robustness_pass": overall_pass,
        "baseline": base,
        "flags": flags,
        "worst_leave_one_symbol": loso[0],
        "worst_leave_one_sector": losector[0],
        "top5_removed": next(x for x in top_removal if x["top_n"] == 5),
        "equal_symbol": equal_symbol,
        "consistency": result["new_robustness"]["consistency"],
        "regimes": regimes,
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
