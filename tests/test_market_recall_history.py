"""Deterministic safety tests for archived-market recall replay."""
from __future__ import annotations

import importlib.util
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("market_history", ROOT / "scripts" / "opportunity_radar_recall_history.py")
assert spec and spec.loader
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def rec(symbol, r1=0, r5=0, vol=2, sector=None, state=None, **kwargs):
    r = {
        "symbol": symbol, "last_date": "2026-10-09",
        "ret_1d_pct": r1, "ret_5d_pct": r5,
        "volume_ratio": vol, "sector_relative_5d_pct": sector,
        "avg_dollar_volume_20d": 10000000,
    }
    r.update(kwargs)
    return r


def packet(rows, signals):
    raw = json.dumps({"source_session_date":"2026-10-09","status":"COMPLETE","complete":True,"records":rows}).encode()
    p = json.loads(raw)
    import hashlib
    h = {
        "status":"COMPLETE", "complete":True,
        "source_session_date":"2026-10-09", "prefilter_sha256":hashlib.sha256(raw).hexdigest(),
        "prefilter_count":len(rows), "signal_count":len(signals),
        "history_requested":len(rows),
    }
    s = {
        "status":"COMPLETE","complete":True, "source_session_date":"2026-10-09",
        "signals":[{
            "affected_assets":symbol,
            "source":{"last_date":"2026-10-09","discovery_state":state}
        } for symbol,state in signals]
    }
    return h,p,s,raw


class HistoryTests(unittest.TestCase):
    def test_complete_label_cannot_hide_stale_symbols(self):
        h,p,s,raw=packet([rec("T",-10,-8)], [("T","RAW_ANOMALY")])
        self.assertEqual(m.verify(h,p,s,raw), [])
        p["records"][0]["last_date"]="2026-10-08"
        self.assertIn("PREFILTER_SYMBOL_SESSION_STALE", m.verify(h,p,s,raw))
        p["records"][0]["last_date"]="2026-10-09"
        s["signals"][0]["source"]["last_date"]="2026-10-08"
        self.assertIn("SIGNAL_SYMBOL_SESSION_STALE", m.verify(h,p,s,raw))

    def test_sha_session_and_count_fail_closed(self):
        h,p,s,raw=packet([rec("T",-10,-8)], [("T","RAW_ANOMALY")])
        self.assertIn("PREFILTER_SHA_MISMATCH", m.verify(h,p,s,raw+b" "))
        h["signal_count"]=2
        self.assertIn("PACKET_COUNT_MISMATCH", m.verify(h,p,s,raw))
        s["source_session_date"]="2026-10-08"
        self.assertIn("SESSION_MISMATCH", m.verify(h,p,s,raw))

    def test_protected_recall_does_not_drop_shock_or_early(self):
        rows = (
            [rec(f"S{i}",-8-i/100,-16,3) for i in range(16)]
            + [rec(f"E{i}",4,2,3) for i in range(16)]
            + [rec(f"R{i}",1,-3,1,sector=-11) for i in range(48)]
            + [rec(f"P{i}",10+i/10,18+i/10,1.5) for i in range(50)]
        )
        signals = (
            [(f"S{i}","RAW_ANOMALY") for i in range(16)]
            + [(f"E{i}","EARLY_WATCH") for i in range(16)]
            + [(f"R{i}","RAW_ANOMALY") for i in range(48)]
        )
        h,p,s,raw=packet(rows,signals)
        result=m.assess(h,p,s,"a"*40)
        self.assertEqual(result["emitted"]["baseline"]["1D_SHOCK"],16)
        self.assertEqual(result["emitted"]["protected_shock_early"]["1D_SHOCK"],16)
        self.assertEqual(result["protected_preserved_early"],16)
        self.assertGreater(result["emitted"]["protected_shock_early"]["1D_PUMP"],0)
        self.assertLessEqual(result["protected_n"],80)

    def test_next_session_reaction_keeps_missing_symbols_explicit(self):
        selected = [{"symbol": "PUMP"}, {"symbol": "MISSING"}]
        future = {
            "PUMP": rec("PUMP", r1=5.25, r5=16.0),
        }
        result = m.forward_reaction(selected, future, "2026-10-09")
        self.assertEqual(result["selected"], 2)
        self.assertEqual(result["observed"], 1)
        self.assertEqual(result["coverage"], 0.5)
        self.assertEqual(result["median_adj_return_pct"], 5.25)
        self.assertEqual(result["marked"][1]["status"], "MISSING_NEXT_SESSION_PREFILTER")
        self.assertTrue(all(x["not_executable_return"] for x in result["marked"]))

    def test_unverified_corporate_action_never_receives_forward_label(self):
        result = m.forward_reaction(
            [{"symbol": "SPLT"}],
            {"SPLT": rec("SPLT", r1=45, corporate_action_unverified=True)},
            "2026-10-09",
        )
        self.assertEqual(result["observed"], 0)
        self.assertIsNone(result["mean_adj_return_pct"])
        self.assertEqual(result["marked"][0]["status"], "CORPORATE_ACTION_NOT_RELIABLY_COMPARABLE")

    def test_calendar_adjacency_conservative_on_missing_sessions(self):
        self.assertTrue(m.adjacent_regular_session_proxy("2026-10-08", "2026-10-09"))
        self.assertTrue(m.adjacent_regular_session_proxy("2026-10-09", "2026-10-12"))
        self.assertFalse(m.adjacent_regular_session_proxy("2026-10-08", "2026-10-12"))
        self.assertFalse(m.adjacent_regular_session_proxy("2026-10-09", "2026-10-13"))

    def test_corporate_action_raw_pump_is_not_a_new_trigger(self):
        r=rec("SPLIT",45,50,10,corporate_action_unverified=True)
        self.assertEqual(m.triggers(r),[])
        self.assertIsNone(m.group(r,[]))

    def test_directional_reversal_group_is_single(self):
        r=rec("REV",9,-18,2)
        self.assertEqual(m.group(r,m.triggers(r)),"PUMP")
        r=rec("REV",-10,20,2)
        self.assertEqual(m.group(r,m.triggers(r)),"SHOCK")


if __name__=="__main__":
    unittest.main()
