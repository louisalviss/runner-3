#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HELPER_DIR = os.environ.get("SUPER_RSI_HELPER_DIR", "/tmp/super-rsi-helper")
sys.path.insert(0, HELPER_DIR)
import exp


def load_profile(path: str) -> dict:
    p = json.loads(Path(path).read_text(encoding="utf-8"))
    if p["strategy"]["direction"] != "LONG_ONLY":
        raise ValueError("Super RSI engine currently supports LONG_ONLY only")
    if p["execution"]["chart_price"] != "MIDPOINT":
        raise ValueError("Canonical Super RSI requires MIDPOINT chart")
    if p["execution"]["order_timing"] != "NEXT_CHART_BAR_OPEN":
        raise ValueError("Canonical Super RSI requires NEXT_CHART_BAR_OPEN")
    return p


def rma(values, n):
    a = np.asarray(values, dtype=float)
    out = np.full(len(a), np.nan)
    valid = []
    start = None
    for i, x in enumerate(a):
        if np.isfinite(x):
            valid.append(i)
        if len(valid) == n:
            start = i
            out[i] = float(np.mean([a[j] for j in valid[-n:]]))
            break
    if start is None:
        return out
    for i in range(start + 1, len(a)):
        x = a[i]
        out[i] = ((n - 1) * out[i - 1] + x) / n if np.isfinite(x) else out[i - 1]
    return out


def load_quotes(symbol: str, profile: dict):
    warmup = pd.Timestamp(profile["dates"]["warmup"])
    end = pd.Timestamp(profile["dates"]["end"])
    source_minutes = int(profile["source_minutes"])

    instrument = exp.resolve_symbol(symbol)
    if not instrument:
        return None, None, [], None

    bidc = exp.pick_const(("OFFER_SIDE_BID", "PRICE_TYPE_BID", "BID"))
    askc = exp.pick_const(("OFFER_SIDE_ASK", "PRICE_TYPE_ASK", "ASK"))
    bids, asks, manifest = [], [], []

    for a, b in exp.month_chunks(warmup, end):
        try:
            db = exp.fetch_side(instrument, bidc, a, b, source_minutes)
            da = exp.fetch_side(instrument, askc, a, b, source_minutes)
            idx = db.index.intersection(da.index)
            if len(idx):
                bids.append(db.loc[idx, ["open", "high", "low", "close"]])
                asks.append(da.loc[idx, ["open", "high", "low", "close"]])
            manifest.append({
                "month": a.strftime("%Y-%m"),
                "bid": int(len(db)),
                "ask": int(len(da)),
                "common": int(len(idx)),
            })
        except Exception as e:
            manifest.append({"month": a.strftime("%Y-%m"), "error": repr(e)})

    if not bids:
        return None, None, manifest, instrument

    bid = pd.concat(bids).sort_index()
    ask = pd.concat(asks).sort_index()
    bid = bid[~bid.index.duplicated(keep="last")]
    ask = ask[~ask.index.duplicated(keep="last")]
    idx = bid.index.intersection(ask.index)
    bid, ask = bid.loc[idx], ask.loc[idx]
    bid = bid[(bid.index >= warmup) & (bid.index < end)]
    ask = ask.loc[bid.index]
    return bid, ask, manifest, instrument


def _ohlc(frame: pd.DataFrame) -> dict:
    return {
        "open": float(frame.iloc[0].open),
        "high": float(frame.high.max()),
        "low": float(frame.low.min()),
        "close": float(frame.iloc[-1].close),
    }


def session_bars(bid_src: pd.DataFrame, ask_src: pd.DataFrame, profile: dict) -> pd.DataFrame:
    idx = bid_src.index.intersection(ask_src.index)
    bid_src, ask_src = bid_src.loc[idx], ask_src.loc[idx]

    tf = int(profile["timeframe_minutes"])
    src = int(profile["source_minutes"])
    if tf < src or tf % src != 0:
        raise ValueError(f"timeframe_minutes={tf} must be divisible by source_minutes={src}")

    sess = profile["session"]
    ny = sess["timezone"]
    open_minute = int(sess["open_minute"])
    close_minute = int(sess["close_minute"])
    allow_partial = bool(sess.get("allow_final_partial_bar", False))

    local = idx.tz_convert(ny)
    meta = pd.DataFrame(index=idx)
    meta["date"] = local.date
    meta["minute"] = local.hour * 60 + local.minute
    meta = meta[(meta.minute >= open_minute) & (meta.minute < close_minute)]

    expected = tf // src
    rows = []
    for _, daymeta in meta.groupby("date", sort=True):
        ids = daymeta.index
        mins = daymeta.minute.to_numpy()
        buckets = ((mins - open_minute) // tf).astype(int)

        for bucket in sorted(set(buckets)):
            sel = ids[buckets == bucket]
            if not len(sel):
                continue
            minute_values = [int(x) for x in daymeta.loc[sel].minute]
            if any(minute_values[j] - minute_values[j - 1] != src for j in range(1, len(minute_values))):
                continue

            later = ids[buckets > bucket]
            is_final = len(later) == 0
            if len(sel) != expected and not (allow_partial and is_final and len(sel) >= 2):
                continue

            bf, af = bid_src.loc[sel], ask_src.loc[sel]
            mf = (bf + af) / 2.0
            first, last = sel[0], sel[-1]
            rows.append({
                "time": first,
                "end": last + pd.Timedelta(minutes=src),
                **{f"mid_{k}": v for k, v in _ohlc(mf).items()},
                **{f"bid_{k}": v for k, v in _ohlc(bf).items()},
                **{f"ask_{k}": v for k, v in _ohlc(af).items()},
            })

    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows).sort_values("time").reset_index(drop=True)


