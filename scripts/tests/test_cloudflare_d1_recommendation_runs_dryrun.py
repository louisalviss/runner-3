"""Synthetic-only acceptance for the eventual one-table additive D1 repair."""
import copy
import importlib.util
import pathlib
import sqlite3
import sys
import unittest
from unittest.mock import patch

ROOT=pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/"scripts"))
spec=importlib.util.spec_from_file_location(
    "d1_additive",ROOT/"scripts/cloudflare_d1_recommendation_runs_dryrun.py")
m=importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
SOURCE_TOKEN="synthetic_source_token_12345678"
TARGET_TOKEN="synthetic_target_token_12345678"

def meta():
    with sqlite3.connect(":memory:") as conn:
        conn.row_factory=sqlite3.Row
        conn.execute(m.SCHEMA_SQL)
        return [dict(x) for x in conn.execute('PRAGMA table_xinfo("recommendation_runs")')]

def record(n, metadata=None):
    return {
        "render_id":"run-"+str(n),"source_scope":"rss",
        "item_count":3,"recommended_count":2,
        "exploration_ratio":0.25,"model_version":"v1",
        "created_at":"2026-10-24 11:17:00",
        "metadata_json":("{}" if metadata is None else metadata),
    }

def fake_reader(source=None,target=None,src_meta=None,dst_meta=None,
                change_source=False,change_target=False):
    src=[record(1)] if source is None else source
    dst=copy.deepcopy(src) if target is None else target
    clock={"source":0,"target":0}
    def read(token,account,uid,sql):
        assert (token,account,uid) in (
            (SOURCE_TOKEN,m.SRC_ACCOUNT,m.SRC_UUID),
            (TARGET_TOKEN,m.DST_ACCOUNT,m.DST_UUID))
        if sql == m.META_SQL:
            return copy.deepcopy(src_meta if account==m.SRC_ACCOUNT and src_meta is not None
                                 else dst_meta if account==m.DST_ACCOUNT and dst_meta is not None
                                 else meta())
        assert sql == m.ROWS_SQL
        side="source" if account==m.SRC_ACCOUNT else "target"
        clock[side]+=1
        rows=copy.deepcopy(src if side=="source" else dst)
        if (side=="source" and change_source or side=="target" and change_target) and rows:
            rows[0]["metadata_json"] = "changed-" + str(clock[side])
        return rows
    return read


