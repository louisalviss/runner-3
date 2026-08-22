from __future__ import annotations

import math
import os
from pathlib import Path

import numpy as np
import pandas as pd
import requests
from huggingface_hub import hf_hub_download

OUT = Path(os.environ.get("OOS_OUT", "research/ema200w_20260823/oos_2025_2026"))
OUT.mkdir(parents=True, exist_ok=True)

HF_REPO = "paperswithbacktest/Stocks-Daily-Price"
HF_FILES = [f"data/train-{i:05d}-of-00004.parquet" for i in range(4)]
MEMBERSHIP_URL = "https://raw.githubusercontent.com/fja05680/sp500/master/sp500_ticker_start_end.csv"
DATA_START = pd.Timestamp("2018-01-01")
OOS_START = pd.Timestamp("2025-01-01")
HORIZONS = (13, 26, 52)


def norm_ticker(x: str) -> str:
    return str(x).strip().upper().replace(".", "-")


def load_memberships():
    r = requests.get(MEMBERSHIP_URL, timeout=60, headers={"User-Agent": "ema200w-oos/1.0"})
    r.raise_for_status()
    p = OUT / "membership.csv"
    p.write_bytes(r.content)
    m = pd.read_csv(p, parse_dates=["start_date", "end_date"])
    m["ticker"] = m["ticker"].map(norm_ticker)
    m["end_date"] = m["end_date"].fillna(pd.Timestamp("2100-01-01"))
    relevant = m[(m["end_date"] >= DATA_START) & (m["start_date"] <= pd.Timestamp("2026-12-31"))].copy()
    periods: dict[str, list[tuple[pd.Timestamp, pd.Timestamp]]] = {}
    for r in relevant.itertuples(index=False):
        periods.setdefault(r.ticker, []).append((pd.Timestamp(r.start_date), pd.Timestamp(r.end_date)))
    universe = set(periods)
    raw = set(universe)
    for s in list(universe):
        raw.add(s.replace("-", "."))
        raw.add(s.replace(".", "-"))
    return relevant, periods, universe, raw


def read_price_parts(raw_symbols: set[str], norm_universe: set[str]) -> pd.DataFrame:
    cols = ["symbol", "date", "open", "high", "low", "close", "adj_close"]
    parts = []
    for fn in HF_FILES:
        print("download", fn, flush=True)
        path = hf_hub_download(repo_id=HF_REPO, repo_type="dataset", filename=fn)
        try:
            d = pd.read_parquet(
                path,
                columns=cols,
                filters=[("date", ">=", DATA_START.strftime("%Y-%m-%d")), ("symbol", "in", sorted(raw_symbols))],
            )
        except Exception as exc:
            print("filtered parquet read failed; fallback full projected read:", repr(exc), flush=True)
            d = pd.read_parquet(path, columns=cols)
            d["date"] = pd.to_datetime(d["date"], errors="coerce")
            d = d[d["date"] >= DATA_START]
            d["symbol_norm"] = d["symbol"].map(norm_ticker)
            d = d[d["symbol_norm"].isin(norm_universe)].drop(columns=["symbol_norm"])
        if d.empty:
            continue
        d["date"] = pd.to_datetime(d["date"], errors="coerce")
        d["symbol"] = d["symbol"].map(norm_ticker)
        d = d[d["symbol"].isin(norm_universe) & (d["date"] >= DATA_START)]
        parts.append(d)
        print("kept rows", len(d), flush=True)
    if not parts:
        raise RuntimeError("No price rows loaded")
    d = pd.concat(parts, ignore_index=True)
    d = d.dropna(subset=["symbol", "date", "open", "high", "low", "close", "adj_close"])
    d = d[(d["close"] > 0) & (d["adj_close"] > 0) & (d["high"] > 0) & (d["low"] > 0)].copy()
    return d.sort_values(["symbol", "date"], kind="mergesort").reset_index(drop=True)


def weekly_bars(d: pd.DataFrame) -> pd.DataFrame:
    factor = d["adj_close"] / d["close"]
    d["adj_open"] = d["open"] * factor
    d["adj_high"] = d["high"] * factor
    d["adj_low"] = d["low"] * factor
    d["adj_c"] = d["adj_close"]
    d["week"] = d["date"].dt.to_period("W-FRI").dt.end_time.dt.normalize()
    w = (
        d.groupby(["symbol", "week"], observed=True, sort=False)
        .agg(open=("adj_open", "first"), high=("adj_high", "max"), low=("adj_low", "min"), close=("adj_c", "last"), last_trade_date=("date", "max"))
        .reset_index()
        .sort_values(["symbol", "week"], kind="mergesort")
        .reset_index(drop=True)
    )
    gap = w.groupby("symbol", observed=True)["week"].diff().dt.days.fillna(0)
    w["segment_no"] = (gap > 84).groupby(w["symbol"], observed=True).cumsum().astype(int)
    w["series_id"] = w["symbol"].astype(str) + "#" + w["segment_no"].astype(str)
    return w


