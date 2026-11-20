import importlib.util
import pathlib
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "content_intelligence_client",
    ROOT / "scripts" / "content_intelligence_client.py",
)
MOD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MOD)


class ContentIntelligenceBatchTests(unittest.TestCase):
    def test_post_batches_respects_explicit_batch_size(self):
        rows = [{"item_id": str(i)} for i in range(23)]
        seen = []

        def fake_request(method, path, payload, core_url=None):
            seen.append(len(payload["rows"]))
            return {"applied": len(payload["rows"])}

        with mock.patch.object(MOD, "request_json", side_effect=fake_request):
            applied = MOD.post_batches("/content-intelligence/items", rows, None, batch_size=10)

        self.assertEqual(applied, 23)
        self.assertEqual(seen, [10, 10, 3])




class InterestSemanticBackfillTests(unittest.TestCase):
    def test_reconstruct_item_preserves_grounded_evidence(self):
        row = {
            "item_id": "https://example.com/1", "canonical_url": "https://example.com/1",
            "source_type": "web", "title": "A specific title",
            "metadata_json": '{"source_verified":true,"topic":"source-supported value"}',
        }
        item = MOD.reconstruct_interest_item(row)
        self.assertEqual(item["metadata"], {"source_verified": True, "topic": "source-supported value"})
        self.assertEqual(item["item_id"], row["item_id"])
        self.assertNotIn("metadata_json", item)

    def test_pending_enrichment_reuses_same_owner_and_verifies_d1(self):
        pending = [
            {"item_id": f"https://example.org/{n}", "canonical_url": f"https://example.org/{n}",
             "source_type": "web", "title": "AI agent workflow", "metadata_json": "{}"}
            for n in range(6)
        ]
        requests = []

        def fake_core(method, path, payload, *, core_url=None, timeout_seconds=30):
            requests.append((method, path, payload))
            return {"ok": True, "applied": len(payload["rows"]), "feature_model": "semantic-bridge-v4"}

        def fake_readback(dbid, ids, *, durable_only=False):
            self.assertEqual(dbid, "db-id")
            return set(ids)

        args = MOD.argparse.Namespace(limit=6, batch_size=3, core_url=None)
        with mock.patch.dict(MOD.os.environ, {"RUNNER3_CORE_TOKEN": "test-token"}), \
             mock.patch.object(MOD, "cloudflare_d1_id", return_value="db-id"), \
             mock.patch.object(MOD, "pending_semantic_interest", return_value=pending), \
             mock.patch.object(MOD, "existing_semantic_features", side_effect=fake_readback), \
             mock.patch.object(MOD, "request_json", side_effect=fake_core), \
             mock.patch("builtins.print") as output:
            self.assertEqual(MOD.cmd_enrich_pending(args), 0)

        self.assertEqual([len(x[2]["rows"]) for x in requests], [3, 3])
        self.assertTrue(all(x[1] == "/content-intelligence/items" for x in requests))
        proof = MOD.json.loads(output.call_args.args[0])
        self.assertEqual(proof["d1_verified_items"], 6)
        self.assertEqual(proof["events_added"], 0)

    def test_no_work_makes_no_billable_core_calls(self):
        args = MOD.argparse.Namespace(limit=25, batch_size=5, core_url=None)
        with mock.patch.dict(MOD.os.environ, {"RUNNER3_CORE_TOKEN": "test-token"}), \
             mock.patch.object(MOD, "cloudflare_d1_id", return_value="db-id"), \
             mock.patch.object(MOD, "pending_semantic_interest", return_value=[]), \
             mock.patch.object(MOD, "request_json") as core, \
             mock.patch("builtins.print"):
            self.assertEqual(MOD.cmd_enrich_pending(args), 0)
            core.assert_not_called()

    def test_hard_limit_blocks_unbounded_fanout(self):
        with self.assertRaisesRegex(RuntimeError, "hard limits"):
            MOD.cmd_enrich_pending(MOD.argparse.Namespace(limit=10000, batch_size=30, core_url=None))

    def test_failed_readback_stops_without_reporting_success(self):
        pending = [{"item_id":"https://example.org/1","canonical_url":"https://example.org/1",
                    "source_type":"web","title":"AI agent"}]
        args = MOD.argparse.Namespace(limit=1,batch_size=1,core_url=None)
        with mock.patch.dict(MOD.os.environ, {"RUNNER3_CORE_TOKEN":"test-token"}), \
             mock.patch.object(MOD,"cloudflare_d1_id",return_value="db-id"), \
             mock.patch.object(MOD,"pending_semantic_interest",return_value=pending), \
             mock.patch.object(MOD,"request_json",return_value={"ok":True,"applied":1,"feature_model":"semantic-bridge-v4"}), \
             mock.patch.object(MOD,"existing_semantic_features",return_value=set()):
            with self.assertRaisesRegex(RuntimeError, "readback incomplete"):
                MOD.cmd_enrich_pending(args)



