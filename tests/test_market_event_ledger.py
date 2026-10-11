"""Deterministic tests for append-only raw price-move registry."""
from __future__ import annotations
import importlib.util
import json
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location("move_ledger", ROOT/"scripts"/"opportunity_radar_market_event_ledger.py")
assert spec and spec.loader
m=importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

def packet():
    health={"source_session_date":"2026-10-09","status":"COMPLETE","complete":True,
            "prefilter_count":3,"prefilter_sha256":"s"*64}
    rows=[
        {"symbol":"T","source_session_date":"2026-10-09","ret_1d_pct":-9.81,
         "ret_5d_pct":-17.0,"volume_ratio":3.94,"shadow_triggers":["1D_SHOCK","5D_SHOCK"],
         "baseline_emitted":True,"baseline_explanation":"EMITTED_RAW_ANOMALY"},
        {"symbol":"FSLY","source_session_date":"2026-10-09","ret_1d_pct":15.8,
         "ret_5d_pct":19.0,"volume_ratio":1.95,"shadow_triggers":["1D_PUMP","5D_PUMP"],
         "baseline_emitted":False,"baseline_explanation":"BELOW_EARLY_VOLUME"},
        {"symbol":"QUIET","source_session_date":"2026-10-09","ret_1d_pct":0.2,
         "ret_5d_pct":1.0,"volume_ratio":0.8,"shadow_triggers":[],
         "baseline_emitted":False,"baseline_explanation":"BELOW_BASELINE_DISCOVERY_RULE"}
    ]
    shadow={"source_session_date":"2026-10-09","status":"SHADOW_AUDIT_ONLY",
            "selection_unchanged":True,"generated_at":"2026-10-11T02:01:00+07:00",
            "records":rows}
    return shadow,health

class MoveLedgerTests(unittest.TestCase):
    def test_both_pumps_and_shocks_capture_even_when_not_emitted(self):
        a,h=packet();events=m.source_events(a,h,"2026-10-11T23:00:00+00:00")
        self.assertEqual(len(events),4)
        self.assertEqual([x["event_id"] for x in events],[
            "2026-10-09|FSLY|1D_PUMP","2026-10-09|FSLY|5D_PUMP",
            "2026-10-09|T|1D_SHOCK","2026-10-09|T|5D_SHOCK"])
        self.assertEqual(events[0]["baseline_exclusion_reason"],"BELOW_EARLY_VOLUME")
        self.assertFalse(events[0]["baseline_emitted"])
        self.assertEqual(events[-1]["state"],"RAW_MOVE_ONLY_NOT_TRADE")

    def test_completed_daily_intraday_high_low_logged_without_close_signal(self):
        shadow, health = packet()
        # Quiet at the close, but intraday extremes exceeded both thresholds.
        row = shadow["records"][2]
        row.update({
            "intraday_extremes_verified": True,
            "intraday_high_vs_prior_adjusted_close_pct": 11.2,
            "intraday_low_vs_prior_adjusted_close_pct": -9.1,
            "shadow_intraday_triggers": ["INTRADAY_HIGH_PUMP", "INTRADAY_LOW_SHOCK"],
        })
        events = m.source_events(shadow, health, "2026-10-12T04:00:00Z")
        by = {e["event_id"]:e for e in events}
        self.assertEqual(len(events), 6)
        high = by["2026-10-09|QUIET|INTRADAY_HIGH_PUMP"]
        low = by["2026-10-09|QUIET|INTRADAY_LOW_SHOCK"]
        self.assertEqual(high["completed_daily_extreme_adjusted_return_pct_first_seen"], 11.2)
        self.assertEqual(low["completed_daily_extreme_adjusted_return_pct_first_seen"], -9.1)
        self.assertEqual(high["intraday_basis"], "COMPLETED_DAILY_BAR_HIGH_LOW_NOT_REALTIME")
        self.assertFalse(high["baseline_emitted"])

    def test_unverified_or_tampered_intraday_event_fails_closed(self):
        shadow, health = packet()
        row = shadow["records"][2]
        row.update({
            "intraday_extremes_verified": False,
            "intraday_high_vs_prior_adjusted_close_pct": 11.2,
            "shadow_intraday_triggers": ["INTRADAY_HIGH_PUMP"],
        })
        with self.assertRaisesRegex(ValueError, "INTRADAY_OHLC_NOT_VERIFIED"):
            m.source_events(shadow, health, "now")
        row["intraday_extremes_verified"] = True
        row["intraday_high_vs_prior_adjusted_close_pct"] = 3.0
        with self.assertRaisesRegex(ValueError, "PRICE_TRIGGER_INCONSISTENT"):
            m.source_events(shadow, health, "now")

    def test_idempotent_append_same_session_and_preserve_first_seen(self):
        a,h=packet();e=m.source_events(a,h,"2026-10-11T23:00:00+00:00")
        first,c=m.append_unseen("",e)
        self.assertEqual(c["new"],4)
        fresh,c2=m.append_unseen(first,m.source_events(a,h,"2026-10-12T23:00:00+00:00"))
        self.assertEqual(first,fresh)
        self.assertEqual(c2["new"],0)
        self.assertEqual(c2["total"],4)

    def test_new_completed_session_appends_without_overwriting_prior(self):
        a,h=packet();e=m.source_events(a,h,"2026-10-11T23:00:00+00:00")
        first,_=m.append_unseen("",e)
        h["source_session_date"]="2026-10-12"
        a["source_session_date"]="2026-10-12"
        for r in a["records"]:r["source_session_date"]="2026-10-12"
        out,stats=m.append_unseen(first,m.source_events(a,h,"2026-10-13T23:00:00+00:00"))
        self.assertEqual(stats["new"],4)
        self.assertEqual(stats["total"],8)
        self.assertTrue(out.startswith(first))
        self.assertEqual(len(out.splitlines()),8)

    def test_fail_closed_stale_or_degraded_source(self):
        a,h=packet()
        h["status"]="DEGRADED"
        with self.assertRaisesRegex(ValueError,"SOURCE_NOT_VERIFIED_COMPLETE"):
            m.source_events(a,h,"now")
        h["status"]="COMPLETE";a["records"][0]["source_session_date"]="2026-10-08"
        with self.assertRaisesRegex(ValueError,"PER_SYMBOL_SESSION_MISMATCH"):
            m.source_events(a,h,"now")

    def test_fail_closed_tampered_trigger_and_duplicate_symbol(self):
        a,h=packet()
        a["records"][1]["ret_1d_pct"]=3.0
        with self.assertRaisesRegex(ValueError,"PRICE_TRIGGER_INCONSISTENT"):
            m.source_events(a,h,"now")
        a,h=packet()
        a["records"][1]["symbol"]="T"
        with self.assertRaisesRegex(ValueError,"DUPLICATE_SOURCE_PRICE_EVENT"):
            m.source_events(a,h,"now")

    def test_old_ledger_duplicate_or_corrupt_fails_closed(self):
        a,h=packet();e=m.source_events(a,h,"now")
        line=json.dumps(e[0])+"\n"
        with self.assertRaisesRegex(ValueError,"EXISTING_EVENT_LEDGER_CORRUPT"):
            m.append_unseen(line+line,e)
        with self.assertRaisesRegex(ValueError,"EXISTING_EVENT_LEDGER_CORRUPT"):
            m.append_unseen(json.dumps({"event_id":"BAD"})+"\n",e)

if __name__=="__main__":unittest.main()
