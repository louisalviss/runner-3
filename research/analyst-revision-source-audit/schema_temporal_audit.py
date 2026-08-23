import io
import json
import re
from urllib.parse import quote

import numpy as np
import pandas as pd
import requests

S = requests.Session()
S.headers.update({"User-Agent": "louis-research-schema-audit/1.0"})

CANDIDATES = [
    "chuyin0321/earnings-estimate-stocks",
    "jwigginton/earnings-estimate-sp500",
    "siddharthmb/stocks-earnings-eps_estimate",
    "siddharthmb/stocks-earnings-sales_estimate",
    "sovai/earnings_surprise",
]


def get_json(url, timeout=60):
    r = S.get(url, timeout=timeout)
    print("HTTP", r.status_code, url)
    r.raise_for_status()
    return r.json()


def first_rows(did):
    u = f"https://datasets-server.huggingface.co/first-rows?dataset={quote(did)}&config=default&split=train"
    j = get_json(u)
    feats = j.get("features") or []
    rows = [x.get("row", {}) for x in (j.get("rows") or [])]
    return feats, rows


def print_first_row_audit(did):
    try:
        feats, rows = first_rows(did)
        print("DATASET", did)
        print("FEATURES", json.dumps(feats, default=str)[:12000])
        print("FIRST_ROWS", json.dumps(rows[:8], default=str)[:16000])
        return feats, rows
    except Exception as e:
        print("FIRST_ROWS_ERROR", did, repr(e))
        return [], []


def hf_parquet_url(did):
    j = get_json(f"https://datasets-server.huggingface.co/parquet?dataset={quote(did)}")
    files = j.get("parquet_files") or []
    if not files:
        raise RuntimeError(f"no parquet files for {did}")
    return [x["url"] for x in files]


def full_sovai_audit():
    did = "sovai/earnings_surprise"
    urls = hf_parquet_url(did)
    print("SOVAI_PARQUET_URLS", json.dumps(urls))
    frames = [pd.read_parquet(u) for u in urls]
    df = pd.concat(frames, ignore_index=True)
    print("SOVAI_SHAPE", df.shape)
    print("SOVAI_COLUMNS", json.dumps(list(df.columns)))
    print("SOVAI_DTYPES", json.dumps({c: str(t) for c,t in df.dtypes.items()}))

    # Normalize candidate date columns.
    for c in df.columns:
        lc = c.lower()
        if lc in {"date", "date_pub", "publication_date", "report_date"} or lc.endswith("_date"):
            try:
                x = pd.to_datetime(df[c], errors="coerce")
                if x.notna().any():
                    print("DATE_RANGE", c, str(x.min()), str(x.max()), "nonnull", int(x.notna().sum()))
            except Exception:
                pass

    cols_lower = {c.lower(): c for c in df.columns}
    ticker = next((cols_lower[k] for k in ["ticker", "symbol"] if k in cols_lower), None)
    snap = next((cols_lower[k] for k in ["date", "snapshot_date", "week"] if k in cols_lower), None)
    pub = next((cols_lower[k] for k in ["date_pub", "publication_date", "report_date"] if k in cols_lower), None)
    est_candidates = [c for c in df.columns if "estimate" in c.lower() or "estimated" in c.lower()]
    actual_candidates = [c for c in df.columns if "actual" in c.lower()]
    print("SOVAI_KEY_COLUMNS", json.dumps({"ticker":ticker,"snapshot":snap,"publication":pub,"estimates":est_candidates,"actuals":actual_candidates}))

    if not (ticker and snap and pub and est_candidates):
        print("SOVAI_TEMPORAL_VERDICT", "INSUFFICIENT_SCHEMA")
        return

    df = df.copy()
    df[snap] = pd.to_datetime(df[snap], errors="coerce")
    df[pub] = pd.to_datetime(df[pub], errors="coerce")
    pre = df[df[snap].notna() & df[pub].notna() & (df[snap] < df[pub])].copy()
    pre["lead_days"] = (pre[pub] - pre[snap]).dt.days
    pre = pre[(pre["lead_days"] >= 0) & (pre["lead_days"] <= 365)]
    print("SOVAI_PREPUB_ROWS", len(pre), "groups", pre.groupby([ticker,pub]).ngroups)

    for est in est_candidates:
        x = pd.to_numeric(pre[est], errors="coerce")
        tmp = pre.assign(_est=x).dropna(subset=["_est"])
        if tmp.empty:
            continue
        g = tmp.sort_values(snap).groupby([ticker,pub], sort=False)
        counts = g.size()
        multi_keys = counts[counts >= 2].index
        if len(multi_keys) == 0:
            print("EST_AUDIT", est, "no multi-snapshot groups")
            continue
        gm = tmp.set_index([ticker,pub]).loc[multi_keys].reset_index().sort_values([ticker,pub,snap])
        gg = gm.groupby([ticker,pub], sort=False)
        nunique = gg["_est"].nunique(dropna=True)
        first = gg["_est"].first()
        last = gg["_est"].last()
        changed = (nunique > 1)
        first_last_diff = (first != last)
        revisions = gg["_est"].apply(lambda s: int((s.diff().abs() > 1e-12).sum()))
        print("EST_AUDIT", est, json.dumps({
            "rows": int(len(gm)),
            "multi_groups": int(len(nunique)),
            "groups_with_any_change": int(changed.sum()),
            "pct_groups_with_any_change": float(changed.mean()),
            "groups_first_last_diff": int(first_last_diff.sum()),
            "pct_first_last_diff": float(first_last_diff.mean()),
            "median_revision_events": float(revisions.median()),
            "p90_revision_events": float(revisions.quantile(.9)),
            "estimate_min": float(gm["_est"].min()),
            "estimate_max": float(gm["_est"].max()),
        }))

    # Explicitly quantify the known leakage fields: future publication/actual visible in pre-publication snapshots.
    known_future = []
    for c in [pub] + actual_candidates:
        if c and c in pre.columns:
            nonnull = int(pre[c].notna().sum())
            if nonnull:
                known_future.append({"column":c,"prepub_nonnull":nonnull,"pct":float(pre[c].notna().mean())})
    print("SOVAI_KNOWN_FUTURE_FIELDS_PRESENT_PREPUB", json.dumps(known_future))
    print("SOVAI_TEMPORAL_NOTE", "Estimate series may be usable only if revision values themselves vary by real snapshot date; date_pub/actual must never enter signal features and report grouping must be reconstructed without future knowledge.")


