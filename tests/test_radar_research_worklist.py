import copy
import unittest
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from radar_queue_lifecycle import bounded_research_worklist

def rec(symbol, pred, move, state="PENDING_CAUSAL_NEWS_VERIFICATION", with_source=True):
    x={"event_id":"O2G|"+symbol, "symbol":symbol, "source_session_date":"2026-11-12",
       "price_predicate":pred, "adjusted_return_pct":move,
       "intake_state":state,"signal_state":"NOT_AUTHORIZED"}
    if with_source:
        x["primary_source_triage_20261113"]={"issuer_source_url":"https://example.com/"+symbol}
    return x

class ResearchWorklistTests(unittest.TestCase):
    def test_priority_and_read_only(self):
        src={"cross_radar_handoff":{"opportunity_to_global":{
            "a":rec("A","5D_PUMP",50),"b":rec("B","1D_SHOCK",-21),
            "c":rec("C","1D_SHOCK",-30),"d":rec("D","1D_PUMP",23),
            "e":rec("E","5D_PUMP",90,with_source=False)},
            "reverse_queue_v2":{"deferred_count":126,"max_active":40,"max_new_per_day":8}}}
        before=copy.deepcopy(src)
        plan=bounded_research_worklist(src,limit=4)
        self.assertEqual([x["symbol"] for x in plan["worklist"]],["C","B","D","A"])
        self.assertEqual(plan["active_pending"],5)
        self.assertEqual(plan["source_screened_active"],4)
        self.assertEqual(plan["missing_dated_source_active"],1)
        self.assertTrue(plan["no_state_write_or_trade"])
        self.assertEqual(src,before)
        self.assertEqual(plan,bounded_research_worklist(src,limit=4))

    def test_pit_economics_is_not_rediscovered_as_missing_source(self):
        economics=rec("NMAX","1D_PUMP",31.4,with_source=False)
        economics["issuer_economic_event_review_20261115_v1"]={
            "source_verified_pit": True,
            "issuer_economic_mechanism_evaluated": True,
            "sec_exhibit_or_full_primary_text_url":"https://www.sec.gov/Archives/nmax.htm",
        }
        dated=rec("CECO","5D_PUMP",48.7,with_source=False)
        dated["pit_primary_source_stage_20261115_v1"]={
            "stage":"OFFICIAL_SEC_FILING_ACCEPTED_IN_PRICE_WINDOW__FULL_EXHIBIT_PENDING",
            "issuer_sec_acceptance_ny":"2026-11-09T07:54:41-05:00",
            "primary_url":"https://www.sec.gov/Archives/ceco.htm",
        }
        missing=rec("MOD","1D_PUMP",27.8,with_source=False)
        src={"cross_radar_handoff":{"opportunity_to_global":{
            "n":economics,"c":dated,"m":missing},
            "reverse_queue_v2":{"deferred_count":249}}}
        before=copy.deepcopy(src)
        plan=bounded_research_worklist(src)
        self.assertEqual([x["symbol"] for x in plan["worklist"]],
                         ["NMAX","CECO","MOD"])
        self.assertEqual([x["next_gate"] for x in plan["worklist"]],[
            "NORMALIZED_FCF_BEAR_UPSIDE_NET_RR_VENUE",
            "ISSUER_EXHIBIT_SEMANTICS_AND_PIT_PRICE_LINK",
            "VERIFY_DATED_PRIMARY_SOURCE"])
        self.assertEqual(plan["source_screened_active"],1)
        self.assertEqual(plan["missing_dated_source_active"],1)
        self.assertEqual(plan["active_pending"],3)
        self.assertTrue(all(not x["causality_certified"]
                            and not x["trade_authorized_by_worklist"]
                            for x in plan["worklist"]))
        self.assertEqual(src,before)

    def test_requires_real_terminal_proof(self):
        case=rec("C","1D_SHOCK",-20,state="RESEARCHED_NO_TRADE")
        src={"cross_radar_handoff":{"opportunity_to_global":{"x":case}}}
        with self.assertRaisesRegex(ValueError,"TERMINAL_RESEARCH_WITHOUT_EVIDENCE"):
            bounded_research_worklist(src)

    def test_empty_and_bad_limit(self):
        self.assertEqual(bounded_research_worklist({})["status"],"NO_ACTIVE_RESEARCH_CASES")
        with self.assertRaisesRegex(ValueError,"RESEARCH_WORKLIST_LIMIT_INVALID"):
            bounded_research_worklist({},limit=0)

    def test_saturation(self):
        src={"cross_radar_handoff":{"opportunity_to_global":{
           str(i):rec(str(i),"1D_SHOCK",-10-i) for i in range(39)},
           "reverse_queue_v2":{"max_active":40,"max_new_per_day":8}}}
        p=bounded_research_worklist(src)
        self.assertEqual(p["active_pending"],39)
        self.assertEqual(p["next_full_daily_intake_needs_closeouts"],7)
        self.assertTrue(p["saturates_cap_if_next_full_daily_intake"])


    def test_full_active_cap_keeps_new_verified_follow_catalyst_visible(self):
        src={"cross_radar_handoff":{
            "opportunity_to_global":{
                str(i):rec(str(i),"1D_SHOCK",-10-i,with_source=False)
                for i in range(40)},
            "reverse_queue_v2":{"latest_completed_price_session":"2026-11-19",
                                 "max_active":40, "max_new_per_day":8,
                                 "deferred_count":1,"deferred":[{
                                      "event_id":"O2G|fresh","symbol":"NEW",
                                      "source_session_date":"2026-11-19",
                                      "adjusted_return_pct":-32.0,
                                      "price_predicate":"1D_SHOCK"}]},
            "follow_catalyst_rechecks_v1":{"cases":{
                "FOLLOWRECHECK|PANW|20261118":{
                    "symbol":"PANW",
                    "research_stage":"SOURCE_MATERIALITY_VERIFIED__NUMERIC_UNDERWRITE_DUE",
                    "full_numeric_deep_underwrite_certified":False,
                    "material_catalyst":{
                       "event_date_public":"2026-11-18",
                       "primary_sec_url":"https://www.sec.gov/Archives/panw"},
                    "original_follow":{
                       "original_intake_id":"THEME|AI_CYBER",
                       "original_detected_at_vn":"2026-08-28 01:43 +07"}}}},
            "global_to_opportunity":{"G2O|fresh":{
                "verified_source":True,"symbol":"NVDA",
                "material_update_key":"new-earnings",
                "source_event_time_vn":"2026-11-19",
                "primary_source_url":"https://www.sec.gov/Archives/nvda",
                "intake_state":"PENDING_ECONOMIC_REVIEW"}}}}
        before=copy.deepcopy(src)
        p=bounded_research_worklist(src,limit=8)
        self.assertEqual(p["active_pending"],40)
        self.assertEqual(p["source_only_catalyst_due"],2)
        self.assertEqual(p["source_only_catalyst_selected"],2)
        self.assertEqual(p["worklist"][0]["symbol"],"PANW")
        self.assertEqual(p["worklist"][1]["symbol"],"NVDA")
        self.assertEqual(p["newest_deferred_price_only_watch"][0]["symbol"],"NEW")
        self.assertEqual(p["next_full_daily_intake_needs_closeouts"],8)
        self.assertTrue(all(not x["trade_authorized_by_worklist"] for x in p["worklist"]))
        self.assertTrue(all(not x["candidate_write_authorized"]
                            for x in p["worklist"][:2]))
        self.assertEqual(src,before)
        self.assertEqual(p,bounded_research_worklist(src,limit=8))

    def test_source_date_future_malformed_and_screens_are_not_promoted(self):
        src={"cross_radar_handoff":{
            "reverse_queue_v2":{"latest_completed_price_session":"2026-11-19"},
            "global_to_opportunity":{
                "G2O|future":{"verified_source":True,"symbol":"AAA",
                    "source_event_time_vn":"2026-11-20",
                    "material_update_key":"f","primary_source_url":"https://issuer.example/a"},
                "G2O|unverified":{"verified_source":False,"symbol":"BBB",
                    "source_event_time_vn":"2026-11-18",
                    "material_update_key":"u","primary_source_url":"https://issuer.example/b"},
                "G2O|watch":{"verified_source":True,"symbol":"CCC",
                    "source_event_time_vn":"2026-11-18",
                    "material_update_key":"w","primary_source_url":"https://issuer.example/c",
                    "intake_state":"SCREENED_INCIDENT_WATCH_NO_TRADE"}}}}
        p=bounded_research_worklist(src)
        self.assertEqual(p["source_only_catalyst_due"],0)
        self.assertEqual(p["worklist"],[])


if __name__ == "__main__":
    unittest.main()
