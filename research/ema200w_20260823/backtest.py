from __future__ import annotations

import json
import math
import os
import time
from pathlib import Path

import numpy as np
import pandas as pd
import requests

PRICE_URL = "https://huggingface.co/datasets/finsaber-team/FINSABER-reproduce/resolve/main/data/price/all_sp500_prices_2000_2024_delisted_include.csv"
MEMBERSHIP_URL = "https://raw.githubusercontent.com/fja05680/sp500/master/sp500_ticker_start_end.csv"
SPY_URL = "https://query1.finance.yahoo.com/v8/finance/chart/SPY?period1=946684800&period2=1735776000&interval=1wk&events=div%2Csplits&includeAdjustedClose=true"
HORIZONS = (13, 26, 52, 104)
OUT = Path(os.environ.get("BACKTEST_OUT", "artifacts/ema200w_20260823"))
CACHE = Path(os.environ.get("BACKTEST_CACHE", "/tmp/ema200w_cache"))
OUT.mkdir(parents=True, exist_ok=True)
CACHE.mkdir(parents=True, exist_ok=True)


def norm_ticker(x: str) -> str:
    return str(x).strip().upper().replace(".", "-")


def download(url: str, path: Path, min_bytes: int = 1000) -> None:
    if path.exists() and path.stat().st_size >= min_bytes:
        return
    tmp = path.with_suffix(path.suffix + ".part")
    headers = {"User-Agent": "Mozilla/5.0 ema200w-research/1.0"}
    with requests.get(url, stream=True, timeout=120, headers=headers, allow_redirects=True) as r:
        r.raise_for_status()
        with open(tmp, "wb") as f:
            for chunk in r.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    f.write(chunk)
    tmp.replace(path)
    if path.stat().st_size < min_bytes:
        raise RuntimeError(f"Downloaded file unexpectedly small: {path} {path.stat().st_size}")


def load_prices() -> pd.DataFrame:
    path = CACHE / "sp500_prices.csv"
    download(PRICE_URL, path, min_bytes=50_000_000)
    use = ["date", "symbol", "open", "high", "low", "close", "adjusted_close"]
    df = pd.read_csv(
        path,
        usecols=use,
        parse_dates=["date"],
        dtype={"symbol": "string", "open": "float64", "high": "float64", "low": "float64", "close": "float64", "adjusted_close": "float64"},
    )
    df = df.dropna(subset=["date", "symbol", "close", "adjusted_close", "high", "low"])
    df = df[(df["close"] > 0) & (df["adjusted_close"] > 0) & (df["high"] > 0) & (df["low"] > 0)].copy()
    df["symbol"] = df["symbol"].map(norm_ticker)
    factor = df["adjusted_close"] / df["close"]
    df["adj_open"] = df["open"] * factor
    df["adj_high"] = df["high"] * factor
    df["adj_low"] = df["low"] * factor
    df["adj_close"] = df["adjusted_close"]
    df["week"] = df["date"].dt.to_period("W-FRI").dt.end_time.dt.normalize()
    df = df.sort_values(["symbol", "date"], kind="mergesort")
    w = (
        df.groupby(["symbol", "week"], sort=False, observed=True)
        .agg(
            open=("adj_open", "first"),
            high=("adj_high", "max"),
            low=("adj_low", "min"),
            close=("adj_close", "last"),
            last_trade_date=("date", "max"),
        )
        .reset_index()
        .sort_values(["symbol", "week"], kind="mergesort")
        .reset_index(drop=True)
    )
    # Prevent ticker-recycling / long suspension gaps from contaminating a 200-week MA.
    gap = w.groupby("symbol", observed=True)["week"].diff().dt.days.fillna(0)
    w["segment_no"] = (gap > 84).groupby(w["symbol"], observed=True).cumsum().astype(int)
    w["series_id"] = w["symbol"].astype(str) + "#" + w["segment_no"].astype(str)
    return w


