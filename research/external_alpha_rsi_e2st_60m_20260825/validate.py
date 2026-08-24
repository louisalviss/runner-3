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

sys.path.insert(0, os.environ.get("EXT_HELPER_DIR", "/tmp/extalpha"))
import exp  # frozen Dukascopy resolver/fetch helper supplied by workflow

WARMUP = pd.Timestamp("2021-12-01T00:00:00Z")
REPORT_START = pd.Timestamp("2022-01-01T00:00:00Z")
END = pd.Timestamp("2026-08-25T00:00:00Z")
NY = "America/New_York"
SEEN = {"AAPL", "AMZN", "MSFT", "NVDA", "TSLA"}


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


def load_quotes(symbol):
    instrument = exp.resolve_symbol(symbol)
    if not instrument:
        return None, None, [], None
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
            manifest.append({"month": a.strftime("%Y-%m"), "bid": len(db), "ask": len(da), "common": len(idx)})
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
    bid = bid[(bid.index >= WARMUP) & (bid.index < END)]
    ask = ask.loc[bid.index]
    return bid, ask, manifest, instrument


def _ohlc(frame):
    return {
        "open": float(frame.iloc[0].open),
        "high": float(frame.high.max()),
        "low": float(frame.low.min()),
        "close": float(frame.iloc[-1].close),
    }


def session_60m(bid5, ask5):
    idx = bid5.index.intersection(ask5.index)
    bid5, ask5 = bid5.loc[idx], ask5.loc[idx]
    local = idx.tz_convert(NY)
    meta = pd.DataFrame(index=idx)
    meta["date"] = local.date
    meta["minute"] = local.hour * 60 + local.minute
    meta = meta[(meta.minute >= 9 * 60 + 30) & (meta.minute < 16 * 60)]
    rows = []
    for day, daymeta in meta.groupby("date", sort=True):
        ids = daymeta.index
        bday, aday = bid5.loc[ids], ask5.loc[ids]
        mins = daymeta.minute.to_numpy()
        buckets = ((mins - (9 * 60 + 30)) // 60).astype(int)
        for bucket in sorted(set(buckets)):
            sel = ids[buckets == bucket]
            if not len(sel):
                continue
            # Require contiguous M5 quotes. A final partial session bar is allowed.
            m = [int(x) for x in daymeta.loc[sel].minute]
            if any(m[j] - m[j - 1] != 5 for j in range(1, len(m))):
                continue
            later = ids[buckets > bucket]
            is_final = len(later) == 0
            if len(sel) != 12 and not (is_final and len(sel) >= 2):
                continue
            bf, af = bday.loc[sel], aday.loc[sel]
            midf = (bf + af) / 2.0
            first = sel[0]
            last = sel[-1]
            rows.append({
                "time": first,
                "end": last + pd.Timedelta(minutes=5),
                **{f"mid_{k}": v for k, v in _ohlc(midf).items()},
                **{f"bid_{k}": v for k, v in _ohlc(bf).items()},
                **{f"ask_{k}": v for k, v in _ohlc(af).items()},
            })
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows).sort_values("time").reset_index(drop=True)


def signals(bars):
    c = bars.mid_close.to_numpy(float)
    h = bars.mid_high.to_numpy(float)
    l = bars.mid_low.to_numpy(float)
    ch = np.r_[np.nan, np.diff(c)]
    up = rma(np.where(np.isnan(ch), np.nan, np.maximum(ch, 0)), 10)
    dn = rma(np.where(np.isnan(ch), np.nan, np.maximum(-ch, 0)), 10)
    rsi = np.where(dn == 0, 100, np.where(up == 0, 0, 100 - 100 / (1 + up / dn)))
    sma = pd.Series(rsi).rolling(10, min_periods=10).mean().to_numpy()
    cross = np.zeros(len(bars), dtype=bool)
    cross[1:] = (
        np.isfinite(rsi[1:]) & np.isfinite(sma[1:]) & np.isfinite(rsi[:-1]) & np.isfinite(sma[:-1])
        & (rsi[1:] > sma[1:]) & (rsi[:-1] <= sma[:-1])
    )
    buy = np.zeros(len(bars), dtype=bool)
    count = 0
    for i in range(len(bars)):
        if np.isfinite(rsi[i]) and rsi[i] > 50:
            count = 0
        if cross[i] and rsi[i] < 50:
            count += 1
        if cross[i] and rsi[i] < 50 and count == 2:
            buy[i] = True
            count = 0

    prev = np.r_[np.nan, c[:-1]]
    tr = np.nanmax(np.vstack([h - l, np.abs(h - prev), np.abs(l - prev)]), axis=0)
    tr[0] = h[0] - l[0]
    atr = rma(tr, 10)
    hl2 = (h + l) / 2
    bu = hl2 + 2.5 * atr
    bl = hl2 - 2.5 * atr
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
    sell[1:] = np.isfinite(direction[1:]) & np.isfinite(direction[:-1]) & ((direction[1:] - direction[:-1]) > 0)
    return buy, sell, rsi, sma, direction


