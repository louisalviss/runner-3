import importlib.util
import pathlib
import unittest
from unittest.mock import patch

SCRIPT = pathlib.Path(__file__).resolve().parents[1] / "scripts" / "content_intelligence_d1_usage_readonly.py"
spec = importlib.util.spec_from_file_location("usage_readonly", SCRIPT)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class UsageReadOnlyTest(unittest.TestCase):
    def test_uses_only_insights_no_execute(self):
        class MockResponse:
            returncode = 0
            stdout = '[{"query":"SELECT foo","totalRowsRead":40,"numberOfTimesRun":2}]'
            stderr = ""
        with patch.object(mod.subprocess, "run", return_value=MockResponse()) as run:
            records = mod.load_insights("runner3-content-intelligence", "1d", 10)
        self.assertEqual(records[0]["totalRowsRead"], 40)
        cmd = run.call_args.args[0]
        self.assertEqual(cmd[:3], ["wrangler", "d1", "insights"])
        self.assertNotIn("execute", cmd)
        self.assertNotIn("--remote", cmd)


if __name__ == "__main__":
    unittest.main()
