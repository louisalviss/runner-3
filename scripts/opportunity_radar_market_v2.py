#!/usr/bin/env python3
"""Opportunity Radar V2 public market/pricing intake scanner.

Runs on public Runner3 so the pricing lane does not depend on private Actions
minutes. It scans the US listed-equity universe for price/relative anomalies and
emits RAW Signals intake packets only. It never decides that an anomaly is a
mispricing and never creates REVIEW/BUY/ACTIVE state.
"""

from __future__ import annotations

import io
import json
import math
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable
from zoneinfo import ZoneInfo

import pandas as pd
import requests
import yfinance as yf

try:
    from curl_cffi import requests as curl_requests
except Exception:
    curl_requests = None

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "data" / "opportunity-radar"
OUT_DIR.mkdir(parents=True, exist_ok=True)
SIGNALS_OUT = OUT_DIR / "market-signals.json"
HEALTH_OUT = OUT_DIR / "market-health.json"

TZ = ZoneInfo("Asia/Ho_Chi_Minh")
NASDAQ_LISTED = "https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt"
OTHER_LISTED = "https://www.nasdaqtrader.com/dynamic/SymDir/otherlisted.txt"
NASDAQ_SCREENER = "https://api.nasdaq.com/api/screener/stocks"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126 Safari/537.36",
    "Accept": "application/json,text/plain,*/*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.nasdaq.com/market-activity/stocks/screener",
}

CFG = {
    "one_day_trigger_pct": -7.0,
    "five_day_trigger_pct": -15.0,
    "sector_underperformance_trigger_pct": -10.0,
    "preferred_volume_ratio": 1.5,
    "min_market_cap_usd": 500_000_000,
    "min_snapshot_dollar_volume_usd": 5_000_000,
    "max_history_symbols": 4500,
    "max_candidates": 80,
    "batch_size": 150,
    "min_history_coverage": 0.80,
}

EXCLUDE_NAME = re.compile(
    r"\b(warrant|warrants|right|rights|unit|units|preferred|preference|"
    r"closed[- ]end fund|etf|exchange traded fund|notes due|senior notes|"
    r"debenture|bond|beneficial interest)\b",
    re.I,
)


def chunks(items: list[str], n: int) -> Iterable[list[str]]:
    for i in range(0, len(items), n):
        yield items[i : i + n]


def num(value: Any) -> float | None:
    if value is None:
        return None
    text = str(value).strip().replace("$", "").replace(",", "").replace("%", "")
    if text.lower() in {"", "n/a", "na", "none", "-", "--"}:
        return None
    try:
        out = float(text)
        return out if math.isfinite(out) else None
    except Exception:
        return None


def pct(new: float, old: float) -> float | None:
    return None if old == 0 else (new / old - 1.0) * 100.0


def fetch_text(url: str) -> str:
    r = requests.get(url, headers={"User-Agent": HEADERS["User-Agent"]}, timeout=35)
    r.raise_for_status()
    return r.text


def load_symbol_directory() -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    df = pd.read_csv(io.StringIO(fetch_text(NASDAQ_LISTED)), sep="|")
    for _, row in df.iterrows():
        symbol = str(row.get("Symbol", "")).strip().upper()
        if not symbol or symbol.startswith("File Creation Time"):
            continue
        out[symbol] = {
            "symbol": symbol,
            "name": str(row.get("Security Name", "")).strip(),
            "exchange": "NASDAQ",
            "etf": str(row.get("ETF", "N")).upper() == "Y",
            "test": str(row.get("Test Issue", "N")).upper() == "Y",
        }

    df = pd.read_csv(io.StringIO(fetch_text(OTHER_LISTED)), sep="|")
    exmap = {"N": "NYSE", "A": "AMEX", "P": "NYSEARCA", "Z": "CBOE", "V": "IEX"}
    for _, row in df.iterrows():
        symbol = str(row.get("ACT Symbol", "")).strip().upper()
        if not symbol or symbol.startswith("File Creation Time"):
            continue
        out[symbol] = {
            "symbol": symbol,
            "name": str(row.get("Security Name", "")).strip(),
            "exchange": exmap.get(str(row.get("Exchange", "")).upper(), "OTHER"),
            "etf": str(row.get("ETF", "N")).upper() == "Y",
            "test": str(row.get("Test Issue", "N")).upper() == "Y",
        }
    return out


def common_like(rec: dict[str, Any]) -> bool:
    if rec["etf"] or rec["test"]:
        return False
    if EXCLUDE_NAME.search(rec.get("name", "")):
        return False
    return bool(re.fullmatch(r"[A-Z0-9.\-]+", rec["symbol"]))


