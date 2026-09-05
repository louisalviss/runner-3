#!/usr/bin/env python3
"""Opportunity Radar V2 public market/pricing intake scanner.

Runs on public Runner3 so the pricing lane does not depend on private Actions
minutes. It scans the US listed-equity universe for price/relative anomalies and
emits RAW Signals intake packets only. It never decides that an anomaly is a
mispricing and never creates REVIEW/BUY/ACTIVE state.

Discovery is intentionally higher-recall than the entry layer:
- EARLY_WATCH keeps testable price anomalies for up to 3 completed sessions.
- 2D_CONTINUATION flags delayed repricing as confirmation metadata only.
- corporate-action guards use adjusted prices and suppress split/dividend artifacts.
These labels never alter BUY/REVIEW gates or deploy capital.
"""

from __future__ import annotations

import io
import json
import math
import re
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Iterable
from zoneinfo import ZoneInfo

import pandas as pd
import pandas_market_calendars as mcal
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
    "early_watch_abs_1d_pct": 3.0,
    "early_watch_volume_ratio": 2.0,
    "early_watch_ttl_sessions": 3,
    "continuation_abs_1d_pct": 3.0,
    "continuation_window_sessions": 2,
    "corporate_action_gap_pp": 5.0,
    "corporate_action_unverified_raw_pct": 30.0,
    "min_market_cap_usd": 500_000_000,
    "min_snapshot_dollar_volume_usd": 5_000_000,
    "max_history_symbols": 4500,
    "max_candidates": 80,
    "max_early_watch": 24,
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


def parse_date(value: Any) -> date | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value)[:10]).date()
    except Exception:
        return None


