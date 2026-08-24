#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HELPER = os.environ.get("WR_TIMING_HELPER_DIR", "/tmp/wrtiming")
sys.path.insert(0, HELPER)
import exp
import wrref

WARMUP = pd.Timestamp("2021-12-01T00:00:00Z")
END = pd.Timestamp("2026-08-25T00:00:00Z")
NY = "America/New_York"
TICK = 0.01
WINDOW = pd.Timedelta(minutes=60)
TARGET_MIN = 10


def load_parent_trades(path: Path, symbol: str):
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        x = json.loads(line)
        if x.get("symbol") == symbol:
            out.append(x)
    out.sort(key=lambda x: x["signal_entry"])
    return out


def load_quotes(symbol: str):
    instrument = exp.resolve_symbol(symbol)
    if not instrument:
        raise RuntimeError(f"instrument not found: {symbol}")
    bidc = exp.pick_const(("OFFER_SIDE_BID", "PRICE_TYPE_BID", "BID"))
    askc = exp.pick_const(("OFFER_SIDE_ASK", "PRICE_TYPE_ASK", "ASK"))
    bids, asks, manifest = [], [], []
    for a, b in exp.month_chunks(WARMUP, END):
        try:
            db = exp.fetch_side(instrument, bidc, a, b, 5)
            da = exp.fetch_side(instrument, askc, a, b, 5)
            idx = db.index.intersection(da.index)
            if len(idx):
                bids.append(db.loc[idx, ["open", "high", "low", "close"]])
                asks.append(da.loc[idx, ["open", "high", "low", "close"]])
            manifest.append({"month": a.strftime("%Y-%m"), "bid": int(len(db)), "ask": int(len(da)), "common": int(len(idx))})
        except Exception as e:
            manifest.append({"month": a.strftime("%Y-%m"), "error": repr(e)})
    if not bids:
        raise RuntimeError(f"no paired M5 history: {symbol}")
    bid = pd.concat(bids).sort_index()
    ask = pd.concat(asks).sort_index()
    bid = bid[~bid.index.duplicated(keep="last")]
    ask = ask[~ask.index.duplicated(keep="last")]
    idx = bid.index.intersection(ask.index)
    bid, ask = bid.loc[idx], ask.loc[idx]
    bid = bid[(bid.index >= WARMUP) & (bid.index < END)]
    ask = ask.loc[bid.index]
    if len(bid) < 1000:
        raise RuntimeError(f"too few paired M5 rows: {symbol}: {len(bid)}")
    return bid, ask, manifest, instrument


def _ohlc(frame: pd.DataFrame):
    return {
        "open": float(frame.iloc[0].open),
        "high": float(frame.high.max()),
        "low": float(frame.low.min()),
        "close": float(frame.iloc[-1].close),
    }


