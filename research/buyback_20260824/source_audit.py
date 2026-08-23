from __future__ import annotations

import json
import time
from datetime import datetime

import pandas as pd
import requests

UA = "research-backtest/1.0 contact research@example.com"
S = requests.Session()
S.headers.update({"User-Agent": UA, "Accept-Encoding": "gzip, deflate"})

FRAMES = ["CY2019Q1", "CY2020Q2", "CY2022Q3", "CY2024Q1"]
CONCEPTS = [
    ("us-gaap", "PaymentsForRepurchaseOfCommonStock", "USD"),
    ("us-gaap", "PaymentsForRepurchaseOfCommonAndPreferredStock", "USD"),
    ("us-gaap", "WeightedAverageNumberOfDilutedSharesOutstanding", "shares"),
]
COMPANIES = {
    "AAPL": "0000320193",
    "MSFT": "0000789019",
    "JPM": "0000019617",
    "XOM": "0000034088",
}


def get(url: str):
    r = S.get(url, timeout=60)
    print("HTTP", r.status_code, len(r.content), url, flush=True)
    r.raise_for_status()
    time.sleep(0.12)
    return r.json()


def frame_audit():
    out = []
    for taxonomy, concept, unit in CONCEPTS:
        for frame in FRAMES:
            url = f"https://data.sec.gov/api/xbrl/frames/{taxonomy}/{concept}/{unit}/{frame}.json"
            try:
                j = get(url)
            except Exception as e:
                out.append({"concept": concept, "frame": frame, "error": repr(e)})
                continue
            facts = pd.DataFrame(j.get("data", []))
            rec = {"concept": concept, "frame": frame, "n": int(len(facts)), "cols": list(facts.columns)}
            if not facts.empty:
                for c in ["filed", "end"]:
                    if c in facts:
                        facts[c] = pd.to_datetime(facts[c], errors="coerce")
                if {"filed", "end"}.issubset(facts.columns):
                    lag = (facts["filed"] - facts["end"]).dt.days
                    rec.update({
                        "lag_median": float(lag.median()) if lag.notna().any() else None,
                        "pct_lag_le_120": float((lag <= 120).mean()),
                        "pct_lag_gt_180": float((lag > 180).mean()),
                        "filed_min": str(facts["filed"].min().date()) if facts["filed"].notna().any() else None,
                        "filed_max": str(facts["filed"].max().date()) if facts["filed"].notna().any() else None,
                    })
                if "form" in facts:
                    rec["forms"] = facts["form"].value_counts(dropna=False).head(8).to_dict()
                rec["sample"] = facts.head(2).to_dict("records")
            out.append(rec)
    print("FRAME_AUDIT", json.dumps(out, default=str), flush=True)
    return out


def companyconcept_audit():
    out = []
    for sym, cik in COMPANIES.items():
        for concept, unit in [
            ("PaymentsForRepurchaseOfCommonStock", "USD"),
            ("PaymentsForRepurchaseOfCommonAndPreferredStock", "USD"),
            ("WeightedAverageNumberOfDilutedSharesOutstanding", "shares"),
        ]:
            url = f"https://data.sec.gov/api/xbrl/companyconcept/CIK{cik}/us-gaap/{concept}.json"
            try:
                j = get(url)
            except Exception as e:
                out.append({"symbol": sym, "concept": concept, "error": repr(e)})
                continue
            rows = pd.DataFrame(j.get("units", {}).get(unit, []))
            rec = {"symbol": sym, "concept": concept, "n": int(len(rows)), "cols": list(rows.columns)}
            if not rows.empty:
                for c in ["filed", "start", "end"]:
                    if c in rows:
                        rows[c] = pd.to_datetime(rows[c], errors="coerce")
                q = rows.copy()
                if "form" in q:
                    q = q[q["form"].isin(["10-Q", "10-K"])]
                if {"start", "end"}.issubset(q.columns):
                    q["duration"] = (q["end"] - q["start"]).dt.days
                    q = q[q["duration"].between(60, 120, inclusive="both")]
                if {"filed", "end"}.issubset(q.columns):
                    q["file_lag"] = (q["filed"] - q["end"]).dt.days
                rec.update({
                    "quarter_like_n": int(len(q)),
                    "quarter_like_2017_2024": int(((q.get("end", pd.Series(dtype="datetime64[ns]")) >= pd.Timestamp("2017-01-01")) & (q.get("end", pd.Series(dtype="datetime64[ns]")) <= pd.Timestamp("2024-12-31"))).sum()) if "end" in q else 0,
                    "accession_n": int(q["accn"].nunique()) if "accn" in q else None,
                    "duplicate_accn_end": int(q.duplicated([c for c in ["accn", "end"] if c in q.columns]).sum()) if len(q) else 0,
                    "lag_median": float(q["file_lag"].median()) if "file_lag" in q and q["file_lag"].notna().any() else None,
                    "sample_quarter_like": q.sort_values("filed").tail(5).to_dict("records") if len(q) else [],
                })
            out.append(rec)
    print("COMPANYCONCEPT_AUDIT", json.dumps(out, default=str), flush=True)
    return out


def main():
    f = frame_audit()
    c = companyconcept_audit()
    rep = [r for r in c if "PaymentsForRepurchase" in r.get("concept", "") and r.get("quarter_like_2017_2024", 0) > 0]
    share = [r for r in c if r.get("concept") == "WeightedAverageNumberOfDilutedSharesOutstanding" and r.get("quarter_like_2017_2024", 0) > 0]
    status = "SOURCE_PASS_FOR_FULL_PIT_BUILD" if len(rep) >= 2 and len(share) >= 2 else "SOURCE_FAIL"
    print("SOURCE_GATE", json.dumps({"status": status, "rep_companyconcept_passes": len(rep), "share_companyconcept_passes": len(share), "note": "Frames are discovery/coverage only; historical signal values must use companyconcept filing-version rows keyed by filed/accn to avoid later-restatement leakage."}), flush=True)


if __name__ == "__main__":
    main()