def screener_request(params: dict[str, str]):
    try:
        r = requests.get(NASDAQ_SCREENER, params=params, headers=HEADERS, timeout=35)
        r.raise_for_status()
        return r
    except Exception:
        if curl_requests is None:
            raise
        r = curl_requests.get(
            NASDAQ_SCREENER,
            params=params,
            headers=HEADERS,
            impersonate="chrome",
            timeout=35,
        )
        r.raise_for_status()
        return r


def load_snapshot() -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for ex in ("NASDAQ", "NYSE", "AMEX"):
        params = {
            "tableonly": "true",
            "limit": "10000",
            "offset": "0",
            "exchange": ex,
            "download": "true",
        }
        payload = screener_request(params).json()
        for row in ((payload.get("data") or {}).get("rows") or []):
            symbol = str(row.get("symbol", "")).strip().upper()
            if symbol:
                out[symbol] = row
        time.sleep(0.2)
    return out


def yf_symbol(symbol: str) -> str:
    return symbol.replace(".", "-")


def extract_frame(raw: pd.DataFrame, ticker: str, batch_len: int) -> pd.DataFrame | None:
    if raw is None or raw.empty:
        return None
    if isinstance(raw.columns, pd.MultiIndex):
        l0 = set(map(str, raw.columns.get_level_values(0)))
        l1 = set(map(str, raw.columns.get_level_values(1)))
        if ticker in l0:
            return raw[ticker].copy()
        if ticker in l1:
            return raw.xs(ticker, axis=1, level=1).copy()
        return None
    return raw.copy() if batch_len == 1 else None


def download_history(symbols: list[str]) -> dict[str, pd.DataFrame]:
    result: dict[str, pd.DataFrame] = {}
    mapping = {yf_symbol(s): s for s in symbols}
    tickers = list(mapping)
    for i, batch in enumerate(chunks(tickers, CFG["batch_size"]), 1):
        raw = None
        for attempt in range(2):
            try:
                raw = yf.download(
                    batch,
                    period="1mo",
                    interval="1d",
                    group_by="ticker",
                    auto_adjust=False,
                    progress=False,
                    threads=True,
                    timeout=30,
                )
                break
            except Exception as exc:
                print(f"history batch {i} attempt {attempt + 1}: {exc}", file=sys.stderr)
                time.sleep(2)
        if raw is None:
            continue
        for ticker in batch:
            frame = extract_frame(raw, ticker, len(batch))
            if frame is not None and not frame.empty and "Close" in frame.columns:
                result[mapping[ticker]] = frame
        time.sleep(0.1)
    return result


def price_metrics(df: pd.DataFrame) -> dict[str, Any]:
    close = pd.to_numeric(df["Close"], errors="coerce").dropna()
    if len(close) < 2:
        return {}
    last = float(close.iloc[-1])
    volume = pd.to_numeric(df.get("Volume", pd.Series(index=df.index, dtype=float)), errors="coerce")
    prior_vol = volume.loc[close.index[:-1]].dropna().tail(20)
    latest_vol = num(volume.loc[close.index[-1]]) if close.index[-1] in volume.index else None
    avg_vol = float(prior_vol.mean()) if not prior_vol.empty else None
    return {
        "price": last,
        "last_date": str(close.index[-1].date()) if hasattr(close.index[-1], "date") else str(close.index[-1]),
        "ret_1d_pct": pct(last, float(close.iloc[-2])),
        "ret_5d_pct": pct(last, float(close.iloc[-6])) if len(close) >= 6 else None,
        "ret_20d_pct": pct(last, float(close.iloc[-21])) if len(close) >= 21 else None,
        "volume": latest_vol,
        "avg_volume_20d": avg_vol,
        "volume_ratio": (latest_vol / avg_vol) if latest_vol and avg_vol and avg_vol > 0 else None,
        "avg_dollar_volume_20d": avg_vol * last if avg_vol else None,
    }


def enriched_record(listing: dict[str, Any], snap: dict[str, Any] | None, metrics: dict[str, Any]) -> dict[str, Any]:
    snap = snap or {}
    snapshot_price = num(snap.get("lastsale"))
    snapshot_volume = num(snap.get("volume"))
    market_cap = num(snap.get("marketCap") if "marketCap" in snap else snap.get("marketcap"))
    rec = {
        "symbol": listing["symbol"],
        "name": str(snap.get("name") or listing["name"]).strip(),
        "exchange": listing["exchange"],
        "sector": str(snap.get("sector") or "").strip(),
        "industry": str(snap.get("industry") or "").strip(),
        "snapshot_price": snapshot_price,
        "snapshot_volume": snapshot_volume,
        "market_cap": market_cap,
        "snapshot_dollar_volume": snapshot_price * snapshot_volume if snapshot_price and snapshot_volume else None,
    }
    rec.update(metrics)
    return rec


