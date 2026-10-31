import importlib.util
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "content_intelligence_client",
    ROOT / "scripts" / "content_intelligence_client.py",
)
CI = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CI)


class RssStableMetadataTests(unittest.TestCase):
    def test_reordering_keeps_item_and_features_stable(self):
        def get_rows(position):
            return CI.manifest_rows({
                "renderId": "daily-test",
                "manifest": [{
                    "itemId": "stable-item",
                    "canonicalUrl": "https://example.test/article",
                    "title": "Science and AI",
                    "sourceKey": "science",
                    "number": position,
                    "summaryEvidenceStatus": "verified",
                }],
            }, "rss")

        a_items, a_features, a_shown = get_rows(1)
        b_items, b_features, b_shown = get_rows(9)
        self.assertEqual(a_items, b_items)
        self.assertEqual(a_features, b_features)
        self.assertEqual(a_items[0]["metadata"], {"summary_evidence_status": "verified"})
        self.assertEqual(a_shown[0]["context"]["number"], 1)
        self.assertEqual(b_shown[0]["context"]["number"], 9)

    def test_evidence_status_updates_stable_item_metadata(self):
        def get_metadata(status):
            items, _, _ = CI.manifest_rows({
                "manifest": [{
                    "itemId": "item-one",
                    "canonicalUrl": "https://example.test/one",
                    "summaryEvidenceStatus": status,
                }],
            }, "rss")
            return items[0]["metadata"]

        self.assertNotEqual(get_metadata("pending"), get_metadata("verified"))


if __name__ == "__main__":
    unittest.main()
