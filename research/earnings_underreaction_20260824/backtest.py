from __future__ import annotations

import json
import os
from pathlib import Path

import numpy as np
import pandas as pd
import requests

PRICE_URL = "https://huggingface.co/datasets/finsaber-team/FINSABER-reproduce/resolve/main/data/price/all_sp500_prices_2000_2024_delisted_include.csv"
MEMBERSHIP_URL = "https://raw.githubusercontent.com/fja05680/sp500/master/sp500_ticker_start_end.csv"
EARNINGS_URL = "https://raw.githubusercontent.com/wuddup-02120/HistoricalEarningsData/refs/heads/master/HistoricalEarningsData/data/aggregated_earnings_data_webscraped.csv"

OUT = Path(os.environ.get("BACKTEST_OUT", "artifacts/earnings_underreaction_20260824"))
CACHE = Path(os.environ.get("BACKTEST_CACHE", "/tmp/earnings_underreaction_cache"))
OUT.mkdir(parents=True, exist_ok=True)
CACHE.mkdir(parents=True, exist_ok=True)

HORIZONS = {"4w": 20, "8w": 40, "13w": 65}
DISCOVERY = (pd.Timestamp("2010-01-01"), pd.Timestamp("2016-12-31"))
VALIDATION = (pd.Timestamp("2017-01-01"), pd.Timestamp("2024-12-31"))


def norm_ticker(x: str) -> str:
    return str(x).strip().upper().replace(".", "-")


def download(url: str, path: Path, min_bytes: int) -> None:
    if path.exists() and path.stat().st_size >= min_bytes:
        return
    tmp = path.with_suffix(path.suffix + ".part")
    headers = {"User-Agent": "Mozilla/5.0 earnings-underreaction-research/1.0"}
    with requests.get(url, stream=True, timeout=180, headers=headers, allow_redirects=True) as r:
        r.raise_for_status()
        with open(tmp, "wb") as f:
            for chunk in r.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    f.write(chunk)
    tmp.replace(path)
    if path.stat().st_size < min_bytes:
        raise RuntimeError(f"download unexpectedly small: {path} ({path.stat().st_size})")


def load_prices() -> dict[str, pd.DataFrame]:
    path = CACHE / "prices.csv"
    download(PRICE_URL, path, 50_000_000)
    use = ["date", "symbol", "open", "high", "low", "close", "adjusted_close"]
    p = pd.read_csv(path, usecols=use, parse_dates=["date"])
    p["symbol"] = p["symbol"].map(norm_ticker)
    p = p.dropna(subset=["date", "symbol", "open", "high", "close", "adjusted_close"])
    p = p[(p["open"] > 0) & (p["high"] > 0) & (p["close"] > 0) & (p["adjusted_close"] > 0)].copy()
    factor = p["adjusted_close"] / p["close"]
    p["adj_open"] = p["open"] * factor
    p["adj_high"] = p["high"] * factor
    p["adj_close"] = p["adjusted_close"]
    p = p[["date", "symbol", "adj_open", "adj_high", "adj_close"]].sort_values(["symbol", "date"], kind="mergesort")
    return {sym: g.reset_index(drop=True) for sym, g in p.groupby("symbol", sort=False)}


def load_memberships() -> dict[str, list[tuple[pd.Timestamp, pd.Timestamp]]]:
    path = CACHE / "membership.csv"
    download(MEMBERSHIP_URL, path, 10_000)
    m = pd.read_csv(path, parse_dates=["start_date", "end_date"])
    m["ticker"] = m["ticker"].map(norm_ticker)
    m["end_date"] = m["end_date"].fillna(pd.Timestamp("2100-01-01"))
    out: dict[str, list[tuple[pd.Timestamp, pd.Timestamp]]] = {}
    for r in m.itertuples(index=False):
        out.setdefault(r.ticker, []).append((pd.Timestamp(r.start_date), pd.Timestamp(r.end_date)))
    return out


def is_member(sym: str, date: pd.Timestamp, periods: dict[str, list[tuple[pd.Timestamp, pd.Timestamp]]]) -> bool:
    return any(start <= date <= end for start, end in periods.get(sym, []))


