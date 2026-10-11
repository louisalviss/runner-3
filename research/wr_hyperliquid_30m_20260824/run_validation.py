#!/usr/bin/env python3
from __future__ import annotations

import bisect
import json
import math
import os
import statistics
import sys
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import requests

API = "https://api.hyperliquid.xyz/info"
OUT = Path(os.getenv("WR_OUT", "/tmp/wr-hl30"))
OUT.mkdir(parents=True, exist_ok=True)

END = datetime(2026, 8, 21, tzinfo=timezone.utc)
FETCH_START = END - timedelta(days=100)
EVAL_START = FETCH_START + timedelta(days=30)
END_MS = int(END.timestamp() * 1000)
FETCH_START_MS = int(FETCH_START.timestamp() * 1000)
EVAL_START_MS = int(EVAL_START.timestamp() * 1000)
STANDARD_TAKER_BPS = 4.5

WR_SYMBOLS = """AAPL ADBE ADI ADP ADSK AEP ALNY AMAT AMD AMGN AMZN AVGO BKR CDNS CMCSA COST CPRT CSCO CSGP CSX CTSH DXCM EA EXC FANG FTNT GILD GOOG GOOGL HON IDXX INTC INTU ISRG KHC LRCX MAR MCHP MDLZ META MPWR MRVL MSFT MU NFLX NVDA ODFL ORLY PANW PAYX PCAR PEP PLTR PYPL QCOM REGN ROST SBUX SNPS TMUS TSLA TTWO TXN VRTX WDAY WDC WMT ZS""".split()
WR_SET = set(WR_SYMBOLS)


def post(payload, retries=6):
    last = None
    for i in range(retries):
        try:
            r = requests.post(API, json=payload, timeout=30)
            if r.status_code == 429:
                time.sleep(1.5 * (i + 1))
                continue
            r.raise_for_status()
            return r.json()
        except Exception as e:
            last = e
            time.sleep(1.0 * (i + 1))
    raise RuntimeError(f"Hyperliquid API failed payload={payload!r}: {last!r}")


def fnum(x, default=0.0):
    try:
        return float(x)
    except Exception:
        return default


def base_ticker(name: str) -> str:
    return str(name).split(":")[-1].upper()


def l2_stats(coin: str):
    try:
        book = post({"type": "l2Book", "coin": coin})
    except Exception as e:
        return {"status": "ERROR", "error": repr(e)}
    levels = book.get("levels") or []
    if len(levels) < 2 or not levels[0] or not levels[1]:
        return {"status": "NO_BOOK", "raw": book}
    bids, asks = levels[0], levels[1]
    best_bid = fnum(bids[0].get("px"))
    best_ask = fnum(asks[0].get("px"))
    if best_bid <= 0 or best_ask <= 0 or best_ask < best_bid:
        return {"status": "BAD_BOOK", "raw": book}
    mid = (best_bid + best_ask) / 2.0
    spread_bps = (best_ask - best_bid) / mid * 10000.0

    def vwap(side_levels, notional):
        remaining = float(notional)
        qty = 0.0
        value = 0.0
        for lv in side_levels:
            px = fnum(lv.get("px")); sz = fnum(lv.get("sz"))
            if px <= 0 or sz <= 0:
                continue
            take_qty = min(sz, remaining / px)
            qty += take_qty
            value += take_qty * px
            remaining -= take_qty * px
            if remaining <= 1e-9:
                break
        if remaining > max(0.01, notional * 1e-6) or qty <= 0:
            return None
        return value / qty

    out = {
        "status": "OK",
        "time": book.get("time"),
        "best_bid": best_bid,
        "best_ask": best_ask,
        "mid": mid,
        "spread_bps": spread_bps,
    }
    for ntl in (1000.0, 10000.0):
        buy = vwap(asks, ntl)
        sell = vwap(bids, ntl)
        if buy is None or sell is None:
            rt = None
        else:
            buy_bps = (buy / mid - 1.0) * 10000.0
            sell_bps = (1.0 - sell / mid) * 10000.0
            rt = buy_bps + sell_bps
        out[f"roundtrip_cross_depth_bps_{int(ntl)}"] = rt
    return out


