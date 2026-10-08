"""Regression tests for cross-session MARKET_PRICING packet corruption."""

from __future__ import annotations

import importlib.util
import sys
import unittest
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
