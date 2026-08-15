import unittest
from pipeline import parse_tienvuc_page, canonicalize_known_terms

SAMPLE = """Chương 1. Demo 1 - Vương Bài Tiến Hóa (Bản dịch)
Tiên Vực
Vương Bài Tiến Hóa (Bản dịch)
Chương 1. Demo 1
Chương trước
Chương sau
Phương Lâm bước vào Mộng Yểm không gian.
Chương trước
Chương sau
"""

class PipelineTests(unittest.TestCase):
    def test_extract(self):
        r = parse_tienvuc_page(SAMPLE)
        self.assertEqual(r["source_part"], 1)
        self.assertEqual(r["source_title"], "Demo 1")
        self.assertEqual(r["body"], "Phương Lâm bước vào Mộng Yểm không gian.")

    def test_canonicalize(self):
        bible = {"entities": [{"canonical": "Mộng Yểm Không Gian", "aliases": ["Mộng Yểm không gian"]}]}
        out, changes = canonicalize_known_terms("vào Mộng Yểm không gian.", bible)
        self.assertIn("Mộng Yểm Không Gian", out)
        self.assertEqual(changes[0]["count"], 1)

if __name__ == "__main__":
    unittest.main()
