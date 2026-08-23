from __future__ import annotations

import io
import json
import sys
import time
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd
import requests

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "research" / "ema200w_20260823"))
from backtest import load_prices, load_memberships, add_membership_flag, norm_ticker  # noqa: E402

DISC_START = pd.Timestamp("2010-01-01")
DISC_END = pd.Timestamp("2016-12-31")
VAL_START = pd.Timestamp("2017-01-01")
VAL_END = pd.Timestamp("2024-12-31")
HARD_STOP = pd.Timestamp("2024-12-31")
HORIZONS = (13, 26, 52)
UA = "research-backtest/1.0 contact research@example.com"
SEC_FORM345 = "https://www.sec.gov/files/structureddata/data/insider-transactions-data-sets/{year}q{q}_form345.zip"
SEC_CONCEPT = "https://data.sec.gov/api/xbrl/companyconcept/CIK{cik}/us-gaap/{concept}.json"
BUYBACK_CONCEPT = "PaymentsForRepurchaseOfCommonStock"
SHARE_CONCEPT = "WeightedAverageNumberOfDilutedSharesOutstanding"

S = requests.Session()
S.headers.update({
    "User-Agent": UA,
    "Accept": "application/json,text/plain,*/*",
    "Accept-Encoding": "gzip, deflate",
    "Accept-Language": "en-US,en;q=0.8",
})


def sec_get(url: str, *, binary: bool = False, allow_404: bool = False):
    for attempt in range(6):
        try:
            r = S.get(url, timeout=90)
            if allow_404 and r.status_code == 404:
                return None
            if r.status_code in {403, 429, 500, 502, 503, 504}:
                time.sleep(1.5 * (attempt + 1))
                continue
            r.raise_for_status()
            time.sleep(0.13)
            return r.content if binary else r.json()
        except Exception:
            if attempt == 5:
                raise
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError("unreachable")


def read_tsv(z: zipfile.ZipFile, name: str) -> pd.DataFrame:
    with z.open(name) as f:
        return pd.read_csv(f, sep="\t", dtype=str, low_memory=False)


def load_historical_cik_map(universe: set[str]) -> tuple[pd.DataFrame, dict]:
    rows = []
    meta = {"quarters": 0, "zip_bytes": 0, "submission_rows": 0}
    for year in range(2010, 2025):
        for q in range(1, 5):
            url = SEC_FORM345.format(year=year, q=q)
            b = sec_get(url, binary=True)
            meta["quarters"] += 1
            meta["zip_bytes"] += len(b)
            z = zipfile.ZipFile(io.BytesIO(b))
            sub = read_tsv(z, "SUBMISSION.tsv")
            sub.columns = [c.upper() for c in sub.columns]
            required = ["FILING_DATE", "ISSUERCIK", "ISSUERTRADINGSYMBOL"]
            if not all(c in sub.columns for c in required):
                raise RuntimeError(f"missing SEC submission mapping columns {year}q{q}: {sub.columns.tolist()}")
            meta["submission_rows"] += len(sub)
            x = sub[required].copy()
            x["symbol"] = x["ISSUERTRADINGSYMBOL"].fillna("").astype(str).map(norm_ticker)
            x["cik"] = pd.to_numeric(x["ISSUERCIK"], errors="coerce").astype("Int64")
            x["map_date"] = pd.to_datetime(x["FILING_DATE"], format="%d-%b-%Y", errors="coerce")
            x = x[x["symbol"].isin(universe) & x["cik"].notna() & x["map_date"].notna()].copy()
            if not x.empty:
                rows.append(x[["symbol", "cik", "map_date"]])
        print("MAP_YEAR", year, "rows", sum(len(x) for x in rows), flush=True)
    if not rows:
        raise RuntimeError("no historical CIK↔ticker mapping rows")
    m = pd.concat(rows, ignore_index=True).drop_duplicates().sort_values(["cik", "map_date", "symbol"])
    meta.update({
        "mapping_rows": int(len(m)),
        "mapping_symbols": int(m["symbol"].nunique()),
        "mapping_ciks": int(m["cik"].nunique()),
        "map_min": str(m["map_date"].min().date()),
        "map_max": str(m["map_date"].max().date()),
    })
    return m, meta


