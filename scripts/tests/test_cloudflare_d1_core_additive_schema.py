"""Synthetic/offline-only Core DDL source-fingerprint acceptance gates."""
import importlib.util
import pathlib
import shutil
import sqlite3
import tempfile
import unittest

SCRIPT=pathlib.Path(__file__).resolve().parents[1]/"cloudflare_d1_core_additive_schema.py"
SPEC=importlib.util.spec_from_file_location("core_ddl",SCRIPT)
app=importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(app)

class SourceMatchedDDL(unittest.TestCase):
    def test_canonical_16_objects_are_exact_source_fingerprints(self):
        candidate=app.build(pathlib.Path("."))
        self.assertEqual(len(app.EXPECTED),16)
        self.assertEqual(candidate.count("CREATE TABLE IF NOT EXISTS"),8)
        self.assertEqual(candidate.count("CREATE INDEX IF NOT EXISTS"),8)

    def test_committed_bundle_matches_source(self):
        self.assertEqual(app.main(["--check"]),0)

    def test_candidate_is_not_runtime_or_remote_apply(self):
        content=app.build(pathlib.Path("."))
        self.assertIn("DO NOT EXECUTE",content)
        self.assertIn("SOURCE is production authority",content)
        self.assertNotIn("wrangler",content.lower())
        self.assertNotIn("https://api.cloudflare.com",content)

    def test_candidate_has_no_destructive_or_data_statements(self):
        content=app.build(pathlib.Path("."))
        lines=[line for line in content.split(";") if "CREATE" in line]
        self.assertEqual(len(lines),16)
        for statement in app.statements(content):
            self.assertTrue(statement.startswith(("CREATE TABLE", "CREATE INDEX")))

    def test_intentionally_uncovered_core_objects_not_fabricated(self):
        content=app.build(pathlib.Path("."))
        for name in ("typed_kv", "r2_receipts", "d1_migrations", "ebook_reader_trace_v113"):
            self.assertNotIn("CREATE TABLE IF NOT EXISTS "+name,content)
        self.assertNotIn("CREATE INDEX IF NOT EXISTS idx_typed_kv",content)

    def test_missing_path_blocks(self):
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaises(OSError):
                app.build(pathlib.Path(folder))

    def test_nonadditive_statement_is_rejected(self):
        with self.assertRaisesRegex(app.Hold,"NON_ADDITIVE_SQL_REJECTED"):
            app.statements("CREATE TABLE IF NOT EXISTS safe(id INT); DELETE FROM safe;")

    def test_additional_table_is_rejected_even_if_create_only(self):
        with tempfile.TemporaryDirectory() as folder:
            tmp=pathlib.Path(folder)
            for name in app.INPUTS:
                dst=tmp/app.CORE_DIR/name
                dst.parent.mkdir(parents=True,exist_ok=True)
                shutil.copyfile(app.CORE_DIR/name,dst)
            path=tmp/app.CORE_DIR/app.INPUTS[0]
            path.write_text(path.read_text()+"\nCREATE TABLE IF NOT EXISTS unexpected(id INT);\n")
            with self.assertRaisesRegex(app.Hold,"STATEMENT_COUNT_DRIFT"):
                app.build(tmp)

    def test_one_column_change_fails_authenticated_source_metadata(self):
        with tempfile.TemporaryDirectory() as folder:
            tmp=pathlib.Path(folder)
            for name in app.INPUTS:
                dst=tmp/app.CORE_DIR/name
                dst.parent.mkdir(parents=True,exist_ok=True)
                shutil.copyfile(app.CORE_DIR/name,dst)
            path=tmp/app.CORE_DIR/"0001_init.sql"
            src=path.read_text()
            self.assertIn("event_type TEXT NOT NULL",src)
            path.write_text(src.replace("event_type TEXT NOT NULL", "event_type INTEGER NOT NULL"))
            with self.assertRaisesRegex(app.Hold,"SOURCE_DDL_OR_COLUMN_FINGERPRINT_MISMATCH"):
                app.build(tmp)

    def test_candidate_parses_in_scratch_sqlite(self):
        content=app.build(pathlib.Path("."))
        with sqlite3.connect(":memory:") as db:
            db.executescript(content)
            tables=db.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'").fetchone()[0]
            indexes=db.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='index' AND name NOT LIKE 'sqlite_%'").fetchone()[0]
            self.assertEqual((tables,indexes),(8,8))

if __name__=="__main__":
    unittest.main()
