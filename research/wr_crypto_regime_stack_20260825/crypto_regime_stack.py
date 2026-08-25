#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import io
import json
import math
import os
import time
import zipfile
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import requests

TF_MS = 300_000
BINANCE = "https://data.binance.vision"
EXPECTED_BASE_N = 359
EXPECTED_BASE_R6 = -91.2313
PREREG = "ac6cde2296e350ff515b4e29d848b4b0bf68841e"
SOURCE_ROOT = Path(os.getenv("SOURCE_ROOT", "/tmp/source"))
OUT = Path(os.getenv("OUT", "/tmp/out"))
MERGE_ROOT = Path(os.getenv("MERGE_ROOT", "/tmp/all"))
FINAL_OUT = Path(os.getenv("FINAL_OUT", "/tmp/final"))
SHARD = int(os.getenv("SHARD", "0"))
SHARDS = int(os.getenv("SHARDS", "8"))


def sess():
    s = requests.Session()
    s.headers["User-Agent"] = "runner3-wr-full-crypto-regime/1.0"
    return s


def get_zip(http, url):
    for k in range(4):
        try:
            r = http.get(url, timeout=45)
            if r.status_code == 404:
                return None
            r.raise_for_status()
            return r.content
        except Exception:
            if k == 3:
                raise
            time.sleep(0.5 * (k + 1))


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
    d = date(2024, 10, 1)
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
    ded = {ot: c for ot, c in rows}
    return pd.Series({ot: ded[ot] for ot in sorted(ded)}, dtype=float, name=sym)


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


def feature_ot(t):
    return int(t["signal"]) - TF_MS + 1


def cost_r(t, bps=6):
    d = abs(float(t["e"]) - float(t["s"]))
    if d <= 0:
        return 0.0
    return (float(t["e"]) / d) * (bps / 10000.0)


def net_r(t, bps=6):
    return float(t["R"]) - cost_r(t, bps)


def metrics(trades, bps=6):
    vals = [net_r(t, bps) for t in trades]
    if not vals:
        return {"n": 0, "R": 0.0, "mean_R": None, "PF": None, "win_rate": None, "max_DD_R": 0.0}
    gp = sum(max(x, 0.0) for x in vals)
    gl = sum(max(-x, 0.0) for x in vals)
    eq = peak = 0.0
    mdd = 0.0
    for x in vals:
        eq += x
        peak = max(peak, eq)
        mdd = min(mdd, eq - peak)
    return {
        "n": len(vals),
        "R": sum(vals),
        "mean_R": float(np.mean(vals)),
        "PF": gp / gl if gl else None,
        "win_rate": 100.0 * sum(x > 0 for x in vals) / len(vals),
        "max_DD_R": mdd,
    }


def by_year(trades):
    return {
        str(y): metrics([
            t for t in trades
            if datetime.fromtimestamp(int(t["signal"]) / 1000, tz=timezone.utc).year == y
        ])
        for y in (2025, 2026)
    }


def ema_flags(s: pd.Series, span: int):
    ema = s.ewm(span=span, adjust=False, min_periods=span).mean()
    slope = ema.diff()
    return (s > ema) & (slope > 0), (s < ema) & (slope < 0), ema


def benchmark_mode():
    OUT.mkdir(parents=True, exist_ok=True)
    trades = load_source_trades()
    fots = sorted({feature_ot(t) for t in trades})
    http = sess()
    btc = load_symbol(http, "BTCUSDT")
    eth = load_symbol(http, "ETHUSDT")
    if len(btc) < 10000 or len(eth) < 10000:
        raise SystemExit(f"BENCHMARK_DATA_FAIL btc={len(btc)} eth={len(eth)}")
    idx = btc.index.intersection(eth.index)
    btc = btc.loc[idx]
    eth = eth.loc[idx]
    btc_up, btc_down, _ = ema_flags(btc, 200)
    eth_up, eth_down, _ = ema_flags(eth, 200)
    btc_ret24 = btc / btc.shift(288) - 1.0
    eth_ret24 = eth / eth.shift(288) - 1.0
    lr = np.log(btc).diff()
    rv24 = lr.rolling(288, min_periods=288).std(ddof=0) * math.sqrt(288.0)
    hist = rv24.shift(1)
    q20 = hist.rolling(8640, min_periods=5760).quantile(0.20)
    q80 = hist.rolling(8640, min_periods=5760).quantile(0.80)
    rows = []
    for ot in fots:
        if ot not in idx:
            rows.append({"feature_ot": ot, "scoreable": False, "reason": "benchmark_bar_missing"})
            continue
        vals = [btc_ret24.get(ot), eth_ret24.get(ot), rv24.get(ot), q20.get(ot), q80.get(ot)]
        if any(pd.isna(v) for v in vals):
            rows.append({"feature_ot": ot, "scoreable": False, "reason": "benchmark_warmup"})
            continue
        rows.append({
            "feature_ot": ot,
            "scoreable": True,
            "btc_up": bool(btc_up.get(ot, False)),
            "btc_down": bool(btc_down.get(ot, False)),
            "eth_up": bool(eth_up.get(ot, False)),
            "eth_down": bool(eth_down.get(ot, False)),
            "btc_ret24": float(btc_ret24.loc[ot]),
            "eth_ret24": float(eth_ret24.loc[ot]),
            "btc_rv24": float(rv24.loc[ot]),
            "rv_q20": float(q20.loc[ot]),
            "rv_q80": float(q80.loc[ot]),
            "vol_mid": bool(q20.loc[ot] <= rv24.loc[ot] <= q80.loc[ot]),
        })
    with (OUT / "benchmark.jsonl").open("w") as f:
        for r in rows:
            f.write(json.dumps(r, separators=(",", ":")) + "\n")
    diag = {"btc_bars": len(btc), "eth_bars": len(eth), "signal_timestamps": len(fots), "scoreable": sum(r.get("scoreable", False) for r in rows)}
    (OUT / "benchmark-diag.json").write_text(json.dumps(diag, indent=2) + "\n")
    print(json.dumps(diag, indent=2), flush=True)


