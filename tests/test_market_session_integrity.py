"""Regression tests for cross-session MARKET_PRICING packet corruption."""

from __future__ import annotations

import importlib.util
import sys
import unittest
from unittest import mock
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / ".github" / "scripts"))


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


scanner = load_module("market_scanner_integrity", ROOT / "scripts" / "opportunity_radar_market_v2.py")
checkpoint = load_module("market_checkpoint_integrity", ROOT / "scripts" / "opportunity_radar_market_checkpoint.py")


def frame(last: str):
    idx = pd.to_datetime(["2026-10-05", last])
    return pd.DataFrame(
        {"Close": [100.0, 90.0], "Adj Close": [100.0, 90.0], "Volume": [100.0, 200.0]},
        index=idx,
    )


class MarketSessionIntegrityTests(unittest.TestCase):
    def test_filter_uses_each_symbols_actual_close_date(self):
        history = {"NEW": frame("2026-10-07"), "STALE": frame("2026-10-06")}
        fresh, stale = scanner.partition_fresh_market_history(history, "2026-10-07")
        self.assertEqual(list(fresh), ["NEW"])
        self.assertEqual(stale, 1)
        records, _, _ = scanner.build_anomalies(
            {
                "NEW": {"symbol": "NEW", "name": "New Company", "exchange": "NASDAQ"},
                "STALE": {"symbol": "STALE", "name": "Stale Company", "exchange": "NASDAQ"},
            },
            {},
            fresh,
            {},
        )
        self.assertTrue(all(x["last_date"] == "2026-10-07" for x in records))


    def test_skip_current_open_session_but_accept_prior_completed_session(self):
        idx = pd.to_datetime(["2026-10-07", "2026-10-08", "2026-10-09"])
        h = {"AAPL": pd.DataFrame(
            {"Close": [98.0, 99.0, 100.0],
             "Adj Close": [98.0, 99.0, 100.0],
             "Volume": [100.0, 200.0, 300.0]}, index=idx)}
        fresh, stale = scanner.partition_fresh_market_history(h, "2026-10-08")
        self.assertEqual(stale, 0)
        self.assertEqual(scanner.price_metrics(fresh["AAPL"])["last_date"], "2026-10-08")
        self.assertEqual(len(fresh["AAPL"]), 2)

    def test_freshness_retry_recovers_actual_completed_session_only(self):
        eligible = ["T", "OTHER", "STILL_STALE"]
        history = {symbol: frame("2026-10-08") for symbol in eligible}
        snapshot = {"T": {"pctchange": "-10.82%"}, "OTHER": {"pctchange": "+0.5%"}}
        calls = []

        def fresh_download(tickers, **kwargs):
            calls.extend(tickers)
            self.assertEqual(kwargs["end"], "2026-10-10")
            self.assertEqual(kwargs["group_by"], "ticker")
            return pd.concat({
                symbol: frame("2026-10-09" if symbol == "T" else "2026-10-08")
                for symbol in tickers
            }, axis=1)

        with unittest.mock.patch.object(scanner.time, "sleep", return_value=None):
            recovered, stats = scanner.recover_fresh_market_history(
                history, eligible, "2026-10-09", snapshot, downloader=fresh_download
            )
        fresh, stale = scanner.partition_fresh_market_history(recovered, "2026-10-09")
        self.assertEqual(list(fresh), ["T"])
        self.assertEqual(stale, 2)
        emitted, _, _ = scanner.build_anomalies(
            {symbol: {"symbol": symbol, "name": symbol, "exchange": "NYSE"} for symbol in eligible},
            {}, fresh, {}
        )
        recovered_t = next((rec for rec in emitted if rec.get("symbol") == "T"), None)
        self.assertIsNotNone(recovered_t)
        self.assertIn("1D_SHOCK", recovered_t["raw_triggers"])
        self.assertEqual(recovered_t["discovery_state"], "RAW_ANOMALY")
        self.assertEqual(stats["retry_recovered"], 1)
        self.assertEqual(calls[0], "T")
        self.assertEqual(stats["independent_snapshot_shocks_unverified"][0]["action"], "NO_SIGNAL")

    def test_stale_universe_fails_closed_and_avoids_wide_retries(self):
        eligible = [f"MOCK{i}" for i in range(100)]
        history = {symbol: frame("2026-10-08") for symbol in eligible}
        snapshot = {"MOCK21": {"pctchange": "-12%"}}
        calls = []

        def stale_download(tickers, **kwargs):
            calls.extend(tickers)
            return pd.concat({symbol: frame("2026-10-08") for symbol in tickers}, axis=1)

        with unittest.mock.patch.object(scanner.time, "sleep", return_value=None):
            recovered, stats = scanner.recover_fresh_market_history(
                history, eligible, "2026-10-09", snapshot, downloader=stale_download
            )
        fresh, _ = scanner.partition_fresh_market_history(recovered, "2026-10-09")
        self.assertEqual(fresh, {})
        self.assertEqual(stats["retry_recovered"], 0)
        self.assertEqual(stats["wide_retry_skipped_reason"], "LOW_PROBE_RECOVERY")
        self.assertLess(len(calls), len(eligible))
        self.assertEqual(stats["independent_snapshot_shocks_unverified"][0]["symbol"], "MOCK21")

    def test_successful_probe_enables_whole_universe_recovery(self):
        eligible = [f"MOCK{i}" for i in range(70)]
        history = {symbol: frame("2026-10-08") for symbol in eligible}

        def fresh_download(tickers, **kwargs):
            return pd.concat({symbol: frame("2026-10-09") for symbol in tickers}, axis=1)

        with unittest.mock.patch.object(scanner.time, "sleep", return_value=None):
            recovered, stats = scanner.recover_fresh_market_history(
                history, eligible, "2026-10-09", {}, downloader=fresh_download
            )
        fresh, stale = scanner.partition_fresh_market_history(recovered, "2026-10-09")
        self.assertEqual(len(fresh), len(eligible))
        self.assertEqual(stale, 0)
        self.assertEqual(stats["retry_recovered"], len(eligible))
        self.assertEqual(stats["retry_unattempted"], 0)


    def test_old_market_session_remains_degraded(self):
        self.assertEqual(
            scanner.classify_source_session("2026-10-06", "2026-10-07"),
            ("DEGRADED", False, "STALE_SOURCE_SESSION"),
        )

    def test_checkpoint_rejects_fake_complete_stale_signal(self):
        health = {
            "status": "COMPLETE", "complete": True, "source_session_date": "2026-10-07",
            "expected_latest_completed_us_session": "2026-10-07",
        }
        packet = {
            "complete": True, "source_session_date": "2026-10-07",
            "expected_latest_completed_us_session": "2026-10-07",
            "signals": [{"intake_id": "PRICE|STALE|2026-10-06", "source": {"last_date": "2026-10-06"}}],
        }
        with self.assertRaisesRegex(RuntimeError, "stale symbol source date"):
            checkpoint.validate_packet(health, packet, {})

    def test_checkpoint_rejects_fake_complete_stale_prefilter(self):
        health = {
            "status": "COMPLETE", "complete": True, "source_session_date": "2026-10-07",
            "expected_latest_completed_us_session": "2026-10-07",
            "signal_count": 0, "prefilter_count": 1,
        }
        packet = {
            "complete": True, "source_session_date": "2026-10-07",
            "expected_latest_completed_us_session": "2026-10-07", "signals": [],
        }
        prefilter = {
            "schema": "opportunity-radar-market-prefilter-v1", "complete": True,
            "status": "COMPLETE", "source_session_date": "2026-10-07",
            "universe_count": 1, "records": [{"last_date": "2026-10-06"}],
        }
        with self.assertRaisesRegex(RuntimeError, "stale symbol source date"):
            checkpoint.validate_packet(health, packet, prefilter)


if __name__ == "__main__":
    unittest.main()
