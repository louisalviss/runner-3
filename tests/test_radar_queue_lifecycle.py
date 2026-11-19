import copy
import unittest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from radar_queue_lifecycle import (bounded_reverse_projection_v2,
                                   screen_full_inventory_cheap_v1,
                                   apply_signed_research_closeouts_v1)

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

    def test_v1_migration_uses_vietnam_day_not_previous_utc_day(self):
        previous, _ = bounded_reverse_projection_v2({}, *packet(), "a"*40, NOW)
        h=previous["cross_radar_handoff"]
        h.pop("reverse_queue_v2")
        h["reverse_price_session_acceptance_v1"]["new_added"]=8
        # With local 05:10 +07 the current UTC date is still yesterday.
        # Eight original same-VN-day admissions must consume the daily budget.
        migrated,stats=bounded_reverse_projection_v2(previous,*packet(),"a"*40,NOW)
        self.assertEqual(stats["daily_used"],8)
        self.assertEqual(stats["reverse_added"],0)
        self.assertEqual(stats["deferred_count"],12)
        again,st=bounded_reverse_projection_v2(migrated,*packet(),"a"*40,NOW)
        self.assertIs(again,migrated)
        self.assertFalse(st["changed"])

    def test_closeout_does_not_override_causality(self):
        obj,_=bounded_reverse_projection_v2({},*packet(S12,["PAYS"]),"a"*40,NOW)
        old=next(iter(obj["cross_radar_handoff"]["opportunity_to_global"].values()))
        close(old,"WAITING_NEW_EVIDENCE")
        out,st=bounded_reverse_projection_v2(obj,*packet(S12,["PAYS"]),"a"*40,TOMORROW)
        self.assertEqual(st["active_pending"],0)
        self.assertEqual(st["terminal_count"],1)
        self.assertEqual(old["causal_statement"],"NO_CAUSAL_CLAIM")
        self.assertEqual(st["reverse_added"],0)


    def test_duplicate_symbol_deferred_ids_survive_new_admissions(self):
        obj, _ = bounded_reverse_projection_v2({}, *packet(), "a"*40, NOW)
        state = obj["cross_radar_handoff"]
        queue = state["reverse_queue_v2"]
        # Six prior deferred price events share symbols with reviewed cases.
        # Preserve them without authorizing new active or trades.
        for i in range(6):
            row = copy.deepcopy(queue["deferred"][i])
            row["symbol"] = f"X{i:02d}"
            row["source_session_date"] = "2026-11-11"
            row["event_id"] = f"2026-11-11|X{i:02d}|5D_SHOCK"
            row["price_event_id"] = row["event_id"]
            queue["deferred"].append(row)
        queue["deferred_count"] = 18
        def event_ids(checkpoint):
            state = checkpoint["cross_radar_handoff"]
            return (set(state["opportunity_to_global"]) |
                    {r["event_id"] for r in state["reverse_queue_v2"]["deferred"]})
        before_ids = event_ids(obj)
        self.assertEqual(len(before_ids), 26)
        projected, stats = bounded_reverse_projection_v2(
            obj, *packet(), "a"*40, TOMORROW)
        self.assertEqual(stats["reverse_added"], 8)
        self.assertEqual(stats["deferred_count"], 10)
        self.assertEqual(stats["active_pending"], 16)
        self.assertEqual(event_ids(projected), before_ids)
        remaining = {r["event_id"] for r in
                     projected["cross_radar_handoff"]["reverse_queue_v2"]["deferred"]}
        for i in range(6):
            self.assertIn(f"2026-11-11|X{i:02d}|5D_SHOCK", remaining)
        replay, replay_stats = bounded_reverse_projection_v2(
            projected, *packet(), "a"*40, TOMORROW)
        self.assertIs(replay, projected)
        self.assertFalse(replay_stats["changed"])
        self.assertEqual(event_ids(replay), before_ids)


    def test_deferred_prior_fifo_stays_stable_when_same_symbol_is_not_admissible(self):
        # A previously persisted old price identity may share a ticker with
        # an ACTIVE researched case. It must keep its original FIFO position
        # without causing an extra CAS write or drifting on same-day replay.
        source = packet()
        obj, _ = bounded_reverse_projection_v2({}, *source, "a"*40, NOW)
        q = obj["cross_radar_handoff"]["reverse_queue_v2"]
        historical = copy.deepcopy(q["deferred"][1])
        historical.update({
            "event_id": "O2G|historical-priority-preservation",
            "price_event_id": S12 + "|X00|5D_SHOCK",
            "symbol": "X00",
        })
        q["deferred"].insert(2, historical)
        q["deferred_count"] = len(q["deferred"])
        before = [r["event_id"] for r in q["deferred"]]
        projected, stats = bounded_reverse_projection_v2(
            obj, *source, "a"*40, NOW)
        after = [r["event_id"] for r in
                 projected["cross_radar_handoff"]["reverse_queue_v2"]["deferred"]]
        self.assertEqual(before, after)
        self.assertIs(projected, obj)
        self.assertFalse(stats["changed"])
        replay, replay_stats = bounded_reverse_projection_v2(
            projected, *source, "a"*40, NOW)
        self.assertIs(replay, projected)
        self.assertFalse(replay_stats["changed"])



