import tempfile
import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import private_backtest_shadow as shadow


class VendorAliasTests(unittest.TestCase):
    def test_meta_maps_to_legacy_fb_in_ephemeral_helper(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/"exp.py"
            p.write_text('def resolve_symbol(symbol):\n    if not symbol:\n        return None\n    return f"{symbol}.US/USD"\n', encoding="utf-8")
            got=shadow.patch_runtime_vendor_aliases(p,{"META":"FB"})
            text=p.read_text(encoding="utf-8")
            self.assertEqual(got,{"META":"FB"})
            self.assertIn('aliases = {"META": "FB"}', text)
            ns={}
            exec(text,ns)
            self.assertEqual(ns["resolve_symbol"]("META"),"FB.US/USD")
            self.assertEqual(ns["resolve_symbol"]("AAPL"),"AAPL.US/USD")

    def test_invalid_alias_fails_closed(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/"exp.py"
            p.write_text('def resolve_symbol(symbol):\n    if not symbol:\n        return None\n    return f"{symbol}.US/USD"\n', encoding="utf-8")
            with self.assertRaises(ValueError):
                shadow.patch_runtime_vendor_aliases(p,{"META;rm":"FB"})


if __name__ == "__main__":
    unittest.main()
