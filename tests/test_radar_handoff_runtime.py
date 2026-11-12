import importlib.util
import base64
import hashlib
import io
import json
from unittest import mock
import sys
import unittest
from pathlib import Path

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / "scripts"))
spec = importlib.util.spec_from_file_location("radar_handoff_runtime", root / "scripts" / "radar_handoff_runtime.py")
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

NOW = "2026-11-13T05:00:00+07:00"
def source_event():
    return {
       "primary_entity": "NVIDIA Corporation / Jensen Huang",
       "material_update_key": "NOV12_2026_CEO_DEPARTURE",
       "source_event_time_vn": "2026-11-12T20:48:00+07:00",
       "last_verified_source_url": "https://www.sec.gov/Archives/example",
       "delivery_status": "pending_actual_delivery",
       "status": "notification_precommitted",
       "notified_at_vn": NOW,
    }
L = {"entries": {"NVIDIA|CEO_DEPARTURE": source_event()}}

class RuntimeAuditTest(unittest.TestCase):
    def test_live_ledger_source_uses_current_contents_api_not_raw_cdn(self):
        raw = json.dumps({"entries": {"NEW_EVENT": {"symbol": "MSFT"}}}).encode("utf-8")
        blob_sha = hashlib.sha1(
            b"blob " + str(len(raw)).encode("ascii") + bytes([0]) + raw
        ).hexdigest()
        payload = json.dumps({
            "type": "file", "encoding": "base64",
            "content": base64.b64encode(raw).decode("ascii"), "sha": blob_sha,
        }).encode("utf-8")
        with mock.patch.object(m.urllib.request, "urlopen", return_value=io.BytesIO(payload)) as op:
            ledger, digest = m.source_ledger_fetch()
        self.assertIn("api.github.com/repos/", op.call_args.args[0].full_url)
        self.assertIn("NEW_EVENT", ledger["entries"])
        self.assertEqual(digest, hashlib.sha256(raw).hexdigest())

    def test_live_ledger_source_rejects_stale_raw_payload(self):
        stale = json.dumps({"entries": {"OLD": {}}}).encode("utf-8")
        with mock.patch.object(m.urllib.request, "urlopen", return_value=io.BytesIO(stale)):
            with self.assertRaises(ValueError):
                m.source_ledger_fetch()

    def test_live_ledger_source_rejects_sha_mismatch(self):
        raw = b'{"entries":{}}'
        payload = json.dumps({
            "type": "file", "encoding": "base64",
            "content": base64.b64encode(raw).decode("ascii"), "sha": "0" * 40,
        }).encode("utf-8")
        with mock.patch.object(m.urllib.request, "urlopen", return_value=io.BytesIO(payload)):
            with self.assertRaises(ValueError):
                m.source_ledger_fetch()

    def test_no_false_delivery_and_no_trade(self):
        projection,s,a,changed = m.audit_projection(L,{},NOW,"ledger_sha")
        self.assertEqual(s["forward_added"],1)
        self.assertTrue(changed)
        self.assertEqual(a["source_events_verified"],1)
        self.assertEqual(a["actual_deliveries_receipt_confirmed"],0)
        self.assertEqual(a["end_to_end_status"],"RESEARCH_HANDOFF_PARTIAL__DELIVERY_OR_UNDERWRITE_OPEN")
        self.assertTrue(a["no_new_trades"])
    def test_resume_real_research_then_idempotent(self):
        first,_,_,_=m.audit_projection(L,{},NOW,"ledger_sha")
        key=next(iter(first["cross_radar_handoff"]["global_to_opportunity"]))
        row=first["cross_radar_handoff"]["global_to_opportunity"][key]
        row["intake_state"]="EVALUATED_UNDERWRITE_DUE"
        row["fast_catalyst_triage_at_vn"]=NOW
        second,s,a,changed=m.audit_projection(L,first,NOW,"ledger_sha")
        self.assertTrue(changed)
        self.assertEqual(s["forward_added"],0)
        self.assertEqual(a["research_triage_completed"],1)
        self.assertEqual(a["actual_deliveries_receipt_confirmed"],0)
        third,s2,a2,changed2=m.audit_projection(L,second,NOW,"ledger_sha")
        self.assertFalse(changed2)
        self.assertEqual(s2["forward_added"],0)
        self.assertEqual(a2,a)
    def test_receipt_requires_both_status_and_provider_receipt(self):
        event=source_event()
        event["delivery_status"]="actual_delivery_confirmed"
        no_receipt,_,audit,_=m.audit_projection({"entries":{"NVIDIA|CEO_DEPARTURE":event}}, {},NOW,"x")
        self.assertEqual(audit["actual_deliveries_receipt_confirmed"],0)
        event["actual_delivery_receipt_id"]="receipt-from-real-provider"
        with_receipt,_,audit2,_=m.audit_projection({"entries":{"NVIDIA|CEO_DEPARTURE":event}}, {},NOW,"x2")
        self.assertEqual(audit2["actual_deliveries_receipt_confirmed"],1)
        self.assertNotEqual(audit2["end_to_end_status"],"FULL_PASS")
    def test_no_reverse_backlog_duplication(self):
        src,_,_,_=m.audit_projection(L,{},NOW,"ledger_sha")
        st=src["cross_radar_handoff"]
        st["opportunity_to_global"]={"old-price":{"intake_state":"PENDING_CAUSAL_NEWS_VERIFICATION","primary_source_triage_20261113":{"ok":True}}}
        result, stats, audit, changed=m.audit_projection(L,src,NOW,"ledger_sha")
        self.assertEqual(stats["reverse_added"],0)
        self.assertEqual(audit["reverse_price_requests_total"],1)
        self.assertEqual(audit["reverse_source_screened"],1)
    def test_verified_source_required(self):
        event=source_event()
        del event["last_verified_source_url"]
        _,_,audit,_=m.audit_projection({"entries":{"bad":event}}, {},NOW,"z")
        self.assertEqual(audit["source_events_verified"],0)
        self.assertEqual(audit["end_to_end_status"],"RESEARCH_HANDOFF_PARTIAL__DELIVERY_OR_UNDERWRITE_OPEN")
    def test_late_event_does_not_fake_causality(self):
        first,_,_,_=m.audit_projection(L,{},NOW,"ledger_sha")
        key=next(iter(first["cross_radar_handoff"]["global_to_opportunity"]))
        row=first["cross_radar_handoff"]["global_to_opportunity"][key]
        self.assertEqual(row["signal_state"],"NOT_AUTHORIZED")
        self.assertEqual(row["intake_state"],"PENDING_ECONOMIC_REVIEW")


    def test_reverse_price_bounded_and_replay_deduplicated(self):
        health = {"status": "COMPLETE", "complete": True, "source_session_date": "2026-11-12",
                  "expected_latest_completed_us_session": "2026-11-12", "prefilter_sha256": "sha"}
        prefilter = {"source_session_date": "2026-11-12",
                     "records": [{"symbol": s, "last_date": "2026-11-12",
                                  "adjustment_verified": True, "corporate_action_unverified": False,
                                  "corporate_action_suspected": False}
                                 for s in ("CDNL", "ADIG", "ENVX", "BW", "BZ", "CTVA",
                                           "GOGO", "LUNR", "FROG", "CTVA")]}
        from radar_bidirectional_handoff import reverse_price_requests
        moves = [{"event_id": f"2026-11-12|{s}|1D_SHOCK",
                  "source_session_date": "2026-11-12",
                  "source_prefilter_sha256": "sha", "symbol": s,
                  "predicate": "1D_SHOCK", "adjusted_return_1d_pct_first_seen": -61 + i}
                 for i, s in enumerate(("CDNL", "ADIG", "ENVX", "BW", "BZ", "CTVA",
                                         "GOGO", "LUNR", "FROG"))]
        first, st = m.bounded_reverse_projection({}, health, prefilter, moves, "ab"*20, NOW)
        self.assertEqual(st["reverse_added"], 8)
        self.assertEqual(st["capacity_skipped"], 1)
        self.assertEqual(len(first["cross_radar_handoff"]["opportunity_to_global"]), 8)
        rpt = first["cross_radar_handoff"]["reverse_price_session_acceptance_v1"]
        self.assertEqual(rpt["new_symbols"], ["CDNL", "ADIG", "ENVX", "BW", "BZ", "CTVA", "GOGO", "LUNR"])
        self.assertTrue(all(x["signal_state"] == "NOT_AUTHORIZED"
                       for x in first["cross_radar_handoff"]["opportunity_to_global"].values()))
        second, st2 = m.bounded_reverse_projection(first, health, prefilter, moves, "ab"*20, NOW)
        self.assertIs(second, first)
        self.assertEqual(st2["reverse_added"], 0)
        self.assertFalse(st2["changed"])

    def test_reverse_backpressure_and_same_symbol_research_reuse(self):
        health = {"status": "COMPLETE", "complete": True, "source_session_date": "2026-11-12",
                  "expected_latest_completed_us_session": "2026-11-12", "prefilter_sha256": "sha"}
        prefilter = {"source_session_date": "2026-11-12",
                     "records": [{"symbol": "TEST", "last_date": "2026-11-12",
                                  "adjustment_verified": True, "corporate_action_unverified": False,
                                  "corporate_action_suspected": False}]}
        moves = [{"event_id": "2026-11-12|TEST|1D_SHOCK", "symbol": "TEST",
                  "predicate": "1D_SHOCK", "source_session_date": "2026-11-12",
                  "source_prefilter_sha256": "sha", "adjusted_return_1d_pct_first_seen": -40}]
        orig = {"cross_radar_handoff":{"opportunity_to_global":{
                    f"e{i}": {"symbol": f"SYM{i}",
                             "intake_state": "PENDING_CAUSAL_NEWS_VERIFICATION"}
                    for i in range(40)}}}
        out, stats = m.bounded_reverse_projection(orig, health, prefilter, moves, "aa"*20, NOW)
        self.assertEqual(stats["reverse_added"], 0)
        self.assertEqual(stats["capacity_skipped"], 1)
        self.assertEqual(len(out["cross_radar_handoff"]["opportunity_to_global"]), 40)
        bad = dict(health, prefilter_sha256="different")
        with self.assertRaises(ValueError):
            m.bounded_reverse_projection(out, bad, prefilter, moves, "aa"*20, NOW)

    def test_reverse_rejects_suspected_corporate_action_and_stale_price(self):
        h = {"status": "COMPLETE", "complete": True,
             "source_session_date": "2026-11-12",
             "expected_latest_completed_us_session": "2026-11-12",
             "prefilter_sha256": "sha"}
        p = {"source_session_date": "2026-11-12",
             "records":[{"symbol":"A","last_date":"2026-11-12","adjustment_verified":True,
                         "corporate_action_unverified":True,"corporate_action_suspected":False}]}
        e = [{"event_id":"2026-11-12|A|1D_SHOCK","source_session_date":"2026-11-12",
              "source_prefilter_sha256":"sha","symbol":"A","predicate":"1D_SHOCK",
              "adjusted_return_1d_pct_first_seen":-30}]
        out,stats = m.bounded_reverse_projection({},h,p,e,"bb"*20,NOW)
        self.assertEqual(stats["reverse_added"],0)
        self.assertEqual(out["cross_radar_handoff"]["reverse_price_session_acceptance_v1"]
                         ["corporate_action_or_adjustment_skipped"],["A"])

if __name__ == "__main__":
    unittest.main()
