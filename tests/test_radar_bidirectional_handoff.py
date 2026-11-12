import importlib.util
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location("handoff", Path(__file__).resolve().parents[1] / "scripts" / "radar_bidirectional_handoff.py")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

NOW = "2026-11-13T04:00:00+07:00"
H = {"status":"COMPLETE","complete":True,"source_session_date":"2026-11-11","prefilter_sha256":"sha1"}
def event(name, source_key):
    return {
        "primary_entity":"NVIDIA Corporation / Jensen Huang",
        "material_update_key":name,
        "source_event_time_vn":"2026-11-12T20:48:00+07:00",
        "last_verified_source_url":"https://www.sec.gov/Archives/edgar/example",
        "delivery_status":"pending_actual_delivery",
        "label":source_key,
    }

class HandoffTest(unittest.TestCase):
    def test_separate_phases_and_pending_delivery(self):
        rows=mod.eligible_global_events({"entries":{"investigation":event("BOARD_PROBE","probe"),"departure":event("CEO_DEPARTURE","departure")}},as_of=NOW)
        self.assertEqual(len(rows),2)
        self.assertEqual(len(set(x["event_id"] for x in rows)),2)
        self.assertEqual({x["symbol"] for x in rows},{"NVDA"})
        self.assertTrue(all(x["intake_state"]=="PENDING_ECONOMIC_REVIEW" for x in rows))
        self.assertTrue(all(x["global_notification_delivery"]=="pending_actual_delivery" for x in rows))
    def test_no_unverified_x_claim_or_no_symbol(self):
        a=event("X_RUMOR","rumor")
        a.pop("last_verified_source_url")
        b=event("RANDOM","general")
        b["primary_entity"]="Some tech company unrelated"
        self.assertEqual(mod.eligible_global_events({"entries":{"a":a,"b":b}},as_of=NOW),[])
    def test_future_catalyst_not_mislabeled_as_price_cause(self):
        row={"symbol":"NVDA","source_session_date":"2026-11-11","event_id":"2026-11-11|NVDA|1D_SHOCK",
             "predicate":"1D_SHOCK","adjusted_return_1d_pct_first_seen":-8,
             "source_prefilter_sha256":"sha1"}
        got=mod.reverse_price_requests([row],H)
        self.assertEqual(len(got),1)
        self.assertEqual(got[0]["causal_statement"],"NO_CAUSAL_CLAIM")
        self.assertEqual(got[0]["intake_state"],"PENDING_CAUSAL_NEWS_VERIFICATION")
    def test_packet_mismatch_suppressed(self):
        r={"symbol":"NVDA","source_session_date":"2026-11-11","event_id":"2026-11-11|NVDA|1D_SHOCK",
           "predicate":"1D_SHOCK","adjusted_return_1d_pct_first_seen":-9,"source_prefilter_sha256":"wrong"}
        self.assertEqual(mod.reverse_price_requests([r],H),[])
        with self.assertRaises(ValueError):
            mod.reverse_price_requests([r],{**H,"complete":False})
    def test_no_duplicate_intake_and_no_promotion(self):
        f=mod.eligible_global_events({"entries":{"ceo":event("CEO_DEPARTURE","departure")}},as_of=NOW)
        first,c=mod.project_checkpoint({"historical":"preserve"},f,[],observed_at_vn=NOW)
        second,d=mod.project_checkpoint(first,f,[],observed_at_vn=NOW)
        self.assertEqual(c["forward_added"],1)
        self.assertEqual(d["forward_added"],0)
        self.assertEqual(first,second)
        self.assertEqual(second["historical"],"preserve")
        self.assertEqual(next(iter(second["cross_radar_handoff"]["global_to_opportunity"].values()))["signal_state"],"NOT_AUTHORIZED")
    def test_completed_review_preserved(self):
        f=mod.eligible_global_events({"entries":{"ceo":event("CEO_DEPARTURE","departure")}},as_of=NOW)
        first,_=mod.project_checkpoint({},f,[],observed_at_vn=NOW)
        key=f[0]["event_id"]
        first["cross_radar_handoff"]["global_to_opportunity"][key]["intake_state"]="REVIEWED_NOT_READY"
        again,c=mod.project_checkpoint(first,f,[],observed_at_vn=NOW)
        self.assertEqual(c["forward_added"],0)
        self.assertEqual(again["cross_radar_handoff"]["global_to_opportunity"][key]["intake_state"],"REVIEWED_NOT_READY")

if __name__ == "__main__":
    unittest.main()