def sector_medians(records: dict[str, dict[str, Any]]) -> dict[str, float]:
    buckets: dict[str, list[float]] = {}
    for rec in records.values():
        sector = rec.get("sector")
        r5 = num(rec.get("ret_5d_pct"))
        if sector and r5 is not None:
            buckets.setdefault(sector, []).append(r5)
    return {k: float(pd.Series(v).median()) for k, v in buckets.items() if len(v) >= 5}


def raw_priority(rec: dict[str, Any]) -> float:
    r1 = num(rec.get("ret_1d_pct")) or 0.0
    r5 = num(rec.get("ret_5d_pct")) or 0.0
    rel = num(rec.get("sector_relative_5d_pct")) or 0.0
    vr = num(rec.get("volume_ratio")) or 0.0
    adv = num(rec.get("avg_dollar_volume_20d")) or num(rec.get("snapshot_dollar_volume")) or 0.0
    s1 = min(30.0, max(0.0, -r1 / abs(CFG["one_day_trigger_pct"]) * 22.0))
    s5 = min(35.0, max(0.0, -r5 / abs(CFG["five_day_trigger_pct"]) * 25.0))
    sr = min(25.0, max(0.0, -rel / abs(CFG["sector_underperformance_trigger_pct"]) * 18.0))
    vol = min(12.0, vr / max(CFG["preferred_volume_ratio"], 0.1) * 8.0)
    liq = min(8.0, max(0.0, math.log10(max(adv, 1.0)) - 5.0) * 2.5)
    return round(min(100.0, 25.0 + max(s1, s5, sr) + vol + liq), 1)


def find_shocks(listings: dict[str, dict[str, Any]], snapshot: dict[str, dict[str, Any]], history: dict[str, pd.DataFrame]) -> list[dict[str, Any]]:
    records: dict[str, dict[str, Any]] = {}
    for symbol, df in history.items():
        if symbol in listings:
            records[symbol] = enriched_record(listings[symbol], snapshot.get(symbol), price_metrics(df))
    med = sector_medians(records)
    out: list[dict[str, Any]] = []
    for rec in records.values():
        r1, r5 = num(rec.get("ret_1d_pct")), num(rec.get("ret_5d_pct"))
        sector_med = med.get(rec.get("sector", ""))
        rel = r5 - sector_med if r5 is not None and sector_med is not None else None
        rec["sector_median_5d_pct"] = sector_med
        rec["sector_relative_5d_pct"] = rel
        triggers: list[str] = []
        if r1 is not None and r1 <= CFG["one_day_trigger_pct"]:
            triggers.append("1D_SHOCK")
        if r5 is not None and r5 <= CFG["five_day_trigger_pct"]:
            triggers.append("5D_SHOCK")
        if rel is not None and rel <= CFG["sector_underperformance_trigger_pct"]:
            triggers.append("SECTOR_UNDERPERFORM")
        if not triggers:
            continue
        rec["raw_triggers"] = triggers
        rec["raw_priority"] = raw_priority(rec)
        rec["volume_confirmation"] = bool((num(rec.get("volume_ratio")) or 0) >= CFG["preferred_volume_ratio"])
        out.append(rec)
    out.sort(key=lambda x: (x["volume_confirmation"], x["raw_priority"]), reverse=True)
    return out[: CFG["max_candidates"]]


def signal_from(rec: dict[str, Any], generated_at: str) -> dict[str, Any]:
    symbol = str(rec.get("symbol") or "").strip().upper()
    last_date = str(rec.get("last_date") or "unknown-date")
    triggers = [str(x) for x in (rec.get("raw_triggers") or []) if x]
    trigger_key = "+".join(sorted(triggers)) or "ANOMALY"
    reaction = []
    if rec.get("ret_1d_pct") is not None:
        reaction.append(f"1D {rec['ret_1d_pct']:.2f}%")
    if rec.get("ret_5d_pct") is not None:
        reaction.append(f"5D {rec['ret_5d_pct']:.2f}%")
    if rec.get("sector_relative_5d_pct") is not None:
        reaction.append(f"sector-relative 5D {rec['sector_relative_5d_pct']:.2f}pp")
    if rec.get("volume_ratio") is not None:
        reaction.append(f"volume {rec['volume_ratio']:.2f}x 20D")
    if rec.get("price") is not None:
        reaction.append(f"price {rec['price']:.2f}")

    return {
        "intake_id": f"PRICE|{symbol}|{last_date}|{trigger_key}",
        "input_lane": "MARKET_PRICING",
        "discovery_channel": "Runner3 Opportunity Radar Market Scanner",
        "verification": "MARKET_DATA_VERIFIED",
        "event_economic_change": f"{symbol} triggered market-pricing anomaly: {', '.join(triggers)}",
        "measurable_variable": "",
        "first_order_impact": "",
        "second_order_lead": "",
        "affected_assets": symbol,
        "market_reaction": "; ".join(reaction),
        "mispricing_hypothesis": "",
        "route_engine": "Shock / Narrative Mispricing",
        "lead_decision": "",
        "last_checked": generated_at,
        "source": {
            "name": rec.get("name"),
            "exchange": rec.get("exchange"),
            "sector": rec.get("sector"),
            "industry": rec.get("industry"),
            "market_cap": rec.get("market_cap"),
            "raw_priority": rec.get("raw_priority"),
            "raw_triggers": triggers,
            "volume_confirmation": rec.get("volume_confirmation"),
            "last_date": rec.get("last_date"),
        },
    }