class FullInventoryCheapScreenTests(unittest.TestCase):
    @staticmethod
    def inventory(size=507):
        # 40 active + 263 deferred + 204 signed terminal; identities never reused.
        active, deferred, terminal = 40, 263, size-303
        reviewed = {
            f"ACTIVE|{i:03d}": {"symbol": f"S{i:03d}", "event_id": f"ACTIVE|{i:03d}",
                                "source_session_date": S12,
                                "intake_state": "PENDING_CAUSAL_NEWS_VERIFICATION"}
            for i in range(active)}
        for i in range(terminal):
            rec = {"symbol": f"T{i:03d}", "event_id": f"TERM|{i:03d}",
                   "source_session_date": S12, "signal_state": "NOT_AUTHORIZED"}
            close(rec, "RESEARCHED_NO_TRADE")
            reviewed[rec["event_id"]] = rec
        wait = [{"event_id": f"DEFERRED|{i:03d}", "symbol": f"D{i:03d}",
                 "source_session_date": S12} for i in range(deferred)]
        q = {"schema": "reverse-research-queue-v2",
             "latest_completed_price_session": S13,
             "latest_prefilter_sha256": "sha",
             "active_count": active, "deferred_count": deferred,
             "terminal_case_count": terminal, "deferred": wait}
        symbols = [f"S{i:03d}" for i in range(active)] + [
            f"D{i:03d}" for i in range(deferred)] + [
            f"T{i:03d}" for i in range(terminal)]
        h = {"status": "COMPLETE", "complete": True,
             "source_session_date": S13,
             "expected_latest_completed_us_session": S13,
             "prefilter_sha256": "sha"}
        p = {"source_session_date": S13, "records": [
            {"symbol": s, "price": 10.0, "last_date": S13,
             "adjustment_verified": True,
             "corporate_action_suspected": False,
             "corporate_action_unverified": False} for s in symbols]}
        return {"cross_radar_handoff": {
            "opportunity_to_global": reviewed,
            "reverse_queue_v2": q}}, h, p

    def test_only_explicit_final_closeout_proof_releases_slots(self):
        obj, h, p = self.inventory()
        rows = obj["cross_radar_handoff"]["opportunity_to_global"]
        rec = rows["ACTIVE|000"]
        rec["signal_state"] = "NOT_AUTHORIZED"
        rec["research_closeout_v2"] = {
            "decision": "WAITING_NEW_EVIDENCE",
            "signal_state": "NOT_AUTHORIZED",
            "reviewed_at_vn": NOW,
            "reason": "Independent issuer source did not establish investable mispricing.",
            "evidence_source_urls": ["https://www.sec.gov/Archives/verified"],
            "reopen_condition": "Distinct, later verified issuer economic event",
            "new_buy_short": False}
        original = copy.deepcopy(obj)
        closed, count = apply_signed_research_closeouts_v1(obj)
        self.assertEqual(count, 1)
        self.assertEqual(original, obj)  # no in-place mutation
        self.assertEqual(closed["cross_radar_handoff"]["opportunity_to_global"]
                         ["ACTIVE|000"]["intake_state"], "WAITING_NEW_EVIDENCE")
        # Projection, not the closeout helper, recomputes queue counts.
        closed["cross_radar_handoff"]["reverse_queue_v2"]["active_count"] = 39
        closed["cross_radar_handoff"]["reverse_queue_v2"]["terminal_case_count"] = 205
        screen = screen_full_inventory_cheap_v1(closed, h, p)
        self.assertEqual((screen["terminal"], screen["active"]), (205, 39))
        self.assertEqual(apply_signed_research_closeouts_v1(closed)[1], 0)

    def test_provisional_or_invalid_proof_never_auto_closes(self):
        obj, _, _ = self.inventory()
        rows = obj["cross_radar_handoff"]["opportunity_to_global"]
        rows["ACTIVE|000"]["research_closeout_v2"] = {
            "reason": "Stale price only, no signed terminal decision"}
        self.assertEqual(apply_signed_research_closeouts_v1(obj), (obj, 0))
        rows["ACTIVE|001"]["research_closeout_v2"] = {
            "decision": "RESEARCHED_NO_TRADE",
            "reviewed_at_vn": NOW,
            "reason": "Only market price movement. No independent source proof.",
            "evidence_source_urls": [],
            "reopen_condition": "Independent issuer economic source",
            "new_buy_short": False,
            "signal_state": "NOT_AUTHORIZED"}
        with self.assertRaisesRegex(ValueError, "TERMINAL_RESEARCH_PROOF_INVALID"):
            apply_signed_research_closeouts_v1(obj)

    def test_all_507_classified_in_single_pass_and_unchanged(self):
        obj, h, p = self.inventory()
        # Exactly one source+mechanism review qualified for numeric deep work.
        row = obj["cross_radar_handoff"]["opportunity_to_global"]["ACTIVE|000"]
        row["issuer_economic_event_review_20261115_v1"] = {
            "source_verified_pit": True,
            "issuer_economic_mechanism_evaluated": True,
            "sec_primary_issuer_filing_url": "https://www.sec.gov/exact"}
        before = copy.deepcopy(obj)
        result = screen_full_inventory_cheap_v1(obj, h, p)
        self.assertEqual(result["all_immutable_event_ids"], 507)
        self.assertEqual(len(result["all_ids_stage"]), 507)
        self.assertEqual((result["active"], result["deferred"], result["terminal"]),
                         (40, 263, 204))
        self.assertEqual(result["deep_underwrite_selected_n"], 1)
        self.assertEqual(result["deep_underwrite_due_ids"], ["ACTIVE|000"])
        self.assertEqual(result["auto_terminal_added"], 0)
        self.assertEqual(result["new_buy_short_or_orders"], 0)
        self.assertEqual(obj, before)
        self.assertEqual(result, screen_full_inventory_cheap_v1(obj, h, p))

    def test_source_only_and_price_only_never_auto_close_or_enter_deep(self):
        obj, h, p = self.inventory()
        rows = obj["cross_radar_handoff"]["opportunity_to_global"]
        rows["ACTIVE|000"]["primary_source_triage_20261113"] = {
            "issuer_source_url": "https://www.sec.gov/evidence"}
        rows["ACTIVE|001"]["issuer_economic_event_review_20261115_v1"] = {
            "source_verified_pit": True,
            "issuer_economic_mechanism_evaluated": True}
        result = screen_full_inventory_cheap_v1(obj, h, p)
        self.assertEqual(result["deep_underwrite_selected_n"], 0)
        self.assertEqual(result["source_investigation_selected_n"], 8)
        self.assertEqual(result["active"], 40)
        self.assertEqual(result["all_ids_stage"]["ACTIVE|000"]["stage"],
                         "ACTIVE_CAUSAL_PIT_OR_MARK_REVIEW")
        self.assertEqual(result["all_ids_stage"]["ACTIVE|001"]["stage"],
                         "ACTIVE_INDEPENDENT_DATED_ISSUER_SOURCE_GAP")

    def test_corporate_action_or_stale_price_blocks_deep(self):
        obj, h, p = self.inventory()
        row = obj["cross_radar_handoff"]["opportunity_to_global"]["ACTIVE|000"]
        row["issuer_economic_event_review_20261115_v1"] = {
            "source_verified_pit": True,
            "issuer_economic_mechanism_evaluated": True,
            "sec_exhibit_or_full_primary_text_url": "https://www.sec.gov/evidence"}
        p["records"][0]["corporate_action_suspected"] = True
        x = screen_full_inventory_cheap_v1(obj, h, p)
        self.assertEqual(x["deep_underwrite_selected_n"], 0)
        self.assertFalse(x["all_ids_stage"]["ACTIVE|000"]["price_session_validated"])
        p["records"][0]["corporate_action_suspected"] = False
        p["records"][0]["last_date"] = S12
        self.assertEqual(screen_full_inventory_cheap_v1(obj, h, p)
                         ["deep_underwrite_selected_n"], 0)

    def test_identity_loss_duplicate_count_and_wrong_sha_fail_closed(self):
        obj, h, p = self.inventory()
        obj["cross_radar_handoff"]["reverse_queue_v2"]["deferred"][0]["event_id"] = "ACTIVE|000"
        with self.assertRaisesRegex(ValueError, "FULL_INVENTORY_DUPLICATE_ID"):
            screen_full_inventory_cheap_v1(obj, h, p)
        obj, h, p = self.inventory()
        obj["cross_radar_handoff"]["reverse_queue_v2"]["active_count"] = 39
        with self.assertRaisesRegex(ValueError, "FULL_INVENTORY_ACTIVE_TERMINAL_COUNT_MISMATCH"):
            screen_full_inventory_cheap_v1(obj, h, p)
        obj, h, p = self.inventory()
        h["prefilter_sha256"] = "unmatched"
        with self.assertRaisesRegex(ValueError, "FULL_INVENTORY_QUEUE_PACKET_SHA_MISMATCH"):
            screen_full_inventory_cheap_v1(obj, h, p)

    def test_no_source_index_needed_and_missing_quote_retained(self):
        obj, h, p = self.inventory()
        p["records"] = p["records"][:10]
        x = screen_full_inventory_cheap_v1(obj, h, p)
        self.assertEqual(x["all_immutable_event_ids"], 507)
        self.assertEqual(x["cached_sec_issuer_provenance_n"], 0)
        self.assertEqual(x["stage_counts"]["DEFERRED_PRICE_SOURCE_NOT_CURRENT"], 263)

if __name__ == "__main__":
    unittest.main()
