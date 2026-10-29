"""Synthetic tests: key-only HMAC receipts, no live D1 calls."""
import unittest
import cloudflare_d1_content_items_key_presence_readonly as m

SOURCE="source-read-only-credential-123456"
TARGET="target-read-only-credential-987654"
SOURCE_KEYS=["A","B","C","D"]
TARGET_KEYS=["A","B","E"]

def receipt(s=4,t=3):
    return {
        "database":"runner3-content-intelligence",
        "status":"UPSTREAM_PARTIAL_COUNTS_CAPPED_HOLD_NO_EXTRA_SCAN",
        "production_writes":0,"snapshot_atomic":False,"cutover_ready":False,
        "tables":{"content_items":{
            "schema_columns_and_pk_equal":True,
            "source_at_cap":False,"target_at_cap":False,
            "source_count":s,"target_count":t,
        }}
    }

def fake(token,account,uid,sql):
    assert sql==m.SQL
    if account==m.SOURCE:
        assert uid==m.SOURCE_D1 and token==SOURCE
        return [{"item_id":k} for k in SOURCE_KEYS]
    assert account==m.TARGET and uid==m.TARGET_D1 and token==TARGET
    return [{"item_id":k} for k in TARGET_KEYS]

class TestKeyPresence(unittest.TestCase):
    def test_identity_sets_without_payloads_or_hmac_exports(self):
        r=m.assess(SOURCE,TARGET,receipt(),fake)
        self.assertEqual(r["source_keys"],4)
        self.assertEqual(r["target_keys"],3)
        self.assertEqual(r["shared_keys"],2)
        self.assertEqual(r["source_only_keys"],2)
        self.assertEqual(r["target_only_keys_preserve"],1)
        self.assertFalse(r["key_hmac_exported"])
        self.assertFalse(r["payload_fingerprints_compared"])
        self.assertFalse(r["repeat_capture_stability_proven"])
        self.assertFalse(r["atomic_snapshot"])
        self.assertFalse(r["cutover_ready"])
        self.assertEqual(r["d1_write_requests"],0)
        self.assertNotIn("source-read-only",str(r))
        self.assertNotIn('"A"',str(r))

    def test_receipt_count_drift_fails_closed(self):
        with self.assertRaisesRegex(m.Hold,"COUNT_TO_PK_READ_DRIFT"):
            m.assess(SOURCE,TARGET,receipt(s=5),fake)

    def test_no_cap_extension_or_stale_receipt(self):
        r=receipt()
        r["tables"]["content_items"]["source_at_cap"]=True
        with self.assertRaises(m.Hold):
            m.assess(SOURCE,TARGET,r,fake)
        r=receipt(s=5000)
        with self.assertRaises(m.Hold):
            m.assess(SOURCE,TARGET,r,fake)
        r=receipt()
        r["cutover_ready"]=True
        with self.assertRaises(m.Hold):
            m.assess(SOURCE,TARGET,r,fake)

    def test_unordered_or_duplicate_keys_fail(self):
        with self.assertRaisesRegex(m.Hold,"DUPLICATE_OR_UNORDERED_KEY"):
            m.digest_ids([{"item_id":"b"},{"item_id":"a"}],b"k"*32)
        with self.assertRaisesRegex(m.Hold,"DUPLICATE_OR_UNORDERED_KEY"):
            m.digest_ids([{"item_id":"a"},{"item_id":"a"}],b"k"*32)

    def test_response_must_be_key_only(self):
        with self.assertRaises(m.Hold):
            m.digest_ids([{"item_id":"A","metadata_json":"private"}],b"k"*32)
        with self.assertRaises(m.Hold):
            m.digest_ids([{"item_id":None}],b"k"*32)

    def test_row_count_boundary_rejected(self):
        rows=[{"item_id":str(i).zfill(6)} for i in range(5001)]
        with self.assertRaisesRegex(m.Hold,"KEY_CAP"):
            m.digest_ids(rows,b"k"*32)

    def test_query_scopes_and_sql_allowlist(self):
        with self.assertRaises(m.Hold):
            m.reader(SOURCE,m.SOURCE,m.TARGET_D1,m.SQL)
        with self.assertRaises(m.Hold):
            m.reader(SOURCE,m.SOURCE,m.SOURCE_D1,"DELETE FROM content_items")
        self.assertEqual(m.MAX_KEYS,5000)
        self.assertEqual(m.SQL,
            'SELECT "item_id" FROM "content_items" ORDER BY "item_id" LIMIT 5001')

    def test_independent_read_credentials_required(self):
        with self.assertRaises(m.Hold):
            m.assess(SOURCE,SOURCE,receipt(),fake)

if __name__=="__main__":
    unittest.main()