def load_memberships() -> tuple[pd.DataFrame, dict[str, list[tuple[pd.Timestamp, pd.Timestamp]]]]:
    path = CACHE / "sp500_ticker_start_end.csv"
    download(MEMBERSHIP_URL, path, min_bytes=10_000)
    m = pd.read_csv(path, parse_dates=["start_date", "end_date"])
    m["ticker"] = m["ticker"].map(norm_ticker)
    m["start_date"] = pd.to_datetime(m["start_date"])
    m["end_date"] = pd.to_datetime(m["end_date"]).fillna(pd.Timestamp("2100-01-01"))
    periods: dict[str, list[tuple[pd.Timestamp, pd.Timestamp]]] = {}
    for r in m.itertuples(index=False):
        periods.setdefault(r.ticker, []).append((r.start_date, r.end_date))
    return m, periods


def add_membership_flag(w: pd.DataFrame, periods: dict[str, list[tuple[pd.Timestamp, pd.Timestamp]]]) -> pd.DataFrame:
    member = np.zeros(len(w), dtype=bool)
    for sym, idx in w.groupby("symbol", sort=False, observed=True).groups.items():
        ps = periods.get(str(sym), [])
        if not ps:
            continue
        dates = w.loc[idx, "week"]
        mask = np.zeros(len(idx), dtype=bool)
        vals = dates.to_numpy(dtype="datetime64[ns]")
        for start, end in ps:
            mask |= (vals >= np.datetime64(start)) & (vals <= np.datetime64(end))
        member[np.asarray(idx, dtype=int)] = mask
    w["is_member"] = member
    return w


def add_indicators_and_outcomes(w: pd.DataFrame) -> pd.DataFrame:
    g = w.groupby("series_id", sort=False, observed=True)
    w["ema200"] = g["close"].transform(lambda s: s.ewm(span=200, adjust=False, min_periods=200).mean())
    w["sma200"] = g["close"].transform(lambda s: s.rolling(200, min_periods=200).mean())
    w["roll52_high"] = g["high"].transform(lambda s: s.rolling(52, min_periods=52).max())
    w["dd52_close"] = w["close"] / w["roll52_high"] - 1.0

    prev_close = g["close"].shift(1)
    prev_ema = g["ema200"].shift(1)
    prev_sma = g["sma200"].shift(1)
    w["prev_ema"] = prev_ema
    w["prev_sma"] = prev_sma

    # CAUSAL touch: only the previous completed week's MA is used as the limit level.
    w["touch_ema"] = (prev_close > prev_ema) & (w["low"] <= prev_ema) & (w["high"] >= prev_ema)
    w["touch_sma"] = (prev_close > prev_sma) & (w["low"] <= prev_sma) & (w["high"] >= prev_sma)
    w["reject_ema"] = w["touch_ema"] & (w["close"] >= w["ema200"])
    w["reject_sma"] = w["touch_sma"] & (w["close"] >= w["sma200"])

    above_ema = (w["close"] > w["ema200"]).astype(float)
    above_sma = (w["close"] > w["sma200"]).astype(float)
    # Rolling state must be calculated within each listing segment.
    w["fresh26_ema"] = above_ema.groupby(w["series_id"], observed=True).transform(
        lambda s: s.shift(1).rolling(26, min_periods=26).sum().eq(26)
    )
    w["fresh26_sma"] = above_sma.groupby(w["series_id"], observed=True).transform(
        lambda s: s.shift(1).rolling(26, min_periods=26).sum().eq(26)
    )
    w["rising_ema"] = g["ema200"].shift(1) > g["ema200"].shift(14)
    w["rising_sma"] = g["sma200"].shift(1) > g["sma200"].shift(14)
    w["confirm_next_ema"] = g["touch_ema"].shift(1).fillna(False).astype(bool) & (w["close"] >= w["ema200"])
    w["confirm_next_sma"] = g["touch_sma"].shift(1).fillna(False).astype(bool) & (w["close"] >= w["sma200"])

    global_end = w["week"].max()
    w["series_last_week"] = g["week"].transform("max")
    w["series_last_close"] = g["close"].transform("last")
    ended_before_dataset = w["series_last_week"] < (global_end - pd.Timedelta(days=28))

    for h in HORIZONS:
        future_px = g["close"].shift(-h)
        target = w["week"] + pd.to_timedelta(h * 7, unit="D")
        fill_delisted = future_px.isna() & ended_before_dataset & (target > w["series_last_week"])
        future_px = future_px.where(~fill_delisted, w["series_last_close"])
        w[f"exit_{h}"] = future_px
        w[f"close_ret_{h}"] = future_px / w["close"] - 1.0
        # Forward worst weekly low including entry week; used only where the horizon return is observable.
        w[f"future_min_low_{h}"] = g["low"].transform(
            lambda s, n=h: s.iloc[::-1].rolling(n + 1, min_periods=1).min().iloc[::-1]
        )
    return w


