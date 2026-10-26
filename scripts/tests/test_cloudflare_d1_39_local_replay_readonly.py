#!/usr/bin/env python3
"""Synthetic only: no Cloudflare, no D1 rows, no runner secrets."""
import sqlite3
import unittest
import cloudflare_d1_39_local_replay_readonly as m

class TestIsolatedReplay(unittest.TestCase):
    def setUp(self):
        self.target={
            ("table","common"):"CREATE TABLE common (id TEXT PRIMARY KEY)"
        }
        self.source={
            **self.target,
            ("table","audit"):"CREATE TABLE audit (id TEXT PRIMARY KEY, common_id TEXT REFERENCES common(id))",
            ("index","idx_audit_common"):"CREATE INDEX idx_audit_common ON audit(common_id)",
            ("trigger","trg_audit"):"CREATE TRIGGER trg_audit AFTER INSERT ON audit BEGIN SELECT 1; END"
        }
        self.candidate=(
            "-- This is review only; no production writes.\n"
            "CREATE TABLE IF NOT EXISTS audit (id TEXT PRIMARY KEY, common_id TEXT REFERENCES common(id));\n"
            "CREATE INDEX IF NOT EXISTS idx_audit_common ON audit(common_id);\n"
            "CREATE TRIGGER IF NOT EXISTS trg_audit AFTER INSERT ON audit BEGIN SELECT 1; END;\n"
        )

    def test_simple_replay_and_trigger_without_application_rows(self):
        result=m.replay(self.target,self.source,self.candidate)
        self.assertEqual(result["baseline_object_count"],1)
        self.assertEqual(result["simulated_create_count"],3)
        self.assertEqual(result["source_object_count"],4)
        self.assertEqual(result["foreign_key_constraints"],1)
        self.assertEqual(result["foreign_key_edges"],[
            {"from_table":"audit","to_table":"common",
             "on_delete":"NO ACTION",
             "from_table_missing_on_target":True,
             "to_table_missing_on_target":False}
        ])
        self.assertFalse(result["target_existing_row_constraints_tested"])
        self.assertFalse(result["source_d1_row_parity_proven"])

    def test_missing_fk_parent_fails_closed(self):
        src=self.source.copy()
        src[("table","audit")]=src[("table","audit")].replace(
            "REFERENCES common(id)","REFERENCES ghost(id)")
        candidate=self.candidate.replace(
            "REFERENCES common(id)","REFERENCES ghost(id)")
        with self.assertRaises(m.Hold):
            m.replay(self.target,src,candidate)

    def test_empty_and_invalid_dangerous_statements_rejected(self):
        for script in (
            "DROP TABLE common;",
            "CREATE TABLE audit (id TEXT); DELETE FROM audit;",
            "INSERT INTO common VALUES ('x');",
            "CREATE TABLE audit(id INT); DROP TABLE common;",
        ):
            with self.subTest(script=script):
                with self.assertRaises(m.Hold):
                    m.replay(self.target,self.source,script)

    def test_preexisting_definition_drift_holds(self):
        bad=self.source.copy()
        bad[("table","common")]="CREATE TABLE common (id INT PRIMARY KEY)"
        with self.assertRaises(m.Hold):
            m.replay(self.target,bad,self.candidate)

    def test_duplicate_if_not_exists_noop_holds(self):
        # Repeating the same CREATE IF NOT EXISTS must not be silently accepted.
        script=self.candidate.replace(
            "CREATE INDEX IF NOT EXISTS idx_audit_common ON audit(common_id);",
            "CREATE TABLE IF NOT EXISTS audit (id TEXT PRIMARY KEY, common_id TEXT REFERENCES common(id));")
        with self.assertRaises(m.Hold):
            m.replay(self.target,self.source,script)

    def test_target_only_unexpected_object_holds(self):
        source={k:v for k,v in self.source.items() if k!=("table","common")}
        with self.assertRaises(m.Hold):
            m.replay(self.target,source,self.candidate)

    def test_statement_split_trigger_body_and_comments(self):
        split=m.split_create_only(self.candidate)
        self.assertEqual(len(split),3)
        self.assertIn("SELECT 1; END",split[2])
        self.assertNotIn("--",str(split))

    def test_token_scope_rejected_before_any_io(self):
        with self.assertRaises(m.Hold):
            m.assess("same-secret-value-abcdefghijkl","same-secret-value-abcdefghijkl")
        with self.assertRaises(m.Hold):
            m.assess("","anything")
        with self.assertRaises(m.Hold):
            m.target_api("a"*30,"not-allowed","identity")
        with self.assertRaises(m.Hold):
            m.target_api("a"*30,"runner3-core","write")

    def test_normalize_rejects_noncreate_and_duplicate(self):
        obj=[{"type":"table","name":"common","sql":"DROP TABLE common"}]
        with self.assertRaises(m.Hold):
            m.normalize(obj)
        obj=[{"type":"table","name":"common","sql":"CREATE TABLE common (id TEXT)"}]*2
        with self.assertRaises(m.Hold):
            m.normalize(obj)

if __name__=="__main__":
    unittest.main()
