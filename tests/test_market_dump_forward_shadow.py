import importlib.util
import unittest
from datetime import date,timedelta
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location("dump_shadow",ROOT/"scripts"/"opportunity_radar_dump_forward_shadow.py")
module=importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
SESS=[]
d=date(2026,10,9)
while len(SESS)<35:
    if d.weekday()<5: SESS.append(d.isoformat())
    d+=timedelta(days=1)

def payload(day,price=100,opening=100,ret=0,ver=True):
    record={"symbol":"A","last_date":day,"open":opening,"price":price,
            "adjusted_open":opening,"adjusted_price":price,
            "ret_1d_pct":ret,"adjustment_verified":ver,
            "corporate_action_suspected":False,"corporate_action_unverified":False}
    return ({"source_session_date":day,"status":"COMPLETE","complete":True,
             "prefilter_count":1,"prefilter_sha256":"sha","fresh_history_coverage":1.0},
            {"source_session_date":day,"complete":True,"records":[record]})

def raw(baseline=False,seen="2026-10-13T08:00:00+00:00"):
    return {"schema":module.RAW_SCHEMA,"event_id":"2026-10-12|A|1D_SHOCK",
            "source_session_date":"2026-10-12","symbol":"A","predicate":"1D_SHOCK",
            "state":"RAW_MOVE_ONLY_NOT_TRADE","adjusted_return_1d_pct_first_seen":-10,
            "volume_ratio_first_seen":1.2,"event_first_logged_at_utc":seen,
            "baseline_emitted":baseline,"source_prefilter_sha256":"sha"}

class ForwardShadowTests(unittest.TestCase):
    def seed(self,baseline=False,seen="2026-10-13T08:00:00+00:00",captured="2026-10-13T08:30:00+00:00"):
        h,p=payload("2026-10-12")
        return module.run(h,p,[raw(baseline,seen)],[],SESS,captured)[0]

    def test_detection_immutable_only_no_backdated_entry(self):
        rows=self.seed()
        self.assertEqual([r["kind"] for r in rows],["DETECTION"])
        self.assertEqual(rows[0]["group"],"C_MISSED_DUMP")

    def test_next_session_open_and_one_day_outcome(self):
        journal=self.seed()
        h,p=payload("2026-10-13",price=92,opening=90)
        added,_=module.run(h,p,[],journal,SESS,"2026-10-14T08:00:00+00:00")
        self.assertEqual([r["kind"] for r in added],["ENTRY","OUTCOME_1D"])
        self.assertAlmostEqual(added[1]["net_50bps_pct"],(92/90-1)*100-.5)

    def test_promotion_unchanged_and_idempotent(self):
        rows=self.seed(baseline=True)
        self.assertEqual(rows[0]["group"],"A_BASELINE_DUMP")
        h,p=payload("2026-10-12")
        new,meta=module.run(h,p,[raw(baseline=True)],rows,SESS,"2026-10-13T08:35:00+00:00")
        self.assertEqual(new,[])
        self.assertFalse(meta["promotion_eligible"])
        self.assertFalse(meta["buy_signal_generated"])

    def test_late_first_seen_is_not_backdated(self):
        journal=self.seed(seen="2026-10-13T14:00:00+00:00",captured="2026-10-13T15:00:00+00:00")
        h,p=payload("2026-10-13")
        added,_=module.run(h,p,[],journal,SESS,"2026-10-14T08:00:00+00:00")
        self.assertEqual([r["kind"] for r in added],["BLOCK"])

    def test_missing_corporate_action_adjustment_quarantines(self):
        journal=self.seed()
        h,p=payload("2026-10-13")
        added,_=module.run(h,p,[],journal,SESS,"2026-10-14T08:00:00+00:00")
        journal+=added
        h,p=payload("2026-10-14",ver=False)
        added,_=module.run(h,p,[],journal,SESS,"2026-10-15T08:00:00+00:00")
        self.assertEqual([r["kind"] for r in added],["BLOCK"])

    def test_consecutive_marks_five_day(self):
        rows=self.seed()
        for d in SESS[2:7]:
            h,v=payload(d,ret=1)
            added,_=module.run(h,v,[],rows,SESS,d+"T23:00:00+00:00")
            rows+=added
        val=[x for x in rows if x["kind"]=="OUTCOME_5D"]
        self.assertEqual(len(val),1)
        self.assertAlmostEqual(val[0]["net_50bps_pct"],(1.01**4-1)*100-.5)
