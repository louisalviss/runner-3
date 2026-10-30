"""Rolling Shock audit must not change signals or invent economic conclusions."""
import importlib.util
import json
import unittest
from pathlib import Path

P = Path(__file__).resolve().parents[1] / "scripts" / "opportunity_radar_market_event_ledger.py"
spec = importlib.util.spec_from_file_location("rolling_source", P)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def event(day, symbol, predicate, change, selected):
    return {
        "schema": mod.SCHEMA,
        "event_id": f"{day}|{symbol}|{predicate}",
        "source_session_date": day,
        "symbol": symbol,
        "predicate": predicate,
        "adjusted_return_1d_pct_first_seen": change if predicate == "1D_SHOCK" else 0,
        "adjusted_return_5d_pct_first_seen": change if predicate == "5D_SHOCK" else 0,
        "baseline_emitted": selected,
    }


class RollingBacklogTests(unittest.TestCase):
    def test_cross_session_dedup_only_at_ticker_level(self):
        rows = [
            event("2026-10-28", "A", "1D_SHOCK", -24, False),
            event("2026-10-29", "A", "5D_SHOCK", -33, True),
            event("2026-10-29", "B", "1D_SHOCK", -15, True),
            event("2026-10-29", "C", "1D_SHOCK", -14.9, False),
        ]
        original = "".join(json.dumps(x) + "\n" for x in rows)
        result = mod.rolling_severe_backlog(original, "2026-10-29")
        self.assertEqual(result["severe_predicate_rows"], 3)
        self.assertEqual(result["severe_unique_symbols"], 2)
        self.assertEqual(result["ever_outside_top80"], 1)
        self.assertEqual(result["multi_session_symbols"], 1)
        self.assertEqual([x["symbol"] for x in result["queue"]], ["A", "B"])
        self.assertTrue(all(x["actionable"] is False for x in result["queue"]))
        self.assertTrue(result["no_automatic_signals_or_trades"])
        self.assertEqual(result, mod.rolling_severe_backlog(original, "2026-10-29"))

    def test_old_sessions_and_future_data(self):
        a = event("2026-10-15", "OLD", "1D_SHOCK", -41, False)
        b = event("2026-10-29", "NEW", "1D_SHOCK", -25, False)
        doc = json.dumps(a) + "\n" + json.dumps(b)
        self.assertEqual(mod.rolling_severe_backlog(doc, "2026-10-29", 1)["severe_unique_symbols"], 1)
        with self.assertRaises(ValueError):
            mod.rolling_severe_backlog(doc, "2026-10-29", 0)
        with self.assertRaises(ValueError):
            mod.rolling_severe_backlog(doc, "2026-10-20")


if __name__ == "__main__":
    unittest.main()
