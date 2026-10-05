import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

MODULE = Path(__file__).resolve().parents[1] / "scripts" / "business_opportunity_ledger_client.py"
SPEC = importlib.util.spec_from_file_location("bizopp_client", MODULE)
mod = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(mod)


class BusinessOpportunityLedgerClientTests(unittest.TestCase):
    def base_packet(self):
        return {
            "schema_version": 1,
            "semantic_synthesis": True,
            "synthesis_authority": "BUSINESS_OPPORTUNITY_RADAR",
            "candidate": {
                "candidate_id": "unit-test",
                "normalized_problem": "A normalized problem",
                "thesis_version": "v1",
                "status": "WATCH",
                "source_lane": "BUSINESS_OPPORTUNITY_RADAR",
                "research_terminal": True,
            },
            "identities": [
                {
                    "identity_type": "alias",
                    "identity_value": "Unit Test",
                    "source_lane": "BUSINESS_OPPORTUNITY_RADAR",
                }
            ],
            "evidence": [],
        }

    def test_requires_semantic_synthesis(self):
        packet = self.base_packet()
        packet["semantic_synthesis"] = False
        with self.assertRaisesRegex(mod.LedgerError, "semantic_synthesis_required"):
            mod.validate_packet(packet)

    def test_rejects_raw_evidence_payload(self):
        packet = self.base_packet()
        packet["evidence"] = [{
            "source_lane": "REDDIT",
            "source_ref": "reddit://x",
            "evidence_type": "pain",
            "direction": "SUPPORT",
            "observed_at": "2026-10-05T00:00:00Z",
            "raw_text": "should not be stored",
        }]
        with self.assertRaisesRegex(mod.LedgerError, "evidence_raw_payload_forbidden"):
            mod.validate_packet(packet)

    def test_generates_deterministic_evidence_id(self):
        packet = self.base_packet()
        packet["evidence"] = [{
            "source_lane": "REDDIT",
            "source_ref": "reddit://x",
            "evidence_type": "pain",
            "direction": "SUPPORT",
            "observed_at": "2026-10-05T00:00:00Z",
        }]
        a = mod.validate_packet(packet)
        b = mod.validate_packet(packet)
        self.assertEqual(a["evidence"][0][0], b["evidence"][0][0])
        self.assertTrue(a["evidence"][0][0].startswith("ev-"))

    def test_reads_only_allowed_env_keys(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "env"
            p.write_text(
                "RUNNER3_CORE_TOKEN_B64=YWJj\n"
                "RUNNER3_CORE_URL=https://example.invalid\n"
                "NOT_ALLOWED=secret\n",
                encoding="utf-8",
            )
            values = mod._load_env_file(p)
            self.assertEqual(values["RUNNER3_CORE_TOKEN_B64"], "YWJj")
            self.assertNotIn("NOT_ALLOWED", values)

    def test_valid_packet_normalizes(self):
        normalized = mod.validate_packet(self.base_packet())
        self.assertEqual(normalized["candidate_id"], "unit-test")
        self.assertEqual(normalized["synthesis_authority"], "BUSINESS_OPPORTUNITY_RADAR")


if __name__ == "__main__":
    unittest.main()
