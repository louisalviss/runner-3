#!/usr/bin/env python3
"""All tests synthetic; never contact Cloudflare."""
import unittest
import cloudflare_d1_row_recovery_dependencies_readonly as m

COLUMNS=("render_id","source_scope","item_count","recommended_count",
         "exploration_ratio","model_version","created_at","metadata_json")
COLS=[{"name":name,"cid":i,"pk":1 if i==0 else 0} for i,name in enumerate(COLUMNS)]
ROWS=[
    {"type":"table","name":"recommendation_runs","tbl_name":"recommendation_runs",
     "sql":"CREATE TABLE recommendation_runs (...)"},
    {"type":"table","name":"content_items","tbl_name":"content_items",
     "sql":"CREATE TABLE content_items (...)"},
]

def fake(model=ROWS, fk=None, columns=COLS):
    fk=fk or {}
    def reader(token, sql):
        if sql == m.META_SQL: return model
        if sql == m.COLUMN_SQL: return columns
        if sql.startswith("PRAGMA foreign_key_list"): return fk.get(sql,[])
        raise AssertionError("UNEXPECTED_QUERY")
    return reader

class Footprint(unittest.TestCase):
    def test_no_fk_or_triggers_is_schema_only_clear(self):
        r=m.assess("audit-token",fake())
        self.assertEqual(r["status"],"SCHEMA_FOOTPRINT_CLEAR_BUT_ROLLBACK_NOT_READY")
        self.assertTrue(r["schema_local_dependency_clear"])
        self.assertFalse(r["row_safe_recovery_rehearsed"])
        self.assertFalse(r["independent_writer_quiescence_verified"])
        self.assertFalse(r["cutover_ready"])
        self.assertEqual(r["cloudflare_write_requests"],0)

    def test_inbound_fk_holds(self):
        sql=m.foreign_key_sql("content_items")
        r=m.assess("audit-token",fake(fk={sql:[{"table":"recommendation_runs"}]}))
        self.assertEqual(r["status"],"SCHEMA_DEPENDENCIES_REQUIRE_MANUAL_REVIEW_HOLD")
        self.assertEqual(r["inbound_foreign_key_count"],1)

    def test_outbound_fk_holds_conservatively(self):
        sql=m.foreign_key_sql("recommendation_runs")
        r=m.assess("audit-token",fake(fk={sql:[{"table":"content_items"}]}))
        self.assertFalse(r["schema_local_dependency_clear"])

    def test_unrelated_trigger_still_holds(self):
        rows=ROWS+[{"type":"trigger","name":"trig","tbl_name":"content_items",
                    "sql":"CREATE TRIGGER trig AFTER INSERT ON content_items BEGIN SELECT 1; END"}]
        r=m.assess("audit-token",fake(model=rows))
        self.assertEqual(r["trigger_count_any_table"],1)
        self.assertFalse(r["schema_local_dependency_clear"])

    def test_view_reference_holds(self):
        rows=ROWS+[{"type":"view","name":"summary","tbl_name":"summary",
                    "sql":"CREATE VIEW summary AS SELECT * FROM recommendation_runs"}]
        r=m.assess("audit-token",fake(model=rows))
        self.assertEqual(r["views_referencing_table_count"],1)
        self.assertFalse(r["schema_local_dependency_clear"])

    def test_unknown_object_blocks(self):
        with self.assertRaises(m.Hold):
            m.assess("audit-token",fake(model=ROWS+[{"type":"index","name":"ix",
                                                    "tbl_name":"recommendation_runs","sql":"..."}]))

    def test_bad_column_shape_blocks(self):
        with self.assertRaises(m.Hold):
            m.assess("audit-token",fake(columns=COLS[:-1]))

    def test_sql_allowlist_blocks_dml(self):
        for sql in ('DELETE FROM recommendation_runs',
                    'UPDATE recommendation_runs SET item_count=1',
                    'INSERT INTO recommendation_runs VALUES (1)',
                    'PRAGMA foreign_keys=OFF',
                    'SELECT * FROM recommendation_runs',
                    'PRAGMA foreign_key_list("bad-name")'):
            self.assertFalse(m.allowed_sql(sql),sql)
        self.assertTrue(m.allowed_sql(m.META_SQL))
        self.assertTrue(m.allowed_sql(m.foreign_key_sql("recommendation_runs")))

    def test_no_forged_fk_sql(self):
        for bad in ('abc";DELETE FROM records;--','a b',''):
            with self.assertRaises(m.Hold):
                m.foreign_key_sql(bad)

    def test_truncated_schema_blocks(self):
        rows=ROWS+[dict(ROWS[1], name="t"+str(i)) for i in range(100)]
        with self.assertRaises(m.Hold):
            m.assess("audit-token",fake(model=rows))

    def test_duplicate_table_blocks(self):
        with self.assertRaises(m.Hold):
            m.assess("audit-token",fake(model=ROWS+[ROWS[0]]))

if __name__ == "__main__":
    unittest.main()
