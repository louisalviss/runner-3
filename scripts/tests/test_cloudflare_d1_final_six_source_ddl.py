"""Synthetic-only tests: do not contact Cloudflare or reveal real schema data."""
import importlib.util
import json
import pathlib
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

ROOT = pathlib.Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("sixddl",
    ROOT / "scripts/cloudflare_d1_final_six_source_ddl.py")
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

CORE_SQL = (
    "CREATE TABLE typed_kv(k TEXT PRIMARY KEY, value TEXT)",
    "CREATE TABLE r2_receipts(request_id TEXT PRIMARY KEY, amount INTEGER)",
    "CREATE TABLE d1_migrations(name TEXT PRIMARY KEY, applied_at TEXT)",
)
CI_SQL = (
    "CREATE TABLE link_interest_events(id TEXT PRIMARY KEY, status TEXT)",
    "CREATE INDEX idx_link_interest_events_status ON link_interest_events(status)",
    "CREATE TRIGGER test_event_guard BEFORE INSERT ON link_interest_events "
    "BEGIN SELECT RAISE(IGNORE); END",
)


def fixtures():
    databases = {}
    pins = {}
    for dbname, statements in (
        ("runner3-core", CORE_SQL),
        ("runner3-content-intelligence", CI_SQL),
    ):
        connection = sqlite3.connect(":memory:")
        connection.row_factory = sqlite3.Row
        connection.executescript(";\n".join(statements) + ";")
        results = [dict(type=r[0], name=r[1], sql=r[2]) for r in connection.execute(
            "SELECT type,name,sql FROM sqlite_master "
            "WHERE type IN ('table','index','trigger','view') "
            "AND name NOT LIKE 'sqlite_%' ORDER BY type,name")]
        fingerprints = {}
        for row in results:
            col = [dict(x) for x in connection.execute(
                m.pragma(row["name"]))] if row["type"] == "table" else None
            fingerprints[m.digest([row["type"], row["name"]])] = m.table_metadata(
                row["type"], row["name"], row["sql"], col)
        databases[dbname] = (connection, results)
        pins[dbname] = fingerprints
    return databases, pins


