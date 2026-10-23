"""Synthetic-only keyed receipt validation; never uses Cloudflare or secrets."""
import importlib.util
import json
import pathlib
import tempfile
import unittest

MODULE_PATH = pathlib.Path(__file__).resolve().parents[1] / "cloudflare_d1_keyed_parity_offline.py"
spec = importlib.util.spec_from_file_location("d1_parity", MODULE_PATH)
p = importlib.util.module_from_spec(spec)
spec.loader.exec_module(p)


def h(n):
    return f"{n:064x}"


def receipt(role, rows=((1, 11), (2, 22)), **kw):
    base = dict(format=p.VERSION, role=role, database="runner3-content-intelligence",
                table="user_content_events", pk_columns=["id"],
                schema_sha256=h(501), capture_window="capture_20261023_001",
                hmac_key_id="session-key-domain-01", capture_complete=True,
                rows=[dict(key_hmac=h(k), payload_hmac=h(v)) for k, v in rows])
    base.update(kw)
    return base


class OfflineContract(unittest.TestCase):
    def test_exact_match_never_proves_cutover(self):
        r = p.compare(receipt("source"), receipt("target"))
        self.assertEqual(r["status"], "DIGESTS_MATCH_NOT_CUTOVER_PROOF")
        self.assertEqual(r["matching"], 2)
        self.assertFalse(r["row_parity_verified"])
        self.assertFalse(r["deletion_parity_verified"])
        self.assertFalse(r["cutover_ready"])

    def test_source_target_only_and_changed_are_separate(self):
        a = receipt("source", ((1, 11), (2, 22), (3, 33)))
        b = receipt("target", ((1, 99), (2, 22), (4, 44)))
        r = p.compare(a, b)
        self.assertEqual((r["source_only"], r["target_only_unresolved"],
                          r["payload_different"], r["matching"]), (1, 1, 1, 1))
        self.assertEqual(r["status"], "DATA_DIFFERENCES_HOLD")
        self.assertFalse(r["source_deleted_proven"])

    def test_target_only_cannot_be_called_deletion(self):
        r = p.compare(receipt("source", ()), receipt("target", ((1, 11),)))
        self.assertEqual(r["target_only_unresolved"], 1)
        self.assertFalse(r["source_deleted_proven"])

    def test_same_count_changed_payload(self):
        r = p.compare(receipt("source", ((1, 11),)), receipt("target", ((1, 99),)))
        self.assertEqual(r["payload_different"], 1)
        self.assertEqual(r["source_only"], 0)

    def test_incomplete_capture_suppresses_diffs(self):
        r = p.compare(receipt("source", capture_complete=False), receipt("target"))
        self.assertEqual(r["status"], "INCOMPLETE_CAPTURE_HOLD")
        self.assertIsNone(r["matching"])

    def test_schema_mismatch_suppresses_diffs(self):
        r = p.compare(receipt("source"), receipt("target", schema_sha256=h(502)))
        self.assertEqual(r["status"], "SCHEMA_MISMATCH_HOLD")
        self.assertIsNone(r["source_only"])

    def test_wrong_hmac_key_domain_blocked(self):
        with self.assertRaisesRegex(p.Blocked, "UNPAIRED_CAPTURE_OR_KEY_DOMAIN"):
            p.compare(receipt("source"), receipt("target", hmac_key_id="different-01"))

    def test_wrong_capture_window_blocked(self):
        with self.assertRaises(p.Blocked):
            p.compare(receipt("source"), receipt("target", capture_window="capture_20261023_002"))

    def test_wrong_pk_columns_blocked(self):
        with self.assertRaises(p.Blocked):
            p.compare(receipt("source"), receipt("target", pk_columns=["item_id"]))

    def test_duplicate_pk_fingerprint_blocked(self):
        with self.assertRaisesRegex(p.Blocked, "DUPLICATE_PRIMARY_KEY_FINGERPRINT"):
            p.compare(receipt("source", ((1, 11), (1, 22))), receipt("target"))

    def test_no_raw_row_column_values_permitted(self):
        record = receipt("source")
        record["rows"][0]["item_id"] = "sensitive"
        with self.assertRaisesRegex(p.Blocked, "RAW_OR_INVALID_ROW_DATA"):
            p.compare(record, receipt("target"))

    def test_no_secret_field_permitted(self):
        record = receipt("source", token="secret")
        with self.assertRaisesRegex(p.Blocked, "INVALID_RECEIPT_FIELDS"):
            p.compare(record, receipt("target"))

    def test_nonboolean_complete_rejected(self):
        with self.assertRaisesRegex(p.Blocked, "INVALID_COMPLETENESS"):
            p.compare(receipt("source", capture_complete="true"), receipt("target"))

    def test_mutated_role_rejected(self):
        with self.assertRaisesRegex(p.Blocked, "ROLE_OR_FORMAT_MISMATCH"):
            p.compare(receipt("target"), receipt("source"))

    def test_bad_sha_rejected(self):
        bad = receipt("target", ((1, 11),))
        bad["rows"][0]["key_hmac"] = "raw"
        with self.assertRaisesRegex(p.Blocked, "RAW_OR_INVALID_ROW_DATA"):
            p.compare(receipt("source", ((1, 11),)), bad)

    def test_output_contains_no_hmacs_or_raw_keys(self):
        r = p.compare(receipt("source"), receipt("target"))
        encoded = json.dumps(r)
        self.assertNotIn(h(1), encoded)
        self.assertNotIn(h(11), encoded)
        self.assertNotIn("key_hmac", encoded)

    def test_cli_offline_json(self):
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            s, t, out = (root / n for n in ("source.json", "target.json", "result.json"))
            s.write_text(json.dumps(receipt("source")))
            t.write_text(json.dumps(receipt("target")))
            self.assertEqual(p.main(["--source", str(s), "--target", str(t), "--out", str(out)]), 2)
            self.assertTrue(out.exists())
            self.assertFalse(json.loads(out.read_text())["cutover_ready"])

    def test_cli_blocks_input_overwrite(self):
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            s, t = (root / n for n in ("source.json", "target.json"))
            s.write_text(json.dumps(receipt("source")))
            t.write_text(json.dumps(receipt("target")))
            self.assertEqual(p.main(["--source", str(s), "--target", str(t), "--out", str(s)]), 3)

    def test_wrong_database_blocked(self):
        with self.assertRaises(p.Blocked):
            p.compare(receipt("source"), receipt("target", database="runner3-core"))

    def test_excess_rows_blocked(self):
        too_many = receipt("source")
        too_many["rows"] = [{}] * (p.MAX_ROWS + 1)
        with self.assertRaisesRegex(p.Blocked, "INVALID_ROW_SET"):
            p.compare(too_many, receipt("target"))

    def test_composite_pk_supported(self):
        r = p.compare(receipt("source", pk_columns=["item_id", "score_type", "model_version"]),
                      receipt("target", pk_columns=["item_id", "score_type", "model_version"]))
        self.assertEqual(r["matching"], 2)


if __name__ == "__main__":
    unittest.main()