def signals(bars: pd.DataFrame, profile: dict):
    s = profile["strategy"]
    rsi_len = int(s["rsi_length"])
    sma_len = int(s["rsi_signal_sma"])
    trigger = float(s["reset_trigger"])
    target_crosses = int(s["cross_count"])
    atr_len = int(s["supertrend_atr"])
    factor = float(s["supertrend_factor"])

    c = bars.mid_close.to_numpy(float)
    h = bars.mid_high.to_numpy(float)
    l = bars.mid_low.to_numpy(float)

    ch = np.r_[np.nan, np.diff(c)]
    up = rma(np.where(np.isnan(ch), np.nan, np.maximum(ch, 0)), rsi_len)
    dn = rma(np.where(np.isnan(ch), np.nan, np.maximum(-ch, 0)), rsi_len)
    rsi = np.where(dn == 0, 100, np.where(up == 0, 0, 100 - 100 / (1 + up / dn)))
    sma = pd.Series(rsi).rolling(sma_len, min_periods=sma_len).mean().to_numpy()

    cross = np.zeros(len(bars), dtype=bool)
    cross[1:] = (
        np.isfinite(rsi[1:])
        & np.isfinite(sma[1:])
        & np.isfinite(rsi[:-1])
        & np.isfinite(sma[:-1])
        & (rsi[1:] > sma[1:])
        & (rsi[:-1] <= sma[:-1])
    )

    buy = np.zeros(len(bars), dtype=bool)
    count = 0
    for i in range(len(bars)):
        if np.isfinite(rsi[i]) and rsi[i] > trigger:
            count = 0
        if cross[i] and rsi[i] < trigger:
            count += 1
        if cross[i] and rsi[i] < trigger and count == target_crosses:
            buy[i] = True
            count = 0

    prev = np.r_[np.nan, c[:-1]]
    tr = np.nanmax(np.vstack([h - l, np.abs(h - prev), np.abs(l - prev)]), axis=0)
    tr[0] = h[0] - l[0]
    atr = rma(tr, atr_len)
    hl2 = (h + l) / 2
    bu = hl2 + factor * atr
    bl = hl2 - factor * atr

    ub = np.full(len(bars), np.nan)
    lb = np.full(len(bars), np.nan)
    st = np.full(len(bars), np.nan)
    direction = np.full(len(bars), np.nan)

    for i in range(len(bars)):
        if not np.isfinite(atr[i]):
            continue
        if i == 0 or not np.isfinite(ub[i - 1]):
            ub[i], lb[i], direction[i], st[i] = bu[i], bl[i], 1, bu[i]
            continue
        ub[i] = bu[i] if (bu[i] < ub[i - 1] or c[i - 1] > ub[i - 1]) else ub[i - 1]
        lb[i] = bl[i] if (bl[i] > lb[i - 1] or c[i - 1] < lb[i - 1]) else lb[i - 1]
        if np.isclose(st[i - 1], ub[i - 1], rtol=1e-10, atol=1e-12):
            direction[i] = -1 if c[i] > ub[i] else 1
        else:
            direction[i] = 1 if c[i] < lb[i] else -1
        st[i] = lb[i] if direction[i] == -1 else ub[i]

    sell = np.zeros(len(bars), dtype=bool)
    sell[1:] = (
        np.isfinite(direction[1:])
        & np.isfinite(direction[:-1])
        & ((direction[1:] - direction[:-1]) > 0)
    )
    return buy, sell


def spread_bps(bid: float, ask: float):
    mid = (bid + ask) / 2.0
    return None if mid <= 0 else 10000.0 * (ask - bid) / mid