def shard_mode():
    OUT.mkdir(parents=True, exist_ok=True)
    trades = load_source_trades()
    fots = sorted({feature_ot(t) for t in trades})
    symbols = sorted({t["symbol"] for t in trades if t["symbol"] not in {"BTCUSDT", "ETHUSDT"}})
    mine = [s for i, s in enumerate(symbols) if i % SHARDS == SHARD]
    http = sess()
    btc = load_symbol(http, "BTCUSDT")
    if len(btc) < 10000:
        raise SystemExit("BTC_DATA_FAIL")
    btc_lr = np.log(btc).diff()
    rows = []
    diag = []
    for sym in mine:
        s = load_symbol(http, sym)
        if s.empty:
            diag.append({"symbol": sym, "bars": 0, "available_features": 0})
            continue
        up, down, _ = ema_flags(s, 50)
        idx = s.index.intersection(btc.index)
        if len(idx):
            pair = pd.DataFrame({"a": np.log(s.loc[idx]).diff(), "b": btc_lr.loc[idx]})
            corr = pair["a"].rolling(288, min_periods=216).corr(pair["b"])
        else:
            corr = pd.Series(dtype=float)
        n = 0
        for ot in fots:
            if ot not in s.index:
                continue
            u = up.get(ot)
            d = down.get(ot)
            if pd.isna(u) or pd.isna(d):
                continue
            c = corr.get(ot, np.nan)
            rows.append({
                "feature_ot": ot,
                "symbol": sym,
                "trend_up": bool(u),
                "trend_down": bool(d),
                "corr24": None if pd.isna(c) else float(c),
            })
            n += 1
        diag.append({"symbol": sym, "bars": len(s), "available_features": n})
        print("ALT_DONE", sym, len(s), n, flush=True)
    with (OUT / f"alt-{SHARD}.jsonl").open("w") as f:
        for r in rows:
            f.write(json.dumps(r, separators=(",", ":")) + "\n")
    (OUT / f"diag-{SHARD}.json").write_text(json.dumps(diag, indent=2) + "\n")
    print(json.dumps({"shard": SHARD, "symbols": mine, "rows": len(rows)}, indent=2), flush=True)


def read_jsonl_files(root: Path, pattern: str):
    out = []
    for p in root.rglob(pattern):
        for ln in p.read_text().splitlines():
            if ln.strip():
                out.append(json.loads(ln))
    return out


def bootstrap(A, B, reps=2000, seed=20260825):
    a_by = defaultdict(list)
    b_by = defaultdict(list)
    for t in A:
        day = datetime.fromtimestamp(int(t["signal"]) / 1000, tz=timezone.utc).date().isoformat()
        a_by[day].append(net_r(t))
    for t in B:
        day = datetime.fromtimestamp(int(t["signal"]) / 1000, tz=timezone.utc).date().isoformat()
        b_by[day].append(net_r(t))
    days = sorted(a_by)
    if not days:
        return {"days": 0, "reps": 0, "B_mean_ci95": [None, None], "delta_ci95": [None, None]}
    rng = np.random.default_rng(seed)
    bm = []
    dm = []
    for _ in range(reps):
        sample = rng.choice(days, size=len(days), replace=True)
        av = []
        bv = []
        for day in sample:
            av.extend(a_by[day])
            bv.extend(b_by.get(day, []))
        if av and bv:
            am = float(np.mean(av))
            bb = float(np.mean(bv))
            bm.append(bb)
            dm.append(bb - am)
    return {
        "days": len(days),
        "reps": len(bm),
        "B_mean_ci95": [float(np.percentile(bm, 2.5)), float(np.percentile(bm, 97.5))] if bm else [None, None],
        "delta_ci95": [float(np.percentile(dm, 2.5)), float(np.percentile(dm, 97.5))] if dm else [None, None],
    }


