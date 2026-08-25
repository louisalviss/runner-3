#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

HELPER_DIR = os.environ.get("WR_ENTRY_HELPER_DIR", "/tmp/wr-entry-helper")
sys.path.insert(0, HELPER_DIR)
import exp

OUT = Path(os.environ.get("WR_ENTRY_OUT", "/tmp/wr-entry"))
MERGE_ROOT = Path(os.environ.get("WR_ENTRY_MERGE_ROOT", "/tmp/all"))
FINAL_OUT = Path(os.environ.get("WR_ENTRY_FINAL_OUT", "/tmp/final"))
SHARD = int(os.environ.get("SHARD", "0"))
SHARDS = int(os.environ.get("SHARDS", "8"))

ALL = "AAPL ADBE ADI ADP ADSK AEP ALNY AMAT AMD AMGN AMZN AVGO BKR CDNS CMCSA COST CPRT CSCO CSGP CSX CTSH DXCM EA EXC FANG FTNT GILD GOOG GOOGL HON IDXX INTC INTU ISRG KHC LRCX MAR MCHP MDLZ META MPWR MRVL MSFT MU NFLX NVDA ODFL ORLY PANW PAYX PCAR PEP PLTR PYPL QCOM REGN ROST SBUX SNPS TMUS TSLA TTWO TXN VRTX WDAY WDC WMT ZS".split()
EXCLUDE = {"AAPL", "AMZN", "MSFT", "NVDA", "TSLA"}
UNIVERSE = [s for s in ALL if s not in EXCLUDE]

WARMUP = pd.Timestamp("2021-12-01T00:00:00Z")
REPORT_START = pd.Timestamp("2022-01-01T00:00:00Z")
END = pd.Timestamp("2026-08-25T00:00:00Z")
NY = ZoneInfo("America/New_York")
OPEN_MINUTE = 570
CLOSE_MINUTE = 960
SRC_MINUTES = 5
TF_MINUTES = 60
WINDOW_M5 = 24
PREREG_COMMIT = "f5dbf044327f9e33383fd759b1f1b3f8b3c901ef"
EXPECTED_N = 4023
EXPECTED_PF = 1.3937737824422902
EXPECTED_MEAN_BPS = 64.07886507098598


def rma(values, n):
    a = np.asarray(values, dtype=float)
    out = np.full(len(a), np.nan)
    valid = []
    start = None
    for i, x in enumerate(a):
        if np.isfinite(x):
            valid.append(i)
        if len(valid) == n:
            start = i
            out[i] = float(np.mean([a[j] for j in valid[-n:]]))
            break
    if start is None:
        return out
    for i in range(start + 1, len(a)):
        x = a[i]
        out[i] = ((n - 1) * out[i - 1] + x) / n if np.isfinite(x) else out[i - 1]
    return out


def load_quotes(symbol: str):
    instrument = exp.resolve_symbol(symbol)
    if not instrument:
        return None, None, [], None
    bidc = exp.pick_const(("OFFER_SIDE_BID", "PRICE_TYPE_BID", "BID"))
    askc = exp.pick_const(("OFFER_SIDE_ASK", "PRICE_TYPE_ASK", "ASK"))
    bids, asks, manifest = [], [], []
    for a, b in exp.month_chunks(WARMUP, END):
        try:
            db = exp.fetch_side(instrument, bidc, a, b, SRC_MINUTES)
            da = exp.fetch_side(instrument, askc, a, b, SRC_MINUTES)
            idx = db.index.intersection(da.index)
            if len(idx):
                bids.append(db.loc[idx, ["open", "high", "low", "close"]])
                asks.append(da.loc[idx, ["open", "high", "low", "close"]])
            manifest.append({"month": a.strftime("%Y-%m"), "bid": int(len(db)), "ask": int(len(da)), "common": int(len(idx))})
        except Exception as e:
            manifest.append({"month": a.strftime("%Y-%m"), "error": repr(e)})
    if not bids:
        return None, None, manifest, instrument
    bid = pd.concat(bids).sort_index()
    ask = pd.concat(asks).sort_index()
    bid = bid[~bid.index.duplicated(keep="last")]
    ask = ask[~ask.index.duplicated(keep="last")]
    idx = bid.index.intersection(ask.index)
    bid, ask = bid.loc[idx], ask.loc[idx]
    bid = bid[(bid.index >= WARMUP) & (bid.index < END)]
    ask = ask.loc[bid.index]
    return bid, ask, manifest, instrument


