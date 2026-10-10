"""Bidirectional MARKET_PRICING recall audit: deterministic, read-only tests."""
from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "opportunity_recall_shadow", ROOT / "scripts" / "opportunity_radar_market_recall_shadow.py"
)
assert spec and spec.loader
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def rec(symbol, one, five, vol, *, state=None, relative=0.0, corp=False):
    out = {
        "symbol": symbol, "last_date": "2026-10-09",
        "ret_1d_pct": one, "ret_5d_pct": five,
        "volume_ratio": vol, "sector_relative_5d_pct": relative,
        "avg_dollar_volume_20d": 15000000,
        "corporate_action_suspected": corp,
    }
    if state:
        out["discovery_state"] = state
    return out


def fixture(rows, selected=()):
    h = {
        "status": "COMPLETE", "complete": True,
        "source_session_date": "2026-10-09",
        "prefilter_count": len(rows), "signal_count": len(selected),
        "scanner_version": "2.2-freshness-recovery",
    }
    p = {"status": "COMPLETE", "complete": True, "source_session_date": "2026-10-09", "records": rows}
    by = {r["symbol"]: r for r in rows}
    s = {
        "status": "COMPLETE", "complete": True, "source_session_date": "2026-10-09",
        "signals": [
            {
                "affected_assets": ticker,
                "source": {
                    "last_date": "2026-10-09",
                    "discovery_state": by[ticker].get("discovery_state") if ticker in by else None,
                    "raw_triggers": by[ticker].get("raw_triggers") if ticker in by else None,
                },
            } for ticker in selected
        ],
        "stats": {"listed_securities": 5, "common_like_universe": 4, "snapshot_rows": 3},
    }
    return h, p, s