def symbol_breadth(trades):
    by = defaultdict(list)
    for t in trades:
        by[t["symbol"]].append(t)
    elig = {s: xs for s, xs in by.items() if len(xs) >= 5}
    pos = sum(metrics(xs)["R"] > 0 for xs in elig.values())
    return {
        "eligible_symbols_ge5": len(elig),
        "positive_symbols": pos,
        "positive_fraction": pos / len(elig) if elig else 0.0,
    }


def merge_mode():
    FINAL_OUT.mkdir(parents=True, exist_ok=True)
    trades = load_source_trades()
    base_m = metrics(trades)
    if base_m["n"] != EXPECTED_BASE_N or abs(base_m["R"] - EXPECTED_BASE_R6) > 5e-4:
        raise SystemExit(f"BASELINE_PARITY_FAIL n={base_m['n']} R6={base_m['R']}")
    bench_rows = read_jsonl_files(MERGE_ROOT, "benchmark.jsonl")
    if not bench_rows:
        raise SystemExit("BENCHMARK_ROWS_MISSING")
    bench = {int(r["feature_ot"]): r for r in bench_rows}
    alt_rows = read_jsonl_files(MERGE_ROOT, "alt-*.jsonl")
    by_ot = defaultdict(list)
    for r in alt_rows:
        by_ot[int(r["feature_ot"])].append(r)

    scoreable = []
    kept = []
    decisions = []
    score_dist = defaultdict(int)
    hits = defaultdict(int)
    for t in trades:
        ot = feature_ot(t)
        b = bench.get(ot)
        ar = by_ot.get(ot, [])
        reason = None
        if not b or not b.get("scoreable"):
            reason = "benchmark_missing"
        n_alt = len(ar)
        n_up = sum(bool(x.get("trend_up")) for x in ar)
        n_down = sum(bool(x.get("trend_down")) for x in ar)
        corrs = [float(x["corr24"]) for x in ar if x.get("corr24") is not None and math.isfinite(float(x["corr24"]))]
        if reason is None and n_alt < 15:
            reason = "breadth_coverage"
        if reason is None and len(corrs) < 10:
            reason = "correlation_coverage"
        if reason is not None:
            decisions.append({"symbol": t["symbol"], "signal": int(t["signal"]), "feature_ot": ot, "scoreable": False, "reason": reason, "alt_n": n_alt, "corr_n": len(corrs)})
            continue
        side = t["side"]
        if side == "L":
            c1 = bool(b["btc_up"])
            c2 = bool(b["eth_up"])
            c3 = float(b["btc_ret24"]) > 0 and float(b["eth_ret24"]) > 0
            c4 = (n_up / n_alt) >= 0.55
        elif side == "S":
            c1 = bool(b["btc_down"])
            c2 = bool(b["eth_down"])
            c3 = float(b["btc_ret24"]) < 0 and float(b["eth_ret24"]) < 0
            c4 = (n_down / n_alt) >= 0.55
        else:
            raise SystemExit(f"UNKNOWN_SIDE {side}")
        c5 = bool(b["vol_mid"])
        median_corr = float(np.median(corrs))
        c6 = median_corr >= 0.35
        comps = [c1, c2, c3, c4, c5, c6]
        score = sum(int(x) for x in comps)
        keep = score >= 5
        scoreable.append(t)
        if keep:
            kept.append(t)
        score_dist[str(score)] += 1
        for i, x in enumerate(comps, 1):
            if x:
                hits[f"c{i}"] += 1
        decisions.append({
            "symbol": t["symbol"], "signal": int(t["signal"]), "feature_ot": ot, "scoreable": True,
            "score": score, "keep": keep, "components": comps, "alt_n": n_alt,
            "bullish_fraction": n_up / n_alt, "bearish_fraction": n_down / n_alt,
            "corr_n": len(corrs), "median_corr": median_corr,
            "btc_ret24": b["btc_ret24"], "eth_ret24": b["eth_ret24"], "btc_rv24": b["btc_rv24"],
        })

    A = metrics(scoreable)
    B = metrics(kept)
    coverage = len(scoreable) / len(trades)
    retention = len(kept) / len(scoreable) if scoreable else 0.0
    delta = None if A["mean_R"] is None or B["mean_R"] is None else B["mean_R"] - A["mean_R"]
    years = by_year(kept)
    br = symbol_breadth(kept)
    boot = bootstrap(scoreable, kept)
    gates = {
        "coverage_ge_95pct": coverage >= 0.95,
        "B_n_ge_80": B["n"] >= 80,
        "retention_15_70pct": 0.15 <= retention <= 0.70,
        "B_mean_positive": B["mean_R"] is not None and B["mean_R"] > 0,
        "B_PF_gt_1_05": B["PF"] is not None and B["PF"] > 1.05,
        "B_mean_ge_A_plus_0_10R": delta is not None and delta >= 0.10,
        "B_total_R_positive": B["R"] > 0,
        "B_positive_2025_and_2026": years["2025"]["R"] > 0 and years["2026"]["R"] > 0,
        "breadth_ge_50pct": br["eligible_symbols_ge5"] > 0 and br["positive_fraction"] >= 0.50,
        "bootstrap_B_lower_gt_0": boot["B_mean_ci95"][0] is not None and boot["B_mean_ci95"][0] > 0,
        "bootstrap_delta_lower_gt_0": boot["delta_ci95"][0] is not None and boot["delta_ci95"][0] > 0,
    }
    passed = all(gates.values())
    report = {
        "status": "COMPLETE" if coverage >= 0.95 else "INFRASTRUCTURE_BLOCKED",
        "candidate": "WR Crypto Stage1 + preregistered 6-component BTC/ETH regime stack",
        "preregistration_commit": PREREG,
        "parent_run": 32618199814,
        "parent_artifact": "wr-crypto-stage1-close-final-corrected",
        "baseline_parity": {"expected_n": EXPECTED_BASE_N, "expected_R6": EXPECTED_BASE_R6, "actual": base_m},
        "scoreable_n": len(scoreable),
        "coverage": coverage,
        "A_scoreable": A,
        "B_regime_score_ge5": B,
        "retention": retention,
        "mean_delta_R": delta,
        "B_long": metrics([t for t in kept if t["side"] == "L"]),
        "B_short": metrics([t for t in kept if t["side"] == "S"]),
        "B_years": years,
        "B_symbol_breadth": br,
        "score_distribution": dict(sorted(score_dist.items())),
        "component_hit_rates": {k: v / len(scoreable) if scoreable else None for k, v in sorted(hits.items())},
        "bootstrap_day_blocks": boot,
        "gates": gates,
        "PASS_FULL_CRYPTO_REGIME_WR": passed,
    }
    (FINAL_OUT / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    with (FINAL_OUT / "decisions.jsonl").open("w") as f:
        for r in decisions:
            f.write(json.dumps(r, separators=(",", ":")) + "\n")
    with (FINAL_OUT / "kept-trades.jsonl").open("w") as f:
        for t in kept:
            f.write(json.dumps(t, separators=(",", ":")) + "\n")
    lines = [
        "# WR Full BTC+ETH Crypto Regime Stack — Final Result", "",
        f"Status: **{report['status']}**",
        f"`PASS_FULL_CRYPTO_REGIME_WR = {str(passed).lower()}`", "",
        f"- coverage: {len(scoreable)}/{len(trades)} = {coverage:.2%}",
        f"- A: n={A['n']}, R={A['R']:.4f}, mean={A['mean_R'] if A['mean_R'] is not None else 'NA'}R, PF={A['PF']}",
        f"- B: n={B['n']}, R={B['R']:.4f}, mean={B['mean_R'] if B['mean_R'] is not None else 'NA'}R, PF={B['PF']}",
        f"- retention: {retention:.2%}",
        f"- B-A mean delta: {delta}",
        f"- 2025 B R: {years['2025']['R']:.4f}",
        f"- 2026 B R: {years['2026']['R']:.4f}",
        f"- bootstrap B mean CI95: {boot['B_mean_ci95']}",
        f"- bootstrap delta CI95: {boot['delta_ci95']}", "", "## Gates"
    ] + [f"- {k}: {'PASS' if v else 'FAIL'}" for k, v in gates.items()]
    (FINAL_OUT / "SUMMARY.md").write_text("\n".join(lines) + "\n")
    print(json.dumps(report, indent=2), flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["benchmark", "shard", "merge"])
    a = ap.parse_args()
    if a.mode == "benchmark":
        benchmark_mode()
    elif a.mode == "shard":
        shard_mode()
    else:
        merge_mode()


if __name__ == "__main__":
    main()
