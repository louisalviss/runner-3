"""Synthetic only: event semantic multiset count, IDs local, no data output."""
import copy
import unittest
import cloudflare_d1_event_semantic_multiset_readonly as m

SOURCE_TOKEN="dummy-audit-source-event-1234"
TARGET_TOKEN="dummy-audit-target-event-5678"
def event(id,item,kind="selected",render="r1",when="2026-10-29T00:00:00Z"):
    return {"id":id,"item_id":item,"render_id":render,
            "event_type":kind,"assistant_recommended":0,
            "assistant_rank":None,"explicit_feedback":None,
            "context_json":None,"event_at":when}

SOURCE_ROWS=[event(1,"item-A"),event(2,"item-A"),
             event(5,"item-B","liked"),event(6,"item-C")]
TARGET_ROWS=[event(101,"item-A"),event(102,"item-A"),
             event(104,"item-D")]
def reader(token,account,db,cursor):
    assert (token,account,db) in (
        (SOURCE_TOKEN,m.SOURCE,m.SOURCE_D1),
        (TARGET_TOKEN,m.TARGET,m.TARGET_D1))
    rows=SOURCE_ROWS if account==m.SOURCE else TARGET_ROWS
    return copy.deepcopy([r for r in rows if r["id"]>cursor][:m.PAGE])

class TestSemanticEvents(unittest.TestCase):
    def test_multiset_preserves_duplicates_not_ids(self):
        result=m.compare(SOURCE_TOKEN,TARGET_TOKEN,reader)
        self.assertEqual(result["source_events_observed"],4)
        self.assertEqual(result["target_events_observed"],3)
        self.assertEqual(result["semantically_matching_event_occurrences"],2)
        self.assertEqual(result["source_only_event_occurrences"],2)
        self.assertEqual(result["target_only_event_occurrences_preserve"],1)
        self.assertEqual(result["duplicate_semantic_occurrences_source"],1)
        self.assertEqual(result["duplicate_semantic_occurrences_target"],1)
        self.assertFalse(result["event_id_joined_across_accounts"])
        self.assertFalse(result["safe_event_replay_approved"])
        self.assertFalse(result["cutover_ready"])
        self.assertEqual(result["d1_writes"],0)
        self.assertNotIn("item-A",str(result))
        self.assertNotIn("dummy-audit",str(result))

    def test_ids_do_not_define_semantic_match(self):
        row=event(1,"item-A")
        other=event(99,"item-A")
        key=b"x"*32
        self.assertEqual(m.event_hmac(row,key),m.event_hmac(other,key))
        different=event(1,"item-B")
        self.assertNotEqual(m.event_hmac(row,key),m.event_hmac(different,key))

    def test_semantic_fields_include_context_and_event_time(self):
        original=event(5,"item-A")
        another=event(5,"item-A",when="2026-10-29T02:30:00Z")
        modified=dict(original);modified["context_json"]='{"a":2}'
        key=b"x"*32
        self.assertNotEqual(m.event_hmac(original,key),
                            m.event_hmac(another,key))
        self.assertNotEqual(m.event_hmac(original,key),
                            m.event_hmac(modified,key))

    def test_bad_token_and_account_rejected(self):
        with self.assertRaises(m.Hold):
            m.compare(SOURCE_TOKEN,SOURCE_TOKEN,reader)
        with self.assertRaises(m.Hold):
            m.remote(SOURCE_TOKEN,m.TARGET,m.SOURCE_D1,0)

    def test_duplicate_and_unordered_autoids_fail(self):
        def duplicate(token,account,db,cursor):
            return [event(3,"a"),event(2,"b")]
        with self.assertRaisesRegex(m.Hold,"EVENT_PK_NOT_ORDERED"):
            m.capture(SOURCE_TOKEN,m.SOURCE,m.SOURCE_D1,b"k"*32,duplicate)

    def test_detects_live_source_event_change(self):
        seq=[0]
        def changing(token,account,db,cursor):
            out=reader(token,account,db,cursor)
            if account==m.SOURCE:
                seq[0]+=1
                if seq[0]>1:
                    out[0]["event_at"]="2026-10-30"
            return out
        with self.assertRaisesRegex(m.Hold,"SNAPSHOTS_UNSTABLE"):
            m.compare(SOURCE_TOKEN,TARGET_TOKEN,changing)

    def test_overcap_and_bad_payload_rejected(self):
        def too_many(token,account,db,cursor):
            return [event(i,"item") for i in range(m.PAGE+1)]
        with self.assertRaisesRegex(m.Hold,"EVENT_PAGE_ROWS_LIMIT"):
            m.capture(SOURCE_TOKEN,m.SOURCE,m.SOURCE_D1,b"k"*32,too_many)
        with self.assertRaises(m.Hold):
            m.event_hmac({"id":1},b"k"*32)
        with self.assertRaises(m.Hold):
            m.typed({"unsafe":"dict"})
        with self.assertRaises(m.Hold):
            m.typed(float("nan"))

if __name__=="__main__":
    unittest.main()
