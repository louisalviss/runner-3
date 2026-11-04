"""No-network regression for signed D1 account-wide preflight."""
import contextlib
import io
import pathlib
import sys
import types
import unittest
from unittest.mock import patch

sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/"scripts"))
import content_intelligence_client as ci

class GuardedV4MaterializationTest(unittest.TestCase):
    def setUp(self):
        self.args=types.SimpleNamespace(model_version="personal-v4",core_url=None,
            seed_score_cache_if_missing=False,preflight_receipt_file="verified.json")
        self.receipt={"ok":True,"runId":"42","runAttempt":"1"}
        a=patch.object(ci,"load_seed_preflight_receipt",return_value=self.receipt)
        b=patch.object(ci,"github_seed_oidc_token",return_value="signed.jwt.token")
        a.start();b.start()
        self.addCleanup(a.stop);self.addCleanup(b.stop)

    def test_clean_profile_needs_signed_preflight(self):
        seen=[]
        def request(method,path,payload,**kw):
            seen.append((method,path,payload,kw.get("extra_headers")))
            return {"ok":True,"guarded":True,"model_version":"personal-v4",
                    "status":"clean","recomputed":False}
        with patch.object(ci,"request_json",side_effect=request):
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(ci.cmd_guarded_recompute(self.args),0)
        self.assertEqual(seen,[("POST","/content-intelligence/profile/recompute",
            {"model_version":"personal-v4","preflight_receipt":self.receipt},
            {"X-Runner3-Seed-OIDC":"signed.jwt.token"})])

    def test_seed_same_authorization(self):
        self.args.seed_score_cache_if_missing=True
        seen=[]
        def request(method,path,payload,**kw):
            seen.append((payload,kw.get("extra_headers")))
            return {"ok":True,"guarded":True,"model_version":"personal-v4",
                    "status":"score_cache_seed_debounced","recomputed":False}
        with patch.object(ci,"request_json",side_effect=request):
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(ci.cmd_guarded_recompute(self.args),0)
        self.assertEqual(seen,[({"model_version":"personal-v4","preflight_receipt":self.receipt,
            "seed_score_cache_if_missing":True},{"X-Runner3-Seed-OIDC":"signed.jwt.token"})])

    def test_preflight_missing_fails_before_network(self):
        with (patch.object(ci,"load_seed_preflight_receipt",side_effect=RuntimeError("PREFLIGHT_REQUIRED")),
              patch.object(ci,"request_json") as network):
            with self.assertRaisesRegex(RuntimeError,"PREFLIGHT_REQUIRED"):
                ci.cmd_guarded_recompute(self.args)
            network.assert_not_called()

    def test_preflight_receipt_run_mismatch(self):
        import json,tempfile,os
        with tempfile.NamedTemporaryFile(mode="w+",encoding="utf-8") as tmp:
            json.dump({"ok":True,"runId":"bad","runAttempt":"1"},tmp);tmp.flush()
            # setUp mocks the loader for API contract tests. Exercise the
            # REAL parser for the mismatched-run security regression.
            self.loaded.stop()
            try:
                with patch.dict(os.environ,{"GITHUB_RUN_ID":"42","GITHUB_RUN_ATTEMPT":"1"}):
                    with self.assertRaisesRegex(RuntimeError,"RUN_MISMATCH"):
                        ci.load_seed_preflight_receipt(tmp.name)
            finally:
                self.loaded.start()

    def test_failed_result_holds(self):
        with patch.object(ci,"request_json",return_value={
            "ok":False,"guarded":True,"model_version":"personal-v4"}):
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(ci.cmd_guarded_recompute(self.args),1)

    def test_wrong_model_rejected(self):
        self.args.model_version="personal-v3"
        with patch.object(ci,"request_json") as network:
            with self.assertRaises(SystemExit):ci.cmd_guarded_recompute(self.args)
            network.assert_not_called()

    def test_unguarded_response_rejected(self):
        with patch.object(ci,"request_json",return_value={
            "ok":True,"guarded":False,"model_version":"personal-v4"}):
            with self.assertRaises(RuntimeError):ci.cmd_guarded_recompute(self.args)

    def test_legacy_double_recompute_removed(self):
        with patch.object(ci,"request_json") as network:
            with self.assertRaisesRegex(SystemExit,"DIRECT_RECOMPUTE_DISABLED"):
                ci.cmd_recompute(self.args)
            network.assert_not_called()

if __name__=="__main__":
    unittest.main()
