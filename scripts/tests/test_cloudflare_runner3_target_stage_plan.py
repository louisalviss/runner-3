"""Synthetic only: no Cloudflare, R2, tokens, deployment, or SSH calls."""
import copy
import importlib.util
import json
import pathlib
import unittest

SCRIPT = pathlib.Path(__file__).resolve().parents[1] / "cloudflare_runner3_target_stage_plan.py"
SPEC = importlib.util.spec_from_file_location("stage", SCRIPT)
stage = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(stage)


def fixtures():
    src = json.loads(stage.SOURCE.read_text(encoding="utf-8"))
    hist = json.loads(stage.DRAFT.read_text(encoding="utf-8"))
    return src, hist


class StagePlanContract(unittest.TestCase):
    def test_normal_plan_is_non_deployable(self):
        result = stage.make_plan(*fixtures())
        self.assertEqual(result["status"], "OFFLINE_REVIEW_ONLY_NOT_DEPLOYABLE")
        self.assertFalse(result["cutover_ready"])
        self.assertFalse(result["target_binding_ids_freshly_verified"])
        self.assertFalse(result["live_row_parity_verified"])
        self.assertFalse(result["target_worker_exists_verified"])
        self.assertTrue(result["no_routes_no_public_deployment"])

    def test_exact_bindings_and_alias_preserved(self):
        r = stage.make_plan(*fixtures())
        self.assertEqual(len(r["d1_bindings"]), 8)
        self.assertEqual(r["d1_unique_target_candidates"], 6)
        a = {x["binding"]: x["target_id_candidate_historical"] for x in r["d1_bindings"]}
        self.assertEqual(a["OPPORTUNITY_DB"], a["BUSINESS_OPPORTUNITY_DB"])
        self.assertEqual(a["TASK_CONTEXT_DB"], a["CONTEXT_INDEX_DB"])

    def test_historical_target_never_source_uuid(self):
        src, hist = fixtures()
        old_ids = {x["database_id"] for x in src["d1_databases"]}
        result = stage.make_plan(src, hist)
        self.assertFalse(old_ids.intersection(
            {x["target_id_candidate_historical"] for x in result["d1_bindings"]}))

    def test_crons_and_r2_and_service_inhibited(self):
        r = stage.make_plan(*fixtures())
        self.assertTrue(r["cron_disabled_in_stage"])
        self.assertEqual(r["source_cron_for_future_cutover_only"], ["17 * * * *"])
        self.assertEqual(r["r2_bindings_inhibited"], ["ARTIFACTS", "AUDIO_MEDIA"])
        self.assertEqual(r["service_bindings_inhibited"], ["RSS_FASTLANE"])
        self.assertEqual(r["r2_requests"], r["worker_deploys"])
        self.assertEqual(r["target_d1_writes"], 0)

    def test_changed_source_uuid_blocks(self):
        src, hist = fixtures()
        src["d1_databases"][0]["database_id"] = "00000000-0000-0000-0000-000000000123"
        with self.assertRaisesRegex(stage.Blocked, "D1_IDENTITY_OR_PARITY_DRIFT"):
            stage.make_plan(src, hist)

    def test_wrong_target_account_blocks(self):
        src, hist = fixtures()
        hist["target_account_id"] = stage.SOURCE_ACCOUNT
        with self.assertRaisesRegex(stage.Blocked, "HISTORY_SCOPE_DRIFT"):
            stage.make_plan(src, hist)

    def test_source_id_reused_as_target_blocks(self):
        src, hist = fixtures()
        hist["bindings"][0]["historical_target_database_id"] = hist["bindings"][0]["source_database_id"]
        with self.assertRaisesRegex(stage.Blocked, "D1_IDENTITY_OR_PARITY_DRIFT"):
            stage.make_plan(src, hist)

    def test_unexpected_binding_blocks(self):
        src, hist = fixtures()
        src["d1_databases"][0]["binding"] = "UNEXPECTED_DB"
        with self.assertRaisesRegex(stage.Blocked, "D1_BINDING_IDENTITY_DRIFT"):
            stage.make_plan(src, hist)

    def test_duplicate_binding_blocks(self):
        src, hist = fixtures()
        src["d1_databases"][1] = copy.deepcopy(src["d1_databases"][0])
        with self.assertRaises(stage.Blocked):
            stage.make_plan(src, hist)

    def test_target_alias_divergence_blocks(self):
        src, hist = fixtures()
        for b in hist["bindings"]:
            if b["binding"] == "BUSINESS_OPPORTUNITY_DB":
                b["historical_target_database_id"] = "00000000-0000-0000-0000-000000000123"
        with self.assertRaisesRegex(stage.Blocked, "TARGET_ALIAS_DIVERGENCE"):
            stage.make_plan(src, hist)

    def test_auto_enable_cron_blocks(self):
        src, hist = fixtures()
        src["triggers"]["crons"] = ["* * * * *"]
        with self.assertRaisesRegex(stage.Blocked, "CRON_EXPECTATION_DRIFT"):
            stage.make_plan(src, hist)

    def test_source_origin_changes_block(self):
        src, hist = fixtures()
        src["vars"]["RSS_READER_PUBLIC_ORIGIN"] = "https://new-target.workers.dev"
        with self.assertRaisesRegex(stage.Blocked, "SOURCE_ORIGIN_DRIFT"):
            stage.make_plan(src, hist)

    def test_unexpected_r2_binding_blocks(self):
        src, hist = fixtures()
        src["r2_buckets"].append({"binding": "UNSAFE", "bucket_name": "bucket"})
        with self.assertRaisesRegex(stage.Blocked, "SERVICE_OR_R2_EXPECTATION_DRIFT"):
            stage.make_plan(src, hist)

    def test_history_parity_claim_blocks(self):
        src, hist = fixtures()
        hist["bindings"][0]["current_target_parity_verified"] = True
        with self.assertRaisesRegex(stage.Blocked, "D1_IDENTITY_OR_PARITY_DRIFT"):
            stage.make_plan(src, hist)

    def test_committed_plan_is_in_sync(self):
        self.assertEqual(stage.main(["--check"]), 0)

    def test_plan_has_no_old_worker_url_or_credentials(self):
        result = json.dumps(stage.make_plan(*fixtures()))
        self.assertNotIn("ducduy2411.workers.dev", result)
        self.assertNotIn("CLOUDFLARE_API_TOKEN", result)
        self.assertNotIn("CLOUDFLARE_TARGET_AUDIT_TOKEN", result)


if __name__ == "__main__":
    unittest.main()
