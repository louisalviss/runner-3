#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import hashlib
import io
import json
from datetime import datetime, timezone
from pathlib import Path

import joblib
import pandas as pd

EXPECTED_UNIVERSE = [
    "AAPL","ADBE","ADI","ADP","ADSK","AEP","ALNY","AMAT","AMD","AMGN","AMZN","AVGO",
    "BKR","CDNS","CMCSA","COST","CPRT","CSCO","CSGP","CSX","CTSH","DXCM","EA","EXC",
    "FANG","FTNT","GILD","GOOG","GOOGL","HON","IDXX","INTC","INTU","ISRG","KHC","LRCX",
    "MAR","MCHP","MDLZ","META","MPWR","MRVL","MSFT","MU","NFLX","NVDA","ODFL","ORLY",
    "PANW","PAYX","PCAR","PEP","PLTR","PYPL","QCOM","REGN","ROST","SBUX","SNPS","TMUS",
    "TSLA","TTWO","TXN","VRTX","WDAY","WDC","WMT","ZS",
]
DETERMINISTIC_FIELDS = [
    "symbol","tf","signal","exit","R","net_1bps","net_2bps","feature_bar",
    "atr_bps","atr_ratio_14_50","range_atr","body_atr","gap_atr","rv20_bps",
    "trend20_atr","efficiency20","location20","session_frac","tf10","prediction","selected",
]


def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def stable_fingerprint(rec: dict) -> str:
    payload = {k: rec[k] for k in DETERMINISTIC_FIELDS}
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    return sha256_bytes(raw)


def load_model(model_path: Path, manifest: dict):
    raw = base64.b64decode(model_path.read_text(encoding="utf-8").strip())
    got = sha256_bytes(raw)
    expected = manifest["model_joblib_sha256"]
    if got != expected:
        raise RuntimeError(f"frozen model hash mismatch: {got} != {expected}")
    return joblib.load(io.BytesIO(raw))


def load_collector_meta(root: Path) -> dict[str, dict]:
    metas = {}
    for p in root.rglob("collector-meta-*.json"):
        m = json.loads(p.read_text(encoding="utf-8"))
        metas[m["symbol"]] = m
    missing = sorted(set(EXPECTED_UNIVERSE) - set(metas))
    extra = sorted(set(metas) - set(EXPECTED_UNIVERSE))
    if missing or extra:
        raise RuntimeError(f"collector completeness failure missing={missing} extra={extra}")
    bad = [s for s,m in metas.items() if m.get("status") != "OK"]
    if bad:
        raise RuntimeError(f"collector failed closed for symbols: {bad}")
    ends = {m["collection_end_exclusive_utc"] for m in metas.values()}
    if len(ends) != 1:
        raise RuntimeError(f"collector end mismatch: {sorted(ends)}")
    return metas


def load_rows(root: Path) -> pd.DataFrame:
    rows = []
    for p in root.rglob("features-*.jsonl"):
        for ln in p.read_text(encoding="utf-8").splitlines():
            if ln.strip():
                rows.append(json.loads(ln))
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    keys = ["symbol", "tf", "signal", "exit"]
    if df.duplicated(keys).any():
        dup = df[df.duplicated(keys, keep=False)][keys].head(20).to_dict("records")
        raise RuntimeError(f"duplicate forward keys: {dup}")
    return df.sort_values(["signal", "symbol", "tf", "exit"]).reset_index(drop=True)