def spread_bps(bid, ask):
    mid = (bid + ask) / 2.0
    return None if mid <= 0 else 10000.0 * (ask - bid) / mid


def run_symbol(symbol):
    bid5, ask5, manifest, instrument = load_quotes(symbol)
    if bid5 is None:
        return {"symbol": symbol, "status": "UNAVAILABLE", "instrument": instrument, "manifest": manifest}, []
    bars = session_60m(bid5, ask5)
    if len(bars) < 100:
        return {"symbol": symbol, "status": "TOO_FEW_BARS", "bars": len(bars), "instrument": instrument}, []
    buy, sell, rsi, sma, direction = signals(bars)
    pos = False
    entry = None
    trades = []
    for i in range(len(bars) - 1):
        # Orders created at close i execute at next chart-bar open i+1.
        nxt = bars.iloc[i + 1]
        sig_time = bars.iloc[i].end
        if pos:
            if sell[i]:
                actual_exit = float(nxt.bid_open)
                mid_exit = float(nxt.mid_open)
                actual_ret = actual_exit / entry["actual_entry"] - 1.0
                mid_ret = mid_exit / entry["mid_entry"] - 1.0
                trades.append({
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
                    "entry_year": entry["signal_entry"].tz_convert(NY).year,
                    "exit_year": sig_time.tz_convert(NY).year,
                })
                pos = False
                entry = None
        else:
            if buy[i]:
                # Report only trades whose signal is inside the frozen report window.
                if sig_time >= REPORT_START and sig_time < END:
                    entry = {
                        "signal_entry": sig_time,
                        "entry_time": nxt.time,
                        "actual_entry": float(nxt.ask_open),
                        "mid_entry": float(nxt.mid_open),
                        "entry_spread_bps": spread_bps(float(nxt.bid_open), float(nxt.ask_open)),
                    }
                    pos = True
                else:
                    # Warm-up entry can affect Pine position state; track it but do not report.
                    entry = {
                        "signal_entry": sig_time,
                        "entry_time": nxt.time,
                        "actual_entry": float(nxt.ask_open),
                        "mid_entry": float(nxt.mid_open),
                        "entry_spread_bps": spread_bps(float(nxt.bid_open), float(nxt.ask_open)),
                        "warmup": True,
                    }
                    pos = True
    # If a warm-up-origin position exits in report window, do not report it.
    trades = [t for t in trades if pd.Timestamp(t["signal_entry"]) >= REPORT_START]
    vals = [t["actual_return"] for t in trades]
    mids = [t["mid_return"] for t in trades]
    def pf(v):
        gp = sum(max(x, 0.0) for x in v); gl = sum(max(-x, 0.0) for x in v)
        return gp / gl if gl else (None if gp == 0 else 999.0)
    summary = {
        "symbol": symbol,
        "status": "OK",
        "instrument": instrument,
        "bars": len(bars),
        "coverage_start": bars.time.iloc[0].isoformat(),
        "coverage_end": bars.end.iloc[-1].isoformat(),
        "signals": int(buy.sum()),
        "trades": len(trades),
        "actual_pf": pf(vals),
        "actual_mean_bps": statistics.mean([x * 10000 for x in vals]) if vals else None,
        "actual_sum_return": sum(vals),
        "mid_pf": pf(mids),
        "mid_mean_bps": statistics.mean([x * 10000 for x in mids]) if mids else None,
        "mid_sum_return": sum(mids),
        "manifest": manifest,
    }
    return summary, trades


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbol", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    out = Path(args.out); out.mkdir(parents=True, exist_ok=True)
    summary, trades = run_symbol(args.symbol.upper())
    (out / f"summary-{args.symbol.upper()}.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    with (out / f"trades-{args.symbol.upper()}.jsonl").open("w", encoding="utf-8") as f:
        for t in trades:
            f.write(json.dumps(t) + "\n")
    print(json.dumps({k: summary.get(k) for k in ["symbol", "status", "bars", "trades", "actual_pf", "actual_mean_bps", "mid_pf", "mid_mean_bps"]}))


if __name__ == "__main__":
    main()