def session_bars_10m(bid5: pd.DataFrame, ask5: pd.DataFrame):
    idx = bid5.index.intersection(ask5.index)
    bid5, ask5 = bid5.loc[idx], ask5.loc[idx]
    local = idx.tz_convert(NY)
    meta = pd.DataFrame(index=idx)
    meta["date"] = local.date
    meta["minute"] = local.hour * 60 + local.minute
    meta = meta[(meta.minute >= 570) & (meta.minute < 960)]
    rows = []
    for _day, dm in meta.groupby("date", sort=True):
        ids = dm.index
        buckets = ((dm.minute.to_numpy() - 570) // TARGET_MIN).astype(int)
        for bucket in sorted(set(buckets)):
            sel = ids[buckets == bucket]
            if len(sel) != 2:
                continue
            mins = [int(x) for x in dm.loc[sel].minute]
            if mins[1] - mins[0] != 5:
                continue
            bf, af = bid5.loc[sel], ask5.loc[sel]
            mf = (bf + af) / 2.0
            start, end = sel[0], sel[-1] + pd.Timedelta(minutes=5)
            mo, bo, ao = _ohlc(mf), _ohlc(bf), _ohlc(af)
            rows.append({
                "time": start,
                "end": end,
                **{f"mid_{k}": v for k, v in mo.items()},
                **{f"bid_{k}": v for k, v in bo.items()},
                **{f"ask_{k}": v for k, v in ao.items()},
            })
    if not rows:
        raise RuntimeError("no complete regular-session 10m bars")
    return pd.DataFrame(rows).sort_values("time").reset_index(drop=True)


def session_entry_allowed(end_ts: pd.Timestamp):
    loc = end_ts.tz_convert(NY)
    day_close = pd.Timestamp(year=loc.year, month=loc.month, day=loc.day, hour=16, minute=0, tz=NY)
    cutoff = day_close - pd.Timedelta(minutes=40)
    # Canonical condition blocks if signal close is in the window OR the next chart bar reaches the window.
    noentry = (loc >= cutoff) or (loc + pd.Timedelta(minutes=TARGET_MIN) >= cutoff)
    return (loc.hour > 9 or (loc.hour == 9 and loc.minute >= 40)) and loc <= day_close and not noentry


def build_wr_fill_events(bars: pd.DataFrame, ask5: pd.DataFrame):
    rbars = [
        wrref.Bar(
            int(r.time.timestamp() * 1000),
            int(r.end.timestamp() * 1000),
            float(r.mid_open), float(r.mid_high), float(r.mid_low), float(r.mid_close),
        )
        for r in bars.itertuples(index=False)
    ]
    ind, pht, plt = wrref.calc_ind(rbars)
    events = []
    raw_setups = 0
    unfilled_setups = 0
    for i in range(len(bars) - 1):
        r = bars.iloc[i]
        n = bars.iloc[i + 1]
        if n.time != r.end:
            continue
        z = ind[i]
        lr = bool(z["ha"] and r.mid_close > z["ema"] and z["ag"] and z["chop_ok"] and z["res"] is not None)
        nl = bool(
            session_entry_allowed(r.end)
            and z["sra_ok"]
            and r.mid_close > r.mid_open
            and lr
            and r.mid_close > z["res"]
            and r.mid_low <= z["res"]
        )
        if not nl:
            continue
        raw_setups += 1
        planned = float(r.mid_high) + TICK
        q = ask5[(ask5.index >= n.time) & (ask5.index < n.end)]
        fill_time = None
        fill_price = None
        for ts, x in q.iterrows():
            ao, ah = float(x.open), float(x.high)
            if ao >= planned:
                fill_time, fill_price = ts, ao
                break
            if ah >= planned:
                fill_time, fill_price = ts, planned
                break
        if fill_time is None:
            unfilled_setups += 1
            continue
        events.append({
            "wr_signal_close": r.end,
            "wr_fill_time": fill_time,
            "wr_planned_entry": planned,
            "wr_actual_entry": fill_price,
            "wr_signal_high": float(r.mid_high),
            "wr_signal_low": float(r.mid_low),
            "wr_resistance": float(z["res"]),
        })
    events.sort(key=lambda x: (x["wr_fill_time"], x["wr_signal_close"]))
    return events, {"raw_wr_setups": raw_setups, "unfilled_wr_setups": unfilled_setups, "filled_wr_events": len(events), "pivot_high_ties": pht, "pivot_low_ties": plt}


def match(symbol: str, parents, events):
    rows = []
    for p in parents:
        t0 = pd.Timestamp(p["signal_entry"])
        a_entry_t = pd.Timestamp(p["entry_time"])
        exit_t = pd.Timestamp(p["exit_time"])
        horizon = min(t0 + WINDOW, exit_t)
        candidate = None
        for e in events:
            if e["wr_signal_close"] < t0:
                continue
            if e["wr_signal_close"] >= t0 + WINDOW:
                break
            if e["wr_fill_time"] >= horizon:
                continue
            if candidate is None or e["wr_fill_time"] < candidate["wr_fill_time"]:
                candidate = e
        a_ret = float(p["actual_return"])
        a_entry = float(p["actual_entry"])
        a_exit = float(p["actual_exit"])
        executed = candidate is not None
        if executed:
            b_entry = float(candidate["wr_actual_entry"])
            b_ret = a_exit / b_entry - 1.0
            improve = (a_entry - b_entry) / a_entry * 10000.0
            delay_min = (candidate["wr_fill_time"] - a_entry_t).total_seconds() / 60.0
        else:
            b_entry = None
            b_ret = 0.0
            improve = None
            delay_min = None
        row = {
            "symbol": symbol,
            "signal_entry": p["signal_entry"],
            "a_entry_time": p["entry_time"],
            "exit_time": p["exit_time"],
            "entry_year": int(p["entry_year"]),
            "a_entry": a_entry,
            "a_exit": a_exit,
            "a_return": a_ret,
            "a_return_bps": a_ret * 10000.0,
            "b_executed": executed,
            "b_entry": b_entry,
            "b_return": b_ret,
            "b_return_bps": b_ret * 10000.0,
            "delta_bps": (b_ret - a_ret) * 10000.0,
            "entry_improvement_bps": improve,
            "entry_delay_vs_A_min": delay_min,
        }
        if executed:
            row.update({
                "wr_signal_close": candidate["wr_signal_close"].isoformat(),
                "wr_fill_time": candidate["wr_fill_time"].isoformat(),
                "wr_planned_entry": candidate["wr_planned_entry"],
                "wr_signal_high": candidate["wr_signal_high"],
                "wr_signal_low": candidate["wr_signal_low"],
                "wr_resistance": candidate["wr_resistance"],
            })
        rows.append(row)
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbol", required=True)
    ap.add_argument("--parent-trades", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    symbol = args.symbol.upper()
    out = Path(args.out); out.mkdir(parents=True, exist_ok=True)
    parents = load_parent_trades(Path(args.parent_trades), symbol)
    if not parents:
        raise RuntimeError(f"no frozen parent opportunities for {symbol}")
    bid5, ask5, manifest, instrument = load_quotes(symbol)
    bars = session_bars_10m(bid5, ask5)
    events, diag = build_wr_fill_events(bars, ask5)
    rows = match(symbol, parents, events)
    summary = {
        "symbol": symbol,
        "status": "OK",
        "instrument": instrument,
        "parent_opportunities": len(parents),
        "matched_opportunities": len(rows),
        "wr_executed": int(sum(x["b_executed"] for x in rows)),
        "wr_missed": int(sum(not x["b_executed"] for x in rows)),
        "bars_10m": len(bars),
        "coverage_start": bars.time.iloc[0].isoformat(),
        "coverage_end": bars.end.iloc[-1].isoformat(),
        "diag": diag,
        "manifest": manifest,
    }
    (out / f"summary-{symbol}.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    with (out / f"opportunities-{symbol}.jsonl").open("w", encoding="utf-8") as f:
        for x in rows:
            f.write(json.dumps(x) + "\n")
    print(json.dumps({k: summary[k] for k in ["symbol", "parent_opportunities", "wr_executed", "wr_missed", "bars_10m"]}), flush=True)


if __name__ == "__main__":
    main()
