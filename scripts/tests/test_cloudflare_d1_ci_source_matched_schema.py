"""Content Intelligence D1 staging fingerprints: synthetic offline-only gates."""
import importlib.util
import pathlib
import shutil
import sqlite3
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
PATH = ROOT / "scripts/cloudflare_d1_ci_source_matched_schema.py"
spec = importlib.util.spec_from_file_location("ci_source_ddl", PATH)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class ContentIntelligenceStaging(unittest.TestCase):
    def test_source_15_object_fingerprints(self):
        sql = mod.build(ROOT)
        self.assertEqual(len(mod.SOURCE), 15)
        self.assertEqual(sum(k == "table" for k, n in mod.SOURCE), 2)
        self.assertEqual(sum(k == "index" for k, n in mod.SOURCE), 12)
        self.assertEqual(sum(k == "trigger" for k, n in mod.SOURCE), 1)
        self.assertEqual(sql.count("CREATE TABLE IF NOT EXISTS"), 2)
        self.assertEqual(sql.count("CREATE INDEX IF NOT EXISTS"), 11)
        self.assertEqual(sql.count("CREATE UNIQUE INDEX IF NOT EXISTS"), 1)
        self.assertEqual(sql.count("CREATE TRIGGER IF NOT EXISTS"), 1)

    def test_checked_in_candidate_reproducible(self):
        self.assertEqual(mod.main(["--root", str(ROOT), "--check"]), 0)

    def test_never_include_extra_repo_only_index(self):
        sql = mod.build(ROOT)
        self.assertNotIn("idx_content_items_last_seen_at", sql)
        self.assertNotIn("CREATE TABLE IF NOT EXISTS content_items", sql)
        self.assertNotIn("CREATE TABLE IF NOT EXISTS user_content_events", sql)

    def test_no_mutating_sql_in_candidate(self):
        sql = mod.build(ROOT)
        self.assertIn("DO NOT AUTO-APPLY", sql)
        self.assertNotIn("DELETE FROM", sql)
        self.assertNotIn("UPDATE ", sql)
        self.assertNotIn("DROP TABLE", sql)
        self.assertNotIn("INSERT INTO", sql)
        self.assertNotIn("https://api.cloudflare.com", sql)

    def test_safe_parser_refuses_delete_update_drop(self):
        for bad in ("DELETE FROM content_scores;",
                    "UPDATE content_scores SET score=0;",
                    "DROP TABLE content_items;",
                    "INSERT INTO content_scores VALUES(1);"):
            with self.subTest(bad=bad), self.assertRaisesRegex(mod.Hold,"UNSAFE_SQL_INPUT"):
                mod.safe_create_only("CREATE INDEX IF NOT EXISTS ix ON t(k);" + bad)

    def test_comments_with_semicolons_are_not_executed(self):
        out = mod.safe_create_only("-- comment; ignore this\n"
             "CREATE TABLE IF NOT EXISTS fixture(a INTEGER);")
        self.assertEqual(out, ["CREATE TABLE IF NOT EXISTS fixture(a INTEGER)"])

    def test_cryptographic_tamper_blocks(self):
        with tempfile.TemporaryDirectory() as path:
            root = pathlib.Path(path)
            for p in (mod.CI, mod.CORE, mod.STAGE, mod.IDEMPOTENCY, mod.TRIGGER):
                dst = root / p
                dst.parent.mkdir(parents=True,exist_ok=True)
                shutil.copyfile(ROOT / p, dst)
            file = root / mod.CORE
            text = file.read_text()
            self.assertIn("status TEXT",text)
            file.write_text(text.replace("status TEXT", "status INTEGER",1))
            with self.assertRaisesRegex(mod.Hold,"SOURCE_DDL_METADATA_DRIFT"):
                mod.build(root)

    def test_unique_index_drift_blocks(self):
        with tempfile.TemporaryDirectory() as path:
            root = pathlib.Path(path)
            for p in (mod.CI, mod.CORE, mod.STAGE, mod.IDEMPOTENCY, mod.TRIGGER):
                dst = root / p
                dst.parent.mkdir(parents=True,exist_ok=True)
                shutil.copyfile(ROOT / p,dst)
            file = root / mod.IDEMPOTENCY
            old = file.read_text()
            self.assertIn("CREATE UNIQUE INDEX",old)
            file.write_text(old.replace("CREATE UNIQUE INDEX","CREATE INDEX",1))
            with self.assertRaisesRegex(mod.Hold,"SOURCE_DDL_METADATA_DRIFT"):
                mod.build(root)

    def test_old_destructive_migration_prefix_ignored_safely(self):
        text=(ROOT / mod.TRIGGER).read_text()
        self.assertIn("DELETE FROM user_content_events",text)
        trigger=mod.read_trigger(text)
        self.assertNotIn("DELETE FROM",trigger)
        self.assertIn("RAISE(IGNORE)",trigger)

    def test_invalid_trigger_blocks(self):
        with self.assertRaisesRegex(mod.Hold,"TRIGGER_BODY_DRIFT"):
            mod.read_trigger("CREATE TRIGGER IF NOT EXISTS "
                "trg_user_content_events_render_dedupe BEFORE INSERT ON foo BEGIN SELECT 1; END;")

    def test_generated_candidate_parses_against_preexisting_target_tables(self):
        # Scratch-only target fixture: baseline common tables copied from the
        # exact existing source schema, but WITHOUT any of its secondary indexes.
        original = mod.safe_create_only((ROOT / mod.CI).read_text())
        stage = mod.safe_create_only((ROOT / mod.STAGE).read_text())
        with sqlite3.connect(":memory:") as db:
            for statement in original + stage:
                if statement.startswith("CREATE TABLE"):
                    db.execute(statement)
            db.executescript(mod.build(ROOT))
            counts = dict(db.execute("SELECT type,COUNT(*) FROM sqlite_master "
                                     "WHERE name NOT LIKE 'sqlite_%' GROUP BY type"))
            self.assertEqual(counts.get("trigger"),1)
            self.assertEqual(counts.get("table"),9)
            self.assertEqual(counts.get("index"),12)

    def test_missing_runtime_input_blocks(self):
        with tempfile.TemporaryDirectory() as path:
            with self.assertRaises(OSError):
                mod.build(pathlib.Path(path))


if __name__ == "__main__":
    unittest.main()
