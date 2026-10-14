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

    def test_adjusted_completed_bar_extremes_detect_reverted_moves(self):
        idx = pd.to_datetime(["2026-10-08", "2026-10-09"])
        df = pd.DataFrame({
            "Close": [100., 100.],
            "Adj Close": [98., 100.],
            "High": [101., 108.],
            "Low": [99., 90.],
            "Volume": [1000., 2000.],
        }, index=idx)
        m = scanner.price_metrics(df)
        self.assertTrue(m["intraday_extremes_verified"])
        self.assertAlmostEqual(m["intraday_high_vs_prior_adjusted_close_pct"], 100*(108/98-1))
        self.assertAlmostEqual(m["intraday_low_vs_prior_adjusted_close_pct"], 100*(90/98-1))
        self.assertLess(abs(m["ret_1d_pct"]), 7)
        self.assertFalse(m["corporate_action_suspected"])

    def test_adjusted_ohlc_missing_fails_closed_without_fabricating_spikes(self):
        idx = pd.to_datetime(["2026-10-08", "2026-10-09"])
        data = {"Close": [100., 100.], "High": [101., 120.],
                "Low": [99., 80.], "Volume": [1000., 2000.]}
        raw = scanner.price_metrics(pd.DataFrame(data, index=idx))
        self.assertFalse(raw["intraday_extremes_verified"])
        self.assertIsNone(raw["intraday_high_vs_prior_adjusted_close_pct"])
        data["Adj Close"] = [100., 100.]
        data["High"] = [101., 98.]  # impossible high below 100 close
        invalid = scanner.price_metrics(pd.DataFrame(data, index=idx))
        self.assertFalse(invalid["intraday_extremes_verified"])

    def test_split_dividend_discontinuity_suppresses_daily_extremes(self):
        idx = pd.to_datetime(["2026-10-08", "2026-10-09"])
        df = pd.DataFrame({
            "Close": [100., 90.], "Adj Close": [100., 100.],
            "High": [101., 115.], "Low": [99., 85.],
            "Volume": [1000., 2000.]
        }, index=idx)
        m = scanner.price_metrics(df)
        self.assertTrue(m["corporate_action_suspected"])
        self.assertFalse(m["intraday_extremes_verified"])

    def test_nasdaq_raw_shock_probe_is_review_only_and_session_verified(self):
        class Response:
            def raise_for_status(self):
                return None
            def json(self):
                return {
                    "status": {"rCode": 200},
                    "data": {"tradesTable": {"rows": [
                        {"date": "10/13/2026", "close": "$22.85", "volume": "48,730,490"},
                        {"date": "10/12/2026", "close": "$25.85", "volume": "23,000,000"},
                    ]}},
                }

        calls = []
        def fake_get(url, **kwargs):
            calls.append((url, kwargs))
            return Response()

        result = scanner.nasdaq_completed_raw_shock_probe(
            ["T", "UNRELATED"],
            {"T": {"pctchange": "-12.5%"}, "UNRELATED": {"pctchange": "1%"}},
            "2026-10-13",
            requester=fake_get,
        )
        self.assertEqual(len(calls), 1)
        self.assertEqual(result["requested"], 1)
        self.assertEqual(len(result["confirmed_raw_moves"]), 1)
        item = result["confirmed_raw_moves"][0]
        self.assertEqual(item["symbol"], "T")
        self.assertEqual(item["session"], "2026-10-13")
        self.assertFalse(item["adjustment_verified"])
        self.assertEqual(item["action"], "NO_SIGNAL")
        self.assertEqual(result["policy"], "DIAGNOSTIC_ONLY_NOT_ADJUSTED_NO_SIGNALS_NO_COVERAGE_CREDIT")

    def test_nasdaq_raw_probe_does_not_accept_prior_session_as_fresh(self):
        class Response:
            def raise_for_status(self):
                return None
            def json(self):
                return {
                    "status": {"rCode": 200},
                    "data": {"tradesTable": {"rows": [
                        {"date": "10/12/2026", "close": "$22", "volume": "100"},
                        {"date": "10/09/2026", "close": "$25", "volume": "100"},
                    ]}},
                }

        result = scanner.nasdaq_completed_raw_shock_probe(
            ["T"], {"T": {"pctchange": "-10%"}},
            "2026-10-13", requester=lambda *args, **kwargs: Response(),
        )
        self.assertEqual(result["confirmed_raw_moves"], [])
        self.assertEqual(result["unverified"][0]["reason"], "MISSING_COMPLETED_SESSION_BAR")

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


    def test_universe_selection_reasons_are_exhaustive_and_do_not_modify_selection(self):
        listings = {
            "T": {"symbol": "T", "name": "AT&T Inc.", "etf": False, "test": False},
            "SPY": {"symbol": "SPY", "name": "SPDR S&P 500 ETF", "etf": True, "test": False},
            "P": {"symbol": "P", "name": "P Inc.", "etf": False, "test": False},
            "V": {"symbol": "V", "name": "V Inc.", "etf": False, "test": False},
            "X": {"symbol": "X", "name": "X Inc.", "etf": False, "test": False},
            "LIMIT": {"symbol": "LIMIT", "name": "LIMIT Inc.", "etf": False, "test": False},
        }
        snapshot = {
            "T": {"marketCap": "1000000000", "lastsale": "$10", "volume": "1000000"},
            "P": {"marketCap": "200000000", "lastsale": "$10", "volume": "1000000"},
            "V": {"marketCap": "1000000000", "lastsale": "$10", "volume": "10000"},
            "X": {"marketCap": "1000000000", "lastsale": "$10", "volume": "1000000"},
            "LIMIT": {"marketCap": "1000000000", "lastsale": "$10", "volume": "1000000"},
        }
        source = {"T": frame("2026-10-09"), "X": frame("2026-10-08")}
        fresh = {"T": source["T"]}
        result = scanner.universe_recall_disposition(
            listings, snapshot, ["T", "X"], source, fresh, "2026-10-09"
        )
        out = {x["symbol"]: x["reason"] for x in result["records"]}
        self.assertEqual(out, {
            "T": "ELIGIBLE_FRESH",
            "SPY": "ETF_OR_TEST_ISSUE",
            "P": "MARKET_CAP_FILTER",
            "V": "SNAPSHOT_DOLLAR_VOLUME_FILTER",
            "X": "STALE_SOURCE_SESSION",
            "LIMIT": "HISTORY_SCAN_LIMIT",
        })
        self.assertEqual(sum(result["reason_counts"].values()), len(listings))
        self.assertEqual(result["fresh_eligible"], 1)

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
