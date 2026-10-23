"""Only synthetic schemas and the already-pinned public-source 33 DDL checks."""
import hashlib
import importlib.util
import json
import os
import pathlib
import sqlite3
import stat
import sys
import tempfile
import unittest
import zipfile
from unittest.mock import patch

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
SCRIPT = ROOT / "scripts/cloudflare_d1_final_39_private_bundle.py"
spec = importlib.util.spec_from_file_location("d1review", SCRIPT)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

SCHEMAS = {
    m.CORE: [
        ("table", "d1_migrations", 'CREATE TABLE "d1_migrations"(name TEXT PRIMARY KEY, applied_at TEXT)'),
        ("table", "r2_receipts", "CREATE TABLE r2_receipts(request_id TEXT PRIMARY KEY, bytes INTEGER)"),
        ("table", "typed_kv", "CREATE TABLE typed_kv(k TEXT PRIMARY KEY, value TEXT)"),
    ],
    m.CONTENT: [
        ("table", "link_interest_events", "CREATE TABLE link_interest_events(id INTEGER PRIMARY KEY, platform TEXT, sent_at INTEGER)"),
        ("index", "idx_link_interest_platform", "CREATE INDEX idx_link_interest_platform ON link_interest_events(platform)"),
        ("index", "idx_link_interest_sent_at", "CREATE INDEX idx_link_interest_sent_at ON link_interest_events(sent_at)"),
    ],
}


def fake_receipt():
    pins, data = {}, {}
    for db, objects in SCHEMAS.items():
        rows, lookup = [], {}
        with sqlite3.connect(":memory:") as con:
            con.row_factory = sqlite3.Row
            for kind, name, sql in objects:
                con.execute(sql)
                actual = con.execute("SELECT sql FROM sqlite_master WHERE name=?", (name,)).fetchone()[0]
                columns = [dict(row) for row in con.execute(
                    'PRAGMA table_xinfo("' + name + '")')] if kind == "table" else None
                hashval = m.table_metadata(kind, name, actual, columns)
                ident = m.digest([kind,name])
                lookup[ident] = hashval
                rows.append(dict(kind=kind,name=name,ddl=actual,object_id=ident,
                                 source_metadata_sha256=hashval))
        pins[db] = lookup
        data[db] = rows
    report = dict(format="d1-six-applied-schema-source-v1",
                  source_account_id=m.ACCOUNT, source_schema_reference_run=39826582807,
                  evidence="READ_ONLY_SQLITE_MASTER_AND_TABLE_XINFO_ONLY",
                  object_count=6, source_query_count=6, raw_application_rows_read=0,
                  source_d1_writes=0, target_d1_queries=0, target_d1_writes=0,
                  r2_requests=0,worker_deploys=0,row_parity_verified=False,
                  cutover_ready=False,databases=data)
    return report,pins