def membership_at(sym: str, date: pd.Timestamp, periods: dict[str, list[tuple[pd.Timestamp, pd.Timestamp]]]) -> bool:
    for start, end in periods.get(sym, []):
        if start <= date <= end:
            return True
    return False


def build_events(w: pd.DataFrame, periods: dict[str, list[tuple[pd.Timestamp, pd.Timestamp]]]) -> pd.DataFrame:
    specs = [
        ("EMA_touch_limit", w["touch_ema"], w["prev_ema"], w["week"], "ema"),
        ("EMA_touch_limit_fresh26", w["touch_ema"] & w["fresh26_ema"], w["prev_ema"], w["week"], "ema"),
        ("EMA_touch_limit_rising", w["touch_ema"] & w["rising_ema"], w["prev_ema"], w["week"], "ema"),
        ("EMA_reject_close", w["reject_ema"], w["close"], w["week"], "ema"),
        ("EMA_fresh26_rising_reject", w["reject_ema"] & w["fresh26_ema"] & w["rising_ema"], w["close"], w["week"], "ema"),
        ("EMA_confirm_next_close", w["confirm_next_ema"], w["close"], w["week"] - pd.Timedelta(days=7), "ema"),
        ("SMA_touch_limit", w["touch_sma"], w["prev_sma"], w["week"], "sma"),
        ("SMA_reject_close", w["reject_sma"], w["close"], w["week"], "sma"),
        ("SMA_fresh26_rising_reject", w["reject_sma"] & w["fresh26_sma"] & w["rising_sma"], w["close"], w["week"], "sma"),
    ]
    cols = ["symbol", "series_id", "week", "close", "roll52_high", "dd52_close", "ema200", "sma200", "prev_ema", "prev_sma"]
    out = []
    for name, mask, entry_px, origin_week, ma_kind in specs:
        e = w.loc[mask.fillna(False), cols].copy()
        if e.empty:
            continue
        e["strategy"] = name
        e["ma_kind"] = ma_kind
        e["entry_price"] = entry_px.loc[e.index].astype(float)
        e["origin_week"] = origin_week.loc[e.index]
        e["source_index"] = e.index.astype(int)
        e = e[e.apply(lambda r: membership_at(r["symbol"], r["origin_week"], periods), axis=1)].copy()
        e["entry_dd52"] = e["entry_price"] / e["roll52_high"] - 1.0
        for h in HORIZONS:
            e[f"ret_{h}"] = w.loc[e["source_index"], f"exit_{h}"].to_numpy() / e["entry_price"].to_numpy() - 1.0
            e[f"maxdd_{h}"] = w.loc[e["source_index"], f"future_min_low_{h}"].to_numpy() / e["entry_price"].to_numpy() - 1.0
            # If the horizon return is censored, do not report truncated drawdown either.
            e.loc[e[f"ret_{h}"].isna(), f"maxdd_{h}"] = np.nan
        out.append(e)
    if not out:
        return pd.DataFrame()
    ev = pd.concat(out, ignore_index=True)
    return ev.sort_values(["strategy", "week", "symbol"]).reset_index(drop=True)


