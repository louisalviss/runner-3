import importlib.util
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

if __name__ == "__main__":
    unittest.main()