def load_earnings() -> pd.DataFrame:
    path = CACHE / "earnings.csv"
    download(EARNINGS_URL, path, 300_000)
    e = pd.read_csv(path, dtype="string")
    e["symbol"] = e["symbol"].map(norm_ticker)
    date_text = e["earnings_date"].str.extract(r"([A-Z][a-z]{2}\s+\d{1,2},\s+\d{4})", expand=False)
    e["event_date"] = pd.to_datetime(date_text, format="%b %d, %Y", errors="coerce")
    e["surprise_pct"] = pd.to_numeric(e["surprise"].str.replace("+", "", regex=False), errors="coerce")
    e = e.dropna(subset=["symbol", "event_date", "surprise_pct"]).copy()
    e = e[(e["event_date"] >= DISCOVERY[0]) & (e["event_date"] <= VALIDATION[1])]
    e = e.drop_duplicates(["symbol", "event_date"], keep="first")
    return e.sort_values(["event_date", "symbol"]).reset_index(drop=True)


def build_events(earnings: pd.DataFrame, prices: dict[str, pd.DataFrame], periods) -> pd.DataFrame:
    rows = []
    for r in earnings.itertuples(index=False):
        sym = r.symbol
        d = pd.Timestamp(r.event_date)
        if not is_member(sym, d, periods):
            continue
        px = prices.get(sym)
        if px is None or len(px) < 260:
            continue
        dates = px["date"].to_numpy(dtype="datetime64[ns]")
        # Previous trading session before the calendar earnings date.
        prev_idx = int(np.searchsorted(dates, np.datetime64(d), side="left")) - 1
        # Second trading session on/after event date. This standardizes AM/PM timing.
        first_on_after = int(np.searchsorted(dates, np.datetime64(d), side="left"))
        reaction_end_idx = first_on_after + 1
        entry_idx = reaction_end_idx + 1
        if prev_idx < 252 or entry_idx >= len(px):
            continue
        if reaction_end_idx >= len(px):
            continue

        prev_close = float(px.at[prev_idx, "adj_close"])
        reaction_close = float(px.at[reaction_end_idx, "adj_close"])
        entry_open = float(px.at[entry_idx, "adj_open"])
        if not np.isfinite(prev_close) or not np.isfinite(entry_open) or prev_close <= 0 or entry_open <= 0:
            continue

        hi52 = float(px.loc[prev_idx - 251:prev_idx, "adj_high"].max())
        dd52 = prev_close / hi52 - 1.0 if hi52 > 0 else np.nan
        mom63 = prev_close / float(px.at[prev_idx - 63, "adj_close"]) - 1.0
        reaction = reaction_close / prev_close - 1.0

        row = {
            "symbol": sym,
            "event_date": d,
            "surprise_pct": float(r.surprise_pct),
            "reaction_2session": reaction,
            "pre_dd52": dd52,
            "pre_mom63": mom63,
            "entry_date": pd.Timestamp(px.at[entry_idx, "date"]),
            "entry_open": entry_open,
        }
        for label, sessions in HORIZONS.items():
            exit_idx = entry_idx + sessions - 1
            if exit_idx < len(px):
                exit_close = float(px.at[exit_idx, "adj_close"])
                row[f"ret_{label}"] = exit_close / entry_open - 1.0
            else:
                row[f"ret_{label}"] = np.nan
        rows.append(row)
    out = pd.DataFrame(rows)
    if out.empty:
        raise RuntimeError("no usable earnings events")
    out["strong_beat"] = out["surprise_pct"] >= 10.0
    out["underreaction"] = out["strong_beat"] & (out["reaction_2session"] <= 0.03)
    out["near_consensus"] = out["surprise_pct"].between(-5.0, 5.0, inclusive="both")
    return out.sort_values(["event_date", "symbol"]).reset_index(drop=True)