def discover_markets():
    dexs_raw = post({"type": "perpDexs"})
    candidates = []
    dex_records = []
    for dex_idx, dex in enumerate(dexs_raw):
        if not dex:
            continue
        dex_name = dex.get("name")
        if not dex_name:
            continue
        try:
            meta_ctx = post({"type": "metaAndAssetCtxs", "dex": dex_name})
            meta, ctxs = meta_ctx[0], meta_ctx[1]
        except Exception as e:
            dex_records.append({"dex": dex_name, "status": "ERROR", "error": repr(e), "raw": dex})
            continue
        dex_record = {"dex_index": dex_idx, "dex": dex_name, "fullName": dex.get("fullName"), "deployerFeeScale": dex.get("deployerFeeScale"), "raw": dex, "status": "OK", "universe_count": len(meta.get("universe", []))}
        dex_records.append(dex_record)
        for i, asset in enumerate(meta.get("universe", [])):
            name = str(asset.get("name", ""))
            ticker = base_ticker(name)
            if ticker not in WR_SET or asset.get("isDelisted"):
                continue
            ctx = ctxs[i] if i < len(ctxs) else {}
            if not ctx or ctx.get("midPx") in (None, ""):
                continue
            candidates.append({
                "ticker": ticker,
                "coin": name,
                "dex": dex_name,
                "dex_index": dex_idx,
                "dex_full_name": dex.get("fullName"),
                "dayNtlVlm": fnum(ctx.get("dayNtlVlm")),
                "openInterest": fnum(ctx.get("openInterest")),
                "midPx": fnum(ctx.get("midPx")),
                "markPx": fnum(ctx.get("markPx")),
                "oraclePx": fnum(ctx.get("oraclePx")),
                "funding_now": fnum(ctx.get("funding")),
                "impactPxs": ctx.get("impactPxs"),
                "growthMode": asset.get("growthMode"),
                "asset_meta": asset,
                "dex_deployerFeeScale": dex.get("deployerFeeScale"),
            })

    # Current L2 is inspected before any WR replay PnL is used.
    for c in candidates:
        c["l2"] = l2_stats(c["coin"])
        time.sleep(0.04)

    grouped = defaultdict(list)
    for c in candidates:
        grouped[c["ticker"]].append(c)
    selected = []
    for ticker, xs in sorted(grouped.items()):
        def key(c):
            sp = c.get("l2", {}).get("spread_bps")
            if sp is None:
                sp = 1e9
            return (-c["dayNtlVlm"], sp, c["coin"])
        selected.append(sorted(xs, key=key)[0])
    return dexs_raw, dex_records, candidates, selected


def fetch_candles(coin: str):
    req = {
        "coin": coin,
        "interval": "30m",
        "startTime": FETCH_START_MS,
        "endTime": END_MS,
    }
    rows = post({"type": "candleSnapshot", "req": req})
    parsed = []
    for x in rows:
        try:
            ts = int(x["t"])
            if ts < FETCH_START_MS or ts >= END_MS:
                continue
            parsed.append((ts, float(x["o"]), float(x["h"]), float(x["l"]), float(x["c"]), float(x.get("v", 0))))
        except Exception:
            pass
    parsed = sorted({x[0]: x for x in parsed}.values(), key=lambda z: z[0])
    if not parsed:
        return pd.DataFrame(columns=["open", "high", "low", "close", "volume"]), rows
    idx = [pd.Timestamp(x[0], unit="ms", tz="UTC") for x in parsed]
    df = pd.DataFrame({
        "open": [x[1] for x in parsed],
        "high": [x[2] for x in parsed],
        "low": [x[3] for x in parsed],
        "close": [x[4] for x in parsed],
        "volume": [x[5] for x in parsed],
    }, index=idx)
    return df, rows