def write_health(**kwargs: Any) -> None:
    HEALTH_OUT.write_text(json.dumps(kwargs, ensure_ascii=False, indent=2, default=str), encoding="utf-8")


def main() -> None:
    generated_at = datetime.now(TZ).isoformat()
    try:
        print("[1/4] Loading Nasdaq symbol directories")
        listings = load_symbol_directory()
        commons = {s: r for s, r in listings.items() if common_like(r)}

        print("[2/4] Loading Nasdaq screener snapshot")
        snapshot_error = None
        try:
            snapshot = load_snapshot()
        except Exception as exc:
            snapshot = {}
            snapshot_error = str(exc)
            print(f"snapshot failed: {exc}", file=sys.stderr)

        eligible: list[str] = []
        for symbol in commons:
            snap = snapshot.get(symbol, {})
            mcap = num(snap.get("marketCap") if "marketCap" in snap else snap.get("marketcap"))
            p, v = num(snap.get("lastsale")), num(snap.get("volume"))
            dv = p * v if p and v else None
            if snapshot:
                if mcap is not None and mcap < CFG["min_market_cap_usd"]:
                    continue
                if dv is not None and dv < CFG["min_snapshot_dollar_volume_usd"]:
                    continue
            eligible.append(symbol)
        eligible = eligible[: CFG["max_history_symbols"]]

        print(f"[3/4] Downloading 1mo daily history for {len(eligible)} symbols")
        history = download_history(eligible)
        coverage = len(history) / max(1, len(eligible))
        if coverage < CFG["min_history_coverage"]:
            raise RuntimeError(f"history coverage too low: {len(history)}/{len(eligible)} ({coverage:.1%})")

        print("[4/4] Building V2 raw pricing signals")
        shocks = find_shocks(commons, snapshot, history)
        signals = [signal_from(x, generated_at) for x in shocks]
        source_dates = sorted({str(x.get("source", {}).get("last_date")) for x in signals if x.get("source", {}).get("last_date")})
        source_session_date = source_dates[-1] if source_dates else None

        payload = {
            "schema_version": 2.0,
            "purpose": "Opportunity Radar V2 raw intake — MARKET_PRICING only; not a trade recommendation",
            "generated_at": generated_at,
            "source_session_date": source_session_date,
            "complete": True,
            "stats": {
                "listed_securities": len(listings),
                "common_like_universe": len(commons),
                "snapshot_rows": len(snapshot),
                "snapshot_error": snapshot_error,
                "history_requested": len(eligible),
                "history_returned": len(history),
                "history_coverage": coverage,
                "signal_count": len(signals),
                "volume_confirmed": sum(1 for x in shocks if x.get("volume_confirmation")),
            },
            "signals": signals,
        }
        SIGNALS_OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        write_health(
            schema_version=2.0,
            generated_at=generated_at,
            source_session_date=source_session_date,
            status="COMPLETE",
            complete=True,
            signal_count=len(signals),
            history_requested=len(eligible),
            history_returned=len(history),
            history_coverage=coverage,
            snapshot_ok=bool(snapshot),
            snapshot_error=snapshot_error,
        )
        print(f"Wrote {SIGNALS_OUT} ({len(signals)} signals)")
        print(f"Wrote {HEALTH_OUT}")
    except Exception as exc:
        write_health(
            schema_version=2.0,
            generated_at=generated_at,
            status="FAILED",
            complete=False,
            error=str(exc),
        )
        print(f"FAILED: {exc}", file=sys.stderr)
        raise


if __name__ == "__main__":
    main()
