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
        ):
            row = self.classify({result: 2})
            self.assertEqual(row["verdict"], "DEFER")
            self.assertFalse(row["drop_eligible"])

    def test_content_card_failure_requires_review(self):
        row = self.classify({"SOURCE_FAIL_NO_CONTENT_CARD": 2})
        self.assertEqual(row["verdict"], "REVIEW")
        self.assertFalse(row["drop_eligible"])


if __name__ == "__main__":
    unittest.main()
