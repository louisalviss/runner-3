#!/usr/bin/env python3
"""Synthetic-only bounded table existence audit (no production API)."""
import unittest
import cloudflare_d1_15_source_table_nonempty_readonly as m

DB_NAMES=["runner3-core","runner3-content-intelligence"] + [f"other-{i}" for i in range(7)]
IDS={name:f"00000000-0000-0000-0000-{i:012d}" for i,name in enumerate(DB_NAMES,1)}
CALLS=[]

def fake(token,path,payload=None):
    CALLS.append((path,payload))
    assert token=="source-audit-dummy-token-long"
    if payload is None:
        return {"success":True,
                "result":[{"name":k,"uuid":v} for k,v in IDS.items()],
                "result_info":{"page":1,"count":9,"total_count":9}}
    assert set(payload)=={"sql"} and payload["sql"].startswith("SELECT 1 AS present")
    assert path in {"/d1/database/"+s+"/query" for s in IDS.values()}
    table=payload["sql"].split('"')[1]
    assert table in {v for tables in m.EXPECTED.values() for v in tables}
    present=table in {"checkpoints","events","typed_kv"}
    return {"success":True,
            "result":[{"success":True,"meta":{
                "rows_written":0,"changed_db":False,"rows_read":int(present)},
                "results":[{"present":1}] if present else []}]}

class TestBoundedNonempty(unittest.TestCase):
    def setUp(self): CALLS.clear()
    def test_fifteen_bounded_constant_queries(self):
        a=m.run("source-audit-dummy-token-long",fake)
        self.assertEqual(a["queries_executed"],15)
        self.assertEqual(a["nonempty_tables"],4)
        self.assertEqual(a["empty_tables"],11)
        self.assertEqual(a["source_d1_writes"],0)
        self.assertEqual(a["application_row_values_read"],0)
        self.assertFalse(a["cutover_ready"])
        self.assertEqual(len(CALLS),16)
        self.assertTrue(all("LIMIT 1" in c[1]["sql"] for c in CALLS[1:]))
        self.assertNotIn("SELECT *",str(CALLS))
        self.assertNotIn("DELETE FROM",str(CALLS))
        self.assertNotIn("source-audit-dummy",str(a))

    def test_token_must_exist(self):
        with self.assertRaises(m.Hold):
            m.run("",fake)
        self.assertEqual(CALLS,[])

    def test_reject_other_table(self):
        with self.assertRaises(m.Hold):
            m.table_sql("unapproved")

    def test_bad_pagination(self):
        def truncated(t,p,v=None):
            d=fake(t,p,v)
            if v is None:d["result_info"]["total_count"]=10
            return d
        with self.assertRaises(m.Hold):
            m.run("source-audit-dummy-token-long",truncated)

    def test_reject_result_with_row_payload(self):
        def bad(t,p,v=None):
            d=fake(t,p,v)
            if v is not None:d["result"][0]["results"]=[{"present":1,"leaked_data":"bad"}]
            return d
        with self.assertRaises(m.Hold):
            m.run("source-audit-dummy-token-long",bad)

    def test_reject_nonzero_write_metadata(self):
        def bad(t,p,v=None):
            d=fake(t,p,v)
            if v is not None:d["result"][0]["meta"]["rows_written"]=1
            return d
        with self.assertRaises(m.Hold):
            m.run("source-audit-dummy-token-long",bad)

    def test_high_row_cost_holds(self):
        def bad(t,p,v=None):
            d=fake(t,p,v)
            if v is not None:d["result"][0]["meta"]["rows_read"]=10000
            return d
        with self.assertRaises(m.Hold):
            m.run("source-audit-dummy-token-long",bad)

if __name__=="__main__":
    unittest.main()