def empty_ledger(manifest: dict) -> dict:
    return {
        "schema_version": 1,
        "protocol": {
            "model_joblib_sha256": manifest["model_joblib_sha256"],
            "dataset_sha256": manifest["dataset_sha256"],
            "source_market_state_run_id": manifest["source_market_state_run_id"],
            "holdout_start_utc": manifest["holdout_start_utc"],
            "holdout_end_utc": manifest["holdout_end_utc"],
            "features": manifest["features"],
            "universe": manifest["universe"],
            "timeframes_minutes": manifest["timeframes_minutes"],
            "selector_threshold": manifest["selector_threshold"],
            "no_retrain_no_tuning": True,
        },
        "records": [],
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True)
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--model", required=True)
    ap.add_argument("--ledger", required=True)
    ap.add_argument("--status", required=True)
    args = ap.parse_args()

    root = Path(args.input)
    manifest_path = Path(args.manifest)
    model_path = Path(args.model)
    ledger_path = Path(args.ledger)
    status_path = Path(args.status)

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("no_retrain_no_tuning") is not True:
        raise RuntimeError("freeze manifest is not locked")
    if manifest["universe"] != EXPECTED_UNIVERSE:
        raise RuntimeError("manifest universe differs from frozen 68-stock universe")

    metas = load_collector_meta(root)
    df = load_rows(root)
    model = load_model(model_path, manifest)
    features = manifest["features"]
    threshold = float(manifest["selector_threshold"])
    start_ms = int(pd.Timestamp(manifest["holdout_start_utc"]).timestamp() * 1000)
    end_ms = int((pd.Timestamp(manifest["holdout_end_utc"]) + pd.Timedelta(milliseconds=1)).timestamp() * 1000)

    if not df.empty:
        df = df[(df["signal"].astype("int64") >= start_ms) & (df["signal"].astype("int64") < end_ms)].copy()
        if not df.empty:
            df["prediction"] = model.predict(df[features])
            df["selected"] = df["prediction"] > threshold

    ledger = empty_ledger(manifest)
    if ledger_path.exists():
        old = json.loads(ledger_path.read_text(encoding="utf-8"))
        if old.get("protocol") != ledger["protocol"]:
            raise RuntimeError("forward protocol changed; refusing to contaminate holdout")
        ledger = old

    existing = {r["key"]: r for r in ledger["records"]}
    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    new_n = new_selected_n = 0

    if not df.empty:
        for _, row in df.iterrows():
            rec = {k: row[k] for k in DETERMINISTIC_FIELDS if k in row.index}
            # Normalize numpy scalars to plain JSON values.
            for k,v in list(rec.items()):
                if hasattr(v, "item"):
                    v = v.item()
                if k == "selected":
                    v = bool(v)
                elif k in {"symbol", "feature_bar"}:
                    v = str(v)
                elif k in {"tf", "signal", "exit"}:
                    v = int(v)
                else:
                    v = float(v)
                rec[k] = v
            key = f"{rec['symbol']}|{rec['tf']}|{rec['signal']}|{rec['exit']}"
            fp = stable_fingerprint(rec)
            if key in existing:
                if existing[key].get("fingerprint_sha256") != fp:
                    raise RuntimeError(f"previously frozen forward record changed: {key}")
                continue
            stored = {"key": key, **rec, "fingerprint_sha256": fp, "recorded_at_utc": now}
            ledger["records"].append(stored)
            existing[key] = stored
            new_n += 1
            new_selected_n += int(stored["selected"])

    ledger["records"].sort(key=lambda r: (r["signal"], r["symbol"], r["tf"], r["exit"]))
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    status_path.parent.mkdir(parents=True, exist_ok=True)
    ledger_path.write_text(json.dumps(ledger, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    records = ledger["records"]
    selected = [r for r in records if r["selected"]]
    status = {
        "schema_version": 1,
        "generated_at_utc": now,
        "protocol_frozen": True,
        "model_joblib_sha256": manifest["model_joblib_sha256"],
        "dataset_sha256": manifest["dataset_sha256"],
        "holdout_start_utc": manifest["holdout_start_utc"],
        "holdout_end_utc": manifest["holdout_end_utc"],
        "collection_end_exclusive_utc": next(iter(metas.values()))["collection_end_exclusive_utc"],
        "completed_trade_rows": len(records),
        "selected_trade_rows": len(selected),
        "selected_symbols": len({r["symbol"] for r in selected}),
        "new_trade_rows_this_run": new_n,
        "new_selected_rows_this_run": new_selected_n,
        "performance_hidden_during_primary_holdout": True,
        "primary_review_not_before_utc": manifest["primary_gate_review"]["not_before_utc"],
        "no_retrain_no_tuning": True,
        "note": "Counts only. Do not change features/model/universe/threshold based on holdout outcomes before primary review.",
    }
    status_path.write_text(json.dumps(status, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(status, indent=2))


if __name__ == "__main__":
    main()
