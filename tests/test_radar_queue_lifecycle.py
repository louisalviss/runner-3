import copy
import unittest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from radar_queue_lifecycle import bounded_reverse_projection_v2

S12 = "2026-11-12"
S13 = "2026-11-13"
NOW = "2026-11-13T05:10:00+07:00"
TOMORROW = "2026-11-14T05:10:00+07:00"


def packet(session=S12, symbols=None):
    symbols = symbols or [f"X{i:02d}" for i in range(20)]
    h = {"status": "COMPLETE", "complete": True,
         "source_session_date": session,
         "expected_latest_completed_us_session": session,
         "prefilter_sha256": "sha"}
    p = {"source_session_date": session,
         "records": [
             {"symbol": sym, "last_date": session,
              "adjustment_verified": True,
              "corporate_action_unverified": False,
              "corporate_action_suspected": False}
             for sym in symbols]}
    raw = [
        {"event_id": f"{session}|{sym}|1D_SHOCK", "symbol": sym,
         "predicate": "1D_SHOCK", "source_session_date": session,
         "source_prefilter_sha256": "sha",
         "adjusted_return_1d_pct_first_seen": -60+i}
        for i, sym in enumerate(symbols)]
    return h,p,raw


def close(row, state, when=NOW):
    row["intake_state"] = state
    row["research_closeout_v2"] = {
        "decision": state,
        "reviewed_at_vn": when,
        "reason": "Economic price-only event is not an approved entry signal.",
        "evidence_source_urls": ["https://www.sec.gov/Archives/edgar/data/1/example"],
        "reopen_condition": "Independent newly dated material economic evidence",
        "new_buy_short": False, "signal_state": "NOT_AUTHORIZED",
    }


class QueueLifecycleTests(unittest.TestCase):
    def test_initial_eight_and_frontier_and_replay(self):
        src=packet()
        obj,stats=bounded_reverse_projection_v2({},*src,"a"*40,NOW)
        self.assertEqual(stats["reverse_added"],8)
        self.assertEqual(stats["deferred_count"],12)
        self.assertEqual(stats["active_pending"],8)
        self.assertEqual(stats["daily_used"],8)
        sec,again=bounded_reverse_projection_v2(obj,*src,"a"*40,NOW)
        self.assertIs(sec,obj)
        self.assertEqual(again["reverse_added"],0)
        self.assertFalse(again["changed"])

    def test_evidence_closeout_frees_slots_but_not_same_day_budget(self):
        obj,_=bounded_reverse_projection_v2({},*packet(),"a"*40,NOW)
        rows=obj["cross_radar_handoff"]["opportunity_to_global"]
        first=list(rows)[:6]
        for k in first:close(rows[k],"RESEARCHED_NO_TRADE")
        p,s=bounded_reverse_projection_v2(obj,*packet(),"a"*40,NOW)
        self.assertEqual(s["reverse_added"],0)
        self.assertEqual(s["active_pending"],2)
        self.assertEqual(s["terminal_count"],6)
        next_day,s2=bounded_reverse_projection_v2(p,*packet(),"a"*40,TOMORROW)
        self.assertEqual(s2["reverse_added"],8)
        self.assertEqual(s2["daily_used"],8)
        self.assertEqual(s2["active_pending"],10)
        self.assertEqual(s2["deferred_count"],4)

    def test_terminal_status_requires_research_proof(self):
        obj,_=bounded_reverse_projection_v2({},*packet(),"a"*40,NOW)
        row=next(iter(obj["cross_radar_handoff"]["opportunity_to_global"].values()))
        row["intake_state"]="RESEARCHED_NO_TRADE"
        with self.assertRaisesRegex(ValueError,"TERMINAL_RESEARCH_WITHOUT_EVIDENCE"):
            bounded_reverse_projection_v2(obj,*packet(),"a"*40,TOMORROW)

    def test_prior_backlog_survives_new_market_session(self):
        obj,_=bounded_reverse_projection_v2({},*packet(),"a"*40,NOW)
        extra=packet(S13,["NEW0","NEW1","NEW2","NEW3","NEW4","NEW5"])
        out,s=bounded_reverse_projection_v2(obj,*extra,"b"*40,TOMORROW)
        self.assertEqual(s["reverse_added"],8)
        n=out["cross_radar_handoff"]["opportunity_to_global"]
        old=sum(x["source_session_date"]==S12 for x in n.values())
        self.assertGreaterEqual(old,12)
        self.assertEqual(s["deferred_count"],10)
        self.assertEqual(out["cross_radar_handoff"]["reverse_price_session_acceptance_v1"]["session"],S13)

    def test_same_symbol_requires_distinct_verified_global_material_event(self):
        obj,_=bounded_reverse_projection_v2({},*packet(S12,["OLD"]),"a"*40,NOW)
        fresh=packet(S13,["OLD"])
        without,st=bounded_reverse_projection_v2(obj,*fresh,"b"*40,TOMORROW)
        self.assertEqual(st["reverse_added"],0)
        g={
         "event_id":"G2O|distinct-event-2026-11-13",
         "symbol":"OLD",
         "material_update_key":"new-verified-issuer-20261113",
         "verified_source":True,
         "primary_source_url":"https://www.sec.gov/new_issuer_event",
         "source_event_time_vn":"2026-11-13T19:30:00+07:00",
        }
        without["cross_radar_handoff"]["global_to_opportunity"]={g["event_id"]:g}
        with_new,st2=bounded_reverse_projection_v2(without,*fresh,"b"*40,TOMORROW)
        self.assertEqual(st2["reverse_added"],1)
        linked=[x for x in with_new["cross_radar_handoff"]["opportunity_to_global"].values()
                if x.get("linked_global_material_update_key") == g["material_update_key"]]
        self.assertEqual(len(linked),1)
        self.assertEqual(linked[0]["causal_statement"],"NO_CAUSAL_CLAIM")
        self.assertEqual(linked[0]["signal_state"],"NOT_AUTHORIZED")
        third,st3=bounded_reverse_projection_v2(with_new,*fresh,"b"*40,TOMORROW)
        self.assertEqual(st3["reverse_added"],0)

    def test_closeout_does_not_override_causality(self):
        obj,_=bounded_reverse_projection_v2({},*packet(S12,["PAYS"]),"a"*40,NOW)
        old=next(iter(obj["cross_radar_handoff"]["opportunity_to_global"].values()))
        close(old,"WAITING_NEW_EVIDENCE")
        out,st=bounded_reverse_projection_v2(obj,*packet(S12,["PAYS"]),"a"*40,TOMORROW)
        self.assertEqual(st["active_pending"],0)
        self.assertEqual(st["terminal_count"],1)
        self.assertEqual(old["causal_statement"],"NO_CAUSAL_CLAIM")
        self.assertEqual(st["reverse_added"],0)


if __name__ == "__main__":
    unittest.main()
