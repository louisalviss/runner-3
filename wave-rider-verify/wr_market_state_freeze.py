#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import hashlib
import io
import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import sklearn
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline

FEATURES = [
    "atr_bps", "atr_ratio_14_50", "range_atr", "body_atr", "gap_atr",
    "rv20_bps", "trend20_atr", "efficiency20", "location20",
    "session_frac", "tf10",
]
UNIVERSE = [
    "AAPL","ADBE","ADI","ADP","ADSK","AEP","ALNY","AMAT","AMD","AMGN","AMZN","AVGO",
    "BKR","CDNS","CMCSA","COST","CPRT","CSCO","CSGP","CSX","CTSH","DXCM","EA","EXC",
    "FANG","FTNT","GILD","GOOG","GOOGL","HON","IDXX","INTC","INTU","ISRG","KHC","LRCX",
    "MAR","MCHP","MDLZ","META","MPWR","MRVL","MSFT","MU","NFLX","NVDA","ODFL","ORLY",
    "PANW","PAYX","PCAR","PEP","PLTR","PYPL","QCOM","REGN","ROST","SBUX","SNPS","TMUS",
    "TSLA","TTWO","TXN","VRTX","WDAY","WDC","WMT","ZS",
]
SOURCE_RUN_ID = 32533359788
HOLDOUT_START = "2026-08-22T00:00:00Z"
HOLDOUT_END = "2026-12-31T23:59:59Z"
TRAINING_DATA_END_EXCLUSIVE = "2026-08-21T00:00:00Z"


def load_rows(root: Path) -> pd.DataFrame:
    rows = []
    for p in root.rglob("features-*.jsonl"):
        for ln in p.read_text(encoding="utf-8").splitlines():
            if ln.strip():
                rows.append(json.loads(ln))
    if not rows:
        raise RuntimeError("no frozen feature rows found")
    df = pd.DataFrame(rows)
    required = {"symbol", "tf", "signal", "exit", "R", "net_1bps", "net_2bps", *FEATURES}
    missing = sorted(required - set(df.columns))
    if missing:
        raise RuntimeError(f"missing columns: {missing}")
    return df.sort_values(["signal", "symbol", "tf", "exit"]).reset_index(drop=True)


def dataset_hash(df: pd.DataFrame) -> str:
    cols = ["symbol", "tf", "signal", "exit", "R", "net_1bps", "net_2bps", *FEATURES]
    payload = df[cols].to_csv(index=False, float_format="%.17g").encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True)
    ap.add_argument("--output", required=True)
    args = ap.parse_args()
    root = Path(args.input); out = Path(args.output); out.mkdir(parents=True, exist_ok=True)
    df = load_rows(root)
    if len(df) != 19683: raise RuntimeError(f"expected canonical 19683 rows, got {len(df)}")
    if sorted(df["symbol"].unique().tolist()) != sorted(UNIVERSE): raise RuntimeError("frozen universe mismatch")
    holdout_ms = int(pd.Timestamp(HOLDOUT_START).timestamp() * 1000)
    if int(df["signal"].max()) >= holdout_ms: raise RuntimeError("training rows overlap holdout")

    model = Pipeline([
        ("imp", SimpleImputer(strategy="median")),
        ("m", HistGradientBoostingRegressor(max_iter=100, learning_rate=0.05, max_depth=2,
            min_samples_leaf=50, l2_regularization=10.0, random_state=7)),
    ])
    model.fit(df[FEATURES], df["net_1bps"])
    pred = model.predict(df[FEATURES]); threshold = float(np.quantile(pred, 0.70))
    bio = io.BytesIO(); joblib.dump(model, bio, compress=3); model_bytes = bio.getvalue()
    model_sha = hashlib.sha256(model_bytes).hexdigest(); model_b64 = base64.b64encode(model_bytes).decode("ascii")

    manifest = {
        "schema_version": 1, "frozen": True,
        "purpose": "Wave Rider market-state final model for genuinely unseen forward holdout",
        "source_repo": "louisalviss/runner-3", "source_market_state_run_id": SOURCE_RUN_ID,
        "training_rows": int(len(df)), "training_symbols": int(df["symbol"].nunique()),
        "training_data_end_exclusive_utc": TRAINING_DATA_END_EXCLUSIVE,
        "holdout_start_utc": HOLDOUT_START, "holdout_end_utc": HOLDOUT_END,
        "features": FEATURES, "universe": UNIVERSE, "timeframes_minutes": [5, 10],
        "target": "net_1bps", "selector": "prediction > frozen training-prediction q70",
        "selector_threshold": threshold, "train_selected_n": int((pred > threshold).sum()),
        "model": {"type": "Pipeline(SimpleImputer(median), HistGradientBoostingRegressor)",
            "params": {"max_iter":100,"learning_rate":0.05,"max_depth":2,"min_samples_leaf":50,
                       "l2_regularization":10.0,"random_state":7}},
        "runtime": {"python":"3.12","scikit_learn":sklearn.__version__,"joblib":joblib.__version__,
                    "numpy":np.__version__,"pandas":pd.__version__},
        "dataset_sha256": dataset_hash(df), "model_joblib_sha256": model_sha,
        "no_retrain_no_tuning": True,
        "primary_gate_review": {"not_before_utc":"2027-01-01T00:00:00Z","minimum_selected_trades":100,
            "net_1bps_R_gt":0.0,"PF_1bps_gte":1.20,"max_DD_R_gte":-20.0,"minimum_distinct_symbols":15,
            "max_single_symbol_abs_R_share":0.25,"annualized_return_is_not_a_primary_gate":True},
        "interim_policy": "Accumulate counts only; do not tune model/features/universe/threshold from holdout outcomes."
    }
    (out/"market_state_hgb_q70.joblib.b64").write_text(model_b64+"\n", encoding="utf-8")
    (out/"market_state_hgb_q70_manifest.json").write_text(json.dumps(manifest, indent=2)+"\n", encoding="utf-8")
    print(json.dumps({"training_rows":len(df),"threshold":threshold,"train_selected_n":int((pred>threshold).sum()),
        "dataset_sha256":manifest["dataset_sha256"],"model_joblib_sha256":model_sha,"runtime":manifest["runtime"]}, indent=2))

if __name__ == "__main__": main()
