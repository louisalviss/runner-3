"""All-synthetic guarded target append tests; NEVER contact Cloudflare."""
import copy
import importlib.util
import json
import pathlib
import sqlite3
import sys
import unittest
from unittest.mock import patch

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/"scripts"))
spec = importlib.util.spec_from_file_location(
    "insertguard", ROOT/"scripts/cloudflare_d1_recommendation_runs_guarded_insert.py")
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
SRC_TOKEN = "synthetic_source_token_123456789"
TGT_READ = "synthetic_target_audit_123456789"
TGT_WRITE = "synthetic_target_write_123456789"
BOOK = "00000001-00000001-00004000-abcdabcdef123456"


def meta():
    with sqlite3.connect(":memory:") as c:
        c.row_factory=sqlite3.Row
        c.execute('''CREATE TABLE recommendation_runs (
        render_id TEXT PRIMARY KEY, source_scope TEXT,
        item_count INTEGER DEFAULT 0, recommended_count INTEGER DEFAULT 0,
        exploration_ratio REAL, model_version TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP, metadata_json TEXT)''')
        return [dict(r) for r in c.execute(
            'PRAGMA table_xinfo("recommendation_runs")')]


def row(i):
    return {
        "render_id": "run-"+str(i),
        "source_scope": "rss",
        "item_count": 3,
        "recommended_count": 2,
        "exploration_ratio": 0.25,
        "model_version": "v1",
        "created_at": "2026-10-24T00:00:00Z",
        "metadata_json": "{}",
    }


class Fixtures:
    def __init__(self, source=None, target=None):
        self.source={x["render_id"]:copy.deepcopy(x)
                     for x in ([row(i) for i in range(47)] if source is None else source)}
        self.target={x["render_id"]:copy.deepcopy(x)
                     for x in ([row(i) for i in range(35)] if target is None else target)}
        self.bookmark=BOOK
        self.mutations=0
        self.reads=0

    def source_read(self, token,account,uuid,sql):
        assert token == SRC_TOKEN and account == m.SRC_ACCOUNT
        assert uuid == m.SRC_UUID and sql in (m.META_SQL,m.ROWS_SQL)
        return meta() if sql==m.META_SQL else [copy.deepcopy(self.source[k])
                                               for k in sorted(self.source)]

    def target_read(self, token,account,uuid,sql):
        assert token == TGT_READ and account == m.DST_ACCOUNT
        assert uuid == m.DST_UUID and sql in (m.META_SQL,m.ROWS_SQL)
        self.reads+=1
        return meta() if sql==m.META_SQL else [copy.deepcopy(self.target[k])
                                               for k in sorted(self.target)]

    def bookmark_read(self,token,url):
        assert token == TGT_READ and url == m.BOOKMARK_URLS[1]
        return {"bookmark":self.bookmark}

    def writer(self,token,sql,params):
        assert token == TGT_WRITE
        self.mutations+=1
        self.assert_sql(sql,params)
        coltokens=sql[len('INSERT INTO "recommendation_runs" ('+m.COLUMNS_SQL+
                          ') VALUES ('):-1].split(",")
        values=[]
        it=iter(params)
        for holder in coltokens:
            values.append(None if holder=="NULL" else next(it))
        # Simulate storage typed by fixed SQLite column affinities.
        converted=[]
        for idx,v in enumerate(values):
            if v is None:
                converted.append(None)
            elif idx in (2,3):
                converted.append(int(v))
            elif idx == 4:
                converted.append(float(v))
            else:
                converted.append(v)
        item=dict(zip(m.COLUMNS,converted))
        if item["render_id"] in self.target:
            raise m.Blocked("SIMULATED_UNIQUE_CONFLICT")
        self.target[item["render_id"]]=item

    def assert_sql(self,sql,params):
        assert sql.startswith('INSERT INTO "recommendation_runs" (')
        assert ";" not in sql
        assert sql.count("?")==len(params)
        assert all(type(p) is str for p in params)

    def run(self, **overrides):
        args=dict(
            source_token=SRC_TOKEN,target_read_token=TGT_READ,
            target_write_token=TGT_WRITE,expected_bookmark=BOOK,
            approval=m.APPROVAL,writer_ack="YES",recovery_ack="YES",
            source_reader=self.source_read,target_reader=self.target_read,
            bookmark_reader=self.bookmark_read,writer=self.writer,
        )
        args.update(overrides)
        return m.apply_gate(**args)


