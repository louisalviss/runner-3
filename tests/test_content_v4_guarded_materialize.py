"""No-network tests for canonical v4 guarded materialization client."""
import contextlib
import io
import pathlib
import sys
import types
import unittest
from unittest.mock import patch

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))
import content_intelligence_client as ci


class GuardedV4MaterializationTest(unittest.TestCase):
    def setUp(self):
        self.args = types.SimpleNamespace(model_version="personal-v4", core_url=None)

    def test_clean_profile_does_not_force_score_recompute(self):
        seen = []

        def request(method, path, payload, **kwargs):
            seen.append((method, path, payload))
            return {"ok": True, "guarded": True, "model_version": "personal-v4", "status": "clean", "recomputed": False}

        with patch.object(ci, "request_json", side_effect=request):
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(ci.cmd_guarded_recompute(self.args), 0)
        self.assertEqual(seen, [("POST", "/content-intelligence/profile/recompute", {"model_version": "personal-v4"})])

    def test_failed_materializer_fails_closed(self):
        with patch.object(ci, "request_json", return_value={"ok": False, "guarded": True, "model_version": "personal-v4"}):
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(ci.cmd_guarded_recompute(self.args), 1)

    def test_wrong_model_rejected_before_call(self):
        self.args.model_version = "personal-v3"
        with patch.object(ci, "request_json") as call:
            with self.assertRaises(SystemExit):
                ci.cmd_guarded_recompute(self.args)
            call.assert_not_called()

    def test_unguarded_reply_rejected(self):
        with patch.object(ci, "request_json", return_value={"ok": True, "guarded": False, "model_version": "personal-v4"}):
            with self.assertRaises(RuntimeError):
                ci.cmd_guarded_recompute(self.args)


if __name__ == "__main__":
    unittest.main()
