import pathlib
import unittest

SCRIPT = pathlib.Path(__file__).resolve().parents[1] / "scripts" / "d1_account_quota_preflight.py"

class D1QuotaGuardSourceContract(unittest.TestCase):
    def test_account_wide_read_and_write_limits(self):
        source = SCRIPT.read_text()
        for token in (
            "READ_HARD_LIMIT = 5000000",
            "READ_SAFE_CEILING = 4000000",
            'sum(x["rowsRead"] for x in databases)',
            "projected_reads <= read_ceiling",
            "projected <= ceiling",
        ):
            self.assertIn(token, source)

if __name__ == "__main__":
    unittest.main()