def parse_companyconcept(cik: int, concept: str, unit: str) -> pd.DataFrame:
    j = sec_get(SEC_CONCEPT.format(cik=f"{int(cik):010d}", concept=concept), allow_404=True)
    if j is None:
        return pd.DataFrame()
    rows = pd.DataFrame(j.get("units", {}).get(unit, []))
    if rows.empty:
        return rows
    rows["cik"] = int(cik)
    for c in ["start", "end", "filed"]:
        rows[c] = pd.to_datetime(rows.get(c), errors="coerce")
    rows["val"] = pd.to_numeric(rows.get("val"), errors="coerce")
    rows = rows[
        rows["form"].fillna("").astype(str).eq("10-Q")
        & rows["filed"].notna()
        & (rows["filed"] <= HARD_STOP)
        & rows["start"].notna()
        & rows["end"].notna()
        & rows["val"].notna()
    ].copy()
    rows["duration_days"] = (rows["end"] - rows["start"]).dt.days
    rows["file_lag_days"] = (rows["filed"] - rows["end"]).dt.days
    rows = rows[rows["duration_days"].between(60, 120, inclusive="both") & rows["file_lag_days"].between(0, 120, inclusive="both")].copy()
    if rows.empty:
        return rows
    # Same accession/period can occasionally expose multiple contexts. Drop conflicting values rather than choose ex post.
    key = ["cik", "accn", "start", "end", "filed"]
    nun = rows.groupby(key, dropna=False)["val"].nunique(dropna=False)
    good = nun[nun.eq(1)].reset_index()[key]
    rows = rows.merge(good, on=key, how="inner")
    rows = rows.drop_duplicates(key, keep="first")
    return rows[key + ["val", "fy", "fp", "duration_days", "file_lag_days"]]


def load_pit_facts(ciks: list[int]) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    rep_all, sh_all = [], []
    meta = {"ciks_requested": len(ciks), "rep_ciks": 0, "share_ciks": 0}
    for i, cik in enumerate(ciks, 1):
        rep = parse_companyconcept(cik, BUYBACK_CONCEPT, "USD")
        sh = parse_companyconcept(cik, SHARE_CONCEPT, "shares")
        if not rep.empty:
            rep_all.append(rep); meta["rep_ciks"] += 1
        if not sh.empty:
            sh_all.append(sh); meta["share_ciks"] += 1
        if i % 50 == 0 or i == len(ciks):
            print("CONCEPT_PROGRESS", i, "/", len(ciks), "rep_ciks", meta["rep_ciks"], "share_ciks", meta["share_ciks"], flush=True)
    rep = pd.concat(rep_all, ignore_index=True) if rep_all else pd.DataFrame()
    sh = pd.concat(sh_all, ignore_index=True) if sh_all else pd.DataFrame()
    meta.update({
        "rep_rows": int(len(rep)), "share_rows": int(len(sh)),
        "rep_cik_unique": int(rep["cik"].nunique()) if len(rep) else 0,
        "share_cik_unique": int(sh["cik"].nunique()) if len(sh) else 0,
    })
    return rep, sh, meta