class ManualInterestRefreshTests(unittest.TestCase):
    def test_refresh_uses_fixed_evidence_window_with_bounded_offset(self):
        with mock.patch.object(MOD, "cloudflare_d1_query", return_value=[]) as query:
            self.assertEqual(MOD.recent_semantic_interest("db-id", 50), [])
        sql, params = query.call_args.args[1:]
        self.assertIn("event_type='interest_saved'", sql)
        self.assertIn("LIMIT 25 OFFSET ?", sql)
        self.assertEqual(params, ["2026-11-14", "2026-11-21", 50])
        with self.assertRaisesRegex(RuntimeError, "offset not allowed"):
            MOD.recent_semantic_interest("db-id", 100)

    def test_refresh_reuses_items_owner_without_creating_events(self):
        rows = [{
            "item_id": "https://example.org/verified",
            "canonical_url": "https://example.org/verified",
            "source_type": "web", "title": "BTC investment thesis",
            "metadata_json": "{}",
        }]
        args = MOD.argparse.Namespace(offset=0, core_url=None)
        def fake_request(method, path, payload, *, core_url=None, timeout_seconds=30):
            self.assertEqual(method, "POST")
            self.assertEqual(path, "/content-intelligence/items")
            self.assertEqual(len(payload["rows"]), 1)
            return {"ok": True, "feature_model": "semantic-bridge-v4",
                    "applied": 1, "semantic_features": 1}
        with mock.patch.dict(MOD.os.environ, {"RUNNER3_CORE_TOKEN":"test-token"}), \
             mock.patch.object(MOD, "cloudflare_d1_id", return_value="db-id"), \
             mock.patch.object(MOD, "recent_semantic_interest", return_value=rows), \
             mock.patch.object(MOD, "existing_semantic_features", return_value={"https://example.org/verified"}), \
             mock.patch.object(MOD, "request_json", side_effect=fake_request), \
             mock.patch("builtins.print") as output:
            self.assertEqual(MOD.cmd_refresh_recent_interest(args), 0)
        proof=MOD.json.loads(output.call_args.args[0])
        self.assertEqual(proof["events_added"], 0)
        self.assertEqual(proof["feature_changes"], 1)
        self.assertEqual(proof["d1_verified_items"], 1)

    def test_refresh_no_work_short_circuits_core(self):
        args = MOD.argparse.Namespace(offset=75, core_url=None)
        with mock.patch.dict(MOD.os.environ, {"RUNNER3_CORE_TOKEN":"test-token"}), \
             mock.patch.object(MOD, "cloudflare_d1_id", return_value="db-id"), \
             mock.patch.object(MOD, "recent_semantic_interest", return_value=[]), \
             mock.patch.object(MOD, "request_json") as core, \
             mock.patch("builtins.print"):
            self.assertEqual(MOD.cmd_refresh_recent_interest(args), 0)
            core.assert_not_called()



if __name__ == "__main__":
    unittest.main()