def nearest_control(sig: pd.Series, pool: pd.DataFrame, kind: str) -> int | None:
    if kind == "strong_beat":
        configs = [
            (14, 0.10, 0.15),
            (28, 0.20, 0.30),
        ]
        base = pool[pool["near_consensus"]].copy()
        for days, dd_tol, mom_tol in configs:
            c = base[
                (base["event_date"].sub(sig["event_date"]).abs().dt.days <= days)
                & ((base["pre_dd52"] - sig["pre_dd52"]).abs() <= dd_tol)
                & ((base["pre_mom63"] - sig["pre_mom63"]).abs() <= mom_tol)
            ].copy()
            if not c.empty:
                dist = (
                    c["event_date"].sub(sig["event_date"]).abs().dt.days / days
                    + (c["pre_dd52"] - sig["pre_dd52"]).abs() / dd_tol
                    + (c["pre_mom63"] - sig["pre_mom63"]).abs() / mom_tol
                )
                return int(dist.idxmin())
    elif kind == "underreaction":
        configs = [
            (28, 10.0, 0.10, 0.15),
            (56, 20.0, 0.20, 0.30),
        ]
        base = pool[pool["strong_beat"] & (pool["reaction_2session"] > 0.03)].copy()
        for days, surprise_tol, dd_tol, mom_tol in configs:
            c = base[
                (base["event_date"].sub(sig["event_date"]).abs().dt.days <= days)
                & ((base["surprise_pct"] - sig["surprise_pct"]).abs() <= surprise_tol)
                & ((base["pre_dd52"] - sig["pre_dd52"]).abs() <= dd_tol)
                & ((base["pre_mom63"] - sig["pre_mom63"]).abs() <= mom_tol)
            ].copy()
            if not c.empty:
                dist = (
                    c["event_date"].sub(sig["event_date"]).abs().dt.days / days
                    + (c["surprise_pct"] - sig["surprise_pct"]).abs() / surprise_tol
                    + (c["pre_dd52"] - sig["pre_dd52"]).abs() / dd_tol
                    + (c["pre_mom63"] - sig["pre_mom63"]).abs() / mom_tol
                )
                return int(dist.idxmin())
    return None


def bootstrap_ci(x: np.ndarray, reps: int = 2000) -> tuple[float, float]:
    x = x[np.isfinite(x)]
    if len(x) < 5:
        return (np.nan, np.nan)
    rng = np.random.default_rng(20260824)
    means = np.empty(reps)
    n = len(x)
    for i in range(reps):
        means[i] = np.mean(x[rng.integers(0, n, size=n)])
    lo, hi = np.quantile(means, [0.025, 0.975])
    return float(lo), float(hi)


def evaluate(events: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp, kind: str) -> list[dict]:
    sub = events[(events["event_date"] >= start) & (events["event_date"] <= end)].copy()
    sig_mask = sub["strong_beat"] if kind == "strong_beat" else sub["underreaction"]
    signals = sub[sig_mask].copy()
    pairs = []
    for idx, s in signals.iterrows():
        ci = nearest_control(s, sub.drop(index=idx), kind)
        if ci is not None:
            pairs.append((idx, ci))

    rows = []
    for label in HORIZONS:
        sig_col = f"ret_{label}"
        all_sig = signals[sig_col].dropna()
        pair_data = []
        for si, ci in pairs:
            sr = sub.loc[si, sig_col]
            cr = sub.loc[ci, sig_col]
            if pd.notna(sr) and pd.notna(cr):
                pair_data.append((float(sr), float(cr)))
        if pair_data:
            arr = np.asarray(pair_data, dtype=float)
            excess = arr[:, 0] - arr[:, 1]
            ci95 = bootstrap_ci(excess)
            median_excess = float(np.median(excess))
            beat = float(np.mean(excess > 0))
            mean_excess = float(np.mean(excess))
            matched_n = len(excess)
        else:
            ci95 = (np.nan, np.nan)
            median_excess = beat = mean_excess = np.nan
            matched_n = 0
        rows.append({
            "kind": kind,
            "horizon": label,
            "signal_n": int(len(all_sig)),
            "matched_n": int(matched_n),
            "win_rate": float((all_sig > 0).mean()) if len(all_sig) else np.nan,
            "median_return": float(all_sig.median()) if len(all_sig) else np.nan,
            "mean_return": float(all_sig.mean()) if len(all_sig) else np.nan,
            "median_matched_excess": median_excess,
            "mean_matched_excess": mean_excess,
            "beat_matched": beat,
            "mean_excess_ci95_lo": ci95[0],
            "mean_excess_ci95_hi": ci95[1],
        })
    return rows


def pct(x) -> str:
    return "NA" if x is None or not np.isfinite(x) else f"{x*100:+.2f}%"


