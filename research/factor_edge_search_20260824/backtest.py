from __future__ import annotations

import json
import os
from pathlib import Path

import numpy as np
import pandas as pd
import requests

PRICE_URL = "https://huggingface.co/datasets/finsaber-team/FINSABER-reproduce/resolve/main/data/price/all_sp500_prices_2000_2024_delisted_include.csv"
MEMBERSHIP_URL = "https://raw.githubusercontent.com/fja05680/sp500/master/sp500_ticker_start_end.csv"
OUT = Path(os.environ.get("FACTOR_OUT", "artifacts/factor_edge_search_20260824"))
CACHE = Path(os.environ.get("FACTOR_CACHE", "/tmp/factor_edge_search_cache"))
OUT.mkdir(parents=True, exist_ok=True)
CACHE.mkdir(parents=True, exist_ok=True)

DISCOVERY = (pd.Timestamp("2005-01-01"), pd.Timestamp("2016-12-31"))
VALIDATION = (pd.Timestamp("2017-01-01"), pd.Timestamp("2024-12-31"))
HORIZONS = (4, 8, 13)


def norm_ticker(x: str) -> str:
    return str(x).strip().upper().replace(".", "-")


def download(url: str, path: Path, min_bytes: int) -> None:
    if path.exists() and path.stat().st_size >= min_bytes:
        return
    headers = {"User-Agent": "Mozilla/5.0 factor-edge-search/1.0"}
    tmp = path.with_suffix(path.suffix + ".part")
    with requests.get(url, stream=True, timeout=180, headers=headers) as r:
        r.raise_for_status()
        with open(tmp, "wb") as f:
            for chunk in r.iter_content(1024 * 1024):
                if chunk:
                    f.write(chunk)
    tmp.replace(path)
    if path.stat().st_size < min_bytes:
        raise RuntimeError(f"small download {path} {path.stat().st_size}")


def load_weekly() -> pd.DataFrame:
    pth = CACHE / "prices.csv"
    download(PRICE_URL, pth, 50_000_000)
    use = ["date", "symbol", "open", "high", "low", "close", "adjusted_close"]
    d = pd.read_csv(pth, usecols=use, parse_dates=["date"])
    d["symbol"] = d["symbol"].map(norm_ticker)
    d = d.dropna(subset=["date", "symbol", "open", "high", "low", "close", "adjusted_close"])
    d = d[(d.open > 0) & (d.high > 0) & (d.low > 0) & (d.close > 0) & (d.adjusted_close > 0)].copy()
    fac = d.adjusted_close / d.close
    d["adj_open"] = d.open * fac
    d["adj_high"] = d.high * fac
    d["adj_low"] = d.low * fac
    d["adj_close"] = d.adjusted_close
    d["week"] = d.date.dt.to_period("W-FRI").dt.end_time.dt.normalize()
    d = d.sort_values(["symbol", "date"], kind="mergesort")
    w = (d.groupby(["symbol", "week"], observed=True, sort=False)
           .agg(open=("adj_open", "first"), high=("adj_high", "max"), low=("adj_low", "min"), close=("adj_close", "last"))
           .reset_index().sort_values(["symbol", "week"], kind="mergesort").reset_index(drop=True))
    gap = w.groupby("symbol", observed=True).week.diff().dt.days.fillna(0)
    w["segment"] = (gap > 84).groupby(w.symbol, observed=True).cumsum().astype(int)
    w["sid"] = w.symbol.astype(str) + "#" + w.segment.astype(str)
    return w


def load_memberships():
    pth = CACHE / "membership.csv"
    download(MEMBERSHIP_URL, pth, 10_000)
    m = pd.read_csv(pth, parse_dates=["start_date", "end_date"])
    m["ticker"] = m.ticker.map(norm_ticker)
    m["end_date"] = m.end_date.fillna(pd.Timestamp("2100-01-01"))
    out = {}
    for r in m.itertuples(index=False):
        out.setdefault(r.ticker, []).append((pd.Timestamp(r.start_date), pd.Timestamp(r.end_date)))
    return out


def add_member(w: pd.DataFrame, periods) -> pd.DataFrame:
    flag = np.zeros(len(w), dtype=bool)
    for sym, idx in w.groupby("symbol", observed=True, sort=False).groups.items():
        vals = w.loc[idx, "week"].to_numpy(dtype="datetime64[ns]")
        mask = np.zeros(len(idx), dtype=bool)
        for s, e in periods.get(str(sym), []):
            mask |= (vals >= np.datetime64(s)) & (vals <= np.datetime64(e))
        flag[np.asarray(idx, dtype=int)] = mask
    w["member"] = flag
    return w