def completed_session_age(start: Any, end: Any) -> int | None:
    s, e = parse_date(start), parse_date(end)
    if not s or not e or e < s:
        return None
    return max(0, len(pd.bdate_range(s, e)) - 1)


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
                    actions=False,
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
    raw_close = pd.to_numeric(df["Close"], errors="coerce")
    adj_available = "Adj Close" in df.columns
    adj_close = pd.to_numeric(df["Adj Close"], errors="coerce") if adj_available else raw_close.copy()
    aligned = pd.concat({"raw": raw_close, "adj": adj_close}, axis=1).dropna()
    if len(aligned) < 2:
        return {}

    raw = aligned["raw"]
    adj = aligned["adj"]
    last_raw = float(raw.iloc[-1])
    last_adj = float(adj.iloc[-1])
    raw_r1 = pct(last_raw, float(raw.iloc[-2]))
    adj_r1 = pct(last_adj, float(adj.iloc[-2]))
    gap = abs(raw_r1 - adj_r1) if raw_r1 is not None and adj_r1 is not None else None

    corporate_action_suspected = bool(
        adj_available
        and raw_r1 is not None
        and abs(raw_r1) >= abs(CFG["one_day_trigger_pct"])
        and gap is not None
        and gap >= CFG["corporate_action_gap_pp"]
    )
    corporate_action_unverified = bool(
        not adj_available
        and raw_r1 is not None
        and abs(raw_r1) >= CFG["corporate_action_unverified_raw_pct"]
    )

    volume = pd.to_numeric(df.get("Volume", pd.Series(index=df.index, dtype=float)), errors="coerce")
    latest_idx = aligned.index[-1]
    prior_vol = volume.loc[aligned.index[:-1]].dropna().tail(20)
    latest_vol = num(volume.loc[latest_idx]) if latest_idx in volume.index else None
    avg_vol = float(prior_vol.mean()) if not prior_vol.empty else None

    return {
        "price": last_raw,
        "adjusted_price": last_adj,
        "last_date": str(latest_idx.date()) if hasattr(latest_idx, "date") else str(latest_idx),
        "ret_1d_pct": adj_r1,
        "ret_5d_pct": pct(last_adj, float(adj.iloc[-6])) if len(adj) >= 6 else None,
        "ret_20d_pct": pct(last_adj, float(adj.iloc[-21])) if len(adj) >= 21 else None,
        "raw_ret_1d_pct": raw_r1,
        "adjustment_gap_1d_pp": gap,
        "adjustment_verified": adj_available,
        "corporate_action_suspected": corporate_action_suspected,
        "corporate_action_unverified": corporate_action_unverified,
        "volume": latest_vol,
        "avg_volume_20d": avg_vol,
        "volume_ratio": (latest_vol / avg_vol) if latest_vol and avg_vol and avg_vol > 0 else None,
        "avg_dollar_volume_20d": avg_vol * last_raw if avg_vol else None,
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
    early = min(18.0, abs(r1) / max(CFG["early_watch_abs_1d_pct"], 0.1) * 8.0)
    vol = min(12.0, vr / max(CFG["preferred_volume_ratio"], 0.1) * 8.0)
    liq = min(8.0, max(0.0, math.log10(max(adv, 1.0)) - 5.0) * 2.5)
    return round(min(100.0, 25.0 + max(s1, s5, sr, early) + vol + liq), 1)


def load_previous_packet() -> dict[str, Any]:
    if not SIGNALS_OUT.exists():
        return {}
    try:
        payload = json.loads(SIGNALS_OUT.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    except Exception as exc:
        print(f"previous packet unreadable: {exc}", file=sys.stderr)
        return {}


def previous_by_symbol(packet: dict[str, Any]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for sig in packet.get("signals") or []:
        if not isinstance(sig, dict):
            continue
        source = sig.get("source") or {}
        symbol = str(sig.get("affected_assets") or source.get("symbol") or "").strip().upper()
        if symbol:
            out[symbol] = sig
    return out


def prior_detection(sig: dict[str, Any] | None) -> tuple[str | None, float | None, str | None]:
    if not sig:
        return None, None, None
    source = sig.get("source") or {}
    detected_at = source.get("earliest_detected_at") or sig.get("last_checked")
    detected_price = num(source.get("earliest_detected_price"))
    if detected_price is None:
        detected_price = num(source.get("price"))
    intake_id = str(sig.get("intake_id") or "") or None
    return str(detected_at) if detected_at else None, detected_price, intake_id


def prior_direction(sig: dict[str, Any] | None) -> int:
    if not sig:
        return 0
    r1 = num((sig.get("source") or {}).get("ret_1d_pct"))
    if r1 is None:
        return 0
    return 1 if r1 > 0 else -1 if r1 < 0 else 0


def build_anomalies(
    listings: dict[str, dict[str, Any]],
    snapshot: dict[str, dict[str, Any]],
    history: dict[str, pd.DataFrame],
    previous_packet: dict[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    records: dict[str, dict[str, Any]] = {}
    for symbol, df in history.items():
        if symbol in listings:
            records[symbol] = enriched_record(listings[symbol], snapshot.get(symbol), price_metrics(df))

    med = sector_medians(records)
    previous = previous_by_symbol(previous_packet)
    normal: list[dict[str, Any]] = []
    early: list[dict[str, Any]] = []
    stats = {
        "corporate_action_suppressed": 0,
        "corporate_action_unverified_suppressed": 0,
        "early_watch": 0,
        "continuation": 0,
        "early_watch_carried": 0,
        "early_watch_emitted": 0,
        "raw_anomaly_emitted": 0,
    }

    for rec in records.values():
        symbol = rec["symbol"]
        r1, r5 = num(rec.get("ret_1d_pct")), num(rec.get("ret_5d_pct"))
        vr = num(rec.get("volume_ratio")) or 0.0
        sector_med = med.get(rec.get("sector", ""))
        rel = r5 - sector_med if r5 is not None and sector_med is not None else None
        rec["sector_median_5d_pct"] = sector_med
        rec["sector_relative_5d_pct"] = rel

        if rec.get("corporate_action_suspected"):
            stats["corporate_action_suppressed"] += 1
            continue
        if rec.get("corporate_action_unverified"):
            stats["corporate_action_unverified_suppressed"] += 1
            continue

        triggers: list[str] = []
        if r1 is not None and r1 <= CFG["one_day_trigger_pct"]:
            triggers.append("1D_SHOCK")
        if r5 is not None and r5 <= CFG["five_day_trigger_pct"]:
            triggers.append("5D_SHOCK")
        if rel is not None and rel <= CFG["sector_underperformance_trigger_pct"]:
            triggers.append("SECTOR_UNDERPERFORM")

        prior = previous.get(symbol)
        prior_source = (prior or {}).get("source") or {}
        prior_state = str(prior_source.get("discovery_state") or "").upper()
        prior_date = prior_source.get("last_date")
        age = completed_session_age(prior_date, rec.get("last_date"))
        pdir = prior_direction(prior)
        cdir = 1 if (r1 or 0) > 0 else -1 if (r1 or 0) < 0 else 0
        is_continuation = bool(
            prior
            and prior_state == "EARLY_WATCH"
            and age is not None
            and 1 <= age <= CFG["continuation_window_sessions"]
            and r1 is not None
            and abs(r1) >= CFG["continuation_abs_1d_pct"]
            and pdir != 0
            and cdir == pdir
        )

        if triggers:
            rec["discovery_state"] = "RAW_ANOMALY"
            rec["raw_triggers"] = triggers
            rec["continuation_candidate"] = is_continuation
            if is_continuation:
                rec["raw_triggers"].append("2D_CONTINUATION")
                stats["continuation"] += 1
            rec["raw_priority"] = raw_priority(rec)
            rec["volume_confirmation"] = vr >= CFG["preferred_volume_ratio"]
            normal.append(rec)
            continue

        fresh_early = bool(
            r1 is not None
            and abs(r1) >= CFG["early_watch_abs_1d_pct"]
            and vr >= CFG["early_watch_volume_ratio"]
        )
        carry_early = bool(
            prior
            and prior_state == "EARLY_WATCH"
            and age is not None
            and 0 <= age <= CFG["early_watch_ttl_sessions"]
        )
        if not fresh_early and not carry_early:
            continue

        ew_triggers: list[str] = []
        if fresh_early:
            ew_triggers.append("EARLY_WATCH_PRICE")
        if carry_early and not fresh_early:
            ew_triggers.append("EARLY_WATCH_CARRY")
            stats["early_watch_carried"] += 1
        if is_continuation:
            ew_triggers.append("2D_CONTINUATION")
            stats["continuation"] += 1

        rec["discovery_state"] = "EARLY_WATCH"
        rec["raw_triggers"] = ew_triggers
        rec["continuation_candidate"] = is_continuation
        rec["raw_priority"] = raw_priority(rec)
        rec["volume_confirmation"] = vr >= CFG["preferred_volume_ratio"]
        stats["early_watch"] += 1
        early.append(rec)

    normal.sort(key=lambda x: (x["volume_confirmation"], x["raw_priority"]), reverse=True)
    early.sort(key=lambda x: (x.get("continuation_candidate", False), x["raw_priority"]), reverse=True)

    # Reserve packet capacity for discovery. Without this reservation a noisy
    # RAW_ANOMALY universe can fill all max_candidates slots and silently drop
    # every EARLY_WATCH signal even though it was detected.
    early_cap = min(CFG["max_early_watch"], CFG["max_candidates"])
    early_selected = early[:early_cap]
    normal_slots = max(0, CFG["max_candidates"] - len(early_selected))
    normal_selected = normal[:normal_slots]
    stats["early_watch_emitted"] = len(early_selected)
    stats["raw_anomaly_emitted"] = len(normal_selected)

    merged = normal_selected + early_selected
    merged.sort(
        key=lambda x: (
            x.get("continuation_candidate", False),
            x.get("volume_confirmation", False),
            x.get("raw_priority", 0),
        ),
        reverse=True,
    )
    return merged, stats


def signal_from(rec: dict[str, Any], generated_at: str, prior: dict[str, Any] | None = None) -> dict[str, Any]:
    symbol = str(rec.get("symbol") or "").strip().upper()
    last_date = str(rec.get("last_date") or "unknown-date")
    triggers = [str(x) for x in (rec.get("raw_triggers") or []) if x]
    trigger_key = "+".join(sorted(triggers)) or "ANOMALY"
    discovery_state = str(rec.get("discovery_state") or "RAW_ANOMALY")

    earliest_at, earliest_price, prior_intake_id = prior_detection(prior)
    if not earliest_at:
        earliest_at = generated_at
    if earliest_price is None:
        earliest_price = num(rec.get("price"))

    continuing_same_price_watch = bool(
        prior
        and str(((prior.get("source") or {}).get("discovery_state") or "")).upper() == "EARLY_WATCH"
        and discovery_state == "EARLY_WATCH"
    )
    intake_id = prior_intake_id if continuing_same_price_watch and prior_intake_id else f"PRICE|{symbol}|{last_date}|{trigger_key}"
    event_key = f"PRICE|{symbol}|{str(earliest_at)[:10]}"

    reaction = []
    if rec.get("ret_1d_pct") is not None:
        reaction.append(f"adjusted 1D {rec['ret_1d_pct']:.2f}%")
    if rec.get("raw_ret_1d_pct") is not None and rec.get("adjustment_gap_1d_pp") is not None:
        reaction.append(f"raw 1D {rec['raw_ret_1d_pct']:.2f}%")
    if rec.get("ret_5d_pct") is not None:
        reaction.append(f"adjusted 5D {rec['ret_5d_pct']:.2f}%")
    if rec.get("sector_relative_5d_pct") is not None:
        reaction.append(f"sector-relative 5D {rec['sector_relative_5d_pct']:.2f}pp")
    if rec.get("volume_ratio") is not None:
        reaction.append(f"volume {rec['volume_ratio']:.2f}x 20D")
    if rec.get("price") is not None:
        reaction.append(f"price {rec['price']:.2f}")

    return {
        "intake_id": intake_id,
        "event_key": event_key,
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
            "symbol": symbol,
            "name": rec.get("name"),
            "exchange": rec.get("exchange"),
            "sector": rec.get("sector"),
            "industry": rec.get("industry"),
            "market_cap": rec.get("market_cap"),
            "price": rec.get("price"),
            "adjusted_price": rec.get("adjusted_price"),
            "ret_1d_pct": rec.get("ret_1d_pct"),
            "raw_ret_1d_pct": rec.get("raw_ret_1d_pct"),
            "adjustment_gap_1d_pp": rec.get("adjustment_gap_1d_pp"),
            "adjustment_verified": rec.get("adjustment_verified"),
            "raw_priority": rec.get("raw_priority"),
            "raw_triggers": triggers,
            "volume_confirmation": rec.get("volume_confirmation"),
            "last_date": rec.get("last_date"),
            "discovery_state": discovery_state,
            "earliest_detected_at": earliest_at,
            "earliest_detected_price": earliest_price,
            "ttl_completed_sessions": CFG["early_watch_ttl_sessions"] if discovery_state == "EARLY_WATCH" else None,
            "continuation_candidate": bool(rec.get("continuation_candidate")),
            "continuation_requires_catalyst_match": bool(rec.get("continuation_candidate")),
            "catalyst_key_status": "UNRESOLVED_PRICING_ONLY",
            "buy_gate_eligible": False if discovery_state == "EARLY_WATCH" or rec.get("continuation_candidate") else None,
        },
    }


def expected_latest_completed_us_session(now: datetime | None = None) -> str:
    """Return the latest NYSE regular session whose market close has passed."""
    current = pd.Timestamp(now or datetime.now(TZ))
    if current.tzinfo is None:
        current = current.tz_localize(TZ)
    current_utc = current.tz_convert("UTC")
    cal = mcal.get_calendar("NYSE")
    start = (current_utc.date() - timedelta(days=14)).isoformat()
    end = (current_utc.date() + timedelta(days=1)).isoformat()
    schedule = cal.schedule(start_date=start, end_date=end)
    completed = schedule[schedule["market_close"] <= current_utc]
    if completed.empty:
        raise RuntimeError("no completed NYSE session found in lookback window")
    return completed.index[-1].date().isoformat()


def classify_source_session(source_session_date: str, expected_session_date: str) -> tuple[str, bool, str | None]:
    if source_session_date == expected_session_date:
        return "COMPLETE", True, None
    return "DEGRADED", False, "STALE_SOURCE_SESSION"


def latest_valid_market_session(history: dict[str, pd.DataFrame]) -> str | None:
    """Return the newest valid upstream market session, independent of emitted signals."""
    latest: str | None = None
    for frame in history.values():
        if frame is None or frame.empty or "Close" not in frame.columns:
            continue
        close = pd.to_numeric(frame["Close"], errors="coerce")
        valid = close[close.notna() & close.map(lambda value: math.isfinite(float(value)) and float(value) > 0)]
        if valid.empty:
            continue
        idx = valid.index[-1]
        session = idx.date().isoformat() if hasattr(idx, "date") else str(idx)[:10]
        if latest is None or session > latest:
            latest = session
    return latest


def write_health(**kwargs: Any) -> None:
    HEALTH_OUT.write_text(json.dumps(kwargs, ensure_ascii=False, indent=2, default=str), encoding="utf-8")


def main() -> None:
    generated_at_dt = datetime.now(TZ)
    generated_at = generated_at_dt.isoformat()
    try:
        previous_packet = load_previous_packet()

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
        anomalies, guard_stats = build_anomalies(commons, snapshot, history, previous_packet)
        previous = previous_by_symbol(previous_packet)
        signals = [signal_from(x, generated_at, previous.get(str(x.get("symbol") or "").upper())) for x in anomalies]
        source_session_date = latest_valid_market_session(history)
        if source_session_date is None:
            raise RuntimeError("no valid market session in fetched history")
        expected_session_date = expected_latest_completed_us_session(generated_at_dt)
        market_status, market_complete, reason_code = classify_source_session(
            source_session_date, expected_session_date
        )

        payload = {
            "schema_version": 2.0,
            "purpose": "Opportunity Radar V2 raw intake — MARKET_PRICING only; not a trade recommendation",
            "generated_at": generated_at,
            "source_session_date": source_session_date,
            "expected_latest_completed_us_session": expected_session_date,
            "status": market_status,
            "reason_code": reason_code,
            "complete": market_complete,
            "discovery_policy": {
                "early_watch_ttl_completed_sessions": CFG["early_watch_ttl_sessions"],
                "continuation_window_completed_sessions": CFG["continuation_window_sessions"],
                "continuation_is_confirmation_only": True,
                "buy_gate_unchanged": True,
                "returns_use_adjusted_close": True,
            },
            "stats": {
                "listed_securities": len(listings),
                "common_like_universe": len(commons),
                "snapshot_rows": len(snapshot),
                "snapshot_error": snapshot_error,
                "history_requested": len(eligible),
                "history_returned": len(history),
                "history_coverage": coverage,
                "signal_count": len(signals),
                "volume_confirmed": sum(1 for x in anomalies if x.get("volume_confirmation")),
                **guard_stats,
            },
            "signals": signals,
        }
        SIGNALS_OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        write_health(
            schema_version=2.0,
            generated_at=generated_at,
            source_session_date=source_session_date,
            expected_latest_completed_us_session=expected_session_date,
            status=market_status,
            reason_code=reason_code,
            complete=market_complete,
            signal_count=len(signals),
            history_requested=len(eligible),
            history_returned=len(history),
            history_coverage=coverage,
            snapshot_ok=bool(snapshot),
            snapshot_error=snapshot_error,
            early_watch=guard_stats["early_watch"],
            early_watch_emitted=guard_stats["early_watch_emitted"],
            raw_anomaly_emitted=guard_stats["raw_anomaly_emitted"],
            continuation=guard_stats["continuation"],
            corporate_action_suppressed=guard_stats["corporate_action_suppressed"],
            corporate_action_unverified_suppressed=guard_stats["corporate_action_unverified_suppressed"],
            buy_gate_unchanged=True,
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
