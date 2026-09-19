#!/usr/bin/env python3
import json
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parent
FILES=[
    ROOT / "louis-vbook.json",
    ROOT / "louis-vbook-strict-20260918.json",
    ROOT / "louis-vbook-live.json",
]

class RegistryAliasConsistencyTest(unittest.TestCase):
    def test_aliases_equal_canonical(self):
        docs=[json.loads(p.read_text(encoding="utf-8")) for p in FILES]
        self.assertEqual(docs[0], docs[1])
        self.assertEqual(docs[0], docs[2])

if __name__ == "__main__":
    unittest.main()
