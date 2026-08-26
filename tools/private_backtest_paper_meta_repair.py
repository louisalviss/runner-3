#!/usr/bin/env python3
from __future__ import annotations

import json
import tempfile
from pathlib import Path

import private_backtest_worker_v2 as core

PROJECT = "private-backtest"
SCOPE = "bt-paper-sim-super-rsi-v1"

HELPER = r'''from __future__ import annotations
import pandas as pd
import dukascopy_python as duka

DUKASCOPY_ALIASES = {"META": "FB"}

def resolve_symbol(symbol):
    s = str(symbol).strip().upper()
    if not s:
        return None
    return f"{DUKASCOPY_ALIASES.get(s, s)}.US/USD"

def pick_const(names):
    for name in names:
        if hasattr(duka, name):
            return getattr(duka, name)
    raise AttributeError(f"None of constants exist in dukascopy_python: {tuple(names)}")

def month_chunks(start, end):
    cur = pd.Timestamp(start); stop = pd.Timestamp(end)
    cur = cur.tz_localize("UTC") if cur.tzinfo is None else cur.tz_convert("UTC")
    stop = stop.tz_localize("UTC") if stop.tzinfo is None else stop.tz_convert("UTC")
    while cur < stop:
        if cur.month == 12:
            nxt = pd.Timestamp(year=cur.year + 1, month=1, day=1, tz="UTC")
        else:
            nxt = pd.Timestamp(year=cur.year, month=cur.month + 1, day=1, tz="UTC")
        yield cur, min(nxt, stop)
        cur = nxt

def _naive_utc(value):
    ts = pd.Timestamp(value)
    ts = ts.tz_localize("UTC") if ts.tzinfo is None else ts.tz_convert("UTC")
    return ts.to_pydatetime().replace(tzinfo=None)

def fetch_side(instrument, offer_side, start, end, source_minutes):
    interval_name = f"INTERVAL_MIN_{int(source_minutes)}"
    if not hasattr(duka, interval_name):
        raise ValueError(f"dukascopy-python does not expose {interval_name}")
    df = duka.fetch(instrument=instrument, interval=getattr(duka, interval_name), offer_side=offer_side,
                    start=_naive_utc(start), end=_naive_utc(end), max_retries=5)
    if df is None or len(df) == 0:
        return pd.DataFrame(columns=["open", "high", "low", "close"])
    out = df.copy(); out.columns = [str(c).lower() for c in out.columns]
    required = ["open", "high", "low", "close"]
    missing = [c for c in required if c not in out.columns]
    if missing:
        raise ValueError(f"Dukascopy frame missing OHLC columns: {missing}; columns={list(out.columns)}")
    out.index = pd.to_datetime(out.index, utc=True)
    out = out.sort_index(); out = out[~out.index.duplicated(keep="last")]
    return out[required].astype(float)
'''

def main():
    work = Path(tempfile.mkdtemp(prefix="paper-meta-repair-"))
    mp = work / "manifest.json"
    core.download_artifact(PROJECT, SCOPE, "manifest.json", mp)
    manifest = json.loads(mp.read_text(encoding="utf-8"))
    helper_name = manifest["files"]["helper"]["name"]
    hp = work / Path(helper_name).name
    hp.write_text(HELPER, encoding="utf-8")
    core.upload_artifact(PROJECT, SCOPE, helper_name, hp, "text/x-python; charset=utf-8")
    manifest["files"]["helper"]["sha256"] = core.sha256_file(hp)
    manifest["transport_repairs"] = list(manifest.get("transport_repairs", [])) + [
        {"repair": "META_DUKASCOPY_LEGACY_ALIAS", "mapping": "META->FB.US/USD", "strategy_changes": "NONE"}
    ]
    mp.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    core.upload_artifact(PROJECT, SCOPE, "manifest.json", mp, "application/json; charset=utf-8")
    print(json.dumps({"scope": SCOPE, "helper": helper_name, "helper_sha256": manifest["files"]["helper"]["sha256"], "repair": "META->FB.US/USD"}))

if __name__ == "__main__":
    main()