def add_membership(w: pd.DataFrame, periods):
    flag = np.zeros(len(w), dtype=bool)
    for sym, idx in w.groupby("symbol", observed=True, sort=False).groups.items():
        ps = periods.get(str(sym), [])
        if not ps:
            continue
        vals = w.loc[idx, "week"].to_numpy(dtype="datetime64[ns]")
        m = np.zeros(len(idx), dtype=bool)
        for a, b in ps:
            m |= (vals >= np.datetime64(a)) & (vals <= np.datetime64(b))
        flag[np.asarray(idx, dtype=int)] = m
    w["is_member"] = flag
    return w


def add_indicators(w: pd.DataFrame) -> pd.DataFrame:
    g = w.groupby("series_id", observed=True, sort=False)
    w["ema200"] = g["close"].transform(lambda s: s.ewm(span=200, adjust=False, min_periods=200).mean())
    w["roll52_high"] = g["high"].transform(lambda s: s.rolling(52, min_periods=52).max())
    w["dd52"] = w["close"] / w["roll52_high"] - 1.0
    w["prev_close"] = g["close"].shift(1)
    w["prev_ema"] = g["ema200"].shift(1)
    w["touch"] = (w["prev_close"] > w["prev_ema"]) & (w["low"] <= w["prev_ema"]) & (w["high"] >= w["prev_ema"])
    w["prior52_touch"] = w["touch"].groupby(w["series_id"], observed=True).transform(
        lambda s: s.shift(1).rolling(52, min_periods=52).max().fillna(True).astype(bool)
    )
    w["no_touch52"] = ~w["prior52_touch"]
    w["rising_ema"] = g["ema200"].shift(1) > g["ema200"].shift(14)

    global_end = w["week"].max()
    w["series_last_week"] = g["week"].transform("max")
    w["series_last_close"] = g["close"].transform("last")
    ended = w["series_last_week"] < (global_end - pd.Timedelta(days=28))
    for h in HORIZONS:
        fut = g["close"].shift(-h)
        target = w["week"] + pd.to_timedelta(h * 7, unit="D")
        fill_ended = fut.isna() & ended & (target > w["series_last_week"])
        fut = fut.where(~fill_ended, w["series_last_close"])
        w[f"exit_{h}"] = fut
        w[f"ctrl_ret_{h}"] = fut / w["close"] - 1.0
    return w


def event_rows(w: pd.DataFrame) -> pd.DataFrame:
    frozen = w["touch"] & w["no_touch52"] & w["rising_ema"] & w["dd52"].ge(-0.20) & w["is_member"] & w["week"].ge(OOS_START)
    e = w.loc[frozen.fillna(False), ["symbol", "series_id", "week", "prev_ema", "close", "roll52_high", "dd52"]].copy()
    e["entry"] = e["prev_ema"]
    e["entry_dd"] = e["entry"] / e["roll52_high"] - 1.0
    for h in HORIZONS:
        e[f"ret_{h}"] = w.loc[e.index, f"exit_{h}"].to_numpy() / e["entry"].to_numpy() - 1.0
    e["source_index"] = e.index.astype(int)
    return e.reset_index(drop=True)


def add_controls(e: pd.DataFrame, w: pd.DataFrame) -> pd.DataFrame:
    valid_pool = w[
        w["is_member"]
        & w["ema200"].notna()
        & w["no_touch52"]
        & w["rising_ema"].fillna(False)
        & w["dd52"].ge(-0.20)
        & w["week"].ge(OOS_START)
    ]
    by_week = {d: p for d, p in valid_pool.groupby("week", observed=True, sort=False)}
    for h in HORIZONS:
        e[f"control_{h}"] = np.nan
        e[f"control_n_{h}"] = 0
        e[f"excess_{h}"] = np.nan
    for i, r in e.iterrows():
        p = by_week.get(r["week"])
        if p is None:
            continue
        base = (p["symbol"] != r["symbol"]) & (~p["touch"].fillna(False))
        dd = p["dd52"].to_numpy(dtype=float)
        m = base.to_numpy(dtype=bool) & np.isfinite(dd) & (np.abs(dd - float(r["entry_dd"])) <= 0.05)
        if m.sum() < 10:
            m = base.to_numpy(dtype=bool) & np.isfinite(dd) & (np.abs(dd - float(r["entry_dd"])) <= 0.10)
        for h in HORIZONS:
            vals = p[f"ctrl_ret_{h}"].to_numpy(dtype=float)[m]
            vals = vals[np.isfinite(vals)]
            if len(vals) >= 5:
                med = float(np.median(vals))
                e.at[i, f"control_{h}"] = med
                e.at[i, f"control_n_{h}"] = len(vals)
                if np.isfinite(r[f"ret_{h}"]):
                    e.at[i, f"excess_{h}"] = float(r[f"ret_{h}"] - med)
    return e


