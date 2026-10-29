#!/usr/bin/env python3
"""Synthetic only: assert static bounded D1 read-only request/cost contract."""
import copy
import unittest
import cloudflare_d1_upstream_bounded_count_readonly as m

SOURCE="source-d1-credential-test-1234567"
TARGET="target-d1-credential-test-7654321"
NUMBERS={
    "content_items":(2900,2853),
    "content_features":(14531,14328),
    "user_content_events":(5055,5017)
}
CALLS=[]
def column_rows(name):
    conf=m.TABLES[name]
    out=[]
    for i,col in enumerate(conf["columns"]):
        out.append({"cid":i,"name":col,
                    "type":"TEXT" if col!="id" else "INTEGER",
                    "notnull":int(col in conf["pk"]),
                    "dflt_value":None,
                    "pk":conf["pk"].index(col)+1 if col in conf["pk"] else 0,
                    "hidden":0})
    return out

def fake(token,account,uid,sql):
    CALLS.append((token,account,uid,sql))
    assert (token,account,uid) in (
        (SOURCE,m.SOURCE,m.SOURCE_D1),(TARGET,m.TARGET,m.TARGET_D1))
    for name in m.TABLES:
        if sql==m.META_SQL[name]:
            return column_rows(name),8
        if sql==m.COUNT_SQL[name]:
            value=NUMBERS[name][0 if account==m.SOURCE else 1]
            return [{"n":value}],value
    raise AssertionError("unexpected SQL")