class BoundedReconciliation(unittest.TestCase):
    def test_real_observed_shape_47_source_35_target(self):
        source=[record(i) for i in range(47)]
        target=copy.deepcopy(source[:35])
        result=m.execute(SOURCE_TOKEN,TARGET_TOKEN,fake_reader(source,target))
        self.assertEqual(result["status"],"ADDITIVE_REHEARSAL_PASS_NOT_AUTHORIZED")
        self.assertEqual(result["source_rows"],47)
        self.assertEqual(result["target_rows"],35)
        self.assertEqual(result["would_insert_rows"],12)
        self.assertEqual(result["matching_existing_rows"],35)
        self.assertEqual(result["live_d1_writes"],0)
        self.assertFalse(result["cutover_ready"])
        self.assertFalse(result["target_d1_write_token_used"])

    def test_real_affinity_zero_integer_roundtrip_is_safe_in_scratch_only(self):
        source=[record(1), record(2)]
        for row in source:
            row["exploration_ratio"]=0
        target=copy.deepcopy(source[:1])
        report=m.execute(SOURCE_TOKEN,TARGET_TOKEN,fake_reader(source,target))
        self.assertEqual(report["would_insert_rows"],1)
        self.assertEqual(report["scratch_real_affinity_integer_inputs"],2)
        self.assertTrue(report["source_target_typed_comparison_not_normalized"])
        self.assertEqual(report["live_d1_writes"],0)

    def test_real_affinity_integer_and_float_difference_is_a_live_conflict(self):
        src=record(1)
        dst=copy.deepcopy(src)
        src["exploration_ratio"]=0
        dst["exploration_ratio"]=0.0
        with self.assertRaisesRegex(m.Blocked,"CONFLICT_OR_UNEXPLAINED"):
            m.execute(SOURCE_TOKEN,TARGET_TOKEN,
                      fake_reader(source=[src],target=[dst]))

    def test_real_affinity_decimal_source_remains_exact(self):
        source=[record(1),record(2)]
        source[1]["exploration_ratio"]=0.125
        report=m.execute(SOURCE_TOKEN,TARGET_TOKEN,
                         fake_reader(source=source,target=[]))
        self.assertEqual(report["would_insert_rows"],2)
        self.assertEqual(report["scratch_real_affinity_integer_inputs"],0)

    def test_bad_sqlite_real_text_value_aborts_without_coercion(self):
        source=record(1)
        source["exploration_ratio"]="0.25"
        with self.assertRaisesRegex(m.Blocked,"VALUE_AFFINITY_DRIFT"):
            m.execute(SOURCE_TOKEN,TARGET_TOKEN,
                      fake_reader(source=[source],target=[]))

    def test_bad_text_storage_type_aborts_without_coercion(self):
        source=record(1)
        source["source_scope"]=42
        with self.assertRaisesRegex(m.Blocked,"VALUE_AFFINITY_DRIFT"):
            m.execute(SOURCE_TOKEN,TARGET_TOKEN,
                      fake_reader(source=[source],target=[]))

    def test_real_affinity_large_integer_rejected(self):
        source=record(1)
        source["exploration_ratio"]=2**53 + 1
        with self.assertRaisesRegex(m.Blocked,"REAL_INTEGER_PRECISION_RISK"):
            m.execute(SOURCE_TOKEN,TARGET_TOKEN,
                      fake_reader(source=[source],target=[]))

    def test_idempotent_no_missing_rows(self):
        result=m.execute(SOURCE_TOKEN,TARGET_TOKEN,fake_reader())
        self.assertEqual(result["status"],"NO_DELTA_NOT_CUTOVER_PROOF")
        self.assertEqual(result["would_insert_rows"],0)

    def test_changed_target_payload_aborts(self):
        with self.assertRaisesRegex(m.Blocked,"CONFLICT_OR_UNEXPLAINED"):
            m.execute(SOURCE_TOKEN,TARGET_TOKEN,
                      fake_reader(target=[record(1,metadata='{"different":true}')]))

    def test_unknown_target_only_row_aborts_not_deleted(self):
        with self.assertRaisesRegex(m.Blocked,"CONFLICT_OR_UNEXPLAINED"):
            m.execute(SOURCE_TOKEN,TARGET_TOKEN,
                      fake_reader(source=[record(1)],target=[record(1),record(2)]))

    def test_source_writes_mid_capture_block(self):
        with self.assertRaisesRegex(m.Blocked,"UNSTABLE"):
            m.execute(SOURCE_TOKEN,TARGET_TOKEN,
                      fake_reader(change_source=True))

    def test_target_writes_mid_capture_block(self):
        with self.assertRaisesRegex(m.Blocked,"UNSTABLE"):
            m.execute(SOURCE_TOKEN,TARGET_TOKEN,
                      fake_reader(change_target=True))

    def test_too_many_missing_rows_aborts(self):
        with self.assertRaisesRegex(m.Blocked,"TOO_MANY_NEW_ROWS"):
            m.execute(SOURCE_TOKEN,TARGET_TOKEN,
                      fake_reader(source=[record(i) for i in range(52)],target=[]))

    def test_source_row_cap_aborts(self):
        with self.assertRaisesRegex(m.Blocked,"DRYRUN_ROW_BUDGET"):
            m.execute(SOURCE_TOKEN,TARGET_TOKEN,
                      fake_reader(source=[record(i) for i in range(251)],target=[]))

    def test_duplicate_pk_aborts(self):
        with self.assertRaisesRegex(m.Blocked,"BAD_OR_DUPLICATE"):
            m.execute(SOURCE_TOKEN,TARGET_TOKEN,
                      fake_reader(source=[record(1),record(1)]))

    def test_binary_blob_data_aborts(self):
        val=record(1)
        val["metadata_json"]=b"binary"
        with self.assertRaisesRegex(m.Blocked,"UNSUPPORTED_BLOB"):
            m.execute(SOURCE_TOKEN,TARGET_TOKEN,fake_reader(source=[val],target=[]))

    def test_dict_data_aborts(self):
        val=record(1)
        val["metadata_json"]={"secret":"private"}
        with self.assertRaisesRegex(m.Blocked,"UNSUPPORTED_BLOB"):
            m.execute(SOURCE_TOKEN,TARGET_TOKEN,fake_reader(source=[val],target=[]))

    def test_bad_type_affinity_aborts(self):
        x=meta()
        x[4]["type"]="TEXT"
        with self.assertRaisesRegex(m.Blocked,"SCHEMA_AFFINITY_CHANGED"):
            m.execute(SOURCE_TOKEN,TARGET_TOKEN,fake_reader(src_meta=x,dst_meta=x))

    def test_schema_metadata_drift_aborts(self):
        x=meta()
        x[0]["name"]="alternate_id"
        with self.assertRaisesRegex(m.Blocked,"SCHEMA_COLUMNS_DRIFT"):
            m.execute(SOURCE_TOKEN,TARGET_TOKEN,fake_reader(dst_meta=x))

    def test_null_optional_column_safe(self):
        x=record(1)
        x["metadata_json"]=None
        x["exploration_ratio"]=None
        result=m.execute(SOURCE_TOKEN,TARGET_TOKEN,fake_reader(source=[x],target=[]))
        self.assertEqual(result["would_insert_rows"],1)

    def test_bad_primary_key_aborts(self):
        x=record(1);x["render_id"]=""
        with self.assertRaisesRegex(m.Blocked,"BAD_OR_DUPLICATE"):
            m.execute(SOURCE_TOKEN,TARGET_TOKEN,fake_reader(source=[x],target=[]))

    def test_sqlite_roundtrip_rejects_type_coercion(self):
        x=record(1);x["item_count"]="3"
        with self.assertRaisesRegex(m.Blocked,"VALUE_AFFINITY_DRIFT"):
            m.execute(SOURCE_TOKEN,TARGET_TOKEN,fake_reader(source=[x],target=[]))

    def test_tokens_must_differ(self):
        with self.assertRaisesRegex(m.Blocked,"SEPARATE_READ_TOKENS_REQUIRED"):
            m.execute(SOURCE_TOKEN,SOURCE_TOKEN,fake_reader())

    def test_existing_rows_preserved_after_simulation(self):
        src=[record(1),record(2),record(3)]
        tgt=copy.deepcopy(src[:2])
        result=m.execute(SOURCE_TOKEN,TARGET_TOKEN,fake_reader(src,tgt))
        self.assertEqual(result["matching_existing_rows"],2)
        self.assertEqual(result["would_insert_rows"],1)

    def test_safe_report_never_exports_keys_or_payloads(self):
        result=m.execute(SOURCE_TOKEN,TARGET_TOKEN,fake_reader(
            source=[record(1,metadata="private payload"),record(2)],
            target=[record(1,metadata="private payload")]))
        content=str(result)
        self.assertNotIn("private payload",content)
        self.assertNotIn("run-1",content)
        self.assertNotIn("run-2",content)
        self.assertFalse(result["writer_quiescence_proven"])
        self.assertFalse(result["rollback_readiness_proven"])

    def test_only_production_allowlisted_read_queries(self):
        self.assertEqual(m.META_SQL,'PRAGMA table_xinfo("recommendation_runs")')
        self.assertIn('ORDER BY "render_id" LIMIT 251',m.ROWS_SQL)
        text=(ROOT/"scripts/cloudflare_d1_recommendation_runs_dryrun.py").read_text()
        self.assertIn("live_d1_writes",text)
        self.assertNotIn("urllib.request.urlopen",text)
        self.assertNotIn("cloudflare.com/client/v4",text)

if __name__=="__main__":
    unittest.main()