def load_spy() -> pd.DataFrame | None:
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        for attempt in range(3):
            r = requests.get(SPY_URL, headers=headers, timeout=30)
            if r.ok:
                break
            time.sleep(2 + attempt * 2)
        r.raise_for_status()
        result = r.json()["chart"]["result"][0]
        ts = pd.to_datetime(result["timestamp"], unit="s", utc=True).tz_convert(None)
        adj = result.get("indicators", {}).get("adjclose", [{}])[0].get("adjclose")
        if not adj:
            adj = result["indicators"]["quote"][0]["close"]
        s = pd.DataFrame({"date": ts, "close": adj}).dropna()
        s["week"] = s["date"].dt.to_period("W-FRI").dt.end_time.dt.normalize()
        s = s.groupby("week", as_index=False)["close"].last().sort_values("week")
        for h in HORIZONS:
            s[f"ret_{h}"] = s["close"].shift(-h) / s["close"] - 1.0
        return s
    except Exception as exc:
        (OUT / "spy_error.txt").write_text(repr(exc), encoding="utf-8")
        return None


def add_matched_controls(events: pd.DataFrame, w: pd.DataFrame) -> pd.DataFrame:
    by_week = {d: g for d, g in w[w["is_member"] & w["ema200"].notna()].groupby("week", sort=False)}
    for h in HORIZONS:
        events[f"control_median_{h}"] = np.nan
        events[f"control_n_{h}"] = 0
        events[f"matched_excess_{h}"] = np.nan
    for i, r in events.iterrows():
        pool = by_week.get(r["week"])
        if pool is None or not np.isfinite(r["entry_dd52"]):
            continue
        base = pool[pool["symbol"] != r["symbol"]]
        if r["ma_kind"] == "ema":
            base = base[~base["touch_ema"]]
        else:
            base = base[~base["touch_sma"]]
        width = 0.05
        cand = base[(base["dd52_close"] - r["entry_dd52"]).abs() <= width]
        if len(cand) < 10:
            width = 0.10
            cand = base[(base["dd52_close"] - r["entry_dd52"]).abs() <= width]
        for h in HORIZONS:
            vals = cand[f"close_ret_{h}"].dropna()
            if len(vals) < 5 or not np.isfinite(r[f"ret_{h}"]):
                continue
            med = float(vals.median())
            events.at[i, f"control_median_{h}"] = med
            events.at[i, f"control_n_{h}"] = int(len(vals))
            events.at[i, f"matched_excess_{h}"] = float(r[f"ret_{h}"] - med)
    return events


def add_spy(events: pd.DataFrame, spy: pd.DataFrame | None) -> pd.DataFrame:
    for h in HORIZONS:
        events[f"spy_ret_{h}"] = np.nan
        events[f"spy_excess_{h}"] = np.nan
    if spy is None or spy.empty:
        return events
    m = spy.set_index("week")
    for h in HORIZONS:
        mapped = events["week"].map(m[f"ret_{h}"])
        events[f"spy_ret_{h}"] = mapped
        events[f"spy_excess_{h}"] = events[f"ret_{h}"] - mapped
    return events


def cluster_boot_ci(x: pd.DataFrame, col: str, seed: int = 7, n_boot: int = 1200) -> tuple[float, float]:
    d = x.dropna(subset=[col]).groupby("week")[col].mean()
    if len(d) < 8:
        return (np.nan, np.nan)
    vals = d.to_numpy()
    rng = np.random.default_rng(seed)
    means = np.empty(n_boot)
    for i in range(n_boot):
        means[i] = rng.choice(vals, size=len(vals), replace=True).mean()
    return float(np.quantile(means, 0.025)), float(np.quantile(means, 0.975))