def bootstrap_week_mean(x: pd.DataFrame, col: str, nboot: int = 3000):
    z = x.dropna(subset=[col]).groupby("week", observed=True)[col].mean().to_numpy(dtype=float)
    if len(z) < 5:
        return (np.nan, np.nan)
    rng = np.random.default_rng(20260823)
    b = np.array([rng.choice(z, len(z), replace=True).mean() for _ in range(nboot)])
    return tuple(np.quantile(b, [0.025, 0.975]))


def stats_for(e: pd.DataFrame, h: int):
    x = e.dropna(subset=[f"ret_{h}"]).copy()
    c = x.dropna(subset=[f"excess_{h}"]).copy()
    ci = bootstrap_week_mean(c, f"excess_{h}")
    positives = x.loc[x[f"ret_{h}"] > 0, f"ret_{h}"].sort_values(ascending=False)
    top5_share = float(positives.head(5).sum() / positives.sum()) if positives.sum() > 0 else np.nan
    return {
        "horizon": h,
        "n": len(x),
        "signal_weeks": x["week"].nunique(),
        "median_return": x[f"ret_{h}"].median(),
        "mean_return": x[f"ret_{h}"].mean(),
        "win_rate": (x[f"ret_{h}"] > 0).mean(),
        "matched_n": len(c),
        "median_excess": c[f"excess_{h}"].median(),
        "mean_excess": c[f"excess_{h}"].mean(),
        "beat_matched": (c[f"excess_{h}"] > 0).mean(),
        "mean_excess_ci_lo": ci[0],
        "mean_excess_ci_hi": ci[1],
        "top5_positive_share": top5_share,
    }


def fmt_pct(v):
    return "NA" if not np.isfinite(v) else f"{100*v:.2f}%"


