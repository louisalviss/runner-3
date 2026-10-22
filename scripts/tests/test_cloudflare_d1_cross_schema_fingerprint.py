"""Synthetic-only D1 cross-account audit tests. No Cloudflare requests."""
import hashlib
import importlib.util
import json
import os
import pathlib
import tempfile
import unittest
from unittest import mock

p = pathlib.Path(__file__).resolve().parents[1] / "cloudflare_d1_cross_schema_fingerprint.py"
spec = importlib.util.spec_from_file_location("cross_d1", p)
a = importlib.util.module_from_spec(spec)
spec.loader.exec_module(a)

HASH = hashlib.sha256(b"CREATE TABLE items(id INT)").hexdigest()
COLS = hashlib.sha256(b"synthetic-column-schema").hexdigest()


def source_db():
    return {"rows_scanned": 0, "table_count": 1,
            "objects": [{"type": "table", "name": "items", "ddl_sha256": HASH}],
            "tables": {"items": {"pk_columns": ["id"], "column_count": 1,
                      "row_count": None, "payload_parity_verified": False,
                      "columns_sha256": COLS}}}


def target_db():
    return {"table_count": 1, "schema_object_count": 1,
            "schema_objects": [{"kind": "table", "name": "items",
               "ddl_sha256": HASH, "pk_columns": ["id"], "column_count": 1,
               "columns_sha256": COLS}]}


def source():
    return {"account_id": a.SOURCE_ACCOUNT, "source_row_parity_verified": False,
            "target_row_parity_verified": False, "target_accessed": False,
            "cutover_ready": False, "r2_requests": 0,
            "databases": {n: source_db() for n in a.REQUIRED}}


def target(missing=(), legacy=True):
    names = set(a.REQUIRED) - set(missing)
    if legacy:
        names.add(a.LEGACY)
    return {"account_id": a.TARGET_ACCOUNT, "role": "target",
            "row_key_content_parity_verified": False, "source_delete_allowed": False,
            "cutover_ready": False, "r2_requests": 0, "database_names": sorted(names),
            "database_schemas": {n: target_db() for n in names},
            "missing_required_names": sorted(set(a.REQUIRED) - names),
            "historical_target_only_name_present": legacy}