def profit_factor(vals):
    gp = sum(max(float(x), 0.0) for x in vals)
    gl = sum(max(-float(x), 0.0) for x in vals)
    return gp / gl if gl else (None if gp == 0 else 999.0)


def run_symbol(symbol: str, profile: dict):
    report_start = pd.Timestamp(profile["dates"]["report_start"])
    end = pd.Timestamp(profile["dates"]["end"])
    tz = profile["session"]["timezone"]

    bid_src, ask_src, manifest, instrument = load_quotes(symbol, profile)
    if bid_src is None:
        return {
            "symbol": symbol,
            "status": "UNAVAILABLE",
            "instrument": instrument,
            "manifest": manifest,
        }, []

    bars = session_bars(bid_src, ask_src, profile)
    if len(bars) < 100:
        return {
            "symbol": symbol,
            "status": "TOO_FEW_BARS",
            "bars": int(len(bars)),
            "instrument": instrument,
        }, []

    buy, sell = signals(bars, profile)
    pos = False
    entry = None
    trades = []

    for i in range(len(bars) - 1):
        nxt = bars.iloc[i + 1]
        sig_time = bars.iloc[i].end

        if pos:
            if sell[i]:
                actual_exit = float(nxt.bid_open)
                mid_exit = float(nxt.mid_open)
                actual_ret = actual_exit / entry["actual_entry"] - 1.0
                mid_ret = mid_exit / entry["mid_entry"] - 1.0
                if not entry.get("warmup"):
                    trades.append({
                        "profile": profile["name"],
                        "symbol": symbol,
                        "signal_entry": entry["signal_entry"].isoformat(),
                        "entry_time": entry["entry_time"].isoformat(),
                        "signal_exit": sig_time.isoformat(),
                        "exit_time": nxt.time.isoformat(),
                        "actual_entry": entry["actual_entry"],
                        "actual_exit": actual_exit,
                        "mid_entry": entry["mid_entry"],
                        "mid_exit": mid_exit,
                        "actual_return": actual_ret,
                        "mid_return": mid_ret,
                        "actual_return_bps": actual_ret * 10000.0,
                        "mid_return_bps": mid_ret * 10000.0,
                        "entry_spread_bps": entry["entry_spread_bps"],
                        "exit_spread_bps": spread_bps(float(nxt.bid_open), float(nxt.ask_open)),
                        "entry_year": int(entry["signal_entry"].tz_convert(tz).year),
                        "exit_year": int(sig_time.tz_convert(tz).year),
                    })
                pos = False
                entry = None
        else:
            if buy[i]:
                entry = {
                    "signal_entry": sig_time,
                    "entry_time": nxt.time,
                    "actual_entry": float(nxt.ask_open),
                    "mid_entry": float(nxt.mid_open),
                    "entry_spread_bps": spread_bps(float(nxt.bid_open), float(nxt.ask_open)),
                    "warmup": not (sig_time >= report_start and sig_time < end),
                }
                pos = True

    vals = [t["actual_return"] for t in trades]
    mids = [t["mid_return"] for t in trades]
    summary = {
        "profile": profile["name"],
        "strategy_name": profile["strategy_name"],
        "symbol": symbol,
        "status": "OK",
        "instrument": instrument,
        "timeframe_minutes": int(profile["timeframe_minutes"]),
        "bars": int(len(bars)),
        "coverage_start": bars.time.iloc[0].isoformat(),
        "coverage_end": bars.end.iloc[-1].isoformat(),
        "signals": int(buy.sum()),
        "trades": int(len(trades)),
        "actual_pf": profit_factor(vals),
        "actual_mean_bps": statistics.mean([x * 10000 for x in vals]) if vals else None,
        "actual_sum_return": float(sum(vals)),
        "mid_pf": profit_factor(mids),
        "mid_mean_bps": statistics.mean([x * 10000 for x in mids]) if mids else None,
        "mid_sum_return": float(sum(mids)),
        "manifest": manifest,
    }
    return summary, trades


def main():
    ap = argparse.ArgumentParser(description="Super RSI profile-driven executable backtest")
    ap.add_argument("--profile", required=True)
    ap.add_argument("--symbol", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    profile = load_profile(args.profile)
    symbol = args.symbol.upper()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    summary, trades = run_symbol(symbol, profile)
    (out / f"summary-{symbol}.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    with (out / f"trades-{symbol}.jsonl").open("w", encoding="utf-8") as f:
        for t in trades:
            f.write(json.dumps(t) + "\n")

    print(json.dumps({
        k: summary.get(k)
        for k in ["profile", "symbol", "status", "bars", "trades", "actual_pf", "actual_mean_bps", "mid_pf", "mid_mean_bps"]
    }), flush=True)


if __name__ == "__main__":
    main()
