from __future__ import annotations

import json
import time
from pathlib import Path

import numpy as np
import pandas as pd
import requests

import backtest as px

OUT = Path("artifacts/quality_factor_20260824")
OUT.mkdir(parents=True, exist_ok=True)
DISCOVERY = px.DISCOVERY
VALIDATION = px.VALIDATION
HORIZONS = px.HORIZONS
UA = "runner-3-quality-factor/1.0 research-contact-github"
SEC_TICKERS = "https://www.sec.gov/files/company_tickers.json"
FALLBACK_CIKS = "https://raw.githubusercontent.com/K0D1Z/sp500-quantitative-dataset/main/data/config/fallback_ciks.json"

FLOW_CONCEPTS = {
    "revenue": ["RevenueFromContractWithCustomerExcludingAssessedTax", "SalesRevenueNet", "Revenues"],
    "net_income": ["NetIncomeLoss", "ProfitLoss"],
    "ocf": ["NetCashProvidedByUsedInOperatingActivities"],
    "capex": ["PaymentsToAcquirePropertyPlantAndEquipment", "PaymentsForAdditionsToPropertyPlantAndEquipment"],
}
POINT_CONCEPTS = {
    "assets": ["Assets"],
    "liabilities": ["Liabilities"],
}


def get_json(url: str, retries=5):
    headers = {"User-Agent": UA, "Accept-Encoding": "gzip, deflate"}
    last = None
    for k in range(retries):
        try:
            r = requests.get(url, headers=headers, timeout=60)
            if r.status_code in (403, 429, 502, 503, 504):
                time.sleep(1 + 1.5 * k)
                continue
            r.raise_for_status()
            return r.json()
        except Exception as e:
            last = e
            time.sleep(1 + 1.5 * k)
    raise RuntimeError(f"failed {url}: {last}")


def build_cik_map(symbols):
    sec = get_json(SEC_TICKERS)
    out = {}
    for item in sec.values():
        t = px.norm_ticker(item.get("ticker", ""))
        if t in symbols:
            out[t] = str(item["cik_str"]).zfill(10)
    try:
        fb = get_json(FALLBACK_CIKS)
        for t, v in fb.items():
            nt = px.norm_ticker(t)
            if nt in symbols and nt not in out:
                cik = v.get("CIK") or v.get("cik")
                if cik:
                    out[nt] = str(cik).zfill(10)
    except Exception:
        pass
    return out


def facts_for_concepts(cf, concepts, flow):
    us = cf.get("facts", {}).get("us-gaap", {})
    rows = []
    for rank, concept in enumerate(concepts):
        node = us.get(concept)
        if not node:
            continue
        vals = node.get("units", {}).get("USD") or []
        tmp = []
        for x in vals:
            if str(x.get("form", "")) not in ("10-K", "10-K/A"):
                continue
            try:
                end = pd.Timestamp(x["end"]); filed = pd.Timestamp(x["filed"]); val = float(x["val"])
            except Exception:
                continue
            lag = (filed - end).days
            if lag < 0 or lag > 210 or not np.isfinite(val):
                continue
            if flow:
                if not x.get("start"):
                    continue
                try:
                    start = pd.Timestamp(x["start"])
                except Exception:
                    continue
                dur = (end - start).days
                if dur < 250 or dur > 460:
                    continue
            tmp.append({"end": end, "filed": filed, "val": val, "rank": rank})
        if tmp:
            rows.extend(tmp)
            break
    if not rows:
        return pd.DataFrame(columns=["end", "filed", "val"])
    d = pd.DataFrame(rows).sort_values(["end", "filed", "rank"]).groupby("end", as_index=False).first()
    return d[["end", "filed", "val"]]