def fetch_funding(coin: str):
    rows_all = []
    cur = FETCH_START_MS
    seen = set()
    for _ in range(20):
        try:
            rows = post({"type": "fundingHistory", "coin": coin, "startTime": cur, "endTime": END_MS})
        except Exception:
            break
        if not rows:
            break
        added = 0
        max_t = cur
        for x in rows:
            try:
                t = int(x["time"]); r = float(x["fundingRate"])
            except Exception:
                continue
            if t in seen:
                continue
            seen.add(t); rows_all.append((t, r)); added += 1; max_t = max(max_t, t)
        if added == 0 or max_t >= END_MS - 1:
            break
        cur = max_t + 1
        time.sleep(0.04)
    rows_all.sort()
    return rows_all


def fee_per_fill_bps(market):
    asset = market.get("asset_meta") or {}
    # Newer deployments may surface an asset-level fee scale; otherwise use the dex-level live value.
    scale_raw = asset.get("deployerFeeScale", market.get("dex_deployerFeeScale", 0))
    scale = fnum(scale_raw, 0.0)
    growth = str(market.get("growthMode", "")).lower() == "enabled"
    factor = 0.1 if growth else 1.0
    return STANDARD_TAKER_BPS * factor * (1.0 + scale), {
        "standard_taker_bps": STANDARD_TAKER_BPS,
        "growth_multiplier": factor,
        "deployer_fee_scale_used": scale,
        "asset_fee_scale_raw": asset.get("deployerFeeScale"),
        "dex_fee_scale_raw": market.get("dex_deployerFeeScale"),
        "growthMode": market.get("growthMode"),
        "model": "4.5bps * growth_multiplier * (1 + deployer_fee_scale); tier-0 estimate, not user-specific fee quote",
    }


def side_sign(t):
    s = str(t.get("side", "")).upper()
    return 1 if s in ("L", "LONG", "BUY") else -1


def metrics(rows, field):
    xs = sorted(rows, key=lambda x: int(x.get("signal", 0)))
    vals = [float(x[field]) for x in xs if x.get(field) is not None and math.isfinite(float(x[field]))]
    if not vals:
        return {"n": 0, "R": 0.0, "avg_R": None, "PF": None, "win_rate": None, "max_DD_R": 0.0}
    gp = sum(max(v, 0.0) for v in vals); gl = sum(max(-v, 0.0) for v in vals)
    eq = peak = 0.0; dd = 0.0
    for v in vals:
        eq += v; peak = max(peak, eq); dd = min(dd, eq - peak)
    return {"n": len(vals), "R": sum(vals), "avg_R": statistics.mean(vals), "PF": (gp / gl if gl else None), "win_rate": 100.0 * sum(v > 0 for v in vals) / len(vals), "max_DD_R": dd}


