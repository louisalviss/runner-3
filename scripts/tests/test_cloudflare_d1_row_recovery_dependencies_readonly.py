#!/usr/bin/env python3
"""Synthetic regression suite. No Cloudflare credentials or network calls."""
import unittest
import urllib.error

import cloudflare_d1_row_recovery_dependencies_readonly as m

COLUMNS=("render_id","source_scope","item_count","recommended_count",
         "exploration_ratio","model_version","created_at","metadata_json")
COLS=[{"name":name,"cid":i,"pk":1 if i==0 else 0} for i,name in enumerate(COLUMNS)]
ROWS=[
    {"type":"table","name":"recommendation_runs","tbl_name":"recommendation_runs",
     "sql":"CREATE TABLE recommendation_runs (render_id TEXT PRIMARY KEY)"},
    {"type":"table","name":"content_items","tbl_name":"content_items",
     "sql":"CREATE TABLE content_items (id TEXT PRIMARY KEY)"},
]

def fake(model=None,columns=None):
    model=ROWS if model is None else model
    columns=COLS if columns is None else columns
    def reader(token,sql):
        if sql==m.META_SQL: return model
        if sql==m.COLUMN_SQL: return columns
        raise AssertionError("UNEXPECTED_SQL")
    return reader

class Footprint(unittest.TestCase):
    def test_no_fk_or_triggers_schema_only_clear(self):
        r=m.assess("audit-token",fake())
        self.assertEqual(r["status"],"SCHEMA_FOOTPRINT_CLEAR_BUT_ROLLBACK_NOT_READY")
        self.assertTrue(r["schema_local_dependency_clear"])
        self.assertEqual(r["possible_foreign_key_table_count"],0)
        self.assertEqual(r["inbound_foreign_key_count"],0)
        self.assertTrue(r["exact_foreign_key_relationships_verified"])
        self.assertFalse(r["row_safe_recovery_rehearsed"])
        self.assertFalse(r["independent_writer_quiescence_verified"])
        self.assertFalse(r["cutover_ready"])
        self.assertEqual(r["cloudflare_write_requests"],0)

    def test_inbound_fk_holds(self):
        rows=[ROWS[0], dict(ROWS[1],sql="CREATE TABLE content_items (run_id TEXT REFERENCES recommendation_runs(render_id))")]
        r=m.assess("audit-token",fake(model=rows))
        self.assertEqual(r["status"],"SCHEMA_DEPENDENCIES_REQUIRE_MANUAL_REVIEW_HOLD")
        self.assertEqual(r["possible_foreign_key_table_count"],1)
        self.assertEqual(r["inbound_foreign_key_count"],1)
        self.assertFalse(r["schema_local_dependency_clear"])

    def test_outbound_fk_holds(self):
        rows=[dict(ROWS[0],sql="CREATE TABLE recommendation_runs (source_id TEXT, FOREIGN KEY(source_id) REFERENCES content_items(id))"), ROWS[1]]
        r=m.assess("audit-token",fake(model=rows))
        self.assertEqual(r["outbound_foreign_key_count"],1)
        self.assertFalse(r["schema_local_dependency_clear"])

    def test_fk_marker_in_comment_holds_conservatively(self):
        rows=[ROWS[0],dict(ROWS[1],sql="CREATE TABLE content_items (id TEXT) /* references */")]
        r=m.assess("audit-token",fake(model=rows))
        self.assertEqual(r["possible_foreign_key_table_count"],1)
        self.assertFalse(r["ddl_fk_marker_and_local_sqlite_agree"])
        self.assertFalse(r["schema_local_dependency_clear"])

    def test_unexpected_table_ddl_blocks(self):
        rows=[ROWS[0],dict(ROWS[1],sql="CREATE VIRTUAL TABLE content_items USING fts5(content)")]
        with self.assertRaises(m.Hold):
            m.assess("audit-token",fake(model=rows))

    def test_trigger_holds(self):
        rows=ROWS+[{"type":"trigger","name":"t","tbl_name":"content_items",
                    "sql":"CREATE TRIGGER t AFTER INSERT ON content_items BEGIN SELECT 1; END"}]
        r=m.assess("audit-token",fake(model=rows))
        self.assertFalse(r["schema_local_dependency_clear"])

    def test_view_reference_holds(self):
        rows=ROWS+[{"type":"view","name":"summary","tbl_name":"summary",
                    "sql":"CREATE VIEW summary AS SELECT * FROM recommendation_runs"}]
        r=m.assess("audit-token",fake(model=rows))
        self.assertEqual(r["views_referencing_table_count"],1)
        self.assertFalse(r["schema_local_dependency_clear"])

    def test_invalid_schema_object_blocks(self):
        with self.assertRaises(m.Hold):
            m.assess("audit-token",fake(model=ROWS+[{"type":"index","name":"ix","tbl_name":"content_items","sql":"CREATE INDEX ..."}]))

    def test_bad_columns_blocks(self):
        with self.assertRaises(m.Hold):
            m.assess("audit-token",fake(columns=COLS[:-1]))

    def test_only_two_sql_shapes_allowed(self):
        self.assertTrue(m.allowed_sql(m.META_SQL))
        self.assertTrue(m.allowed_sql(m.COLUMN_SQL))
        for sql in ('DELETE FROM recommendation_runs',
                    'UPDATE recommendation_runs SET item_count=1',
                    'SELECT * FROM recommendation_runs',
                    'PRAGMA foreign_key_list("recommendation_runs")',
                    'PRAGMA foreign_keys=off'):
            self.assertFalse(m.allowed_sql(sql),sql)

    def test_too_many_objects_blocks(self):
        rows=ROWS+[dict(ROWS[1],name="t"+str(i)) for i in range(100)]
        with self.assertRaises(m.Hold):
            m.assess("audit-token",fake(model=rows))

    def test_duplicates_block(self):
        with self.assertRaises(m.Hold):
            m.assess("audit-token",fake(model=ROWS+[ROWS[0]]))

    def test_multiple_foreign_keys_count_exact_relationships(self):
        rows=[
            dict(ROWS[0],sql="CREATE TABLE recommendation_runs (render_id TEXT PRIMARY KEY)"),
            dict(ROWS[1],sql='CREATE TABLE content_items (id TEXT PRIMARY KEY, run1 TEXT REFERENCES recommendation_runs(render_id) ON DELETE CASCADE, run2 TEXT REFERENCES recommendation_runs(render_id))')
        ]
        r=m.assess("audit-token",fake(model=rows))
        self.assertEqual(r["inbound_foreign_key_count"],2)
        self.assertEqual(r["local_sqlite_foreign_key_table_count"],1)
        self.assertTrue(r["ddl_fk_marker_and_local_sqlite_agree"])
        self.assertFalse(r["schema_local_dependency_clear"])

    def test_multiple_sql_statements_rejected_by_ddl_replay(self):
        rows=[ROWS[0],dict(ROWS[1],sql="CREATE TABLE content_items (id TEXT); DROP TABLE recommendation_runs")]
        with self.assertRaises(m.Hold):
            m.assess("audit-token",fake(model=rows))

    def test_view_and_trigger_still_hold_without_fk(self):
        rows=ROWS+[{"type":"trigger","name":"changed","tbl_name":"content_items",
                    "sql":"CREATE TRIGGER changed AFTER INSERT ON content_items BEGIN SELECT 1; END"},
                   {"type":"view","name":"v","tbl_name":"v",
                    "sql":"CREATE VIEW v AS SELECT * FROM recommendation_runs"}]
        r=m.assess("audit-token",fake(model=rows))
        self.assertEqual(r["inbound_foreign_key_count"],0)
        self.assertFalse(r["schema_local_dependency_clear"])

    def test_http_failures_are_sanitized(self):
        def denied(req,timeout=None):
            raise urllib.error.HTTPError(req.full_url,403,"secret backend response",{},None)
        for sql,tag in ((m.META_SQL,"SCHEMA"),(m.COLUMN_SQL,"COLUMNS")):
            with self.subTest(sql=tag),self.assertRaises(m.Hold) as result:
                m.query("sensitive-test-token-should-not-leak",sql,opener=denied)
            self.assertEqual(str(result.exception),"CLOUDFLARE_HTTP_403_"+tag)

    def test_network_failure_sanitized(self):
        def fail(req,timeout=None):
            raise urllib.error.URLError("secret network details")
        with self.assertRaises(m.Hold) as result:
            m.query("sensitive-test-token-should-not-leak",m.META_SQL,opener=fail)
        self.assertEqual(str(result.exception),"CLOUDFLARE_NETWORK_SCHEMA")

if __name__=="__main__":
    unittest.main()