def company_snapshots(symbol, cik):
    cf = get_json(f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json")
    series = {}
    for key, concepts in FLOW_CONCEPTS.items():
        d = facts_for_concepts(cf, concepts, True)
        if not d.empty:
            series[key] = d.rename(columns={"filed": f"{key}_filed", "val": key})
    for key, concepts in POINT_CONCEPTS.items():
        d = facts_for_concepts(cf, concepts, False)
        if not d.empty:
            series[key] = d.rename(columns={"filed": f"{key}_filed", "val": key})
    if not series:
        return pd.DataFrame()
    ends = sorted(set().union(*[set(d.end) for d in series.values()]))
    b = pd.DataFrame({"end": ends})
    for d in series.values():
        b = b.merge(d, on="end", how="left")
    filed_cols = [c for c in b if c.endswith("_filed")]
    b["filed"] = b[filed_cols].max(axis=1)
    b["symbol"] = symbol
    for c in ["revenue", "net_income", "ocf", "capex", "assets", "liabilities"]:
        if c not in b:
            b[c] = np.nan
    b = b.sort_values("end")
    b["fcf"] = b.ocf - b.capex.abs()
    b["roa"] = b.net_income / b.assets.replace(0, np.nan)
    b["fcf_assets"] = b.fcf / b.assets.replace(0, np.nan)
    b["net_margin"] = b.net_income / b.revenue.replace(0, np.nan)
    b["revenue_yoy"] = b.revenue / b.revenue.shift(1) - 1
    b["revenue_accel"] = b.revenue_yoy - b.revenue_yoy.shift(1)
    b["leverage"] = b.liabilities / b.assets.replace(0, np.nan)
    return b[["symbol", "end", "filed", "roa", "fcf_assets", "net_margin", "revenue_yoy", "revenue_accel", "leverage"]].dropna(subset=["filed"])


def load_fundamentals(w):
    symbols = set(w.loc[w.member & w.week.between(DISCOVERY[0], VALIDATION[1]), "symbol"].astype(str).unique())
    cmap = build_cik_map(symbols)
    snaps = []; failed = []
    for i, sym in enumerate(sorted(symbols)):
        cik = cmap.get(sym)
        if not cik:
            failed.append((sym, "no_cik")); continue
        try:
            s = company_snapshots(sym, cik)
            if s.empty:
                failed.append((sym, "no_facts"))
            else:
                snaps.append(s)
        except Exception as e:
            failed.append((sym, repr(e)[:120]))
        if (i + 1) % 100 == 0:
            print("SEC", i + 1, "/", len(symbols), "ok", len(snaps), flush=True)
        time.sleep(0.08)
    allsnap = pd.concat(snaps, ignore_index=True) if snaps else pd.DataFrame()
    pd.DataFrame(failed, columns=["symbol", "reason"]).to_csv(OUT / "fundamental_failures.csv", index=False)
    return allsnap, {"member_symbols": len(symbols), "cik_mapped": len(cmap), "companies_with_facts": len(snaps), "snapshot_rows": len(allsnap), "failed": len(failed)}


def attach(base, snaps):
    cols = ["roa", "fcf_assets", "net_margin", "revenue_yoy", "revenue_accel", "leverage", "fund_filed"]
    for c in cols:
        base[c] = pd.NaT if c == "fund_filed" else np.nan
    if snaps.empty:
        return base
    for sym, idx in base.groupby("symbol", observed=True, sort=False).groups.items():
        s = snaps[snaps.symbol.eq(sym)].copy()
        if s.empty:
            continue
        s = s.rename(columns={"filed": "fund_filed"}).sort_values("fund_filed")
        left = base.loc[idx, ["week"]].sort_values("week")
        m = pd.merge_asof(left, s.drop(columns=["symbol", "end"]).sort_values("fund_filed"), left_on="week", right_on="fund_filed", direction="backward")
        m.index = left.index
        for c in cols:
            base.loc[m.index, c] = m[c].to_numpy()
    return base


def rank_features(base):
    for c in ["roa", "fcf_assets", "net_margin", "revenue_yoy", "revenue_accel"]:
        base[f"{c}_pct"] = base.groupby("week", observed=True)[c].rank(pct=True, method="average")
    base["quality_score"] = base[["roa_pct", "fcf_assets_pct", "revenue_yoy_pct"]].mean(axis=1, skipna=False)
    base["quality_pct"] = base.groupby("week", observed=True).quality_score.rank(pct=True, method="average")
    return base

SPECS = {
    "ROA_TOP20": (lambda x: x.roa_pct >= .80, lambda x: x.roa_pct.between(.40, .60), "profitability / ROA"),
    "FCF_ASSETS_TOP20": (lambda x: x.fcf_assets_pct >= .80, lambda x: x.fcf_assets_pct.between(.40, .60), "free-cash-flow profitability"),
    "REV_ACCEL_TOP20": (lambda x: x.revenue_accel_pct >= .80, lambda x: x.revenue_accel_pct.between(.40, .60), "revenue growth acceleration"),
    "QUALITY_TOP20": (lambda x: x.quality_pct >= .80, lambda x: x.quality_pct.between(.40, .60), "composite profitability + cash generation + growth"),
    "QUALITY_LOWVOL": (lambda x: (x.quality_pct >= .70) & (x.vol_pct <= .30), lambda x: (x.quality_pct <= .50) & (x.vol_pct <= .30), "quality conditional on low volatility"),
}


def evaluate(base, start, end, name, spec):
    sigfn, ctrlfn, mech = spec
    p = base[base.week.between(start, end)].copy()
    signals = p[sigfn(p)].copy()
    rows = []
    for h in HORIZONS:
        vals = []; weeks = []
        col = f"ret{h}"
        for week, sg in signals.groupby("week", observed=True):
            wp = p[p.week.eq(week)]
            cp = wp[ctrlfn(wp)]
            if cp.empty:
                continue
            for si, s in sg.iterrows():
                c = cp[cp.symbol.ne(s.symbol)]
                if c.empty or pd.isna(s[col]):
                    continue
                # Match current price state so quality is the main differentiator.
                dist = (c.prox52 - s.prox52).abs() / .10 + (c.vol13 - s.vol13).abs() / max(float(c.vol13.median()), 1e-6)
                ci = dist.idxmin(); cr = c.at[ci, col]
                if pd.notna(cr):
                    vals.append((float(s[col]), float(cr))); weeks.append(week)
        if vals:
            z = np.asarray(vals); ex = z[:,0] - z[:,1]
            d = pd.DataFrame({"week": weeks, "ex": ex})
            wm = d.groupby("week", observed=True).ex.mean().to_numpy()
            rng = np.random.default_rng(20260824 + h); n = len(wm)
            if n >= 8:
                bs = np.array([np.mean(wm[rng.integers(0,n,n)]) for _ in range(2500)])
                lo, hi = np.quantile(bs, [.025,.975])
            else: lo = hi = np.nan
            sr = z[:,0]
            rows.append({"strategy":name,"mechanism":mech,"horizon":h,"signal_n":len(sr),"matched_n":len(ex),"win_rate":float(np.mean(sr>0)),"median_return":float(np.median(sr)),"median_excess":float(np.median(ex)),"mean_excess":float(np.mean(ex)),"beat_matched":float(np.mean(ex>0)),"ci_lo":float(lo),"ci_hi":float(hi)})
        else:
            rows.append({"strategy":name,"mechanism":mech,"horizon":h,"signal_n":0,"matched_n":0,"win_rate":np.nan,"median_return":np.nan,"median_excess":np.nan,"mean_excess":np.nan,"beat_matched":np.nan,"ci_lo":np.nan,"ci_hi":np.nan})
    return rows


def pct(x): return "NA" if not np.isfinite(x) else f"{100*x:+.2f}%"


def main():
    w = px.add_member(px.features(px.load_weekly()), px.load_memberships())
    base = px.cross_section(w)
    snaps, meta = load_fundamentals(w)
    base = rank_features(attach(base, snaps))
    rows=[]
    for split,(a,b) in {"discovery":DISCOVERY,"validation":VALIDATION}.items():
        for name,spec in SPECS.items():
            for r in evaluate(base,a,b,name,spec): r["split"]=split; rows.append(r)
    res=pd.DataFrame(rows); res.to_csv(OUT/"results.csv",index=False)
    v=res[(res.split=="validation")&(res.horizon==13)].copy()
    v["gate"]=(v.matched_n>=100)&(v.median_excess>0)&(v.beat_matched>=.55)&(v.ci_lo>0)
    v["score"]=v.median_excess.fillna(-9)+.5*(v.beat_matched.fillna(0)-.5)
    best=v.sort_values(["gate","score"],ascending=[False,False]).iloc[0]
    lines=["# PIT Quality / Profitability Factor Search","",f"Coverage: {json.dumps(meta)}","Discovery 2005-2016; validation 2017-2024; filing-date PIT fundamentals; monthly signals; 13w primary.","Gate: matched N>=100, median excess>0, beat-control>=55%, signal-month bootstrap CI lower>0.","","| Strategy | N | Win | Median ret | Median excess | Beat control | CI95 | Gate |","|---|---:|---:|---:|---:|---:|---:|---|"]
    for r in v.itertuples(index=False):
        lines.append(f"| {r.strategy} | {r.signal_n} | {pct(r.win_rate)} | {pct(r.median_return)} | {pct(r.median_excess)} | {pct(r.beat_matched)} | [{pct(r.ci_lo)}, {pct(r.ci_hi)}] | {'PASS' if r.gate else 'FAIL'} |")
    lines += ["",f"Best: {best.strategy}; median excess {pct(best.median_excess)}; beat {pct(best.beat_matched)}; CI [{pct(best.ci_lo)}, {pct(best.ci_hi)}]; gate {'PASS' if best.gate else 'FAIL'}."]
    (OUT/"RESULT.md").write_text("\n".join(lines)+"\n",encoding="utf-8")
    (OUT/"summary.json").write_text(json.dumps({"meta":meta,"best":best.to_dict(),"validation13":v.to_dict("records")},indent=2,default=str),encoding="utf-8")
    print("\n".join(lines))

if __name__ == "__main__": main()