def summarize(events: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    rows = []
    for strategy, e in events.groupby("strategy", sort=True):
        for h in HORIZONS:
            x = e.dropna(subset=[f"ret_{h}"])
            if x.empty:
                continue
            lo, hi = cluster_boot_ci(x, f"ret_{h}")
            ctrl = x.dropna(subset=[f"matched_excess_{h}"])
            spy = x.dropna(subset=[f"spy_excess_{h}"])
            week_means = x.groupby("week")[f"ret_{h}"].mean()
            rows.append({
                "strategy": strategy,
                "horizon_weeks": h,
                "n": len(x),
                "unique_signal_weeks": x["week"].nunique(),
                "mean_return": x[f"ret_{h}"].mean(),
                "median_return": x[f"ret_{h}"].median(),
                "win_rate": (x[f"ret_{h}"] > 0).mean(),
                "q10_return": x[f"ret_{h}"].quantile(0.10),
                "q25_return": x[f"ret_{h}"].quantile(0.25),
                "q75_return": x[f"ret_{h}"].quantile(0.75),
                "q90_return": x[f"ret_{h}"].quantile(0.90),
                "median_maxdd": x[f"maxdd_{h}"].median(),
                "q10_maxdd": x[f"maxdd_{h}"].quantile(0.10),
                "cluster_week_mean_return": week_means.mean(),
                "cluster_boot95_low": lo,
                "cluster_boot95_high": hi,
                "matched_n": len(ctrl),
                "mean_matched_excess": ctrl[f"matched_excess_{h}"].mean() if len(ctrl) else np.nan,
                "median_matched_excess": ctrl[f"matched_excess_{h}"].median() if len(ctrl) else np.nan,
                "pct_outperform_matched": (ctrl[f"matched_excess_{h}"] > 0).mean() if len(ctrl) else np.nan,
                "spy_n": len(spy),
                "mean_spy_excess": spy[f"spy_excess_{h}"].mean() if len(spy) else np.nan,
                "median_spy_excess": spy[f"spy_excess_{h}"].median() if len(spy) else np.nan,
            })
    summary = pd.DataFrame(rows)

    era_rows = []
    eras = [("2004-2009", "2004-01-01", "2009-12-31"), ("2010-2019", "2010-01-01", "2019-12-31"), ("2020-2024", "2020-01-01", "2024-12-31"), ("pre2015", "2004-01-01", "2014-12-31"), ("2015-2024", "2015-01-01", "2024-12-31")]
    for strategy, e in events.groupby("strategy", sort=True):
        for label, a, b in eras:
            x = e[(e["week"] >= a) & (e["week"] <= b)].dropna(subset=["ret_52"])
            if x.empty:
                continue
            ctrl = x.dropna(subset=["matched_excess_52"])
            era_rows.append({
                "strategy": strategy,
                "era": label,
                "n_52w": len(x),
                "unique_signal_weeks": x["week"].nunique(),
                "mean_52w": x["ret_52"].mean(),
                "median_52w": x["ret_52"].median(),
                "win_52w": (x["ret_52"] > 0).mean(),
                "median_maxdd_52w": x["maxdd_52"].median(),
                "matched_n": len(ctrl),
                "mean_matched_excess_52w": ctrl["matched_excess_52"].mean() if len(ctrl) else np.nan,
                "pct_outperform_matched_52w": (ctrl["matched_excess_52"] > 0).mean() if len(ctrl) else np.nan,
            })
    return summary, pd.DataFrame(era_rows)


def pct(x: float) -> str:
    return "NA" if pd.isna(x) else f"{x * 100:.1f}%"


def write_report(summary: pd.DataFrame, era: pd.DataFrame, events: pd.DataFrame, w: pd.DataFrame) -> None:
    focus = summary[summary["horizon_weeks"] == 52].copy().sort_values("mean_matched_excess", ascending=False)
    lines = [
        "# 200-week MA US-stock backtest — causal / point-in-time filtered",
        "",
        f"Price coverage: {w['week'].min().date()} to {w['week'].max().date()}",
        f"Weekly rows: {len(w):,}; symbols: {w['symbol'].nunique():,}; listing segments: {w['series_id'].nunique():,}",
        f"Events after point-in-time S&P 500 membership filter: {len(events):,}",
        "",
        "Method: previous completed week's 200W MA is the causal touch level. A touch-limit entry requires the current week's adjusted high/low to actually trade through that level. Delisted/ended series are retained; when a requested horizon extends past a genuine pre-dataset-end series termination, the final observed adjusted close is used as the exit instead of silently dropping the trade. Active names whose horizon extends beyond 2024-12-31 are censored.",
        "",
        "Matched control: same signal week, point-in-time S&P 500 members, similar 52-week drawdown (±5pp, widened to ±10pp only when needed), excluding stocks simultaneously touching the same MA. This asks whether the MA level adds information beyond simply being in a comparable drawdown.",
        "",
        "## 52-week result",
        "",
        "| Strategy | N | Median | Win | Median max DD | Matched excess mean | Beat matched | SPY excess mean |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for r in focus.itertuples(index=False):
        lines.append(f"| {r.strategy} | {int(r.n)} | {pct(r.median_return)} | {pct(r.win_rate)} | {pct(r.median_maxdd)} | {pct(r.mean_matched_excess)} | {pct(r.pct_outperform_matched)} | {pct(r.mean_spy_excess)} |")
    lines += ["", "## Era stability — 52 weeks", "", "| Strategy | Era | N | Median | Win | Matched excess mean | Beat matched |", "|---|---|---:|---:|---:|---:|---:|"]
    for r in era.sort_values(["strategy", "era"]).itertuples(index=False):
        lines.append(f"| {r.strategy} | {r.era} | {int(r.n_52w)} | {pct(r.median_52w)} | {pct(r.win_52w)} | {pct(r.mean_matched_excess_52w)} | {pct(r.pct_outperform_matched_52w)} |")
    lines += [
        "",
        "## Caveats",
        "",
        "- FINSABER identifies the price file as S&P 500 prices including delisted names; membership is independently filtered with the fja05680 point-in-time S&P 500 history.",
        "- The price archive ends 2024-12-31, so 2025-2026 are not part of this historical test.",
        "- Adjusted OHLC is reconstructed by scaling raw OHLC with adjusted_close/close. This keeps split/dividend scaling internally consistent.",
        "- Final observed price on early-ended series is a practical delisting proxy, not CRSP delisting-return quality. Therefore this is materially cleaner than current-survivor backtests but not institutional-grade CRSP validation.",
        "- Multiple variants are exploratory. Do not select the best-looking row as a production rule without a frozen follow-up test.",
    ]
    (OUT / "report.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    print("Loading price archive...", flush=True)
    w = load_prices()
    print(f"Weekly rows={len(w):,} symbols={w['symbol'].nunique():,}", flush=True)
    _, periods = load_memberships()
    w = add_membership_flag(w, periods)
    print(f"PIT member weekly rows={w['is_member'].sum():,}", flush=True)
    w = add_indicators_and_outcomes(w)
    events = build_events(w, periods)
    print(f"Events={len(events):,}", flush=True)
    events = add_matched_controls(events, w)
    spy = load_spy()
    events = add_spy(events, spy)
    summary, era = summarize(events)

    summary.to_csv(OUT / "summary.csv", index=False)
    era.to_csv(OUT / "era_52w.csv", index=False)
    events.to_csv(OUT / "events.csv", index=False)
    write_report(summary, era, events, w)
    meta = {
        "price_url": PRICE_URL,
        "membership_url": MEMBERSHIP_URL,
        "price_start": str(w["week"].min().date()),
        "price_end": str(w["week"].max().date()),
        "weekly_rows": int(len(w)),
        "symbols": int(w["symbol"].nunique()),
        "series_segments": int(w["series_id"].nunique()),
        "point_in_time_member_rows": int(w["is_member"].sum()),
        "events": int(len(events)),
        "spy_loaded": bool(spy is not None and not spy.empty),
        "horizons_weeks": list(HORIZONS),
    }
    (OUT / "metadata.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    print(summary[summary["horizon_weeks"] == 52].sort_values("mean_matched_excess").to_string(index=False), flush=True)
    print(f"Wrote {OUT}", flush=True)


if __name__ == "__main__":
    main()
