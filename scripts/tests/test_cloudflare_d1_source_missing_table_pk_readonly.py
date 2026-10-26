#!/usr/bin/env python3
"""Synthetic-only validation of strict source metadata scan; no Cloudflare."""
import unittest
import cloudflare_d1_source_missing_table_pk_readonly as m

DBS = list(m.EXPECTED) + [
    "clm-copilot-v1", "louis-task-context", "personal-library",
    "runner3-opportunity-radar", "runner3-rss", "volamidle-rogue-data",
    "clm-copilot-calibration",
]

def fake(token, database=None, sql=None):
    assert token == "dummy-source-audit-token-123456"
    if database is None:
        assert sql is None
        return {"success":True,"result":[
            {"name":name,"uuid":f"00000000-0000-0000-0000-{i:012d}"}
            for i,name in enumerate(DBS,1)
        ],"result_info":{"page":1,"count":9,"total_count":9}}
    assert database in {
        f"00000000-0000-0000-0000-{i:012d}" for i in (1,2)
    }
    assert sql.startswith('PRAGMA table_xinfo("')
    assert sql.endswith('")')
    table=sql.split('"')[1]
    assert table in {t for group in m.EXPECTED.values() for t in group}
    pk=0 if table in ("events","link_interest_events") else 1
    return {"success":True,"result":[{
        "success":True,"meta":{"rows_written":0,"changed_db":False},
        "results":[{"name":"id","pk":pk},{"name":"value","pk":0}]
    }]}

class TestSchemaOnlyPK(unittest.TestCase):
    def test_fixed_fifteen_and_no_rows(self):
        obj=m.inspect("dummy-source-audit-token-123456",fake)
        self.assertEqual(obj["tables_scanned"],15)
        self.assertEqual(obj["tables_with_declared_pk"],13)
        self.assertEqual(len(obj["tables_without_declared_pk"]),2)
        self.assertEqual(obj["d1_writes"],0)
        self.assertEqual(obj["row_reads"],0)
        self.assertEqual(obj["r2_requests"],0)
        self.assertEqual(obj["target_requests"],0)
        self.assertFalse(obj["cutover_ready"])
        self.assertNotIn("CREATE TABLE",str(obj))
        self.assertNotIn("00000000-0000",str(obj))
        self.assertNotIn("dummy-source-audit",str(obj))
        self.assertNotIn('"value"',str(obj))

    def test_missing_token(self):
        with self.assertRaises(m.Hold):
            m.inspect("",fake)

    def test_unallowlisted_table(self):
        with self.assertRaises(m.Hold):
            m.pragma("not_in_allowlist")

    def test_truncated_inventory(self):
        def broken(t,db,sql):
            out=fake(t,db,sql)
            if db is None:
                out["result_info"]["total_count"]=10
            return out
        with self.assertRaises(m.Hold):
            m.inspect("dummy-source-audit-token-123456",broken)

    def test_nonzero_write_metadata_aborts(self):
        def modified(t,db,sql):
            out=fake(t,db,sql)
            if db is not None:
                out["result"][0]["meta"]["rows_written"]=1
            return out
        with self.assertRaises(m.Hold):
            m.inspect("dummy-source-audit-token-123456",modified)

    def test_duplicate_primary_key_ordinal_aborts(self):
        def broken(t,db,sql):
            out=fake(t,db,sql)
            if db is not None:
                out["result"][0]["results"][1]["pk"]=1
            return out
        with self.assertRaises(m.Hold):
            m.inspect("dummy-source-audit-token-123456",broken)

if __name__ == "__main__":
    unittest.main()