class ShadowAuditTests(unittest.TestCase):
    def test_pump_with_sub_2x_volume_is_detected_but_baseline_miss_explained(self):
        rows = [rec("FSLY", 15.86, 13.52, 1.95), rec("KLRA", 16.1, 11.74, 1.50)]
        result = m.audit(*fixture(rows))
        lookup = {r["symbol"]: r for r in result["records"]}
        self.assertEqual(result["counts"]["qualified_price_moves"]["1D_PUMP"], 2)
        self.assertEqual(result["counts"]["baseline_emitted_price_moves"].get("1D_PUMP", 0), 0)
        self.assertEqual(lookup["FSLY"]["baseline_explanation"], "BELOW_EARLY_VOLUME")
        self.assertEqual(lookup["KLRA"]["shadow_selection"], "SELECTED")
        self.assertEqual(result["counts"]["new_shadow_symbols_not_in_baseline"], 2)

    def test_shock_and_early_baseline_emitted_unchanged(self):
        rows = [
            rec("T", -9.808, -7.69, 3.94, state="RAW_ANOMALY"),
            rec("AMT", 9.30, 12.36, 2.99, state="EARLY_WATCH"),
            rec("AGNT", -7.23, 1.92, 0.94, state="RAW_ANOMALY"),
        ]
        result = m.audit(*fixture(rows, selected=["T", "AMT"]))
        by = {x["symbol"]: x for x in result["records"]}
        self.assertEqual(by["T"]["baseline_explanation"], "EMITTED_RAW_ANOMALY")
        self.assertEqual(by["AMT"]["baseline_explanation"], "EMITTED_EARLY_WATCH")
        self.assertEqual(by["AGNT"]["baseline_explanation"], "RANK_CAP_RAW")
        self.assertEqual(by["AGNT"]["shadow_group"], "SHOCK")
        self.assertEqual(result["counts"]["qualified_price_moves"]["1D_SHOCK"], 2)

    def test_corporate_action_never_promoted_from_raw_jump(self):
        rows = [rec("SPLT", 30.0, 40.0, 12.0, corp=True)]
        result = m.audit(*fixture(rows))
        self.assertEqual(result["counts"]["qualified_price_moves"], {})
        self.assertEqual(result["records"][0]["baseline_explanation"], "CORPORATE_ACTION_SUPPRESSED")
        self.assertEqual(result["records"][0]["shadow_selection"], "NOT_SELECTED")

    def test_reverse_5d_pump_caught_even_when_last_day_flat(self):
        rows = [rec("PCRX", -0.20, 44.0, 2.38)]
        result = m.audit(*fixture(rows))
        self.assertEqual(result["counts"]["qualified_price_moves"]["5D_PUMP"], 1)
        self.assertEqual(result["records"][0]["shadow_group"], "PUMP")

    def test_hard_cap_and_dedupe_deterministic(self):
        rows = [rec("P%02d" % i, 7+i, 18.0, 2.1) for i in range(45)]
        result = m.audit(*fixture(rows))
        selected = [x for x in result["records"] if x["shadow_selection"]=="SELECTED"]
        dropped = [x for x in result["records"] if x["shadow_selection"]=="SHADOW_QUOTA"]
        self.assertEqual(len(selected), 28)
        self.assertEqual(len(dropped), 17)
        self.assertEqual(result["counts"]["shadow_group_eligible"]["PUMP"], 45)
        self.assertEqual(result["counts"]["baseline_emitted"], 0)

    def test_mixed_reversal_keeps_one_symbol_one_slot(self):
        rows = [rec("BRUN", 8.93, -20.17, 1.09)]
        result = m.audit(*fixture(rows))
        self.assertIn("1D_PUMP", result["records"][0]["shadow_triggers"])
        self.assertIn("5D_SHOCK", result["records"][0]["shadow_triggers"])
        self.assertEqual(result["records"][0]["shadow_group"], "PUMP")
        self.assertEqual(result["counts"]["shadow_selected_total"], 1)

    def test_full_upstream_dispositions_match_fresh_prefilter(self):
        rows = [rec("T", -9.8, -7.69, 3.9)]
        h, p, signals = fixture(rows, selected=["T"])
        upstream = {
            "schema": "opportunity-radar-recall-universe-stage-v1",
            "source_session_date": "2026-10-09", "listed_total": 3,
            "fresh_eligible": 1, "eligible_requested": 1,
            "reason_counts": {
                "ELIGIBLE_FRESH": 1, "ETF_OR_TEST_ISSUE": 1,
                "SNAPSHOT_DOLLAR_VOLUME_FILTER": 1,
            },
            "records": [
                {"symbol": "T", "reason": "ELIGIBLE_FRESH"},
                {"symbol": "SPY", "reason": "ETF_OR_TEST_ISSUE"},
                {"symbol": "MICRO", "reason": "SNAPSHOT_DOLLAR_VOLUME_FILTER"},
            ],
        }
        result = m.audit(h, p, signals, upstream=upstream)
        self.assertEqual(result["universe_funnel"]["upstream_symbol_exclusion_reason_coverage"], "FULL_PER_SYMBOL")
        self.assertEqual(len(result["universe_dispositions"]), 3)
        upstream["records"][2]["reason"] = "MARKET_CAP_FILTER"
        with self.assertRaisesRegex(ValueError, "UPSTREAM_STAGE_COVERAGE_MISMATCH"):
            m.audit(h, p, signals, upstream=upstream)

    def test_degraded_or_cross_session_source_fails_closed(self):
        h,p,s=fixture([rec("T",-10,-10,4)],selected=["T"])
        h["complete"]=False
        with self.assertRaisesRegex(ValueError, "SOURCE_NOT_COMPLETE"):
            m.audit(h,p,s)
        h["complete"]=True
        p["source_session_date"]="2026-10-08"
        with self.assertRaisesRegex(ValueError, "SOURCE_NOT_COMPLETE"):
            m.audit(h,p,s)

    def test_protected_pump_policy_preserves_raw_shock_and_early_and_explains_displacement(self):
        shocks = [
            {**rec(f"S{i}", -8-i/100, -16, 3, state="RAW_ANOMALY"),
             "raw_triggers": ["1D_SHOCK", "5D_SHOCK"]} for i in range(16)
        ]
        early = [
            {**rec(f"E{i}", 4, 2, 3, state="EARLY_WATCH"),
             "raw_triggers": ["EARLY_WATCH_PRICE"]} for i in range(16)
        ]
        sector = [
            {**rec(f"R{i}", -1, -5, 1, state="RAW_ANOMALY", relative=-11),
             "raw_triggers": ["SECTOR_UNDERPERFORM"]} for i in range(48)
        ]
        pump = [rec(f"P{i}", 10+i/10, 18+i/10, 1.8) for i in range(50)]
        rows = shocks + early + sector + pump
        baseline = [r["symbol"] for r in shocks+early+sector]
        result = m.audit(*fixture(rows, selected=baseline))
        c = result["counts"]
        self.assertEqual(c["protected_selected_total"], 80)
        self.assertEqual(c["protected_new_pumps"], 24)
        self.assertEqual(c["protected_displaced_baseline"], 24)
        self.assertEqual(c["protected_displacement_reasons"], {"SECTOR_ONLY": 24})
        self.assertEqual(len(result["protected_review_queue"]["added"]), 24)
        self.assertEqual(len(result["protected_review_queue"]["displaced"]), 24)
        selected = {r["symbol"] for r in result["records"] if r["protected_comparison"] in ("PRESERVED_BASELINE", "ADDED_PUMP_SHADOW_ONLY")}
        self.assertTrue({r["symbol"] for r in shocks+early}.issubset(selected))
        self.assertEqual(c["protected_selected_price_moves"]["1D_SHOCK"], 16)

    def test_protected_policy_fails_closed_if_source_exceeds_actual_cap(self):
        rows = [rec("A", -8, 0, 2, state="RAW_ANOMALY"),
                rec("B", 8, 0, 2, state="EARLY_WATCH")]
        h,p,s = fixture(rows, selected=["A","B"])
        p["config_snapshot"] = {"max_candidates": 1}
        with self.assertRaisesRegex(ValueError, "BASELINE_EXCEEDS_COMPARABLE_PACKET_CAP"):
            m.audit(h,p,s)

    def test_missing_selected_signal_and_duplicate_prefilter_rejected(self):
        h,p,s=fixture([rec("T",-10,-10,4)],selected=["XX"])
        with self.assertRaisesRegex(ValueError, "SOURCE_SIGNAL_NOT_IN_PREFILTER"):
            m.audit(h,p,s)
        h,p,s=fixture([rec("T",-10,-10,4),rec("T",10,10,4)])
        with self.assertRaisesRegex(ValueError, "DUPLICATE_PREFILTER_SYMBOL"):
            m.audit(h,p,s)


if __name__ == "__main__":
    unittest.main()