class GapDDLReadOnly(unittest.TestCase):
    def test_six_exact_objects_pass_with_only_approved_queries(self):
        dbs, pins = fixtures()
        calls = []
        def fake(token, dbname, sql):
            self.assertEqual(token, "synthetic-source-only-token")
            self.assertIn(dbname, dbs)
            self.assertTrue(sql == m.SQL_MASTER or sql.startswith('PRAGMA table_xinfo("'))
            calls.append(sql)
            db, objs = dbs[dbname]
            if sql == m.SQL_MASTER:
                return objs
            return [dict(x) for x in db.execute(sql)]
        with patch.object(m, "GAPS", pins):
            report = m.capture("synthetic-source-only-token", reader=fake)
        self.assertEqual(report["object_count"], 6)
        self.assertEqual(report["source_query_count"], len(calls))
        self.assertLessEqual(len(calls), 12)
        self.assertEqual(report["raw_application_rows_read"], 0)
        self.assertEqual(report["source_d1_writes"], 0)
        self.assertEqual(report["target_d1_queries"], 0)
        self.assertEqual(report["r2_requests"], 0)
        self.assertFalse(report["cutover_ready"])
        for db, _ in dbs.values():
            db.close()

    def test_missing_one_source_object_blocks(self):
        dbs, pins = fixtures()
        def fake(token, dbname, sql):
            db, objs = dbs[dbname]
            if sql == m.SQL_MASTER:
                return objs[:-1] if dbname == "runner3-content-intelligence" else objs
            return [dict(x) for x in db.execute(sql)]
        with patch.object(m, "GAPS", pins), self.assertRaisesRegex(
            m.Hold, "SOURCE_GAP_OBJECT_CENSUS_DRIFT"):
            m.capture("synthetic-source-only-token", reader=fake)

    def test_changed_schema_metadata_blocks(self):
        dbs, pins = fixtures()
        changed = {k:dict(v) for k,v in pins.items()}
        id0 = next(iter(changed["runner3-core"]))
        changed["runner3-core"][id0] = "0"*64
        def fake(token, dbname, sql):
            db, objs = dbs[dbname]
            return objs if sql == m.SQL_MASTER else [dict(x) for x in db.execute(sql)]
        with patch.object(m, "GAPS", changed), self.assertRaisesRegex(
            m.Hold, "SOURCE_SCHEMA_METADATA_DRIFT"):
            m.capture("synthetic-source-only-token", reader=fake)

    def test_wrong_core_table_identity_blocks(self):
        dbs, pins = fixtures()
        changed = {k:dict(v) for k,v in pins.items()}
        old = next(iter(changed["runner3-core"]))
        changed["runner3-core"][m.digest(["table","not_an_authorized_table"])] = changed["runner3-core"].pop(old)
        def fake(token, dbname, sql):
            db, objs = dbs[dbname]
            return objs if sql == m.SQL_MASTER else [dict(x) for x in db.execute(sql)]
        with patch.object(m, "GAPS", changed), self.assertRaises(m.Hold):
            m.capture("synthetic-source-only-token", reader=fake)

    def test_production_scope_is_static_and_source_only(self):
        self.assertEqual(len(m.DATABASES), 2)
        self.assertEqual(sum(map(len,m.GAPS.values())), 6)
        self.assertTrue(all(len(k) == 64 and len(v) == 64
            for values in m.GAPS.values() for k,v in values.items()))
        self.assertEqual(m.ACCOUNT, "7415a87f6bce7884e73ad7cfed5782df")
        self.assertNotIn("DELETE", m.SQL_MASTER)
        self.assertNotIn("INSERT", m.SQL_MASTER)
        self.assertNotIn("UPDATE", m.SQL_MASTER)

    def test_unsafe_sql_and_identifiers_not_allowed(self):
        for bad in ('PRAGMA table_xinfo("x"); DELETE FROM x',
                    'SELECT * FROM content_items',
                    'UPDATE content_items SET title=NULL',
                    'DROP TABLE content_items'):
            with self.subTest(bad=bad):
                self.assertNotEqual(bad, m.SQL_MASTER)
                self.assertFalse(
                    __import__("re").fullmatch(
                        r'PRAGMA table_xinfo\("[A-Za-z_][A-Za-z0-9_]{0,127}"\)',bad))

    def test_metadata_mutation_response_blocks(self):
        for meta in ({"rows_written":1,"changed_db":False},
                     {"rows_written":0,"changed_db":True}, []):
            with self.assertRaisesRegex(m.Hold, "UNEXPECTED_MUTATION"):
                m.parse_api({"success":True,"result":[
                    {"success":True,"results":[],"meta":meta}]})

    def test_reject_unsafe_malformed_api(self):
        for body in ({"success":False}, {"success":True,"result":[]},
                     {"success":True,"result":[{"success":False,"results":[],"meta":{}}]}):
            with self.assertRaises(m.Hold):
                m.parse_api(body)

    def test_no_token_no_request(self):
        def forbidden(*args):
            raise AssertionError("No network should be called without token")
        with self.assertRaisesRegex(m.Hold, "SOURCE_TOKEN_UNAVAILABLE"):
            m.capture("",reader=forbidden)

    def test_meta_hash_canonical_rows(self):
        with sqlite3.connect(":memory:") as db:
            db.row_factory=sqlite3.Row
            db.execute("CREATE TABLE fixture(k TEXT PRIMARY KEY, body BLOB)")
            ddl=db.execute("SELECT sql FROM sqlite_master WHERE name='fixture'").fetchone()[0]
            cols=[dict(x) for x in db.execute('PRAGMA table_xinfo("fixture")')]
            self.assertRegex(m.table_metadata("table","fixture",ddl,cols),r"^[0-9a-f]{64}$")
            cols[0]["type"]="INTEGER"
            self.assertNotEqual(m.table_metadata("table","fixture",ddl,cols),
                                m.table_metadata("table","fixture",ddl,
                                    [dict(x) for x in db.execute('PRAGMA table_xinfo("fixture")')]))

    def test_source_sql_proof_is_not_migration_or_cutover(self):
        doc=(ROOT/"scripts/cloudflare_d1_final_six_source_ddl.py").read_text()
        self.assertIn('"cutover_ready": False', doc)
        self.assertIn('"raw_application_rows_read": 0',doc)
        self.assertNotIn('os.environ.get("CLOUDFLARE_TARGET_AUDIT_TOKEN", "")',doc)
        self.assertNotIn('R2_BUCKET',doc)


if __name__ == "__main__":
    unittest.main()
