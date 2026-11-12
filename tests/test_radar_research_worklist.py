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
        self.assertEqual([x["symbol"] for x in plan["worklist"]],["E","C","B","D"])
        self.assertEqual(plan["active_pending"],5)
        self.assertEqual(plan["source_screened_active"],4)
        self.assertEqual(plan["missing_dated_source_active"],1)
        self.assertTrue(plan["no_state_write_or_trade"])
        self.assertEqual(src,before)
        self.assertEqual(plan,bounded_research_worklist(src,limit=4))

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

if __name__ == "__main__":
    unittest.main()