class TestBoundedCounts(unittest.TestCase):
    def setUp(self): CALLS.clear()
    def test_three_tables_and_no_data_export(self):
        result=m.assess(SOURCE,TARGET,fake)
        self.assertEqual(set(result["tables"]),set(m.TABLES))
        self.assertEqual(result["d1_sql_calls"],12)
        self.assertEqual(len(CALLS),12)
        for name,(source,target) in NUMBERS.items():
            self.assertEqual(result["tables"][name]["source_minus_target"],
                             source-target)
            self.assertLess(source,m.TABLES[name]["limit"])
            self.assertFalse(result["tables"][name]["source_only_keys_verified"])
        self.assertFalse(result["keyed_row_parity_verified"])
        self.assertFalse(result["snapshot_atomic"])
        self.assertFalse(result["cutover_ready"])
        self.assertEqual(result["production_writes"],0)
        self.assertNotIn("source-d1-credential",str(result))
        self.assertNotIn("target-d1-credential",str(result))

    def test_fixed_read_allowlist_and_static_caps(self):
        self.assertEqual(len(m.ALLOWLIST),6)
        self.assertEqual(set(m.TABLES),set(NUMBERS))
        self.assertTrue(all("LIMIT " in sql and "SELECT 1" in sql
                            for sql in m.COUNT_SQL.values()))
        self.assertTrue(all("PRAGMA table_xinfo" in sql
                            for sql in m.META_SQL.values()))
        self.assertTrue(all("DROP" not in sql and "UPDATE" not in sql
                            for sql in m.ALLOWLIST))
        for name in m.TABLES:
            self.assertGreater(m.TABLES[name]["limit"],NUMBERS[name][0])

    def test_reject_equal_credentials(self):
        with self.assertRaises(m.Hold):m.assess(SOURCE,SOURCE,fake)
        self.assertFalse(CALLS)

    def test_reject_wrong_schema_identity(self):
        def drift(token,account,uid,sql):
            rows,cost=fake(token,account,uid,sql)
            if account==m.TARGET and sql==m.META_SQL["content_items"]:
                rows[0]["name"]="wrong"
            return rows,cost
        with self.assertRaises(m.Hold):m.assess(SOURCE,TARGET,drift)

    def test_reject_pk_change(self):
        def drift(token,account,uid,sql):
            rows,cost=fake(token,account,uid,sql)
            if sql==m.META_SQL["content_features"]:
                rows[1]["pk"]=0
            return rows,cost
        with self.assertRaises(m.Hold):m.assess(SOURCE,TARGET,drift)

    def test_count_at_hard_cap_is_lower_bound_not_exact(self):
        def cap(token,account,uid,sql):
            rows,cost=fake(token,account,uid,sql)
            if account==m.SOURCE and sql==m.COUNT_SQL["content_features"]:
                rows=[{"n":m.TABLES["content_features"]["limit"]}]
                cost=m.TABLES["content_features"]["limit"]
            return rows,cost
        result=m.assess(SOURCE,TARGET,cap)
        self.assertEqual(len(CALLS),12)
        self.assertTrue(result["any_count_capped"])
        self.assertEqual(result["capped_tables"],["content_features"])
        self.assertEqual(result["status"],
                         "UPSTREAM_PARTIAL_COUNTS_CAPPED_HOLD_NO_EXTRA_SCAN")
        feature=result["tables"]["content_features"]
        self.assertIsNone(feature["source_count"])
        self.assertEqual(feature["source_lower_bound"],19000)
        self.assertTrue(feature["source_at_cap"])
        self.assertEqual(feature["target_count"],NUMBERS["content_features"][1])
        self.assertIsNone(feature["source_minus_target"])
        self.assertFalse(feature["count_below_strict_cap"])
        self.assertFalse(result["keyed_row_parity_verified"])
        self.assertFalse(result["cutover_ready"])
        self.assertEqual(result["production_writes"],0)
        # Other table counts are still precise under their static cap.
        self.assertEqual(result["tables"]["content_items"]["source_count"],2900)
        self.assertEqual(result["tables"]["user_content_events"]["source_count"],5055)

    def test_reject_result_claiming_more_than_fixed_cap(self):
        def above_cap(token,account,uid,sql):
            rows,cost=fake(token,account,uid,sql)
            if sql==m.COUNT_SQL["content_items"]:
                rows=[{"n":m.TABLES["content_items"]["limit"]+1}]
            return rows,cost
        with self.assertRaisesRegex(m.Hold,"COUNT_EXCEEDS_ALLOWLIST_LIMIT"):
            m.assess(SOURCE,TARGET,above_cap)

    def test_target_cap_is_not_assumed_source_cap(self):
        def cap(token,account,uid,sql):
            rows,cost=fake(token,account,uid,sql)
            if account==m.TARGET and sql==m.COUNT_SQL["content_features"]:
                rows=[{"n":m.TABLES["content_features"]["limit"]}]
                cost=m.TABLES["content_features"]["limit"]
            return rows,cost
        result=m.assess(SOURCE,TARGET,cap)
        self.assertFalse(result["tables"]["content_features"]["source_at_cap"])
        self.assertTrue(result["tables"]["content_features"]["target_at_cap"])
        self.assertEqual(result["tables"]["content_features"]["source_count"],14531)
        self.assertIsNone(result["tables"]["content_features"]["target_count"])
        self.assertIsNone(result["tables"]["content_features"]["source_minus_target"])

    def test_reject_scan_exceeding_account_budget(self):
        def expensive(token,account,uid,sql):
            rows,cost=fake(token,account,uid,sql)
            if account==m.SOURCE and sql in m.COUNT_SQL.values():
                cost=m.MAX_METRIC_ROWS_READ
            return rows,cost
        with self.assertRaisesRegex(m.Hold,"ACCOUNT_READ_BUDGET"):
            m.assess(SOURCE,TARGET,expensive)

    def test_reject_excess_or_raw_count_columns(self):
        for bad in ([{"n":1,"item_id":"secret"}],[{"n":1.2}],[]):
            with self.subTest(bad=bad),self.assertRaises(m.Hold):
                m.count(bad,"content_items")

    def test_reject_nonallowlisted_sql_before_request(self):
        with self.assertRaises(m.Hold):
            m.query(SOURCE,m.SOURCE,m.SOURCE_D1,"DELETE FROM content_items")
        with self.assertRaises(m.Hold):
            m.query(SOURCE,m.TARGET,m.SOURCE_D1,m.COUNT_SQL["content_items"])

if __name__=="__main__":
    unittest.main()