class PrivateBundle(unittest.TestCase):
    def test_valid_six_source_objects(self):
        receipt, pins = fake_receipt()
        out = m.check_receipt(receipt,pins)
        self.assertEqual(len(out[m.CORE]),3)
        self.assertEqual(len(out[m.CONTENT]),3)
        self.assertEqual([k for k,_,_,_ in out[m.CONTENT]],
                         ["table","index","index"])

    def test_build_complete_review_does_not_execute_d1(self):
        receipt, pins = fake_receipt()
        result = m.build_review(ROOT,receipt,pins)
        self.assertEqual(set(result),{m.CORE,m.CONTENT})
        self.assertIn("CREATE TABLE typed_kv",result[m.CORE])
        self.assertIn("CREATE TABLE link_interest_events",result[m.CONTENT])
        self.assertIn("PRIVATE REVIEW ONLY",result[m.CORE])
        self.assertIn("cutover=false",result[m.CONTENT])
        self.assertNotIn("https://api.cloudflare.com",repr(result))
        self.assertNotIn("INSERT INTO",repr(result))

    def test_core_has_21_and_ci_has_18_total_statements(self):
        receipt,pins=fake_receipt()
        files=m.build_review(ROOT,receipt,pins)
        core=files[m.CORE]
        ci=files[m.CONTENT]
        self.assertEqual(core.count("CREATE TABLE IF NOT EXISTS"),9)
        self.assertEqual(core.count("CREATE INDEX IF NOT EXISTS"),9)
        self.assertEqual(core.count("CREATE TABLE ") - core.count("CREATE TABLE IF NOT EXISTS"),3)
        self.assertEqual(ci.count("CREATE TRIGGER IF NOT EXISTS"),1)
        self.assertEqual(ci.count("CREATE TABLE IF NOT EXISTS"),2)
        self.assertEqual(ci.count("CREATE INDEX IF NOT EXISTS"),11)
        self.assertEqual(ci.count("CREATE UNIQUE INDEX IF NOT EXISTS"),1)

    def test_bad_account_blocks(self):
        a,p=fake_receipt();a["source_account_id"]="wrong"
        with self.assertRaisesRegex(m.Hold,"SOURCE_RECEIPT_CONTRACT"):
            m.check_receipt(a,p)

    def test_content_row_fields_forbidden(self):
        a,p=fake_receipt();a["databases"][m.CORE][0]["row_value"]="not allowed"
        with self.assertRaisesRegex(m.Hold,"RAW_ROW_OR_UNEXPECTED"):
            m.check_receipt(a,p)

    def test_extra_ddl_statement_forbidden(self):
        a,p=fake_receipt()
        a["databases"][m.CORE][0]["ddl"] += "; DROP TABLE x"
        with self.assertRaisesRegex(m.Hold,"NON_CREATE_OR_UNSAFE"):
            m.check_receipt(a,p)

    def test_updated_real_source_statement_fails_pinned_metadata(self):
        a,p=fake_receipt()
        a["databases"][m.CORE][0]["ddl"] = a["databases"][m.CORE][0]["ddl"].replace(
            "applied_at TEXT","applied_at INTEGER")
        with self.assertRaisesRegex(m.Hold,"SCRATCH_SOURCE_DDL_FINGERPRINT"):
            m.check_receipt(a,p)

    def test_changed_pin_fails(self):
        a,p=fake_receipt()
        a["databases"][m.CONTENT][0]["source_metadata_sha256"]="0"*64
        with self.assertRaisesRegex(m.Hold,"SOURCE_OBJECT_PIN_MISMATCH"):
            m.check_receipt(a,p)

    def test_missing_schema_object_fails(self):
        a,p=fake_receipt()
        a["databases"][m.CORE].pop()
        with self.assertRaisesRegex(m.Hold,"SIX_OBJECT_CENSUS_INVALID"):
            m.check_receipt(a,p)

    def test_row_read_or_target_contact_flag_fails(self):
        for field in ("raw_application_rows_read","source_d1_writes",
                      "target_d1_queries","target_d1_writes","r2_requests"):
            a,p=fake_receipt()
            a[field]=1
            with self.subTest(field=field),self.assertRaisesRegex(
                m.Hold,"SOURCE_RECEIPT_CONTRACT"):
                m.check_receipt(a,p)

    def test_duplicate_schema_object_rejected(self):
        a,p=fake_receipt();a["databases"][m.CORE][1]=dict(a["databases"][m.CORE][0])
        with self.assertRaisesRegex(m.Hold,"DUPLICATE_SOURCE_OBJECT"):
            m.check_receipt(a,p)

    def test_read_archive_sha_and_member_are_exact(self):
        a,_=fake_receipt()
        with tempfile.TemporaryDirectory() as td:
            file=pathlib.Path(td)/"review.zip"
            with zipfile.ZipFile(file,"w") as z:
                z.writestr(m.RECEIPT_MEMBER,json.dumps(a))
            digest=hashlib.sha256(file.read_bytes()).hexdigest()
            self.assertEqual(m.read_archive(file,expected_sha=digest)["object_count"],6)
            with self.assertRaisesRegex(m.Hold,"ARTIFACT_SHA256_MISMATCH"):
                m.read_archive(file,expected_sha="0"*64)

    def test_archive_other_member_rejected(self):
        a,_=fake_receipt()
        with tempfile.TemporaryDirectory() as td:
            path=pathlib.Path(td)/"review.zip"
            with zipfile.ZipFile(path,"w") as z:z.writestr("evil.txt",json.dumps(a))
            digest=hashlib.sha256(path.read_bytes()).hexdigest()
            with self.assertRaisesRegex(m.Hold,"ARTIFACT_MEMBERS_INVALID"):
                m.read_archive(path,expected_sha=digest)

    def test_storage_private_and_exclusive(self):
        a,p=fake_receipt()
        generated=m.build_review(ROOT,a,p)
        with tempfile.TemporaryDirectory() as td:
            output=pathlib.Path(td)/"restricted"
            self.assertEqual(m.store_private(output,generated),2)
            self.assertEqual(stat.S_IMODE(output.stat().st_mode)&0o077,0)
            for name in m.OUTPUTS.values():
                file=output/name
                self.assertTrue(file.is_file())
                self.assertEqual(stat.S_IMODE(file.stat().st_mode)&0o077,0)
            with self.assertRaisesRegex(m.Hold,"OUTPUT_ALREADY_EXISTS"):
                m.store_private(output,generated)

    def test_symlink_destination_rejected(self):
        a,p=fake_receipt()
        generated=m.build_review(ROOT,a,p)
        with tempfile.TemporaryDirectory() as td:
            root=pathlib.Path(td)
            real=root/"safe";real.mkdir()
            link=root/"link";link.symlink_to(real)
            with self.assertRaisesRegex(m.Hold,"OUTPUT_DIRECTORY_INVALID"):
                m.store_private(link,generated)

    def test_reference_artifact_pin_is_64_hex(self):
        self.assertEqual(len(m.ARCHIVE_SHA256),64)
        self.assertEqual(m.RUN_ID,39987228477)
        self.assertEqual(sum(map(len,m.GAPS.values())),6)


if __name__=="__main__":
    unittest.main()