class Contracts(unittest.TestCase):
    def test_complete_snapshot_not_data_parity(self):
        r = a.compare(a.source_receipt(source()), a.target_receipt(target()))
        self.assertEqual(r["status"], "SCHEMA_SNAPSHOT_MATCH_NOT_ROW_PARITY")
        self.assertEqual(len(r["schema_matching"]), 9)
        self.assertTrue(r["legacy_preserved"])
        self.assertFalse(r["row_parity"])
        self.assertFalse(r["cutover_ready"])

    def test_nine_target_including_legacy_means_one_missing(self):
        r = a.compare(a.source_receipt(source()),
                      a.target_receipt(target(missing=["runner3-core"])))
        self.assertEqual(r["target_count"], 9)
        self.assertEqual(r["missing_on_target"], ["runner3-core"])
        self.assertEqual(r["status"], "SCHEMA_GAPS_FOUND")

    def test_missing_legacy_is_gap(self):
        r = a.compare(a.source_receipt(source()),
                      a.target_receipt(target(legacy=False)))
        self.assertFalse(r["legacy_preserved"])
        self.assertEqual(r["status"], "SCHEMA_GAPS_FOUND")

    def test_source_identity_missing_blocks(self):
        s = source()
        s["databases"].pop("runner3-core")
        with self.assertRaisesRegex(a.Blocked, "SOURCE_DATABASE_CENSUS_BAD"):
            a.source_receipt(s)

    def test_target_unknown_db_blocks(self):
        t = target()
        t["database_names"].append("unknown")
        t["database_schemas"]["unknown"] = target_db()
        with self.assertRaisesRegex(a.Blocked, "TARGET_DATABASE_CENSUS_BAD"):
            a.target_receipt(t)

    def test_source_payload_claim_blocks(self):
        s = source()
        s["target_row_parity_verified"] = True
        with self.assertRaisesRegex(a.Blocked, "SOURCE_CONTRACT_BAD"):
            a.source_receipt(s)

    def test_target_payload_claim_blocks(self):
        t = target()
        t["source_delete_allowed"] = True
        with self.assertRaisesRegex(a.Blocked, "TARGET_CONTRACT_BAD"):
            a.target_receipt(t)

    def test_ddl_mismatch(self):
        t = target()
        t["database_schemas"]["runner3-core"]["schema_objects"][0]["ddl_sha256"] = "a"*64
        r = a.compare(a.source_receipt(source()), a.target_receipt(t))
        self.assertIn("runner3-core", r["schema_mismatch"])

    def test_pk_mismatch(self):
        t = target()
        t["database_schemas"]["runner3-core"]["schema_objects"][0]["pk_columns"] = []
        r = a.compare(a.source_receipt(source()), a.target_receipt(t))
        self.assertIn("runner3-core", r["schema_mismatch"])

    def test_ddl_hash_malformed(self):
        s = source()
        s["databases"]["runner3-core"]["objects"][0]["ddl_sha256"] = "abc"
        with self.assertRaisesRegex(a.Blocked, "OBJECT_BAD"):
            a.source_receipt(s)

    def test_missing_table_metadata(self):
        s = source()
        s["databases"]["runner3-core"]["tables"] = {}
        s["databases"]["runner3-core"]["table_count"] = 0
        with self.assertRaisesRegex(a.Blocked, "TABLE_METADATA_MISSING"):
            a.source_receipt(s)

    def test_duplicate_pk(self):
        t = target()
        t["database_schemas"]["runner3-core"]["schema_objects"][0]["pk_columns"] = ["id", "id"]
        with self.assertRaisesRegex(a.Blocked, "PK_OR_COLUMNS_BAD"):
            a.target_receipt(t)

    def test_missing_table_declaration(self):
        t = target()
        t["database_schemas"]["runner3-core"]["table_count"] = 0
        with self.assertRaisesRegex(a.Blocked, "TARGET_COUNTS_BAD"):
            a.target_receipt(t)

    def test_digest_no_plaintext_schema(self):
        r = a.source_receipt(source())
        s = json.dumps(r)
        self.assertNotIn("items", s)
        self.assertNotIn("CREATE TABLE", s)
        self.assertNotIn("pk_columns", s)
        self.assertNotIn(HASH, s)

    def test_forged_parity_rejected(self):
        x = a.source_receipt(source())
        x["cutover_ready"] = True
        with self.assertRaisesRegex(a.Blocked, "RECEIPT_CONTRACT_BAD"):
            a.compare(x, a.target_receipt(target()))

    def test_comparison_runs_without_token(self):
        x = a.source_receipt(source())
        y = a.target_receipt(target(missing=["runner3-rss"]))
        with tempfile.TemporaryDirectory() as d:
            p = pathlib.Path(d)
            (p/"source.json").write_text(json.dumps(x))
            (p/"target.json").write_text(json.dumps(y))
            with mock.patch.dict(os.environ, {
                    "CLOUDFLARE_API_TOKEN": "", "CLOUDFLARE_TARGET_AUDIT_TOKEN": "",
                    "CF_TOKEN": ""}):
                rc = a.main(["--role", "compare", "--source", str(p/"source.json"),
                              "--target", str(p/"target.json"),
                              "--out", str(p/"report.json")])
            self.assertEqual(rc, 2)
            self.assertEqual(json.loads((p/"report.json").read_text())["missing_on_target"],
                             ["runner3-rss"])

    def test_compare_rejects_secret(self):
        with mock.patch.dict(os.environ, {"CLOUDFLARE_API_TOKEN": "synthetic"}):
            with self.assertRaisesRegex(a.Blocked, "COMPARE_SECRETS_PRESENT"):
                a.main(["--role", "compare", "--source", "/none", "--target", "/none",
                        "--out", "/none"])


    def test_targeted_scope_exact_two(self):
        x = a.source_receipt(source())
        y = a.target_receipt(target())
        self.assertEqual(set(x["targeted_objects"]), a.TARGETED)
        self.assertEqual(set(y["targeted_objects"]), a.TARGETED)

    def test_targeted_schema_identical_no_object_diff(self):
        report = a.compare(a.source_receipt(source()), a.target_receipt(target()))
        for db in a.TARGETED:
            details = report["targeted_object_diff"][db]
            self.assertFalse(details["source_only_object_ids"])
            self.assertFalse(details["target_only_object_ids"])
            self.assertFalse(details["changed_object_ids"])
            self.assertEqual(details["matching_object_count"], 1)

    def test_source_column_digest_missing_blocked(self):
        s = source()
        del s["databases"]["runner3-core"]["tables"]["items"]["columns_sha256"]
        with self.assertRaisesRegex(a.Blocked, "COLUMN_DIGEST_BAD"):
            a.source_receipt(s)

    def test_target_column_digest_malformed_blocked(self):
        t = target()
        t["database_schemas"]["runner3-core"]["schema_objects"][0]["columns_sha256"] = "abc"
        with self.assertRaisesRegex(a.Blocked, "COLUMN_DIGEST_BAD"):
            a.target_receipt(t)

    def test_one_column_change_fails_schema_and_objects(self):
        t = target()
        t["database_schemas"]["runner3-core"]["schema_objects"][0]["columns_sha256"] = "0"*64
        report = a.compare(a.source_receipt(source()), a.target_receipt(t))
        self.assertIn("runner3-core", report["schema_mismatch"])
        self.assertEqual(len(report["targeted_object_diff"]["runner3-core"]["changed_object_ids"]), 1)
        self.assertFalse(report["row_parity"])

    def test_source_only_view_per_object(self):
        s = source()
        s["databases"]["runner3-core"]["objects"].append(
            {"type": "view", "name": "missing_in_target", "ddl_sha256": HASH})
        report = a.compare(a.source_receipt(s), a.target_receipt(target()))
        self.assertEqual(len(report["targeted_object_diff"]["runner3-core"]["source_only_object_ids"]), 1)

    def test_target_only_index_per_object(self):
        t = target()
        db = t["database_schemas"]["runner3-content-intelligence"]
        db["schema_objects"].append(
            {"kind": "index", "name": "new_target_index", "ddl_sha256": HASH})
        db["schema_object_count"] += 1
        report = a.compare(a.source_receipt(source()), a.target_receipt(t))
        self.assertEqual(len(report["targeted_object_diff"]["runner3-content-intelligence"]["target_only_object_ids"]), 1)

    def test_missing_targeted_db_stays_explicit(self):
        report = a.compare(a.source_receipt(source()),
                           a.target_receipt(target(missing=["runner3-core"])))
        self.assertIn("runner3-core", report["missing_on_target"])
        self.assertNotIn("runner3-core", report["targeted_object_diff"])

    def test_forged_or_missing_targeted_receipt_rejected(self):
        x, y = a.source_receipt(source()), a.target_receipt(target())
        del y["targeted_objects"]["runner3-core"]
        with self.assertRaisesRegex(a.Blocked, "TARGETED_SCOPE_BAD"):
            a.compare(x, y)

    def test_detailed_receipts_do_not_expose_object_names(self):
        x, y = a.source_receipt(source()), a.target_receipt(target())
        report = a.compare(x, y)
        serialized = json.dumps([x, y, report])
        self.assertNotIn('"items"', serialized)
        self.assertNotIn('"pk_columns"', serialized)
        self.assertNotIn("CREATE TABLE", serialized)
        self.assertNotIn(COLS, serialized)
        self.assertFalse(report["deletion_parity"])


if __name__ == "__main__":
    unittest.main()
