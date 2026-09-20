#!/usr/bin/env python3
import unittest
import android_registry_gate as gate


class GatePolicyTest(unittest.TestCase):
    def classify(self, results, transients=None, stable=True, registered=True, repeats=2):
        source = "S"
        checker = {
            "summary": {source: {
                "results": results,
                "transient_anomalies": transients or {},
                "stable": stable,
                "takeover_packages": {},
            }},
            "runs": [],
        }
        return gate.classify(source, checker, registered, repeats)

    def test_clean_reader_kept(self):
        self.assertEqual(self.classify({"PASS_READER": 2})["verdict"], "KEEP")

    def test_takeover_is_not_source_failure(self):
        row = self.classify({"PASS_SOURCE_EXTERNAL_TAKEOVER": 2})
        self.assertEqual(row["verdict"], "KEEP_WITH_ANOMALY")
        self.assertFalse(row["drop_eligible"])

    def test_no_data_requires_repeat_and_clean_control(self):
        self.assertTrue(self.classify({"SOURCE_FAIL_NO_DATA": 2})["drop_eligible"])
        self.assertFalse(self.classify({"SOURCE_FAIL_NO_DATA": 1}, repeats=1)["drop_eligible"])
        self.assertFalse(self.classify(
            {"SOURCE_FAIL_NO_DATA": 2}, {"TRANSPORT_OFFLINE": 1}
        )["drop_eligible"])

    def test_transport_and_unresolved_never_drop(self):
        for result in (
            "TRANSPORT_OFFLINE",
            "TRANSPORT_INTERRUPTED",
            "CONTROL_TRANSIENT",
            "SOURCE_NOT_FOUND",
            "UNRESOLVED_SOURCE_SELECTOR",
            "SOURCE_PATH_PARTIAL_TOC_UNRESOLVED",
            "DEVICE_PRECONDITION_SOURCE_NOT_IN_STRICT_REGISTRY",
            "DEVICE_PRECONDITION_SOURCE_INSTALL_VERIFY_FAILED",
        ):
            row = self.classify({result: 2})
            self.assertEqual(row["verdict"], "DEFER")
            self.assertFalse(row["drop_eligible"])

    def test_content_card_failure_requires_review(self):
        row = self.classify({"SOURCE_FAIL_NO_CONTENT_CARD": 2})
        self.assertEqual(row["verdict"], "REVIEW")
        self.assertFalse(row["drop_eligible"])


    def test_force_reinstall_reaches_checker(self):
        original = gate._run_one_checker
        calls = []
        try:
            def fake(source, repeats, guard_seconds, timeout, registry_url=None, force_reinstall=False):
                calls.append((source, registry_url, force_reinstall))
                return {
                    "ok": True,
                    "summary": {source: {
                        "results": {"PASS_READER": repeats},
                        "transient_anomalies": {},
                        "stable": repeats >= 2,
                        "takeover_packages": {},
                    }},
                    "runs": [{"source": source, "result": "PASS_READER"}],
                    "attempts_log": [],
                }
            gate._run_one_checker = fake
            merged = gate.run_checker(["S"], 1, 1.2, 30, "https://candidate.invalid/registry.json", True)
            self.assertTrue(merged["ok"])
            self.assertEqual(calls, [("S", "https://candidate.invalid/registry.json", True)])
        finally:
            gate._run_one_checker = original

    def test_per_source_process_failure_is_isolated(self):
        original = gate._run_one_checker
        try:
            def fake(source, repeats, guard_seconds, timeout):
                if source == "bad":
                    return {"ok": False, "fatal": "CHECKER_TIMEOUT"}
                return {
                    "ok": True,
                    "summary": {source: {
                        "results": {"PASS_READER": repeats},
                        "transient_anomalies": {},
                        "stable": repeats >= 2,
                        "takeover_packages": {},
                    }},
                    "runs": [{"source": source, "result": "PASS_READER"}],
                    "attempts_log": [],
                }
            gate._run_one_checker = fake
            merged = gate.run_checker(["bad", "good"], 2, 1.2, 30)
            self.assertFalse(merged["ok"])
            self.assertEqual(merged["per_source_errors"]["bad"], "CHECKER_TIMEOUT")
            self.assertIn("good", merged["summary"])
            self.assertNotIn("bad", merged["summary"])
            self.assertEqual(gate.classify("bad", merged, True, 2)["verdict"], "DEFER")
            self.assertEqual(gate.classify("good", merged, True, 2)["verdict"], "KEEP")
        finally:
            gate._run_one_checker = original


if __name__ == "__main__":
    unittest.main()
