"""No remote calls, credentials, Cloudflare writes, or restore attempts."""
import importlib.util
import io
import json
import pathlib
import sys
import unittest
import urllib.error
from unittest.mock import patch

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
spec = importlib.util.spec_from_file_location(
    "timetravel", ROOT / "scripts/cloudflare_d1_target_time_travel_readonly.py")
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
TOKEN = "synthetic_target_readonly_token"
BOOKMARK = "00000001-00000002-00004e2f-0a83ea2fceebc654de0640c422be4653"


class FakeResponse:
    def __init__(self, data, status=200):
        self.status = status
        self.data = io.BytesIO(json.dumps(data).encode())
    def __enter__(self): return self
    def __exit__(self, *args): return False
    def read(self, size=-1): return self.data.read(size)


def fake_request(token, url, version="production", bookmark=BOOKMARK):
    assert token == TOKEN
    assert url in m.PATHS
    if url == m.PATHS[0]:
        return {"name": m.DATABASE, "uuid": m.TARGET_UUID, "version": version}
    return {"bookmark": bookmark}


class TimeTravelGate(unittest.TestCase):
    def test_valid_production_backend_and_bookmark(self):
        result=m.inspect(TOKEN,request=fake_request)
        self.assertTrue(result["bookmark_api_read_success"])
        self.assertEqual(result["status"],"TIME_TRAVEL_ELIGIBLE_NOT_ROLLBACK_READY")
        self.assertEqual(len(result["observed_bookmark_sha256"]),64)
        self.assertNotIn(BOOKMARK,json.dumps(result))
        self.assertFalse(result["bookmark_preserved_for_actual_restore"])
        self.assertFalse(result["safe_restore_approved"])
        self.assertFalse(result["cutover_ready"])
        self.assertEqual(result["target_d1_writes"],0)

    def test_only_two_readonly_target_routes(self):
        self.assertEqual(len(m.PATHS),2)
        self.assertTrue(all("/accounts/"+m.TARGET_ACCOUNT+"/" in x for x in m.PATHS))
        self.assertTrue(all(m.TARGET_UUID in x for x in m.PATHS))
        self.assertTrue(m.PATHS[1].endswith("/time_travel/bookmark"))
        self.assertNotIn("/restore",str(m.PATHS))

    def test_real_transport_uses_only_get(self):
        seen=[]
        def opener(req,timeout):
            seen.append((req.full_url,req.get_method(),req.data,timeout))
            body={"success":True,"result":{
                "name":m.DATABASE,"uuid":m.TARGET_UUID,"version":"production"}}
            return FakeResponse(body)
        result=m.get_json(TOKEN,m.PATHS[0],opener=opener)
        self.assertEqual(result["version"],"production")
        self.assertEqual(seen,[(m.PATHS[0],"GET",None,25)])
        self.assertNotIn(TOKEN,json.dumps(result))

    def test_disallowed_route_blocks_before_network(self):
        def denied(*args,**kw):
            self.fail("No HTTP on disallowed URL")
        for route in (m.PATHS[0].replace(m.TARGET_ACCOUNT,
                    "7415a87f6bce7884e73ad7cfed5782df"),
                      m.PATHS[1].replace("bookmark","restore"),
                      "https://example.com"):
            with self.subTest(route=route), self.assertRaisesRegex(
                m.Hold,"URL_NOT_ALLOWLISTED"):
                m.get_json(TOKEN,route,opener=denied)

    def test_alpha_backend_blocks_even_with_bookmark(self):
        with self.assertRaisesRegex(m.Hold,"BACKEND_NOT_PRODUCTION"):
            m.inspect(TOKEN,request=lambda t,u:fake_request(t,u,version="alpha"))

    def test_mismatched_target_name_blocks(self):
        def fake(t,u):
            out=fake_request(t,u)
            if u==m.PATHS[0]:out["name"]="wrong-database"
            return out
        with self.assertRaisesRegex(m.Hold,"WRONG_TARGET_D1_IDENTITY"):
            m.inspect(TOKEN,request=fake)

    def test_mismatched_uuid_blocks(self):
        def fake(t,u):
            out=fake_request(t,u)
            if u==m.PATHS[0]:out["uuid"]="wrong"
            return out
        with self.assertRaisesRegex(m.Hold,"WRONG_TARGET_D1_IDENTITY"):
            m.inspect(TOKEN,request=fake)

    def test_empty_bookmark_blocks(self):
        with self.assertRaisesRegex(m.Hold,"BOOKMARK_UNAVAILABLE"):
            m.inspect(TOKEN,request=lambda t,u:fake_request(t,u,bookmark=""))

    def test_bookmark_control_bytes_blocks(self):
        with self.assertRaisesRegex(m.Hold,"BOOKMARK_UNAVAILABLE"):
            m.inspect(TOKEN,request=lambda t,u:fake_request(t,u,bookmark="aaa\nccc" * 5))

    def test_write_token_main_blocks_without_network(self):
        with patch.dict("os.environ",{"CLOUDFLARE_TARGET_D1_WRITE_TOKEN":"synthetic"},clear=True):
            with patch.object(m,"inspect",side_effect=AssertionError("should not call")):
                self.assertEqual(m.main(),3)

    def test_no_read_token_blocks(self):
        with self.assertRaisesRegex(m.Hold,"TARGET_AUDIT_TOKEN_MISSING"):
            m.get_json("",m.PATHS[0])

    def test_non_200_http_blocks(self):
        with self.assertRaisesRegex(m.Hold,"HTTP_NON_200"):
            m.get_json(TOKEN,m.PATHS[0],opener=lambda a,timeout:FakeResponse({},403))

    def test_unexpected_api_result_blocks(self):
        for value in ({"success":False,"result":{}},
                      {"success":True,"result":[]},{}):
            with self.subTest(value=value),self.assertRaisesRegex(
                m.Hold,"TARGET_API_NOT_SUCCESS"):
                m.get_json(TOKEN,m.PATHS[0],
                           opener=lambda a,timeout:FakeResponse(value))

    def test_observation_cannot_authorize_writes(self):
        result=m.inspect(TOKEN,request=fake_request)
        self.assertFalse(result["pre_apply_fresh_bookmark_verified"])
        self.assertFalse(result["target_writers_quiesced"])
        self.assertFalse(result["safe_restore_approved"])
        self.assertTrue(result["whole_database_restore_is_destructive"])
        self.assertEqual(result["source_d1_queries"],0)
        self.assertEqual(result["r2_requests"],0)


if __name__ == "__main__":
    unittest.main()