def main() -> None:
    prices = load_prices()
    periods = load_memberships()
    earnings = load_earnings()
    events = build_events(earnings, prices, periods)
    events.to_csv(OUT / "events.csv", index=False)

    results = []
    for split_name, (start, end) in {"discovery": DISCOVERY, "validation": VALIDATION}.items():
        for kind in ("strong_beat", "underreaction"):
            for r in evaluate(events, start, end, kind):
                r["split"] = split_name
                results.append(r)
    res = pd.DataFrame(results)
    res.to_csv(OUT / "results.csv", index=False)

    val_primary = res[(res["split"] == "validation") & (res["kind"] == "underreaction") & (res["horizon"] == "13w")].iloc[0]
    gate = {
        "min_matched_n_100": bool(val_primary["matched_n"] >= 100),
        "median_excess_gt_0": bool(val_primary["median_matched_excess"] > 0),
        "beat_matched_ge_55pct": bool(val_primary["beat_matched"] >= 0.55),
        "mean_excess_ci_lo_gt_0": bool(val_primary["mean_excess_ci95_lo"] > 0),
    }
    gate["overall"] = all(gate.values())

    summary = {
        "frozen_rule": {
            "strong_beat": "EPS surprise >= +10%",
            "underreaction": "strong beat and 2-session reaction <= +3%",
            "reaction_window": "previous close to close of second trading session on/after earnings date",
            "entry": "next trading session adjusted open after reaction window",
            "primary_horizon": "13w / 65 sessions",
            "secondary_horizons": ["4w", "8w"],
        },
        "coverage": {
            "raw_earnings_rows_2010_2024": int(len(earnings)),
            "usable_PIT_events": int(len(events)),
            "symbols": int(events["symbol"].nunique()),
            "event_min": str(events["event_date"].min().date()),
            "event_max": str(events["event_date"].max().date()),
        },
        "validation_primary_gate": gate,
    }
    with open(OUT / "summary.json", "w") as f:
        json.dump(summary, f, indent=2)

    lines = [
        "# Earnings Surprise + Price Underreaction — Frozen Backtest",
        "",
        "Status: exploratory causal-layer test; not production.",
        "",
        "## Frozen hypothesis",
        "- Strong beat: EPS surprise >= +10%.",
        "- Underreaction: strong beat + 2-session price reaction <= +3%.",
        "- Reaction: previous close -> close of second trading session on/after announcement date.",
        "- Entry: following trading session adjusted open.",
        "- Primary: 13w (65 sessions); 4w/8w secondary.",
        "- Discovery: 2010-2016; validation: 2017-2024.",
        "",
        "This tests the freely available surprise + price-reaction layer only. Historical PIT analyst revisions/guidance are NOT present in this public dataset, so they are intentionally not claimed or synthesized.",
        "",
        "## Coverage",
        f"- Raw earnings rows with numeric surprise, 2010-2024: {len(earnings):,}",
        f"- Usable PIT S&P500 events with prices: {len(events):,}",
        f"- Symbols: {events['symbol'].nunique():,}",
        f"- Event range: {events['event_date'].min().date()} to {events['event_date'].max().date()}",
        "",
        "## Results",
        "| Split | Rule | Hold | N | Matched | Win | Median ret | Median excess | Beat matched | Mean excess CI95 |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for r in results:
        lines.append(
            f"| {r['split']} | {r['kind']} | {r['horizon']} | {r['signal_n']} | {r['matched_n']} | "
            f"{pct(r['win_rate'])} | {pct(r['median_return'])} | {pct(r['median_matched_excess'])} | "
            f"{pct(r['beat_matched'])} | [{pct(r['mean_excess_ci95_lo'])}, {pct(r['mean_excess_ci95_hi'])}] |"
        )
    lines += [
        "",
        "## Pre-registered validation gate — Underreaction / 13w",
        f"- Matched N >= 100: {'PASS' if gate['min_matched_n_100'] else 'FAIL'}",
        f"- Median matched excess > 0: {'PASS' if gate['median_excess_gt_0'] else 'FAIL'}",
        f"- Beat matched >= 55%: {'PASS' if gate['beat_matched_ge_55pct'] else 'FAIL'}",
        f"- Mean excess 95% CI lower bound > 0: {'PASS' if gate['mean_excess_ci_lo_gt_0'] else 'FAIL'}",
        f"- Overall: {'PASS' if gate['overall'] else 'FAIL'}",
        "",
        "Decision rule: if validation fails, do not retune the +10% surprise or +3% underreaction thresholds on 2017-2024 and call it validation. Any changed thresholds are a new hypothesis.",
    ]
    (OUT / "RESULT.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