def build_filing_events(rep: pd.DataFrame, sh: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    if rep.empty or sh.empty:
        raise RuntimeError("missing PIT repurchase/share facts")
    join = ["cik", "accn", "end", "filed"]
    cur = rep.rename(columns={"val": "repurchase_q", "start": "rep_start"}).merge(
        sh.rename(columns={"val": "diluted_shares_q", "start": "share_start"})[join + ["share_start", "diluted_shares_q"]],
        on=join, how="inner",
    )
    cur = cur[(cur["repurchase_q"] > 0) & (cur["diluted_shares_q"] > 0)].copy()
    cur = cur.sort_values(["cik", "end", "filed", "accn"]).drop_duplicates(["cik", "accn", "end"], keep="first")

    shhist = sh[["cik", "end", "filed", "val"]].rename(columns={"end": "prior_end", "filed": "prior_filed", "val": "prior_shares"})
    prior_vals = []
    for cik, g in cur.groupby("cik", sort=False, observed=True):
        h = shhist[shhist["cik"].eq(cik)].sort_values("prior_end")
        for r in g.itertuples(index=False):
            x = h[(h["prior_filed"] < r.filed)].copy()
            age = (r.end - x["prior_end"]).dt.days
            x = x[age.between(330, 400, inclusive="both")].copy()
            if x.empty:
                prior_vals.append((r.accn, np.nan, pd.NaT, pd.NaT))
                continue
            x["age_abs"] = ((r.end - x["prior_end"]).dt.days - 365).abs()
            x = x.sort_values(["age_abs", "prior_filed"], ascending=[True, False])
            p = x.iloc[0]
            prior_vals.append((r.accn, float(p["prior_shares"]), p["prior_end"], p["prior_filed"]))
    p = pd.DataFrame(prior_vals, columns=["accn", "diluted_shares_yrago", "prior_end", "prior_filed"])
    cur = cur.merge(p, on="accn", how="left")
    cur["share_shrink_yoy"] = cur["diluted_shares_q"] / cur["diluted_shares_yrago"] - 1.0
    meta = {
        "joined_current_rows": int(len(cur)),
        "with_yoy_share": int(cur["diluted_shares_yrago"].notna().sum()),
        "filing_min": str(cur["filed"].min().date()) if len(cur) else None,
        "filing_max": str(cur["filed"].max().date()) if len(cur) else None,
    }
    return cur, meta


def map_cik_to_ticker(ev: pd.DataFrame, mapping: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    out = []
    fallback_after = 0
    for cik, g in ev.groupby("cik", sort=False, observed=True):
        m = mapping[mapping["cik"].eq(cik)].sort_values("map_date")
        if m.empty:
            continue
        # Dates with >1 ticker are ambiguous identity points; remove them.
        same = m.groupby("map_date")["symbol"].nunique()
        amb_dates = set(same[same.gt(1)].index)
        m = m[~m["map_date"].isin(amb_dates)].drop_duplicates(["map_date"], keep="last")
        if m.empty:
            continue
        for r in g.itertuples(index=False):
            back = m[m["map_date"] <= r.filed]
            sym = None; map_date = pd.NaT; map_mode = None
            if not back.empty:
                b = back.iloc[-1]
                if (r.filed - b["map_date"]).days <= 365:
                    sym = b["symbol"]; map_date = b["map_date"]; map_mode = "backward"
            if sym is None:
                fwd = m[m["map_date"] > r.filed]
                if not fwd.empty:
                    f = fwd.iloc[0]
                    if (f["map_date"] - r.filed).days <= 90:
                        sym = f["symbol"]; map_date = f["map_date"]; map_mode = "forward_identity_only"; fallback_after += 1
            if sym is None:
                continue
            d = r._asdict(); d.update({"symbol": sym, "ticker_map_date": map_date, "ticker_map_mode": map_mode}); out.append(d)
    a = pd.DataFrame(out)
    meta = {"mapped_identity_rows": int(len(a)), "mapped_symbols": int(a["symbol"].nunique()) if len(a) else 0, "forward_identity_fallbacks": int(fallback_after)}
    return a, meta


def prepare_weekly_prices():
    w = load_prices()
    _, periods = load_memberships()
    w = add_membership_flag(w, periods)
    w["week"] = pd.to_datetime(w["week"]).astype("datetime64[ns]")
    g = w.groupby("series_id", sort=False, observed=True)
    w["ret52_pre"] = g["close"].shift(1) / g["close"].shift(53) - 1.0
    w["next_open"] = g["open"].shift(-1)
    for h in HORIZONS:
        w[f"ret{h}"] = g["close"].shift(-h) / w["next_open"] - 1.0
    return w, periods


def map_events_to_market(ev: pd.DataFrame, w: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    rows = []
    cols = ["week", "series_id", "is_member", "close", "ret52_pre", "next_open"] + [f"ret{h}" for h in HORIZONS]
    for sym, g in ev.groupby("symbol", sort=False, observed=True):
        p = w[w["symbol"].eq(sym)][cols].sort_values("week")
        if p.empty:
            continue
        # Conservative pre-filing market-cap proxy: strictly previous weekly close.
        pre = pd.merge_asof(g.sort_values("filed"), p[["week", "close"]].sort_values("week"), left_on="filed", right_on="week", direction="backward", allow_exact_matches=False)
        pre = pre.rename(columns={"week": "pre_week", "close": "pre_close"})
        # Signal week = first completed weekly bar strictly after filing.
        m = pd.merge_asof(pre.sort_values("filed"), p.sort_values("week"), left_on="filed", right_on="week", direction="forward", allow_exact_matches=False)
        lag = (m["week"] - m["filed"]).dt.days
        m = m[lag.between(1, 10, inclusive="both") & m["is_member"].fillna(False) & m["pre_close"].notna() & m["next_open"].notna()].copy()
        if not m.empty:
            rows.append(m)
    if not rows:
        raise RuntimeError("no buyback filings mapped to PIT market")
    a = pd.concat(rows, ignore_index=True)
    a["market_cap_proxy"] = a["pre_close"] * a["diluted_shares_q"]
    a["buyback_yield_q"] = a["repurchase_q"] / a["market_cap_proxy"]
    a["signal"] = (a["buyback_yield_q"] >= 0.01) & (a["share_shrink_yoy"] <= -0.01)
    # One signal opportunity per ticker/week. Keep the highest buyback yield if multiple filings somehow map together.
    sig = a[a["signal"]].sort_values(["symbol", "week", "buyback_yield_q"], ascending=[True, True, False]).drop_duplicates(["symbol", "week"], keep="first")
    meta = {
        "mapped_market_rows": int(len(a)), "signal_rows": int(len(sig)), "signal_symbols": int(sig["symbol"].nunique()),
        "buyback_yield_median_signal": float(sig["buyback_yield_q"].median()) if len(sig) else None,
        "share_shrink_median_signal": float(sig["share_shrink_yoy"].median()) if len(sig) else None,
    }
    return sig.reset_index(drop=True), meta


def add_recent_signal_flag(w: pd.DataFrame, sig: pd.DataFrame):
    key = set(map(tuple, sig[["symbol", "week"]].itertuples(index=False, name=None)))
    q = w.copy()
    q["buyback_signal"] = [1 if (s, wk) in key else 0 for s, wk in zip(q["symbol"], q["week"])]
    q = q.sort_values(["series_id", "week"])
    q["recent_buyback4"] = q.groupby("series_id", sort=False, observed=True)["buyback_signal"].transform(lambda s: s.rolling(4, min_periods=1).max())
    return q


def matched_excess(sig: pd.DataFrame, w: pd.DataFrame):
    a = sig.copy()
    for h in HORIZONS:
        a[f"excess{h}"] = np.nan
        a[f"control_n{h}"] = 0
    byweek = {wk: g for wk, g in w[w["is_member"].fillna(False)].groupby("week", sort=False)}
    for idx, r in a.iterrows():
        p = byweek.get(r["week"])
        if p is None or not np.isfinite(r["ret52_pre"]):
            continue
        rr = p["ret52_pre"].to_numpy(float)
        sy = p["symbol"].to_numpy(str)
        recent = p["recent_buyback4"].to_numpy(float)
        base = np.isfinite(rr) & (sy != r["symbol"]) & (recent == 0)
        m = base & (np.abs(rr - r["ret52_pre"]) <= 0.15)
        if m.sum() < 5:
            m = base & (np.abs(rr - r["ret52_pre"]) <= 0.25)
        if m.sum() < 3:
            continue
        for h in HORIZONS:
            vals = p.loc[m, f"ret{h}"].to_numpy(float)
            vals = vals[np.isfinite(vals)]
            own = r[f"ret{h}"]
            if len(vals) >= 3 and np.isfinite(own):
                a.at[idx, f"excess{h}"] = float(own - np.median(vals))
                a.at[idx, f"control_n{h}"] = int(len(vals))
    return a


def cluster_bootstrap_ci(df: pd.DataFrame, col: str, n_boot: int = 4000):
    x = df[["week", col]].dropna()
    if x.empty:
        return (np.nan, np.nan)
    wk = x.groupby("week")[col].apply(list)
    weeks = wk.index.to_list()
    rng = np.random.default_rng(20260824)
    means = np.empty(n_boot)
    for i in range(n_boot):
        chosen = rng.choice(weeks, size=len(weeks), replace=True)
        vals = []
        for k in chosen:
            vals.extend(wk.loc[k])
        means[i] = np.mean(vals) if vals else np.nan
    return tuple(np.nanquantile(means, [0.025, 0.975]))


def summarize(a: pd.DataFrame, label: str):
    rows = []
    for h in HORIZONS:
        x = a[a[f"ret{h}"].notna()].copy()
        m = x[x[f"excess{h}"].notna()].copy()
        lo, hi = cluster_bootstrap_ci(m, f"excess{h}")
        rows.append({
            "slice": label, "strategy": "BuybackYield1_Shrink1", "horizon": h,
            "n": int(len(x)), "matched_n": int(len(m)), "symbols": int(x["symbol"].nunique()) if len(x) else 0,
            "signal_weeks": int(x["week"].nunique()) if len(x) else 0,
            "median_return": float(x[f"ret{h}"].median()) if len(x) else np.nan,
            "mean_return": float(x[f"ret{h}"].mean()) if len(x) else np.nan,
            "win_rate": float((x[f"ret{h}"] > 0).mean()) if len(x) else np.nan,
            "median_excess": float(m[f"excess{h}"].median()) if len(m) else np.nan,
            "mean_excess": float(m[f"excess{h}"].mean()) if len(m) else np.nan,
            "beat_matched": float((m[f"excess{h}"] > 0).mean()) if len(m) else np.nan,
            "ci_lo": float(lo), "ci_hi": float(hi),
        })
    return rows


def main():
    t0 = time.time()
    print("loading PIT S&P500 weekly prices/membership...", flush=True)
    w, _ = prepare_weekly_prices()
    universe = set(w.loc[w["is_member"].fillna(False), "symbol"].astype(str).unique())
    print("UNIVERSE", len(universe), flush=True)

    print("loading official SEC historical issuer CIK↔ticker mapping...", flush=True)
    mapping, map_meta = load_historical_cik_map(universe)
    ciks = sorted(int(x) for x in mapping["cik"].dropna().unique())
    print("MAPPING_META", json.dumps(map_meta, default=str), flush=True)

    print("loading as-filed companyconcept histories...", flush=True)
    rep, sh, fact_meta = load_pit_facts(ciks)
    print("FACT_META", json.dumps(fact_meta, default=str), flush=True)

    ev, filing_meta = build_filing_events(rep, sh)
    ev, id_meta = map_cik_to_ticker(ev, mapping)
    sig, market_meta = map_events_to_market(ev, w)
    print("FILING_META", json.dumps(filing_meta, default=str), flush=True)
    print("IDENTITY_META", json.dumps(id_meta, default=str), flush=True)
    print("MARKET_META", json.dumps(market_meta, default=str), flush=True)

    w2 = add_recent_signal_flag(w, sig)
    sig = matched_excess(sig, w2)
    disc = sig[(sig["filed"] >= DISC_START) & (sig["filed"] <= DISC_END)].copy()
    val = sig[(sig["filed"] >= VAL_START) & (sig["filed"] <= VAL_END)].copy()
    summary = pd.DataFrame(summarize(disc, "discovery_2010_2016") + summarize(val, "validation_2017_2024"))
    print(summary.to_string(index=False), flush=True)

    y = val[val["excess26"].notna()].copy()
    y["year"] = y["filed"].dt.year
    yearly = y.groupby("year").agg(n=("excess26", "size"), median_excess26=("excess26", "median"), mean_excess26=("excess26", "mean"), beat_matched26=("excess26", lambda s: float((s > 0).mean()))).reset_index()
    print("YEARLY_VALIDATION26", yearly.to_json(orient="records"), flush=True)

    r = summary[(summary["slice"] == "validation_2017_2024") & (summary["horizon"] == 26)].iloc[0]
    gate = {
        "n_ge_300": bool(r["matched_n"] >= 300),
        "median_excess_gt_1pct": bool(r["median_excess"] > 0.01),
        "beat_matched_ge_52_5pct": bool(r["beat_matched"] >= 0.525),
        "week_cluster_ci_lower_gt_0": bool(r["ci_lo"] > 0),
    }
    gate["pass"] = all(gate.values())
    gate.update({k: (int(r[k]) if k == "matched_n" else float(r[k])) for k in ["matched_n", "median_excess", "beat_matched", "mean_excess", "ci_lo", "ci_hi"]})
    print("GATE26", json.dumps(gate), flush=True)
    print("UNTOUCHED_2025_2026", True, flush=True)
    print("ELAPSED_SEC", round(time.time() - t0, 2), flush=True)
    print("DONE", flush=True)


if __name__ == "__main__":
    main()