def _ohlc(frame: pd.DataFrame):
    return {"open": float(frame.iloc[0].open), "high": float(frame.high.max()), "low": float(frame.low.min()), "close": float(frame.iloc[-1].close)}


def regular_mask(index: pd.DatetimeIndex):
    local = index.tz_convert(NY)
    minute = local.hour * 60 + local.minute
    return (minute >= OPEN_MINUTE) & (minute < CLOSE_MINUTE)


def regular_m5(frame: pd.DataFrame):
    return frame.loc[regular_mask(frame.index)].copy().sort_index()


def session_bars(bid_src: pd.DataFrame, ask_src: pd.DataFrame):
    idx = bid_src.index.intersection(ask_src.index)
    bid_src, ask_src = bid_src.loc[idx], ask_src.loc[idx]
    local = idx.tz_convert(NY)
    meta = pd.DataFrame(index=idx)
    meta["date"] = local.date
    meta["minute"] = local.hour * 60 + local.minute
    meta = meta[(meta.minute >= OPEN_MINUTE) & (meta.minute < CLOSE_MINUTE)]
    expected = TF_MINUTES // SRC_MINUTES
    rows = []
    for _, daymeta in meta.groupby("date", sort=True):
        ids = daymeta.index
        mins = daymeta.minute.to_numpy()
        buckets = ((mins - OPEN_MINUTE) // TF_MINUTES).astype(int)
        for bucket in sorted(set(buckets)):
            sel = ids[buckets == bucket]
            if not len(sel):
                continue
            minute_values = [int(x) for x in daymeta.loc[sel].minute]
            if any(minute_values[j] - minute_values[j - 1] != SRC_MINUTES for j in range(1, len(minute_values))):
                continue
            later = ids[buckets > bucket]
            is_final = len(later) == 0
            if len(sel) != expected and not (is_final and len(sel) >= 2):
                continue
            bf, af = bid_src.loc[sel], ask_src.loc[sel]
            mf = (bf + af) / 2.0
            first, last = sel[0], sel[-1]
            rows.append({
                "time": first,
                "end": last + pd.Timedelta(minutes=SRC_MINUTES),
                **{f"mid_{k}": v for k, v in _ohlc(mf).items()},
                **{f"bid_{k}": v for k, v in _ohlc(bf).items()},
                **{f"ask_{k}": v for k, v in _ohlc(af).items()},
            })
    return pd.DataFrame(rows).sort_values("time").reset_index(drop=True) if rows else pd.DataFrame()


def signals(bars: pd.DataFrame):
    c = bars.mid_close.to_numpy(float)
    h = bars.mid_high.to_numpy(float)
    l = bars.mid_low.to_numpy(float)
    ch = np.r_[np.nan, np.diff(c)]
    up = rma(np.where(np.isnan(ch), np.nan, np.maximum(ch, 0)), 10)
    dn = rma(np.where(np.isnan(ch), np.nan, np.maximum(-ch, 0)), 10)
    rsi = np.where(dn == 0, 100, np.where(up == 0, 0, 100 - 100 / (1 + up / dn)))
    sma = pd.Series(rsi).rolling(10, min_periods=10).mean().to_numpy()
    cross = np.zeros(len(bars), dtype=bool)
    cross[1:] = np.isfinite(rsi[1:]) & np.isfinite(sma[1:]) & np.isfinite(rsi[:-1]) & np.isfinite(sma[:-1]) & (rsi[1:] > sma[1:]) & (rsi[:-1] <= sma[:-1])
    buy = np.zeros(len(bars), dtype=bool)
    count = 0
    for i in range(len(bars)):
        if np.isfinite(rsi[i]) and rsi[i] > 50:
            count = 0
        if cross[i] and rsi[i] < 50:
            count += 1
        if cross[i] and rsi[i] < 50 and count == 2:
            buy[i] = True
            count = 0

    prev = np.r_[np.nan, c[:-1]]
    tr = np.nanmax(np.vstack([h - l, np.abs(h - prev), np.abs(l - prev)]), axis=0)
    tr[0] = h[0] - l[0]
    atr = rma(tr, 10)
    hl2 = (h + l) / 2
    bu = hl2 + 2.5 * atr
    bl = hl2 - 2.5 * atr
    ub = np.full(len(bars), np.nan)
    lb = np.full(len(bars), np.nan)
    st = np.full(len(bars), np.nan)
    direction = np.full(len(bars), np.nan)
    for i in range(len(bars)):
        if not np.isfinite(atr[i]):
            continue
        if i == 0 or not np.isfinite(ub[i - 1]):
            ub[i], lb[i], direction[i], st[i] = bu[i], bl[i], 1, bu[i]
            continue
        ub[i] = bu[i] if (bu[i] < ub[i - 1] or c[i - 1] > ub[i - 1]) else ub[i - 1]
        lb[i] = bl[i] if (bl[i] > lb[i - 1] or c[i - 1] < lb[i - 1]) else lb[i - 1]
        if np.isclose(st[i - 1], ub[i - 1], rtol=1e-10, atol=1e-12):
            direction[i] = -1 if c[i] > ub[i] else 1
        else:
            direction[i] = 1 if c[i] < lb[i] else -1
        st[i] = lb[i] if direction[i] == -1 else ub[i]
    sell = np.zeros(len(bars), dtype=bool)
    sell[1:] = np.isfinite(direction[1:]) & np.isfinite(direction[:-1]) & ((direction[1:] - direction[:-1]) > 0)
    return buy, sell


def entry_variants(signal_end, exit_time, level, ask_reg: pd.DataFrame, exit_bid: float):
    window = ask_reg[(ask_reg.index >= signal_end) & (ask_reg.index < exit_time)].head(WINDOW_M5)
    coverage = len(window) > 0
    b_exec = False
    c_exec = False
    b_fill = None
    c_fill = None
    b_time = None
    c_time = None
    breakout_pos = None
    if coverage:
        for j, (ts, r) in enumerate(window.iterrows()):
            if float(r.high) >= level:
                b_exec = True
                b_fill = float(r.open) if float(r.open) >= level else float(level)
                b_time = ts
                breakout_pos = j
                break
        if breakout_pos is not None:
            for ts, r in list(window.iloc[breakout_pos + 1 :].iterrows()):
                ao, al = float(r.open), float(r.low)
                if ao <= level:
                    c_exec = True
                    c_fill = ao
                    c_time = ts
                    break
                if al <= level:
                    c_exec = True
                    c_fill = float(level)
                    c_time = ts
                    break
    b_bps = (exit_bid / b_fill - 1.0) * 10000.0 if b_exec else 0.0
    c_bps = (exit_bid / c_fill - 1.0) * 10000.0 if c_exec else 0.0
    return {
        "coverage": coverage,
        "window_bars": int(len(window)),
        "B_exec": b_exec,
        "B_entry": b_fill,
        "B_entry_time": None if b_time is None else b_time.isoformat(),
        "B_bps": b_bps,
        "C_exec": c_exec,
        "C_entry": c_fill,
        "C_entry_time": None if c_time is None else c_time.isoformat(),
        "C_bps": c_bps,
    }


def run_symbol(symbol: str):
    bid_src, ask_src, manifest, instrument = load_quotes(symbol)
    if bid_src is None:
        return {"symbol": symbol, "status": "UNAVAILABLE", "instrument": instrument, "manifest": manifest}, []
    bars = session_bars(bid_src, ask_src)
    if len(bars) < 100:
        return {"symbol": symbol, "status": "TOO_FEW_BARS", "bars": int(len(bars)), "instrument": instrument}, []
    ask_reg = regular_m5(ask_src)
    buy, sell = signals(bars)
    pos = False
    entry = None
    out = []
    for i in range(len(bars) - 1):
        nxt = bars.iloc[i + 1]
        sig_time = bars.iloc[i].end
        if pos:
            if sell[i]:
                exit_bid = float(nxt.bid_open)
                exit_time = nxt.time
                if not entry["warmup"]:
                    a_bps = (exit_bid / entry["market_entry"] - 1.0) * 10000.0
                    variants = entry_variants(entry["signal_time"], exit_time, entry["level"], ask_reg, exit_bid)
                    out.append({
                        "symbol": symbol,
                        "signal_time": entry["signal_time"].isoformat(),
                        "signal_day_utc": entry["signal_time"].date().isoformat(),
                        "year": int(entry["signal_time"].tz_convert(NY).year),
                        "level_mid_high": entry["level"],
                        "market_entry": entry["market_entry"],
                        "market_entry_time": entry["market_entry_time"].isoformat(),
                        "exit_bid": exit_bid,
                        "exit_time": exit_time.isoformat(),
                        "A_bps": a_bps,
                        **variants,
                    })
                pos = False
                entry = None
        elif buy[i]:
            entry = {
                "signal_time": sig_time,
                "market_entry_time": nxt.time,
                "market_entry": float(nxt.ask_open),
                "level": float(bars.iloc[i].mid_high),
                "warmup": not (REPORT_START <= sig_time < END),
            }
            pos = True
    diag = {
        "symbol": symbol,
        "status": "OK",
        "instrument": instrument,
        "bars60": int(len(bars)),
        "m5_regular": int(len(ask_reg)),
        "signals": int(buy.sum()),
        "opportunities": int(len(out)),
        "coverage": int(sum(bool(x["coverage"]) for x in out)),
        "B_exec": int(sum(bool(x["B_exec"]) for x in out)),
        "C_exec": int(sum(bool(x["C_exec"]) for x in out)),
        "manifest_errors": int(sum("error" in x for x in manifest)),
    }
    return diag, out


def profit_factor(vals):
    gp = sum(max(float(x), 0.0) for x in vals)
    gl = sum(max(-float(x), 0.0) for x in vals)
    return gp / gl if gl else (None if gp == 0 else 999.0)


def metrics(rows, key, exec_key=None):
    vals = [float(x[key]) for x in rows]
    if not vals:
        return {"opportunities": 0, "executed": 0, "execution_rate": None, "sum_return": 0.0, "mean_bps": None, "PF": None, "win_rate": None, "max_DD_bps": 0.0}
    executed = len(rows) if exec_key is None else sum(bool(x[exec_key]) for x in rows)
    eq = peak = 0.0
    dd = 0.0
    for v in vals:
        eq += v
        peak = max(peak, eq)
        dd = min(dd, eq - peak)
    return {
        "opportunities": len(vals),
        "executed": executed,
        "execution_rate": executed / len(vals),
        "sum_return": sum(vals) / 10000.0,
        "mean_bps": statistics.mean(vals),
        "PF": profit_factor(vals),
        "win_rate": 100.0 * sum(v > 0 for v in vals) / len(vals),
        "max_DD_bps": dd,
    }


def by_year(rows, key, exec_key=None):
    return {str(y): metrics([x for x in rows if int(x["year"]) == y], key, exec_key) for y in (2022, 2023, 2024, 2025, 2026)}


def breadth(rows, key, exec_key):
    symbols = {}
    for r in rows:
        if bool(r[exec_key]):
            symbols.setdefault(r["symbol"], []).append(r)
    eligible = {s: xs for s, xs in symbols.items() if len(xs) >= 10}
    positive = sum(sum(float(x[key]) for x in xs) > 0 for xs in eligible.values())
    return {
        "eligible_symbols_ge10_exec": len(eligible),
        "positive_symbols": positive,
        "positive_fraction": positive / len(eligible) if eligible else 0.0,
        "per_symbol": {s: {"executed": len(xs), "sum_return": sum(float(x[key]) for x in xs) / 10000.0, "mean_bps": statistics.mean(float(x[key]) for x in xs), "PF": profit_factor([float(x[key]) for x in xs])} for s, xs in sorted(symbols.items())},
    }


def bootstrap(rows, key, reps=5000, seed=20260825):
    by_day = {}
    for r in rows:
        by_day.setdefault(r["signal_day_utc"], []).append(r)
    days = sorted(by_day)
    if not days:
        return {"days": 0, "reps": 0, "candidate_mean_ci": [None, None], "delta_ci": [None, None]}
    rng = np.random.default_rng(seed)
    cm, dm = [], []
    for _ in range(reps):
        sample = rng.choice(days, size=len(days), replace=True)
        a_vals, c_vals = [], []
        for d in sample:
            xs = by_day[d]
            a_vals.extend(float(x["A_bps"]) for x in xs)
            c_vals.extend(float(x[key]) for x in xs)
        a = float(np.mean(a_vals))
        c = float(np.mean(c_vals))
        cm.append(c)
        dm.append(c - a)
    return {
        "days": len(days),
        "reps": reps,
        "candidate_mean_bootstrap": float(np.mean(cm)),
        "delta_mean_bootstrap": float(np.mean(dm)),
        "candidate_mean_ci": [float(np.percentile(cm, 2.5)), float(np.percentile(cm, 97.5))],
        "delta_ci": [float(np.percentile(dm, 2.5)), float(np.percentile(dm, 97.5))],
    }


def shard_mode():
    OUT.mkdir(parents=True, exist_ok=True)
    mine = [s for i, s in enumerate(UNIVERSE) if i % SHARDS == SHARD]
    all_rows, diags = [], []
    for symbol in mine:
        diag, rows = run_symbol(symbol)
        diags.append(diag)
        all_rows.extend(rows)
        print("SYMBOL", json.dumps(diag), flush=True)
    with (OUT / f"opportunities-{SHARD}.jsonl").open("w") as f:
        for r in all_rows:
            f.write(json.dumps(r, separators=(",", ":")) + "\n")
    (OUT / f"diagnostics-{SHARD}.json").write_text(json.dumps(diags, indent=2) + "\n")
    print("SHARD_DONE", SHARD, len(mine), len(all_rows), flush=True)


def read_rows():
    rows = []
    for p in MERGE_ROOT.rglob("opportunities-*.jsonl"):
        for line in p.read_text().splitlines():
            if line.strip():
                rows.append(json.loads(line))
    rows.sort(key=lambda x: (x["signal_time"], x["symbol"]))
    return rows


def candidate_report(rows, label, key, exec_key, A):
    m = metrics(rows, key, exec_key)
    yrs = by_year(rows, key, exec_key)
    br = breadth(rows, key, exec_key)
    boot = bootstrap(rows, key)
    positive_years = sum((yrs[str(y)]["mean_bps"] or 0) > 0 for y in (2022, 2023, 2024, 2025, 2026))
    delta = m["mean_bps"] - A["mean_bps"] if m["mean_bps"] is not None else None
    gates = {
        "coverage_ge_99pct": sum(bool(x["coverage"]) for x in rows) / len(rows) >= 0.99,
        "execution_rate_15_85pct": m["execution_rate"] is not None and 0.15 <= m["execution_rate"] <= 0.85,
        "candidate_mean_positive": m["mean_bps"] is not None and m["mean_bps"] > 0,
        "candidate_PF_gt_A": m["PF"] is not None and A["PF"] is not None and m["PF"] > A["PF"],
        "candidate_mean_ge_A_plus_10bps": delta is not None and delta >= 10.0,
        "positive_years_ge_4of5": positive_years >= 4,
        "positive_2025_and_2026": (yrs["2025"]["mean_bps"] or 0) > 0 and (yrs["2026"]["mean_bps"] or 0) > 0,
        "positive_symbol_breadth_ge_60pct": br["eligible_symbols_ge10_exec"] > 0 and br["positive_fraction"] >= 0.60,
        "bootstrap_candidate_lower_gt_0": boot["candidate_mean_ci"][0] is not None and boot["candidate_mean_ci"][0] > 0,
        "bootstrap_delta_lower_gt_0": boot["delta_ci"][0] is not None and boot["delta_ci"][0] > 0,
    }
    return {"label": label, "metrics": m, "executed_only": metrics([x for x in rows if bool(x[exec_key])], key, None), "by_year": yrs, "breadth": br, "bootstrap": boot, "mean_delta_vs_A_bps": delta, "gates": gates, "pass_except_parent_parity": all(gates.values())}


def merge_mode():
    FINAL_OUT.mkdir(parents=True, exist_ok=True)
    rows = read_rows()
    if not rows:
        report = {"status": "INFRASTRUCTURE_BLOCKED", "reason": "no opportunity rows", "PASS_WR_EXECUTION_MODULE": False}
        (FINAL_OUT / "report.json").write_text(json.dumps(report, indent=2) + "\n")
        (FINAL_OUT / "SUMMARY.md").write_text("# WR Breakout/Retest Execution Module\n\nINFRASTRUCTURE_BLOCKED: no rows.\n")
        return
    A = metrics(rows, "A_bps", None)
    parity = {
        "n_exact": A["opportunities"] == EXPECTED_N,
        "PF_within_0_01": A["PF"] is not None and abs(A["PF"] - EXPECTED_PF) <= 0.01,
        "mean_within_1bps": A["mean_bps"] is not None and abs(A["mean_bps"] - EXPECTED_MEAN_BPS) <= 1.0,
        "actual_n": A["opportunities"],
        "actual_PF": A["PF"],
        "actual_mean_bps": A["mean_bps"],
        "expected_n": EXPECTED_N,
        "expected_PF": EXPECTED_PF,
        "expected_mean_bps": EXPECTED_MEAN_BPS,
    }
    parity_pass = parity["n_exact"] and parity["PF_within_0_01"] and parity["mean_within_1bps"]
    coverage = sum(bool(x["coverage"]) for x in rows) / len(rows)
    B = candidate_report(rows, "BREAKOUT_STOP", "B_bps", "B_exec", A)
    C = candidate_report(rows, "BREAKOUT_RETEST", "C_bps", "C_exec", A)
    for cand in (B, C):
        cand["gates"]["parent_baseline_parity"] = parity_pass
        cand["PASS"] = parity_pass and cand["pass_except_parent_parity"]
    status = "COMPLETE" if parity_pass and coverage >= 0.99 else "INFRASTRUCTURE_BLOCKED"
    overall = status == "COMPLETE" and (B["PASS"] or C["PASS"])
    report = {
        "status": status,
        "candidate": "WR-like signal-bar-high breakout/retest execution on frozen RSI E2+ST external alpha",
        "preregistration_commit": PREREG_COMMIT,
        "parent_baseline_parity": parity,
        "coverage": coverage,
        "A_market": A,
        "A_by_year": by_year(rows, "A_bps", None),
        "B_breakout_stop": B,
        "C_breakout_retest": C,
        "PASS_WR_EXECUTION_MODULE": overall,
        "no_parameter_sweep": True,
        "fixed_window": "24 regular-session M5 bars = 120 regular-session minutes",
    }
    (FINAL_OUT / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    with (FINAL_OUT / "opportunities.jsonl").open("w") as f:
        for r in rows:
            f.write(json.dumps(r, separators=(",", ":")) + "\n")
    lines = [
        "# WR Breakout/Retest Execution Module — Final",
        "",
        f"Status: **{status}**",
        f"`PASS_WR_EXECUTION_MODULE = {str(overall).lower()}`",
        "",
        f"- Parent parity: {'PASS' if parity_pass else 'FAIL'}; n={A['opportunities']}; PF={A['PF']:.6f}; mean={A['mean_bps']:.3f} bps",
        f"- Coverage: {coverage:.2%}",
    ]
    for name, cand in (("B BREAKOUT_STOP", B), ("C BREAKOUT_RETEST", C)):
        m = cand["metrics"]
        lines += [
            "",
            f"## {name}",
            f"- executed: {m['executed']}/{m['opportunities']} = {m['execution_rate']:.2%}",
            f"- opportunity mean: {m['mean_bps']:.3f} bps",
            f"- PF: {m['PF']:.6f}",
            f"- sum return: {m['sum_return']:.6f}",
            f"- delta vs A: {cand['mean_delta_vs_A_bps']:.3f} bps/opportunity",
            f"- bootstrap candidate CI: [{cand['bootstrap']['candidate_mean_ci'][0]:.3f}, {cand['bootstrap']['candidate_mean_ci'][1]:.3f}] bps",
            f"- bootstrap delta CI: [{cand['bootstrap']['delta_ci'][0]:.3f}, {cand['bootstrap']['delta_ci'][1]:.3f}] bps",
            f"- PASS: {cand['PASS']}",
            "- gates: " + ", ".join(f"{k}={'PASS' if v else 'FAIL'}" for k, v in cand["gates"].items()),
        ]
    (FINAL_OUT / "SUMMARY.md").write_text("\n".join(lines) + "\n")
    print(json.dumps(report, indent=2), flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["shard", "merge"])
    args = ap.parse_args()
    shard_mode() if args.mode == "shard" else merge_mode()


if __name__ == "__main__":
    main()
