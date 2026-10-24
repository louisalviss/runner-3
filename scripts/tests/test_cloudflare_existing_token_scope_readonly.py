"""Synthetic-only validation of Cloudflare existing-secret GET-only probes."""
import io
import json
import os
import pathlib
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/"scripts"))
import cloudflare_existing_token_scope_readonly as m

class Resp:
    status=200
    def __init__(self,obj):self.raw=io.BytesIO(json.dumps(obj).encode())
    def __enter__(self):return self
    def __exit__(self,*args):return False
    def read(self,amt):return self.raw.read(amt)

TOKEN="synthetic-only-credential-123456"
ID="a"*32
def test_getter(token,url):
    if url==m.URLS["user_verify"]:
        return 200,{"status":"active","id":ID}
    if url==m.URLS["target_account_verify"]:
        return 403,None
    if url==m.URLS["source_metadata"]:
        return 200,{"name":"runner3-content-intelligence","uuid":m.SOURCE_D1}
    if url==m.URLS["target_metadata"]:
        return 200,{"name":"runner3-content-intelligence","uuid":m.TARGET_D1}
    if url==m.BASE+"/user/tokens/"+ID:
        return 200,{"policies":[{"effect":"allow",
                  "permission_groups":[{"name":"D1 Write"}],
                  "resources":{"com.cloudflare.api.account."+m.TARGET_ACCOUNT:"*"}}]}
    raise AssertionError("Unexpected HTTP route")

