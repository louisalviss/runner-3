"""Offline tests only: neither GitHub nor Cloudflare credentials used."""
import importlib.util
import json
import os
import pathlib
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/"scripts"))
spec=importlib.util.spec_from_file_location(
    "census",ROOT/"scripts/cloudflare_gh_secret_name_census.py")
m=importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
TOK="synthetic_NeverAnActualCredential_abcdef123456"
def probe(value):
    assert value == TOK
    return {
        "source_metadata_verified":False,
        "target_metadata_verified":True,
        "target_metadata_http_status":200,
        "self_policy_readable":False,
        "d1_write_permission_named":None,
        "policy_target_resource_mentioned":None,
    }

class GHNames(unittest.TestCase):
    def test_returns_only_cloudflare_name_not_value_or_other_names(self):
        raw=json.dumps({"CLOUDFLARE_FULL_ACCESS_TOKEN":TOK,
                        "CF_MIGRATION_TOKEN":TOK,
                        "AWS_SECRET_ACCESS_KEY":"should_never_expose",
                        "GITHUB_TOKEN":"secret", "MY_PASSWORD":"other_secret"})
        result=m.inspect_names(raw,probe=probe)
        self.assertEqual(result["cloudflare_matching_secret_names"],
                         ["CF_MIGRATION_TOKEN","CLOUDFLARE_FULL_ACCESS_TOKEN"])
        payload=json.dumps(result)
        for secret in (TOK,"should_never_expose","other_secret","MY_PASSWORD","AWS_SECRET_ACCESS_KEY"):
            self.assertNotIn(secret,payload)
        self.assertEqual(result["matching_secret_count"],2)
        self.assertEqual(result["cloudflare_d1_mutations"],0)

    def test_existing_read_only_token_cannot_prove_write(self):
        r=m.inspect_names(json.dumps({"CLOUDFLARE_TARGET_AUDIT_TOKEN":TOK}),
                          probe=probe)
        v=r["cloudflare_secret_checks"]["CLOUDFLARE_TARGET_AUDIT_TOKEN"]
        self.assertTrue(v["target_d1_metadata_verified"])
        self.assertFalse(v["d1_write_proven"])
        self.assertFalse(r["actual_target_d1_write_permission_proven"])
        self.assertIsNone(v["d1_write_permission_name_visible"])

    def test_cloudflare_global_api_key_name_only_not_used_as_bearer(self):
        r=m.inspect_names(json.dumps({"CLOUDFLARE_GLOBAL_API_KEY":"globalkey"}),
                          probe=lambda *_:self.fail("Global API Key not bearer"))
        self.assertEqual(r["cloudflare_secret_checks"]["CLOUDFLARE_GLOBAL_API_KEY"][
                             "tested_as_cloudflare_bearer_token"],False)

    def test_empty_cloudflare_secret_is_reported_as_not_present(self):
        r=m.inspect_names(json.dumps({"CLOUDFLARE_TARGET_D1_WRITE_TOKEN":""}),
                          probe=lambda *_:self.fail("empty token should not call HTTP"))
        v=r["cloudflare_secret_checks"]["CLOUDFLARE_TARGET_D1_WRITE_TOKEN"]
        self.assertFalse(v["present_nonempty"])
        self.assertIsNone(v["target_d1_metadata_verified"])

    def test_unknown_keys_no_network(self):
        r=m.inspect_names(json.dumps({"UNRELATED_KEY":TOK}),
                          probe=lambda *_:self.fail("no HTTP"))
        self.assertEqual(r["matching_secret_count"],0)

    def test_rejects_json_array(self):
        with self.assertRaisesRegex(m.Hold,"CONTEXT_NOT_OBJECT"):
            m.inspect_names("[]")

    def test_rejects_malformed_json(self):
        with self.assertRaisesRegex(m.Hold,"INVALID_GITHUB_SECRETS_CONTEXT"):
            m.inspect_names("{malformed")

    def test_rejects_oversized_json_without_parsing(self):
        with self.assertRaisesRegex(m.Hold,"MISSING_OR_OVERSIZED"):
            m.inspect_names("x"*250001)

    def test_cloudflare_name_validation_excludes_bad_keys(self):
        for n in ("xCLOUDFLARE_API_TOKEN", "CLOUDFLARE_☃", "cf_token", "CF.TEST"):
            self.assertFalse(m.cloudflare_candidate(n))
        self.assertTrue(m.cloudflare_candidate("CLOUDFLARE_API_TOKEN"))
        self.assertTrue(m.cloudflare_candidate("CF_TOKEN"))

    def test_refuses_overlarge_candidate_count(self):
        d={f"CLOUDFLARE_SECRET_{i:02d}":TOK for i in range(45)}
        with self.assertRaisesRegex(m.Hold,"COUNT_BUDGET"):
            m.inspect_names(json.dumps(d),probe=lambda *_:self.fail("HTTP"))

    def test_refuses_overlarge_token_probe_count(self):
        d={f"CLOUDFLARE_SECRET_{i:02d}_TOKEN":TOK for i in range(23)}
        with self.assertRaisesRegex(m.Hold,"PROBE_BUDGET"):
            m.inspect_names(json.dumps(d),probe=lambda *_:self.fail("HTTP"))

    def test_write_privilege_not_proven_even_named_policy(self):
        def fuller(token):
            d=probe(token);d["d1_write_permission_named"]=True
            return d
        r=m.inspect_names(json.dumps({"CLOUDFLARE_FULL_ACCESS_TOKEN":TOK}),
                          probe=fuller)
        self.assertTrue(r["cloudflare_secret_checks"]["CLOUDFLARE_FULL_ACCESS_TOKEN"]["d1_write_permission_name_visible"])
        self.assertFalse(r["actual_target_d1_write_permission_proven"])

    def test_workflow_secrets_context_only_in_one_step(self):
        flow=(ROOT/".github/workflows/cloudflare-gh-secret-name-census.yml").read_text()
        self.assertIn("GH_ALL_SECRETS_JSON: \${{ toJSON(secrets) }}".replace("\\",""),flow)
        self.assertIn("github.event_name == 'push'",flow)
        self.assertNotIn("workflow_dispatch:",flow)
        self.assertIn("persist-credentials: false",flow)
        self.assertEqual(flow.count("toJSON(secrets)"),1)
        self.assertIn("retention-days: 2",flow)

    def test_main_context_required(self):
        cases=[
            {"GITHUB_REPOSITORY":"someone/else","GITHUB_EVENT_NAME":"push","GITHUB_REF":"refs/heads/main"},
            {"GITHUB_REPOSITORY":m.REPO,"GITHUB_EVENT_NAME":"pull_request","GITHUB_REF":"refs/heads/main"},
            {"GITHUB_REPOSITORY":m.REPO,"GITHUB_EVENT_NAME":"push","GITHUB_REF":"refs/heads/other"},
        ]
        for context in cases:
            with self.subTest(context=context),patch.dict(os.environ,context,clear=True):
                with patch.object(m,"inspect_names",side_effect=AssertionError("No secret reads")):
                    self.assertEqual(m.main(),3)

    def test_sanitized_artifact_and_stdout_only_counts(self):
        with tempfile.TemporaryDirectory() as folder:
            path=pathlib.Path(folder)/"report.json"
            env={"GITHUB_REPOSITORY":m.REPO,"GITHUB_EVENT_NAME":"push",
                 "GITHUB_REF":"refs/heads/main","GH_ALL_SECRETS_JSON":
                 json.dumps({"CLOUDFLARE_FULL_ACCESS_TOKEN":TOK})}
            with patch.dict(os.environ,env,clear=True),patch.object(m,"OUTPUT",path):
                with patch.object(m,"inspect_names",side_effect=lambda jsonraw: m.inspect_names(jsonraw,probe=probe)):
                    self.assertEqual(m.main(),0)
            content=path.read_text()
            self.assertNotIn(TOK,content)
            self.assertIn("CLOUDFLARE_FULL_ACCESS_TOKEN",content)

if __name__=="__main__":
    unittest.main()