def features(w: pd.DataFrame) -> pd.DataFrame:
    g = w.groupby("sid", observed=True, sort=False)
    w["ret1"] = g.close.pct_change()
    w["mom12_1"] = g.close.shift(4) / g.close.shift(52) - 1
    w["ret4"] = w.close / g.close.shift(4) - 1
    w["vol13"] = g.ret1.transform(lambda s: s.rolling(13, min_periods=13).std())
    w["high52"] = g.high.transform(lambda s: s.rolling(52, min_periods=52).max())
    w["prox52"] = w.close / w.high52 - 1
    w["next_open"] = g.open.shift(-1)
    for h in HORIZONS:
        w[f"ret{h}"] = g.close.shift(-h) / w.next_open - 1
    return w


def signal_calendar(w: pd.DataFrame) -> pd.Series:
    # Last W-FRI label in each calendar month in the dataset.
    dates = pd.Series(sorted(w.week.unique()))
    last = dates.groupby(dates.dt.to_period("M")).max()
    return w.week.isin(last.to_list())


def cross_section(w: pd.DataFrame) -> pd.DataFrame:
    base = w[w["member"] & signal_calendar(w) & w.mom12_1.notna() & w.vol13.notna() & w.prox52.notna() & w.next_open.notna()].copy()
    base["mom_pct"] = base.groupby("week", observed=True).mom12_1.rank(pct=True, method="average")
    base["vol_pct"] = base.groupby("week", observed=True).vol13.rank(pct=True, method="average")
    return base

SPECS = {
    "MOM_TOP20": {
        "signal": lambda x: x.mom_pct >= 0.80,
        "control": lambda x: x.mom_pct.between(0.40, 0.60),
        "mechanism": "12-1 month cross-sectional momentum",
    },
    "MOM_TOP10": {
        "signal": lambda x: x.mom_pct >= 0.90,
        "control": lambda x: x.mom_pct.between(0.40, 0.60),
        "mechanism": "strong 12-1 month cross-sectional momentum",
    },
    "HIGH52_MOM": {
        "signal": lambda x: (x.mom_pct >= 0.70) & (x.prox52 >= -0.02),
        "control": lambda x: (x.mom_pct >= 0.70) & (x.prox52 <= -0.05),
        "mechanism": "52-week-high effect conditional on positive momentum",
    },
    "LOWVOL_MOM": {
        "signal": lambda x: (x.mom_pct >= 0.70) & (x.vol_pct <= 0.50),
        "control": lambda x: (x.mom_pct >= 0.70) & (x.vol_pct > 0.50),
        "mechanism": "low-volatility momentum",
    },
    "WINNER_CRASH_REVERSAL": {
        "signal": lambda x: (x.mom_pct >= 0.60) & (x.ret4 <= -0.15),
        "control": lambda x: (x.mom_pct >= 0.60) & x.ret4.between(-0.05, 0.05),
        "mechanism": "short-term reversal after a sharp pullback in prior winners",
    },
}


def nearest_control(sig: pd.Series, pool: pd.DataFrame, spec: dict) -> int | None:
    c = pool[spec["control"](pool)].copy()
    if c.empty:
        return None
    # Same signal month is mandatory. Within month, match drawdown/proximity and volatility loosely.
    c = c[c.week.eq(sig.week)]
    if c.empty:
        return None
    # Avoid same symbol when possible.
    c2 = c[c.symbol.ne(sig.symbol)]
    if not c2.empty:
        c = c2
    # Distance deliberately excludes the defining feature when that is the hypothesized edge.
    dd_sig = -float(sig.prox52)
    dd_c = -c.prox52.astype(float)
    vol_sig = float(sig.vol13)
    scale_v = max(float(c.vol13.median()), 1e-6)
    dist = (dd_c - dd_sig).abs() / 0.10 + (c.vol13.astype(float) - vol_sig).abs() / scale_v
    return int(dist.idxmin())


def bootstrap_ci(x: np.ndarray, reps=2000):
    x = x[np.isfinite(x)]
    if len(x) < 10:
        return (np.nan, np.nan)
    rng = np.random.default_rng(20260824)
    means = np.empty(reps)
    n = len(x)
    for i in range(reps):
        means[i] = np.mean(x[rng.integers(0, n, n)])
    return tuple(np.quantile(means, [0.025, 0.975]))


