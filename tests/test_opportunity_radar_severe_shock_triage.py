"""Contract tests for severe Shock triage on the existing recall-shadow artifact."""
import importlib.util
from pathlib import Path
import unittest


P = Path(__file__).resolve().parents[1] / "scripts" / "opportunity_radar_market_recall_shadow.py"
spec = importlib.util.spec_from_file_location("market_recall_shadow", P)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class SevereShockTriageTests(unittest.TestCase):
    def test_outside_top80_still_queued_and_sorted_first(self):
        rows = [
            {"symbol": "A", "ret_1d_pct": -22, "ret_5d_pct": -9, "baseline_emitted": False,
             "baseline_explanation": "RANK_CAP_RAW", "shadow_triggers": ["1D_SHOCK"]},
            {"symbol": "B", "ret_1d_pct": -25, "ret_5d_pct": -28, "baseline_emitted": True,
             "baseline_explanation": "EMITTED_RAW_ANOMALY", "shadow_triggers": ["1D_SHOCK", "5D_SHOCK"]},
            {"symbol": "C", "ret_1d_pct": 4, "ret_5d_pct": -16, "baseline_emitted": False,
             "baseline_explanation": "RANK_CAP_RAW", "shadow_triggers": ["5D_SHOCK"]},
            {"symbol": "D", "ret_1d_pct": -14, "ret_5d_pct": -14, "baseline_emitted": False},
        ]
        result = mod.severe_shock_triage(rows, "2026-10-29")
        self.assertEqual(result["total"], 3)
        self.assertEqual(result["outside_capped_top80"], 2)
        self.assertEqual(result["inside_capped_top80"], 1)
        self.assertEqual([x["symbol"] for x in result["queue"]], ["A", "C", "B"])
        self.assertTrue(all(x["triage_disposition"] == "PENDING_CAUSAL_REVIEW" for x in result["queue"]))
        self.assertTrue(all(x["actionable"] is False for x in result["queue"]))
        self.assertTrue(all(x["catalyst_verified"] is False for x in result["queue"]))

    def test_no_backward_hindsight_and_no_duplicate_signal(self):
        rows = [{"symbol": "XYZ", "ret_1d_pct": -15.0, "ret_5d_pct": None,
                 "baseline_emitted": True, "shadow_triggers": ["1D_SHOCK"]}]
        result = mod.severe_shock_triage(rows, "2026-10-29")
        self.assertEqual(result["queue"][0]["event_id"], "2026-10-29|XYZ|SEVERE_SHOCK_TRIAGE")
        self.assertEqual(result["queue"][0]["source_session_date"], "2026-10-29")
        self.assertEqual(result["policy"], "SHADOW_ONLY_NO_AUTOMATIC_SIGNALS_OR_ENTRY")
        self.assertEqual(mod.severe_shock_triage([], "2026-10-29")["total"], 0)


if __name__ == "__main__":
    unittest.main()