class GuardedInsert(unittest.TestCase):
    def test_fresh_12_missing_exact_append_simulation(self):
        f=Fixtures()
        report=f.run()
        self.assertEqual(report["status"],
                         "ONE_TABLE_ADDITIVE_INSERTS_VERIFIED_NOT_CUTOVER")
        self.assertEqual(report["new_rows_inserted"],12)
        self.assertEqual((report["source_rows_at_end"],report["target_rows_at_end"]),(47,47))
        self.assertEqual(f.mutations,12)
        self.assertFalse(report["cutover_ready"])
        self.assertFalse(report["all_d1_tables_verified"])

    def test_real_affinity_integral_source_insert_is_not_falsely_strict(self):
        src=[row(i) for i in range(47)]
        tgt=[copy.deepcopy(x) for x in src[:35]]
        for r in src: r["exploration_ratio"]=0
        for r in tgt: r["exploration_ratio"]=0
        f=Fixtures(source=src,target=tgt)
        result=f.run()
        self.assertEqual(result["new_rows_inserted"],12)
        self.assertEqual(f.mutations,12)
        self.assertEqual(result["strict_payload_difference_count_after_copy"],12)
        self.assertFalse(result["strict_row_parity_proven"])
        self.assertFalse(result["all_observed_rows_equal"])
        self.assertEqual(result["status"],
            "ONE_TABLE_AFFINITY_EQUIVALENT_NOT_STRICT_PARITY_HOLD")

    def test_inserted_real_value_accepts_either_original_or_real_storage(self):
        original=row(1);original["exploration_ratio"]=0
        real=copy.deepcopy(original);real["exploration_ratio"]=0.0
        self.assertTrue(m.same_as_inserted_storage(real,original))
        self.assertTrue(m.same_as_inserted_storage(original,original))

    def test_inserted_non_real_type_changed_is_not_equivalent(self):
        original=row(1);other=copy.deepcopy(original)
        other["item_count"]="3"
        self.assertFalse(m.same_as_inserted_storage(other,original))
        other=copy.deepcopy(original);other["metadata_json"]="DIFFERENT"
        self.assertFalse(m.same_as_inserted_storage(other,original))

    def test_existing_real_affinity_type_drift_is_still_preflight_conflict(self):
        src=[row(i) for i in range(47)]
        tgt=copy.deepcopy(src[:35])
        src[0]["exploration_ratio"]=0
        tgt[0]["exploration_ratio"]=0.0
        f=Fixtures(source=src,target=tgt)
        with self.assertRaisesRegex(m.Blocked,"WRITE_PREFLIGHT_CONFLICT"):
            f.run()
        self.assertEqual(f.mutations,0)

    def test_main_non_strict_affinity_holds_after_persisting_sanitized_counts(self):
        import tempfile
        with tempfile.TemporaryDirectory() as folder:
            report_path=pathlib.Path(folder)/"sanitized.json"
            f=Fixtures(
                source=[{**row(i),"exploration_ratio":0} for i in range(47)],
                target=[{**row(i),"exploration_ratio":0} for i in range(35)])
            prepared=f.run()
            self.assertFalse(prepared["strict_row_parity_proven"])
            with patch("sys.argv",["copier","--apply"]),patch.object(m,"OUT",report_path):
                with patch.object(m,"require_recent_solo_dryrun",return_value=True):
                    with patch.object(m,"apply_gate",return_value=prepared):
                        self.assertEqual(m.main(),2)
            sanitized=json.loads(report_path.read_text())
            self.assertEqual(sanitized["strict_payload_difference_count_after_copy"],12)
            self.assertNotIn("run-35",report_path.read_text())

    def test_existing_target_35_untouched(self):
        f=Fixtures()
        prior=copy.deepcopy(f.target)
        f.run()
        self.assertEqual({k:f.target[k] for k in prior},prior)

    def test_required_three_distinct_tokens(self):
        f=Fixtures()
        with self.assertRaisesRegex(m.Blocked,"THREE_DISTINCT"):
            f.run(target_write_token=TGT_READ)
        self.assertEqual(f.mutations,0)

    def test_missing_write_token(self):
        f=Fixtures()
        with self.assertRaisesRegex(m.Blocked,"THREE_DISTINCT"):
            f.run(target_write_token="")
        self.assertEqual(f.mutations,0)

    def test_wrong_manual_phrase(self):
        f=Fixtures()
        with self.assertRaisesRegex(m.Blocked,"EXPLICIT_TARGET_WRITE_APPROVAL"):
            f.run(approval="YES")
        self.assertEqual(f.mutations,0)

    def test_target_writer_quiescence_ack_missing(self):
        f=Fixtures()
        with self.assertRaisesRegex(m.Blocked,"EXPLICIT_TARGET_WRITE_APPROVAL"):
            f.run(writer_ack="")
        self.assertEqual(f.mutations,0)

    def test_row_recovery_ack_missing(self):
        f=Fixtures()
        with self.assertRaisesRegex(m.Blocked,"EXPLICIT_TARGET_WRITE_APPROVAL"):
            f.run(recovery_ack="NO")
        self.assertEqual(f.mutations,0)

    def test_absent_preserved_bookmark(self):
        f=Fixtures()
        with self.assertRaisesRegex(m.Blocked,"PRESERVED_PREAPPLY"):
            f.run(expected_bookmark="")
        self.assertEqual(f.mutations,0)

    def test_stale_bookmark_abort_before_writes(self):
        f=Fixtures()
        f.bookmark="a"*36
        with self.assertRaisesRegex(m.Blocked,"TARGET_BOOKMARK_MOVED"):
            f.run()
        self.assertEqual(f.mutations,0)

    def test_actual_missing_count_drift_blocks(self):
        f=Fixtures(source=[row(i) for i in range(47)],
                   target=[row(i) for i in range(36)])
        with self.assertRaisesRegex(m.Blocked,"WRITE_EXPECTED_12_DELTA_CHANGED"):
            f.run()
        self.assertEqual(f.mutations,0)

    def test_changed_existing_target_payload_blocks(self):
        target=[row(i) for i in range(35)]
        target[0]["metadata_json"]="changed"
        f=Fixtures(target=target)
        with self.assertRaisesRegex(m.Blocked,"WRITE_PREFLIGHT_CONFLICT"):
            f.run()
        self.assertEqual(f.mutations,0)

    def test_target_only_row_blocks(self):
        f=Fixtures(target=[row(i) for i in range(35)]+[row(100)])
        with self.assertRaisesRegex(m.Blocked,"WRITE_PREFLIGHT_CONFLICT"):
            f.run()
        self.assertEqual(f.mutations,0)

    def test_disallowed_semicolon_sql_blocks(self):
        sql,params=m.params_and_sql(row(5))
        with self.assertRaisesRegex(m.Blocked,"WRITE_SQL_NOT_ALLOWLISTED"):
            m.write_one(TGT_WRITE,sql+"; DROP TABLE x",params,
                        opener=lambda *args: self.fail("No HTTP permitted"))

    def test_null_columns_bind_as_sql_null(self):
        item=row(5)
        item["source_scope"]=None
        item["metadata_json"]=None
        sql,params=m.params_and_sql(item)
        self.assertEqual(sql.count("NULL"),2)
        self.assertEqual(sql.count("?"),6)
        self.assertNotIn("None",params)

    def test_sql_injection_remains_bound_param(self):
        item=row(5)
        item["metadata_json"]="'); DROP TABLE recommendation_runs; --"
        sql,params=m.params_and_sql(item)
        self.assertNotIn("DROP TABLE",sql)
        self.assertIn("DROP TABLE",params[-1])

    def test_write_response_must_change_exactly_one(self):
        class Resp:
            status=200
            def __init__(self,answer):self.answer=answer
            def __enter__(self):return self
            def __exit__(self,*args):return False
            def read(self,size):return json.dumps(self.answer).encode()
        sql,params=m.params_and_sql(row(1))
        for count in (0,2):
            with self.subTest(count=count),self.assertRaisesRegex(
                m.Blocked,"TARGET_INSERT_WRITE_COUNT_UNEXPECTED"):
                m.write_one(TGT_WRITE,sql,params,opener=lambda *a,**k:
                    Resp({"success":True,"result":[{"success":True,
                         "meta":{"changed_db":True,"changes":count}}]}))
    
    def test_target_write_route_is_exact(self):
        self.assertIn(m.DST_ACCOUNT,m.WRITE_URL)
        self.assertIn(m.DST_UUID,m.WRITE_URL)
        self.assertNotIn(m.SRC_ACCOUNT,m.WRITE_URL)
        self.assertNotIn("/restore",m.WRITE_URL)

    def test_external_target_writer_midway_halts_not_deletes(self):
        f=Fixtures()
        original=f.writer
        def inject(token,sql,params):
            original(token,sql,params)
            if f.mutations == 2:
                f.target["run-0"]["metadata_json"]="external-write"
        with self.assertRaisesRegex(m.Blocked,"TARGET_POST_INSERT_READBACK_HOLD"):
            f.run(writer=inject)
        self.assertEqual(f.mutations,2)
        self.assertIn("run-35",f.target)
        self.assertIn("run-36",f.target)

    def test_source_write_after_preflight_halts_not_deletes(self):
        f=Fixtures()
        original=f.writer
        def inject(token,sql,params):
            original(token,sql,params)
            if f.mutations == 12:
                f.source["run-47"]=row(47)
        with self.assertRaisesRegex(m.Blocked,"FINAL_SOURCE_CATCHUP_DRIFT"):
            f.run(writer=inject)
        self.assertEqual(f.mutations,12)
        self.assertEqual(len(f.target),47)

    def test_solo_proof_missing_blocks_main_before_any_d1_write(self):
        with patch("sys.argv",["copier","--apply"]):
            with patch.object(m,"require_recent_solo_dryrun",
                side_effect=m.SoloProofHold("SOLO_PROOF_STALE_OR_CLOCK_INVALID")):
                with patch.object(m,"apply_gate",
                    side_effect=AssertionError("remote D1 called without solo proof")):
                    self.assertEqual(m.main(),3)

    def test_workflow_requires_recent_manual_dryrun_job_no_cloudflare_secrets(self):
        text=(ROOT/".github/workflows/cloudflare-d1-recommendation-runs-guarded-insert.yml").read_text()
        self.assertIn("  recent-dryrun-gate:",text)
        jobs=text.split("  recent-dryrun-gate:",1)[1]
        no_cloudflare=jobs.split("  additive-write:",1)[0]
        self.assertNotIn("CLOUDFLARE_",no_cloudflare)
        self.assertIn("needs: recent-dryrun-gate",jobs)
        self.assertNotIn("environment: cloudflare-target-d1-writes",text)
        self.assertIn("D1_SOLO_DRYRUN_RUN_ID",text)
        self.assertIn("APPROVE_TARGET_ONLY_RECOMMENDATION_RUNS_12_INSERTS",text)

    def test_no_apply_flag_never_uses_credentials_or_calls_remote(self):
        with patch("sys.argv",["copier"]):
            with patch.object(m,"apply_gate",side_effect=AssertionError("remote")):
                self.assertEqual(m.main(),3)

    def test_read_token_and_bookmark_not_in_result(self):
        f=Fixtures()
        report=f.run()
        encoded=json.dumps(report)
        for val in (SRC_TOKEN,TGT_READ,TGT_WRITE,BOOK,"run-35"):
            self.assertNotIn(val,encoded)
        self.assertFalse(report["whole_database_restore_executed"])
        self.assertFalse(report["source_writer_quiescence_proven"])

if __name__=="__main__":
    unittest.main()