def evaluate(base: pd.DataFrame, start, end, name, spec):
    p = base[base.week.between(start, end)].copy()
    sig = p[spec["signal"](p)].copy()
    pairs = []
    for idx, s in sig.iterrows():
        ci = nearest_control(s, p, spec)
        if ci is not None:
            pairs.append((idx, ci))
    rows = []
    for h in HORIZONS:
        col = f"ret{h}"
        allsig = sig[col].dropna()
        vals = []
        for si, ci in pairs:
            a = p.at[si, col]
            b = p.at[ci, col]
            if pd.notna(a) and pd.notna(b):
                vals.append((float(a), float(b)))
        if vals:
            z = np.asarray(vals)
            ex = z[:, 0] - z[:, 1]
            lo, hi = bootstrap_ci(ex)
            medex = float(np.median(ex)); meanex = float(np.mean(ex)); beat = float(np.mean(ex > 0)); mn = len(ex)
        else:
            lo = hi = medex = meanex = beat = np.nan; mn = 0
        rows.append({
            "strategy": name, "mechanism": spec["mechanism"], "horizon": h,
            "signal_n": int(len(allsig)), "matched_n": int(mn),
            "win_rate": float((allsig > 0).mean()) if len(allsig) else np.nan,
            "median_return": float(allsig.median()) if len(allsig) else np.nan,
            "median_excess": medex, "mean_excess": meanex, "beat_matched": beat,
            "ci_lo": float(lo), "ci_hi": float(hi),
        })
    return rows


def pct(x):
    return "NA" if not np.isfinite(x) else f"{x*100:+.2f}%"


def main():
    w = add_member(features(load_weekly()), load_memberships())
    base = cross_section(w)
    base.to_csv(OUT / "monthly_features.csv", index=False)
    rows = []
    for split, (start, end) in {"discovery": DISCOVERY, "validation": VALIDATION}.items():
        for name, spec in SPECS.items():
            for r in evaluate(base, start, end, name, spec):
                r["split"] = split
                rows.append(r)
    res = pd.DataFrame(rows)
    res.to_csv(OUT / "results.csv", index=False)

    val13 = res[(res.split == "validation") & (res.horizon == 13)].copy()
    val13["gate"] = (val13.matched_n >= 100) & (val13.median_excess > 0) & (val13.beat_matched >= 0.55) & (val13.ci_lo > 0)
    val13["score"] = val13.median_excess.fillna(-9) + 0.5 * (val13.beat_matched.fillna(0) - 0.5)
    best = val13.sort_values(["gate", "score"], ascending=[False, False]).iloc[0]

    lines = [
        "# Frozen Factor Edge Search — Validation",
        "",
        "Status: exploratory mechanism search; rules fixed before reading validation.",
        "Discovery 2005-2016; validation 2017-2024; monthly signals; PIT S&P500 membership.",
        "Primary horizon: 13 weeks. Gate: matched N>=100, median excess>0, beat-control>=55%, mean-excess CI95 lower bound>0.",
        "",
        "## Validation results",
        "| Strategy | Hold | N | Matched | Win | Median ret | Median excess | Beat control | Mean excess CI95 | Gate |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    for r in res[res.split.eq("validation")].itertuples(index=False):
        gate = "PASS" if (r.horizon == 13 and r.matched_n >= 100 and r.median_excess > 0 and r.beat_matched >= .55 and r.ci_lo > 0) else ("FAIL" if r.horizon == 13 else "secondary")
        lines.append(f"| {r.strategy} | {r.horizon}w | {r.signal_n} | {r.matched_n} | {pct(r.win_rate)} | {pct(r.median_return)} | {pct(r.median_excess)} | {pct(r.beat_matched)} | [{pct(r.ci_lo)}, {pct(r.ci_hi)}] | {gate} |")
    lines += ["", "## Best validation candidate", f"- Strategy: {best.strategy}", f"- Median excess: {pct(best.median_excess)}", f"- Beat control: {pct(best.beat_matched)}", f"- Mean excess CI95: [{pct(best.ci_lo)}, {pct(best.ci_hi)}]", f"- Gate: {'PASS' if bool(best.gate) else 'FAIL'}"]
    (OUT / "RESULT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (OUT / "summary.json").write_text(json.dumps({"best": best.to_dict(), "validation_13w": val13.to_dict("records")}, indent=2, default=str), encoding="utf-8")
    print("\n".join(lines))

if __name__ == "__main__":
    main()
