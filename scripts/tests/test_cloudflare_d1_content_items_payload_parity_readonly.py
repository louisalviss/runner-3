"""Synthetic tests for fixed cursor-paged, ephemeral-HMAC payload comparison."""
import copy
import unittest
import cloudflare_d1_content_items_payload_parity_readonly as m

SOURCE_TOKEN="dummy-source-audit-123456"
TARGET_TOKEN="dummy-target-audit-987654"
CALLS=[]
def row(item,weight="A",title="original"):
    fields={c:None for c in m.COLUMNS}
    fields.update({
        "item_id":item,
        "canonical_url":"https://example.test/"+item,
        "source_type":"rss",
        "source_name":"source",
        "title":title,
        "content_hash":weight,
        "last_seen_at":"2026-10-29T01:00:00Z",
    })
    return fields

SOURCE_ROWS=[row("A"),row("B"),row("C",title="source-only")]
TARGET_ROWS=[row("A"),row("B",title="older"),row("D",title="target-only")]
def counts():
    return {"database":"runner3-content-intelligence",
            "production_writes":0,"cutover_ready":False,
            "tables":{"content_items":{
                "schema_columns_and_pk_equal":True,
                "source_at_cap":False,"target_at_cap":False,
                "source_count":3,"target_count":3}}}
def pk():
    return {"status":"CONTENT_ITEMS_PK_PRESENCE_SNAPSHOT_ONLY_HOLD",
            "payload_fingerprints_compared":False,"d1_write_requests":0,
            "source_keys":3,"target_keys":3,
            "shared_keys":2,"source_only_keys":1,
            "target_only_keys_preserve":1}
def reader(token,account,database,cursor):
    CALLS.append((account,cursor))
    assert (token,account,database) in (
        (SOURCE_TOKEN,m.SOURCE,m.SOURCE_D1),
        (TARGET_TOKEN,m.TARGET,m.TARGET_D1))
    data=SOURCE_ROWS if account==m.SOURCE else TARGET_ROWS
    return copy.deepcopy([r for r in data if r["item_id"]>cursor][:m.PAGE_SIZE])

class TestContentItemPayload(unittest.TestCase):
    def setUp(self):CALLS.clear()
    def test_shared_payload_and_target_only_preservation(self):
        r=m.analyze(SOURCE_TOKEN,TARGET_TOKEN,counts(),pk(),reader)
        self.assertEqual(r["common_pk_count"],2)
        self.assertEqual(r["common_pk_payload_matches"],1)
        self.assertEqual(r["common_pk_payload_mismatches"],1)
        self.assertEqual(r["source_only_keys"],1)
        self.assertEqual(r["target_only_keys_preserve"],1)
        self.assertEqual(r["common_pk_column_difference_counts"]["title"],1)
        self.assertEqual(r["common_pk_column_difference_counts"]["content_hash"],0)
        self.assertEqual(r["d1_write_requests"],0)
        self.assertFalse(r["cutover_ready"])
        self.assertFalse(r["atomic_cross_account_snapshot"])
        self.assertFalse(r["source_data_values_or_keys_exported"])
        self.assertNotIn("older",str(r))
        self.assertNotIn("example.test",str(r))

    def test_mismatched_preflight_counts_stop(self):
        c=counts();c["tables"]["content_items"]["source_count"]=4
        with self.assertRaisesRegex(m.Hold,"COUNT_RECEIPT_STALE"):
            m.analyze(SOURCE_TOKEN,TARGET_TOKEN,c,pk(),reader)

    def test_mismatched_key_receipt_stops(self):
        p=pk();p["shared_keys"]=3
        with self.assertRaisesRegex(m.Hold,"PK_CENSUS_CHANGED"):
            m.analyze(SOURCE_TOKEN,TARGET_TOKEN,counts(),p,reader)

    def test_reject_token_reuse_or_unapproved_route(self):
        with self.assertRaises(m.Hold):
            m.analyze(SOURCE_TOKEN,SOURCE_TOKEN,counts(),pk(),reader)
        with self.assertRaises(m.Hold):
            m.remote(SOURCE_TOKEN,m.TARGET,m.SOURCE_D1,"")

    def test_reject_invalid_or_unordered_rows(self):
        with self.assertRaises(m.Hold):
            m.digest_row({"item_id":"A"},b"k"*32)
        def unordered(t,a,d,c):
            return [row("B"),row("A")] if a==m.SOURCE else reader(t,a,d,c)
        with self.assertRaisesRegex(m.Hold,"DUPLICATE_OR_UNORDERED_PKS"):
            m.analyze(SOURCE_TOKEN,TARGET_TOKEN,counts(),pk(),unordered)

    def test_fail_closed_on_payload_stability_change(self):
        count=[0]
        def changes(t,a,d,c):
            out=reader(t,a,d,c)
            if a==m.TARGET:
                count[0]+=1
                if count[0]>1:
                    out[0]["title"]="late edit"
            return out
        with self.assertRaisesRegex(m.Hold,"SNAPSHOT_UNSTABLE"):
            m.analyze(SOURCE_TOKEN,TARGET_TOKEN,counts(),pk(),changes)

    def test_type_domain_separation_and_null_vs_empty(self):
        key=b"s"*32
        a=row("A")
        b=dict(a);b["source_key"]=""
        c=dict(a);c["source_key"]=None
        d=dict(a);d["source_key"]=42
        da=m.digest_row(a,key)
        db=m.digest_row(b,key)
        dc=m.digest_row(c,key)
        dd=m.digest_row(d,key)
        self.assertNotEqual(db[1]["row"],dc[1]["row"])
        self.assertNotEqual(dc[1]["row"],dd[1]["row"])
        self.assertEqual(da[0],db[0])
        with self.assertRaises(m.Hold):m.encode({"object":"unsafe"})
        with self.assertRaises(m.Hold):m.encode(float("nan"))

    def test_cursor_page_limit_and_max_key_budget(self):
        def too_many(t,a,d,c):
            return [row(str(i).zfill(5)) for i in range(m.PAGE_SIZE+1)]
        with self.assertRaisesRegex(m.Hold,"PAGE_RESULT_EXCEEDED"):
            m.capture(SOURCE_TOKEN,m.SOURCE,m.SOURCE_D1,b"k"*32,too_many)
        self.assertEqual(m.MAX_KEYS,5000)
        self.assertEqual(m.PAGE_SIZE,100)
        self.assertEqual(m.MAX_PAGES,51)
        self.assertIn("WHERE",m.QUERY)
        self.assertIn("LIMIT 100",m.QUERY)

if __name__=="__main__":
    unittest.main()
