#!/usr/bin/env python3
"""Regression checks for global-auth outage and cache-preserving Semrush replay."""
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location("daily", Path(__file__).with_name("semrush_daily.py"))
daily = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(daily)

class SemrushCircuitBreakerTests(unittest.TestCase):
    def setUp(self):
        # All tests must be strictly offline: never call the real Bitwarden
        # login wrapper or provider RPC, even when a new recovery branch fires.
        stub = patch.object(daily, 'recover_expired_session',
                            return_value={'ok': False, 'state': 'TEST_OFFLINE_STUB'})
        stub.start()
        self.addCleanup(stub.stop)

    def test_live_auth_blocks_entire_batch_after_first_attempt(self):
        with tempfile.TemporaryDirectory() as td:
            temp = Path(td)
            (temp / "2026-10-10-semrush-queue.json").write_text(json.dumps(
                {"items": [{"domain": d, "discovery_score": 1}
                           for d in ("example-a.com", "example-b.com", "example-c.com")]}))
            seen = []
            def exporter(domain, path, timeout):
                seen.append(domain)
                return {"status": "FAIL", "reason": "RuntimeError:BROKER_DPA:SEMRUSH_LIVE_AUTH_UNAVAILABLE"}
            with patch.object(daily, "SCANS", temp), patch.object(daily, "run_export", exporter), \
                    patch("sys.argv", ["semrush_daily.py", "--date", "2026-10-10"]):
                rc = daily.main()
            self.assertEqual(rc, 3)
            self.assertEqual(seen, ["example-a.com"])
            report = json.loads((temp / "2026-10-10-semrush-results.json").read_text())
            self.assertEqual(report["status"], "BLOCKED")
            self.assertEqual(report["fail_count"], 1)
            self.assertEqual(report["not_run_count"], 2)
            self.assertIn("SEMRUSH_LIVE_AUTH_UNAVAILABLE", report["global_blocker"])

    def test_cached_export_survives_global_blocker(self):
        with tempfile.TemporaryDirectory() as td:
            temp = Path(td)
            (temp / "2026-10-10-semrush-queue.json").write_text(json.dumps(
                {"items": [{"domain": d, "discovery_score": 1}
                           for d in ("a.com", "b.com", "c.com")]}))
            out = temp / "2026-10-10-semrush"
            out.mkdir()
            (out / "c.com.json").write_text(json.dumps({"domain": "c.com", "rows": []}))
            seen = []
            def exporter(domain, path, timeout):
                seen.append(domain)
                return {"status": "FAIL", "reason": "RuntimeError:BROKER_DPA:SEMRUSH_LIVE_AUTH_UNAVAILABLE"}
            with patch.object(daily, "SCANS", temp), patch.object(daily, "run_export", exporter), \
                    patch("sys.argv", ["semrush_daily.py", "--date", "2026-10-10"]):
                rc = daily.main()
            self.assertEqual(rc, 3)
            self.assertEqual(seen, ["a.com"])
            j = json.loads((temp / "2026-10-10-semrush-results.json").read_text())
            self.assertEqual([x["status"] for x in j["items"]], ["FAIL", "NOT_RUN", "PASS"])
            self.assertEqual(j["pass_count"], 1)
            self.assertEqual(j["status"], "BLOCKED")

    def test_expired_shard_session_stops_other_domains_and_preserves_cached(self):
        with tempfile.TemporaryDirectory() as td:
            temp = Path(td)
            (temp / "2026-10-17-semrush-queue.json").write_text(json.dumps(
                {"items": [{"domain": x} for x in ("cached.com", "expired.com", "skip.com")]}))
            out = temp / "2026-10-17-semrush"
            out.mkdir()
            (out / "cached.com.json").write_text(json.dumps({"domain": "cached.com", "rows": []}))
            calls = []
            def exporter(domain, path, timeout):
                calls.append(domain)
                return {"status": "FAIL", "reason":
                    "RuntimeError:BROKER_DPA:{'message': 'NON_JSON', 'sample': 'Session expired, access again from Dashboard\\\\n'}"}
            with patch.object(daily, "SCANS", temp), patch.object(daily, "run_export", exporter), \
                    patch("sys.argv", ["semrush_daily.py", "--date", "2026-10-17"]):
                rc = daily.main()
            self.assertEqual(rc, 3)
            self.assertEqual(calls, ["expired.com"])
            report = json.loads((temp / "2026-10-17-semrush-results.json").read_text())
            self.assertEqual(report["status"], "BLOCKED")
            self.assertEqual([x["status"] for x in report["items"]], ["PASS", "FAIL", "NOT_RUN"])
            self.assertEqual((report["pass_count"], report["fail_count"], report["not_run_count"]), (1, 1, 1))

    def test_expired_session_recovers_once_then_caches_export(self):
        with tempfile.TemporaryDirectory() as td:
            temp = Path(td)
            (temp / "2026-10-17-semrush-queue.json").write_text(json.dumps(
                {"items": [{"domain": x} for x in ("a.com", "b.com")]}))
            attempts = []
            renewals = []
            def exporter(domain, output, timeout):
                attempts.append(domain)
                if domain == "a.com" and attempts.count(domain) == 1:
                    return {"status": "FAIL", "reason":
                            "RuntimeError:BROKER_DPA:{'message':'NON_JSON','sample':'Session expired, access again from Dashboard'}"}
                output.parent.mkdir(parents=True, exist_ok=True)
                output.write_text(json.dumps({"domain":domain,"rows":[]}))
                return {"status":"PASS","domain":domain}
            def recovery():
                renewals.append(True)
                return {"ok":True,"state":"SHARD_REFRESHED"}
            with patch.object(daily, "SCANS", temp), patch.object(daily,"run_export",exporter),                     patch.object(daily,"recover_expired_session",recovery),                     patch("sys.argv",["semrush_daily.py","--date","2026-10-17"]):
                rc=daily.main()
            self.assertEqual(rc,0)
            self.assertEqual(attempts,["a.com","a.com","b.com"])
            self.assertEqual(len(renewals),1)
            self.assertEqual(json.loads((temp/"2026-10-17-semrush-results.json").read_text())["status"],"PASS")

    def test_refresh_failure_blocks_batch_preserving_cached(self):
        with tempfile.TemporaryDirectory() as td:
            temp=Path(td)
            (temp/"2026-10-17-semrush-queue.json").write_text(json.dumps(
                {"items":[{"domain":x} for x in ("cached.com","expired.com","later.com")]}))
            out=temp/"2026-10-17-semrush";out.mkdir()
            (out/"cached.com.json").write_text(json.dumps({"domain":"cached.com","rows":[]}))
            attempts=[]
            def exporter(domain, output, timeout):
                attempts.append(domain)
                return {"status":"FAIL","reason":"Session expired, access again from Dashboard"}
            with patch.object(daily,"SCANS",temp),patch.object(daily,"run_export",exporter),                     patch.object(daily,"recover_expired_session",lambda:{"ok":False,"state":"NOX_DASHBOARD_CHALLENGE"}),                     patch("sys.argv",["semrush_daily.py","--date","2026-10-17"]):
                rc=daily.main()
            self.assertEqual(rc,3)
            self.assertEqual(attempts,["expired.com"])
            report=json.loads((temp/"2026-10-17-semrush-results.json").read_text())
            self.assertEqual([r["status"] for r in report["items"]],["PASS","FAIL","NOT_RUN"])
            self.assertEqual(report["status"],"BLOCKED")
            self.assertIn("NOX_DASHBOARD_CHALLENGE",report["global_blocker"])

    def test_one_successful_refresh_does_not_allow_second_retry(self):
        with tempfile.TemporaryDirectory() as td:
            temp=Path(td)
            (temp/"2026-10-17-semrush-queue.json").write_text(json.dumps(
                {"items":[{"domain":x} for x in ("a.com","b.com")]}))
            seen=[]
            def exporter(domain, output, timeout):
                seen.append(domain)
                return {"status":"FAIL","reason":"Session expired, access again from Dashboard"}
            with patch.object(daily,"SCANS",temp),patch.object(daily,"run_export",exporter),                     patch.object(daily,"recover_expired_session",lambda:{"ok":True,"state":"SHARD_REFRESHED"}),                     patch("sys.argv",["semrush_daily.py","--date","2026-10-17"]):
                rc=daily.main()
            self.assertEqual(rc,3)
            self.assertEqual(seen,["a.com","a.com"])
            report=json.loads((temp/"2026-10-17-semrush-results.json").read_text())
            self.assertEqual(report["status"],"BLOCKED")
            self.assertIn("SEMRUSH_AUTO_RECOVERY_RETRY_FAILED",report["global_blocker"])

    def test_cloudflare_does_not_trigger_credentialed_refresh(self):
        with tempfile.TemporaryDirectory() as td:
            temp=Path(td)
            (temp/"2026-10-17-semrush-queue.json").write_text(json.dumps(
                {"items":[{"domain":"a.com"},{"domain":"b.com"}]}))
            with patch.object(daily,"SCANS",temp),                     patch.object(daily,"run_export",lambda *_:{"status":"FAIL","reason":"NOX_DASHBOARD_CHALLENGE"}),                     patch.object(daily,"recover_expired_session",side_effect=AssertionError("must not refresh")),                     patch("sys.argv",["semrush_daily.py","--date","2026-10-17"]):
                rc=daily.main()
            self.assertEqual(rc,3)
            report=json.loads((temp/"2026-10-17-semrush-results.json").read_text())
            self.assertEqual([r["status"] for r in report["items"]],["FAIL","NOT_RUN"])

    def test_semrush_auth_is_named_global_blocker(self):
        self.assertIn("SEMRUSH_LIVE_AUTH_UNAVAILABLE", daily.GLOBAL_BLOCKERS)
        self.assertIn("Session expired, access again from Dashboard", daily.GLOBAL_BLOCKERS)

if __name__=="__main__":
    unittest.main()
