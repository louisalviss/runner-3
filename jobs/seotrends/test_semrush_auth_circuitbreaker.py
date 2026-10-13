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

    def test_semrush_auth_is_named_global_blocker(self):
        self.assertIn("SEMRUSH_LIVE_AUTH_UNAVAILABLE", daily.GLOBAL_BLOCKERS)

if __name__=="__main__":
    unittest.main()