def main():
    membership, periods, universe, raw_symbols = load_memberships()
    print("membership symbols", len(universe), flush=True)
    d = read_price_parts(raw_symbols, universe)
    print("daily rows", len(d), "symbols", d.symbol.nunique(), "max", d.date.max(), flush=True)
    w = weekly_bars(d)
    del d
    w = add_membership(w, periods)
    w = add_indicators(w)
    e = event_rows(w)
    e = add_controls(e, w)

    max_week = w["week"].max()
    coverage = []
    for h in HORIZONS:
        observable_cutoff = max_week - pd.Timedelta(days=h * 7)
        coverage.append((h, observable_cutoff))

    summaries = pd.DataFrame([stats_for(e, h) for h in HORIZONS])
    yearly = []
    for year in (2025, 2026):
        y = e[e["week"].dt.year.eq(year)]
        for h in HORIZONS:
            s = stats_for(y, h)
            s["year"] = year
            yearly.append(s)
    yearly = pd.DataFrame(yearly)

    # Frozen decision gates were specified before this OOS run.
    s13 = summaries[summaries.horizon.eq(13)].iloc[0]
    gates = {
        "win_rate_ge_65": bool(s13.win_rate >= 0.65) if np.isfinite(s13.win_rate) else False,
        "median_return_gt_0": bool(s13.median_return > 0) if np.isfinite(s13.median_return) else False,
        "median_excess_ge_1_5": bool(s13.median_excess >= 0.015) if np.isfinite(s13.median_excess) else False,
        "beat_matched_ge_55": bool(s13.beat_matched >= 0.55) if np.isfinite(s13.beat_matched) else False,
    }
    gate_pass = all(gates.values())

    e.to_csv(OUT / "events.csv", index=False)
    summaries.to_csv(OUT / "summary.csv", index=False)
    yearly.to_csv(OUT / "yearly.csv", index=False)

    # Basic PIT price coverage diagnostic during OOS.
    oos_rows = w[w["week"].ge(OOS_START)]
    member_rows = oos_rows[oos_rows["is_member"]]
    member_symbols_with_prices = member_rows["symbol"].nunique()
    expected_symbols = set()
    for sym, ps in periods.items():
        if any(b >= OOS_START and a <= max_week for a, b in ps):
            expected_symbols.add(sym)
    missing = sorted(expected_symbols - set(oos_rows["symbol"].unique()))
    (OUT / "missing_oos_members.txt").write_text("\n".join(missing), encoding="utf-8")

    lines = []
    lines.append("# EMA200W frozen-rule true OOS — 2025–2026")
    lines.append("")
    lines.append("Rule frozen before reading OOS: `first EMA200W touch after >=52 weeks without a prior touch + EMA200W rising + DD52 >= -20%`; causal entry at prior completed week's EMA200W; primary horizon 13 weeks.")
    lines.append("")
    lines.append("## Data")
    lines.append("")
    lines.append(f"- Independent price source: `{HF_REPO}`.")
    lines.append(f"- Daily price coverage loaded: {w.week.min().date()} to {max_week.date()}.")
    lines.append(f"- OOS starts: {OOS_START.date()}.")
    lines.append(f"- PIT membership source: fja05680/sp500 start/end history.")
    lines.append(f"- Historical member symbols represented in price data: {w.symbol.nunique()}.")
    lines.append(f"- OOS expected PIT member symbols: {len(expected_symbols)}; with at least one OOS price row: {member_symbols_with_prices}; completely missing: {len(missing)}.")
    lines.append("- Adjusted OHLC is reconstructed using `adj_close / close`, matching the discovery implementation.")
    lines.append("")
    lines.append("## Results")
    lines.append("")
    lines.append("| Hold | N | Win rate | Median return | Mean return | Median matched excess | Beat matched | Mean excess 95% cluster-bootstrap CI |")
    lines.append("|---|---:|---:|---:|---:|---:|---:|---:|")
    for r in summaries.itertuples(index=False):
        lines.append(f"| {r.horizon}w | {r.n} | {fmt_pct(r.win_rate)} | {fmt_pct(r.median_return)} | {fmt_pct(r.mean_return)} | {fmt_pct(r.median_excess)} | {fmt_pct(r.beat_matched)} | {fmt_pct(r.mean_excess_ci_lo)} to {fmt_pct(r.mean_excess_ci_hi)} |")
    lines.append("")
    lines.append("## 13-week pre-registered gates")
    lines.append("")
    lines.append(f"- Win rate >=65%: {'PASS' if gates['win_rate_ge_65'] else 'FAIL'} ({fmt_pct(s13.win_rate)}).")
    lines.append(f"- Median return >0: {'PASS' if gates['median_return_gt_0'] else 'FAIL'} ({fmt_pct(s13.median_return)}).")
    lines.append(f"- Median matched excess >=+1.5%: {'PASS' if gates['median_excess_ge_1_5'] else 'FAIL'} ({fmt_pct(s13.median_excess)}).")
    lines.append(f"- Beat matched-control >=55%: {'PASS' if gates['beat_matched_ge_55'] else 'FAIL'} ({fmt_pct(s13.beat_matched)}).")
    lines.append(f"- Overall frozen gate: **{'PASS' if gate_pass else 'FAIL'}**.")
    lines.append(f"- Top-5 winners as share of total positive 13w return: {fmt_pct(s13.top5_positive_share)} (concentration diagnostic, not a gate).")
    lines.append("")
    lines.append("## By calendar year")
    lines.append("")
    lines.append("| Year | Hold | N | Win | Median return | Median excess | Beat matched |")
    lines.append("|---:|---:|---:|---:|---:|---:|---:|")
    for r in yearly.itertuples(index=False):
        lines.append(f"| {r.year} | {r.horizon}w | {r.n} | {fmt_pct(r.win_rate)} | {fmt_pct(r.median_return)} | {fmt_pct(r.median_excess)} | {fmt_pct(r.beat_matched)} |")
    lines.append("")
    lines.append("## Observable cutoffs")
    lines.append("")
    for h, c in coverage:
        lines.append(f"- {h}w outcomes are fully observable only for signals through approximately {c.date()}; later signals are retained in `events.csv` but censored for that horizon.")
    lines.append("")
    lines.append("## Caveats")
    lines.append("")
    lines.append("- This is independent price data, but not CRSP/Sharadar-grade security-master validation. Missing historical/delisted symbols are explicitly reported.")
    lines.append("- Dividend-adjusted history can be retroactively rescaled by later distributions; this matches the discovery implementation but is not a perfect point-in-time adjustment model.")
    lines.append("- 2026 has a shorter observable window and therefore fewer completed 13-week signals.")
    lines.append("- No thresholds were changed after reading these OOS results. Any later rule change must be treated as a new research hypothesis, not as part of this OOS test.")
    lines.append("")
    lines.append("## Decision")
    lines.append("")
    if gate_pass:
        lines.append("The frozen rule passes the previously stated OOS gate. Proceed to the independent PIT fundamental-quality test and portfolio simulation; do not retune this rule on 2025–2026.")
    else:
        lines.append("The frozen rule fails at least one previously stated OOS gate. Do not promote it to production. Preserve this result and treat any modification as a new hypothesis requiring a new untouched validation set.")

    (OUT / "RESULT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines), flush=True)


if __name__ == "__main__":
    main()
