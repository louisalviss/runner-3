import importlib.util
import pathlib
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "content_intelligence_client",
    ROOT / "scripts" / "content_intelligence_client.py",
)
MOD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MOD)


class ContentIntelligenceBatchTests(unittest.TestCase):
    def test_post_batches_respects_explicit_batch_size(self):
        rows = [{"item_id": str(i)} for i in range(23)]
        seen = []

        def fake_request(method, path, payload, core_url=None):
            seen.append(len(payload["rows"]))
            return {"applied": len(payload["rows"])}

        with mock.patch.object(MOD, "request_json", side_effect=fake_request):
            applied = MOD.post_batches("/content-intelligence/items", rows, None, batch_size=10)

        self.assertEqual(applied, 23)
        self.assertEqual(seen, [10, 10, 3])


if __name__ == "__main__":
    unittest.main()