def large_dataset_schema_only(did):
    # Use datasets-server first rows plus parquet metadata. Do not treat unknown provenance as PIT-valid.
    urls = hf_parquet_url(did)
    print("LARGE_DATASET_PARQUET_COUNT", did, len(urls))
    # Download only the first parquet file headers/body; size is manageable on hosted runner.
    u = urls[0]
    r = S.get(u, timeout=180)
    print("DOWNLOAD", did, r.status_code, len(r.content))
    r.raise_for_status()
    import pyarrow.parquet as pq
    pf = pq.ParquetFile(io.BytesIO(r.content))
    cols = pf.schema.names
    print("PARQUET_SCHEMA", did, json.dumps(cols))
    # Read only likely provenance/timestamp/estimate columns from first row group.
    likely = [c for c in cols if any(k in c.lower() for k in ("date","time","ticker","symbol","estimate","eps","fiscal","period","analyst","source","revision"))]
    if not likely:
        likely = cols[:20]
    tab = pf.read_row_group(0, columns=likely[:30]).to_pandas()
    print("ROWGROUP_SAMPLE_SHAPE", did, tab.shape)
    print("ROWGROUP_SAMPLE_DTYPES", did, json.dumps({c:str(t) for c,t in tab.dtypes.items()}))
    print("ROWGROUP_SAMPLE", did, tab.head(12).to_json(orient="records", date_format="iso")[:20000])
    for c in tab.columns:
        if "date" in c.lower() or "time" in c.lower():
            z = pd.to_datetime(tab[c], errors="coerce")
            if z.notna().any():
                print("SAMPLE_DATE_RANGE", did, c, str(z.min()), str(z.max()), int(z.notna().sum()))
    print("PROVENANCE_WARNING", did, "No explicit dataset card/license/source provenance was found in source audit; cannot call PIT-valid from schema alone.")


def docs_audit():
    docs = {
        "alphavantage":"https://www.alphavantage.co/documentation/",
        "finnhub":"https://finnhub.io/docs/api",
    }
    for name,u in docs.items():
        try:
            t = S.get(u, timeout=60).text
            low = re.sub(r"\s+", " ", t)
            for needle in ["EARNINGS_ESTIMATES", "earnings estimates", "estimate revision", "recommendation trends"]:
                pos = low.lower().find(needle.lower())
                if pos >= 0:
                    print("DOC_SNIPPET", name, needle, low[max(0,pos-1200):pos+3500][:5000])
        except Exception as e:
            print("DOC_ERROR", name, repr(e))


def main():
    for did in CANDIDATES:
        print_first_row_audit(did)
    full_sovai_audit()
    for did in ["siddharthmb/stocks-earnings-eps_estimate", "siddharthmb/stocks-earnings-sales_estimate"]:
        try:
            large_dataset_schema_only(did)
        except Exception as e:
            print("LARGE_DATASET_ERROR", did, repr(e))
    docs_audit()
    print("SCHEMA_TEMPORAL_AUDIT_DONE")

if __name__ == "__main__":
    main()
