#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import importlib.util
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
REFERENCE = ROOT / "wave-rider-verify" / "reference_verify.py"
EXPECTED_REFERENCE_BLOB = "2ba5f66d33e2e483a4c669c95f3b97778c80fcd0"
HOLDOUT_START = date(2026, 8, 15)
SYMBOLS = ("BNBUSDT", "TRXUSDT")
TF = 5


def git_blob_sha(data: bytes) -> str:
    hdr = f"blob {len(data)}\0".encode()
    return hashlib.sha1(hdr + data).hexdigest()


def load_frozen_reference():
    raw = REFERENCE.read_bytes()
    actual = git_blob_sha(raw)
    if actual != EXPECTED_REFERENCE_BLOB:
        raise RuntimeError(
            f"Wave Rider reference changed: expected {EXPECTED_REFERENCE_BLOB}, got {actual}. "
            "Holdout is frozen; refusing to run modified logic."
        )
    spec = importlib.util.spec_from_file_location("wr_forward_count_ref", REFERENCE)
    if spec is None or spec.loader is None:
        raise RuntimeError("Could not import frozen reference")
    wr = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = wr
    spec.loader.exec_module(wr)
    return wr


def archive_exists(symbol: str, d: date) -> bool:
    ds = d.isoformat()
    url = f"https://data.binance.vision/data/futures/um/daily/klines/{symbol}/1m/{symbol}-1m-{ds}.zip"
    try:
        r = requests.head(url, allow_redirects=True, timeout=20)
        if r.status_code == 200:
            return True
        if r.status_code not in (403, 405):
            return False
        # Some CDNs are inconsistent on HEAD; use a tiny streamed GET fallback.
        with requests.get(url, stream=True, timeout=20) as g:
            return g.status_code == 200
    except requests.RequestException:
        return False


def latest_common_published_day() -> date:
    start = datetime.now(timezone.utc).date() - timedelta(days=1)
    for lag in range(0, 5):
        d = start - timedelta(days=lag)
        if d < HOLDOUT_START:
            break
        if all(archive_exists(s, d) for s in SYMBOLS):
            return d
    raise RuntimeError("No common published Binance daily archive found for the forward window")


def run_symbol(wr, symbol: str, end_day: date) -> int:
    wr.SYMBOL = symbol
    wr.START = HOLDOUT_START.isoformat()
    wr.END = end_day.isoformat()

    one, tick, missing = wr.fetch_1m()
    eval_missing = [
        d for d in missing if HOLDOUT_START <= date.fromisoformat(d) <= end_day
    ]
    if eval_missing:
        raise RuntimeError(f"{symbol}: incomplete holdout data: {','.join(eval_missing)}")

    st = int(
        datetime.combine(HOLDOUT_START, datetime.min.time(), tzinfo=timezone.utc).timestamp()
        * 1000
    )
    en = int(
        (
            datetime.combine(end_day + timedelta(days=1), datetime.min.time(), tzinfo=timezone.utc)
            - timedelta(milliseconds=1)
        ).timestamp()
        * 1000
    )
    trades, _ = wr.run(TF, wr.agg(one, TF), tick, st, en)
    return len(trades)


def main() -> None:
    wr = load_frozen_reference()
    end_day = latest_common_published_day()

    # Intentionally expose only sample accumulation, never R/expectancy/trade outcomes.
    print(f"WR_FORWARD_PROTOCOL start={HOLDOUT_START.isoformat()} tf={TF}m ref={EXPECTED_REFERENCE_BLOB}")
    print(f"WR_FORWARD_DATA_THROUGH {end_day.isoformat()}")
    for symbol in SYMBOLS:
        n = run_symbol(wr, symbol, end_day)
        next_cp = 50 if n < 50 else (100 if n < 100 else 0)
        remaining = max(next_cp - n, 0) if next_cp else 0
        print(f"WR_FORWARD_COUNT symbol={symbol} n={n} next={next_cp} remaining={remaining}")


if __name__ == "__main__":
    main()