def main():
    sys.path.insert(0, "/tmp/wr-helper")
    import wr_dukascopy_expanded_matrix as exp

    dexs_raw, dex_records, candidates, selected = discover_markets()
    discovery = {
        "parent_symbols": WR_SYMBOLS,
        "dexs": dexs_raw,
        "dex_records": dex_records,
        "candidate_markets": candidates,
        "selected_markets_pre_pnl": selected,
    }
    (OUT / "discovery.json").write_text(json.dumps(discovery, indent=2, default=str))
    print("DEXES", [d.get("name") for d in dexs_raw if d])
    print("OVERLAP", len(selected), [(x["ticker"], x["coin"], round(x["dayNtlVlm"], 2)) for x in selected])

    all_trades = []
    market_reports = []
    for m in selected:
        ticker = m["ticker"]; coin = m["coin"]
        try:
            df, raw_candles = fetch_candles(coin)
            funding = fetch_funding(coin)
            if df.empty:
                market_reports.append({**m, "status": "NO_CANDLES"})
                continue

            base, ref = exp.load_modules(30)
            base.tv_tick = lambda _i, _v: 0.01
            bars = exp.to_bars(df[["open", "high", "low", "close"]], base.Bar, 30)
            trades, raw = base.run_case(ref, bars, exp.provider_info(ticker), df.index.min().to_pydatetime(), anchor="start", use_session=True)
            trades = [dict(t) for t in trades if int(t.get("signal", 0)) >= EVAL_START_MS and int(t.get("signal", 0)) < END_MS]

            fund_times = [x[0] for x in funding]
            fund_rates = [x[1] for x in funding]
            taker_bps, fee_meta = fee_per_fill_bps(m)
            rt1 = m.get("l2", {}).get("roundtrip_cross_depth_bps_1000")
            rt10 = m.get("l2", {}).get("roundtrip_cross_depth_bps_10000")

            for t in trades:
                e = float(t["e"]); s = float(t["s"]); dist = abs(e - s)
                if dist <= 0:
                    continue
                ratio = e / dist
                gross = float(t["R"])
                fee_rt_bps = 2.0 * taker_bps
                fee_net = gross - ratio * fee_rt_bps / 10000.0
                l2_1k_net = None if rt1 is None else gross - ratio * (fee_rt_bps + float(rt1)) / 10000.0
                l2_10k_net = None if rt10 is None else gross - ratio * (fee_rt_bps + float(rt10)) / 10000.0

                entry_t = int(t.get("entry", t.get("signal", 0)))
                exit_t = int(t.get("exit", entry_t))
                lo = bisect.bisect_left(fund_times, entry_t)
                hi = bisect.bisect_right(fund_times, exit_t)
                sum_rates = sum(fund_rates[lo:hi])
                funding_R = -side_sign(t) * sum_rates * ratio
                l2_1k_funding = None if l2_1k_net is None else l2_1k_net + funding_R

                row = {
                    "ticker": ticker,
                    "coin": coin,
                    **t,
                    "gross_R_hl": gross,
                    "fee_only_R": fee_net,
                    "fee_l2_1k_R": l2_1k_net,
                    "fee_l2_10k_R": l2_10k_net,
                    "funding_R": funding_R,
                    "fee_l2_1k_funding_R": l2_1k_funding,
                    "ratio_entry_to_stop": ratio,
                    "taker_fee_per_fill_bps_est": taker_bps,
                    "l2_roundtrip_1k_bps_live": rt1,
                    "l2_roundtrip_10k_bps_live": rt10,
                }
                all_trades.append(row)

            market_reports.append({
                **m,
                "status": "OK",
                "candle_count": int(len(df)),
                "candle_start": df.index.min().isoformat(),
                "candle_end": df.index.max().isoformat(),
                "evaluation_start": EVAL_START.isoformat(),
                "evaluation_end": END.isoformat(),
                "funding_points": len(funding),
                "funding_mean": statistics.mean([r for _, r in funding]) if funding else None,
                "funding_median": statistics.median([r for _, r in funding]) if funding else None,
                "wr_trade_count": len(trades),
                "fee_per_fill_bps_est": taker_bps,
                "fee_meta": fee_meta,
                "raw_engine": raw,
            })
            print("MARKET", ticker, coin, "candles", len(df), "trades", len(trades), "fee_bps", taker_bps, "l2rt1k", rt1)
        except Exception as e:
            market_reports.append({**m, "status": "ERROR", "error": repr(e)})
            print("ERROR", ticker, coin, repr(e), flush=True)
        time.sleep(0.08)

    gross = metrics(all_trades, "gross_R_hl")
    fee_only = metrics(all_trades, "fee_only_R")
    l2_1k = metrics(all_trades, "fee_l2_1k_R")
    l2_10k = metrics(all_trades, "fee_l2_10k_R")
    l2_1k_funding = metrics(all_trades, "fee_l2_1k_funding_R")

    sym = {}
    for ticker in sorted(set(x["ticker"] for x in all_trades)):
        rr = [x for x in all_trades if x["ticker"] == ticker]
        sym[ticker] = {
            "gross": metrics(rr, "gross_R_hl"),
            "fee_only": metrics(rr, "fee_only_R"),
            "fee_l2_1k": metrics(rr, "fee_l2_1k_R"),
            "fee_l2_1k_funding": metrics(rr, "fee_l2_1k_funding_R"),
        }

    l2_covered = l2_1k["n"]
    breadth_pos = sum(v["fee_l2_1k"]["R"] > 0 for v in sym.values() if v["fee_l2_1k"]["n"])
    breadth_neg = sum(v["fee_l2_1k"]["R"] < 0 for v in sym.values() if v["fee_l2_1k"]["n"])
    funding_points_total = sum(int(x.get("funding_points", 0) or 0) for x in market_reports)

    if not all_trades or l2_covered == 0:
        verdict = "INSUFFICIENT_EVIDENCE"
    elif l2_covered < 0.8 * len(all_trades):
        verdict = "INSUFFICIENT_EVIDENCE_L2_COVERAGE"
    elif l2_1k["R"] <= 0 or l2_1k.get("PF") is None or l2_1k["PF"] <= 1.0:
        verdict = "REJECT_CURRENT_HYPERLIQUID_EXECUTION"
    elif funding_points_total and (l2_1k_funding["R"] <= 0 or l2_1k_funding.get("PF") is None or l2_1k_funding["PF"] <= 1.0):
        verdict = "REJECT_AFTER_FUNDING"
    else:
        verdict = "PROMISING_RECENT_EXECUTION_PROXY_NOT_CANONICAL"

    report = {
        "status": "COMPLETE",
        "verdict": verdict,
        "candidate": "WR 2.5.13 frozen base — US stocks 30m",
        "venue": "Hyperliquid HIP-3",
        "evidence_class": "recent Hyperliquid candle replay + live L2/fee proxy; NOT historical L2 actual execution",
        "frozen_parent_symbols": len(WR_SYMBOLS),
        "live_exact_overlap_selected": len(selected),
        "selected_markets": selected,
        "market_reports": market_reports,
        "fetch_window": {"start": FETCH_START.isoformat(), "end": END.isoformat(), "days": 100},
        "evaluation_window": {"start": EVAL_START.isoformat(), "end": END.isoformat(), "days": 70},
        "trade_rows": len(all_trades),
        "metrics": {
            "gross_hyperliquid_candles": gross,
            "fee_only_tier0_est": fee_only,
            "fee_plus_live_l2_1k": l2_1k,
            "fee_plus_live_l2_10k": l2_10k,
            "fee_plus_live_l2_1k_plus_funding": l2_1k_funding,
        },
        "l2_trade_coverage_fraction": (l2_covered / len(all_trades) if all_trades else 0.0),
        "funding_points_total": funding_points_total,
        "symbol_breadth_fee_l2_1k": {"symbols": len(sym), "positive": breadth_pos, "negative": breadth_neg},
        "symbols": sym,
        "method_notes": [
            "Venue selection uses current liquidity only and occurs before PnL inspection.",
            "Historical order books are not available through the normal public info API; current L2 crossing/depth is used as an execution proxy.",
            "All WR entries/exits are treated as taker for the fee proxy.",
            "Historical funding is applied at funding timestamps while replay trades are open when returned by the API.",
            "The result is recent validation only and cannot replace the 2022-2026 midpoint history.",
        ],
    }
    (OUT / "report.json").write_text(json.dumps(report, indent=2, default=str))
    with (OUT / "trades.jsonl").open("w") as f:
        for x in all_trades:
            f.write(json.dumps(x, default=str) + "\n")

    print("FINAL", json.dumps({
        "verdict": verdict,
        "overlap": len(selected),
        "trades": len(all_trades),
        "gross": gross,
        "fee_only": fee_only,
        "fee_l2_1k": l2_1k,
        "fee_l2_1k_funding": l2_1k_funding,
        "breadth": report["symbol_breadth_fee_l2_1k"],
        "l2_coverage": report["l2_trade_coverage_fraction"],
    }, default=str), flush=True)


if __name__ == "__main__":
    main()