class SafeTokenProbe(unittest.TestCase):
    def test_token_secret_absent_no_calls(self):
        self.assertEqual(m.inspect_secret("",requester=lambda *_:self.fail("network")),
                         {"present":False})

    def test_introspection_named_write_only_if_policy_visible(self):
        x=m.inspect_secret(TOKEN,requester=test_getter)
        self.assertTrue(x["active_token_verified"])
        self.assertTrue(x["source_metadata_verified"])
        self.assertTrue(x["target_metadata_verified"])
        self.assertTrue(x["d1_write_permission_named"])
        self.assertTrue(x["policy_target_resource_mentioned"])
        self.assertFalse(x["actual_target_d1_write_test_performed"])
        self.assertNotIn(TOKEN,json.dumps(x))
        self.assertNotIn(ID,json.dumps(x))

    def test_without_policy_rights_d1_write_is_unknown_not_false(self):
        def getter(token,url):
            if "/tokens/"+ID in url:return 403,None
            return test_getter(token,url)
        x=m.inspect_secret(TOKEN,requester=getter)
        self.assertTrue(x["target_metadata_verified"])
        self.assertIsNone(x["d1_write_permission_named"])
        self.assertFalse(x["self_policy_readable"])

    def test_read_access_is_not_write_proof(self):
        def getter(token,url):
            if url==m.BASE+"/user/tokens/"+ID:
                return 200,{"policies":[{"effect":"allow",
                   "permission_groups":[{"name":"D1 Read"}],
                   "resources":{"com.cloudflare.api.account."+m.TARGET_ACCOUNT:"*"}}]}
            return test_getter(token,url)
        x=m.inspect_secret(TOKEN,requester=getter)
        self.assertTrue(x["target_metadata_verified"])
        self.assertFalse(x["d1_write_permission_named"])

    def test_source_metadata_does_not_imply_target_access(self):
        def getter(token,url):
            if url==m.URLS["target_metadata"]:return 403,None
            return test_getter(token,url)
        x=m.inspect_secret(TOKEN,requester=getter)
        self.assertTrue(x["source_metadata_verified"])
        self.assertFalse(x["target_metadata_verified"])

    def test_wrong_target_uuid_is_not_verified(self):
        def getter(token,url):
            if url==m.URLS["target_metadata"]:
                return 200,{"name":"runner3-content-intelligence","uuid":"not-the-target"}
            return test_getter(token,url)
        self.assertFalse(m.inspect_secret(TOKEN,requester=getter)["target_metadata_verified"])

    def test_token_verify_missing_does_not_prove_inactive(self):
        def getter(token,url):
            if url in (m.URLS["user_verify"],m.URLS["target_account_verify"]):
                return 403,None
            return test_getter(token,url)
        x=m.inspect_secret(TOKEN,requester=getter)
        self.assertFalse(x["active_token_verified"])
        self.assertTrue(x["target_metadata_verified"])
        self.assertIsNone(x["d1_write_permission_named"])

    def test_http_requests_are_get_only_and_route_allowlisted(self):
        seen=[]
        def opener(req,timeout):
            seen.append((req.full_url,req.get_method(),req.data,timeout))
            return Resp({"success":True,"result":{"uuid":m.TARGET_D1}})
        status,result=m.readonly_get(TOKEN,m.URLS["target_metadata"],opener=opener)
        self.assertEqual((status,result["uuid"]),(200,m.TARGET_D1))
        self.assertEqual(seen,[(m.URLS["target_metadata"],"GET",None,15)])
        self.assertEqual(m.readonly_get(TOKEN,
            "https://api.cloudflare.com/client/v4/accounts/"+m.TARGET_ACCOUNT+
            "/d1/database/"+m.TARGET_D1+"/query",opener=opener),(0,None))
        self.assertEqual(len(seen),1)

    def test_bad_host_and_mutation_route_block(self):
        for url in ("https://evil.example.com/client/v4/user/tokens/verify",
                    m.BASE+"/accounts/"+m.TARGET_ACCOUNT+"/d1/database/"+m.TARGET_D1+"/query",
                    m.BASE+"/accounts/"+m.TARGET_ACCOUNT+"/d1/database/"+m.TARGET_D1+"/time_travel/restore"):
            self.assertEqual(m.readonly_get(TOKEN,url,
                opener=lambda *_:self.fail("MUTATION_OR_UNTRUSTED_HOST")),(0,None))

    def test_account_token_can_be_verified_without_user_token_permission(self):
        def getter(token,url):
            if url==m.URLS["user_verify"]:return 403,None
            if url==m.URLS["target_account_verify"]:return 200,{"status":"active","id":ID}
            if url==m.BASE+f"/accounts/{m.TARGET_ACCOUNT}/tokens/"+ID:
                return 200,{"policies":[]}
            return test_getter(token,url)
        x=m.inspect_secret(TOKEN,requester=getter)
        self.assertTrue(x["active_token_verified"])
        self.assertTrue(x["self_policy_readable"])
        self.assertFalse(x["d1_write_permission_named"])

    def test_no_raw_policy_resource_or_token_export(self):
        x=m.inspect_secret(TOKEN,requester=test_getter)
        payload=json.dumps(x)
        self.assertNotIn("permission_groups",payload)
        self.assertNotIn(m.TARGET_ACCOUNT,payload)
        self.assertNotIn(ID,payload)
        self.assertNotIn(TOKEN,payload)

    def test_main_refuses_pull_request_or_other_repo(self):
        for values in (
            {"GITHUB_REPOSITORY":"outsider/repo","GITHUB_REF":"refs/heads/main","GITHUB_EVENT_NAME":"push"},
            {"GITHUB_REPOSITORY":"louisalviss/runner-3","GITHUB_REF":"refs/heads/feature","GITHUB_EVENT_NAME":"push"},
            {"GITHUB_REPOSITORY":"louisalviss/runner-3","GITHUB_REF":"refs/heads/main","GITHUB_EVENT_NAME":"pull_request"},
        ):
            with patch.dict(os.environ,values,clear=True):
                with patch.object(m,"inspect_secret",side_effect=AssertionError("remote")):
                    self.assertEqual(m.main(),3)

    def test_main_sanitized_report_no_tokens(self):
        with tempfile.TemporaryDirectory() as td:
            dest=pathlib.Path(td)/"scope.json"
            env={"GITHUB_REPOSITORY":"louisalviss/runner-3",
                 "GITHUB_REF":"refs/heads/main","GITHUB_EVENT_NAME":"push",
                 "CLOUDFLARE_API_TOKEN":TOKEN}
            with patch.dict(os.environ,env,clear=True),patch.object(m,"OUT",dest):
                with patch.object(m,"inspect_secret",side_effect=lambda token:{"present":bool(token)}) as probe:
                    self.assertEqual(m.main(),0)
            result=json.loads(dest.read_text())
            self.assertEqual(result["secret_checks"]["CLOUDFLARE_API_TOKEN"]["present"],True)
            self.assertEqual(result["r2_requests"],0)
            self.assertEqual(result["d1_writes"],0)
            self.assertNotIn(TOKEN,dest.read_text())

if __name__=="__main__":unittest.main()
