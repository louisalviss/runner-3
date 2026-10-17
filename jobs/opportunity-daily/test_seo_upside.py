#!/usr/bin/env python3
"""Offline SEO upside tests: avoid false positives, promotion or provider calls."""
import json
import pathlib
import tempfile
import unittest
from seo_upside import attach, evaluate, rank_headroom, read_export

def row(k, pos=6, url="https://example.com/tools/estimate-maker", vol=1900, cpc=13, kd=24):
    return {"phrase":k, "position":pos, "url":url, "volume":vol,
            "cpc":cpc, "keywordDifficulty":kd}

def export(domain="example.com"):
    return {"domain":domain, "rows":[row("free estimate"), row("estimate maker", pos=4)]}

class SEOUpsideTests(unittest.TestCase):
    def test_ranking_headroom_not_authority(self):
        x=evaluate("example.com", export())
        self.assertEqual(x["status"], "NEEDS_AUTHORITY_PROOF")
        self.assertEqual(x["headroom"]["candidate_page_count"], 1)
        self.assertFalse(x["authority_verified"])
        self.assertFalse(x["can_promote_buy"])

    def test_single_keyword_not_enough(self):
        x=evaluate("example.com", {"domain":"example.com", "rows":[row("free estimate")]})
        self.assertEqual(x["status"], "NO_RANKING_HEADROOM_SIGNAL")

    def test_no_blog_or_other_domain(self):
        e={"domain":"example.com","rows":[row("free estimate",url="https://other.com/tools/estimate-maker"),
                                             row("estimate maker",url="https://example.com/blog/estimate-maker")]}
        self.assertEqual(evaluate("example.com",e)["status"],"NO_RANKING_HEADROOM_SIGNAL")

    def test_deduplicated_keyword_and_branded(self):
        rows=[row("example estimate"),row("estimate maker"),row("estimate maker",pos=5)]
        x=rank_headroom("example.com", rows)
        self.assertEqual(x["candidate_page_count"],0)

    def test_export_domain_mismatch(self):
        self.assertEqual(evaluate("example.com",export("fake.com"))["status"],"BLOCKED_EXPORT_MISMATCH")

    def test_large_or_invalid_export(self):
        self.assertEqual(evaluate("example.com", {"domain":"example.com","rows":[{}]*30001})["status"],"BLOCKED_EXPORT_TOO_LARGE")

    def test_authority_alone_not_actionable(self):
        proof={"backlinks":{"verified":True,"source":"Ahrefs","checked_at":"2026-10-17","referring_domains":130}}
        self.assertEqual(evaluate("example.com",export(),proof)["status"],"NEEDS_PAGE_AUDIT")

    def test_verified_gap_can_be_supported_not_buy_approved(self):
        proof={"backlinks":{"verified":True,"source":"Ahrefs","checked_at":"2026-10-17","referring_domains":130},
               "issues":[{"verified":True,"type":"intent_mismatch","url":"https://example.com/tools/estimate-maker"}]}
        x=evaluate("example.com",export(),proof)
        self.assertEqual(x["status"],"SUPPORTED_UPSIDE_HYPOTHESIS")
        self.assertFalse(x["can_promote_buy"])

    def test_unverified_issue_not_accepted(self):
        proof={"backlinks":{"verified":True,"source":"Ahrefs","checked_at":"2026-10-17","referring_domains":130},
               "issues":[{"verified":False,"type":"missing_contextual_link","url":"https://example.com/tools/estimate-maker"}]}
        self.assertEqual(evaluate("example.com",export(),proof)["status"],"NEEDS_PAGE_AUDIT")

    def test_attach_no_domain_preserves_buy_decision(self):
        v={"date_vn":"2026-10-17","qualification":{"candidates":[
            {"identity":"flippa:100","source":"FLIPPA","category":"BUY_DD",
             "buy":{"state":"DD_PENDING"},"evidence":{}}]}}
        x=attach(v,pathlib.Path("/nonexistent"))
        self.assertEqual(x["status_counts"],{"NO_VERIFIED_LISTING_DOMAIN":1})
        self.assertEqual(v["qualification"]["candidates"][0]["buy"]["state"],"DD_PENDING")

    def test_attach_cached_verified_domain(self):
        with tempfile.TemporaryDirectory() as tmp:
            d=pathlib.Path(tmp)/"flippa-sem-20261017"
            d.mkdir()
            (d/"example.com.json").write_text(json.dumps(export()))
            v={"date_vn":"2026-10-17","qualification":{"candidates":[{"identity":"flippa:100","source":"FLIPPA",
                "category":"DEFER","buy":{"state":"DEFER"},"evidence":{}}]},
                "flippa_semrush":{"items":[{"listing_identity":"flippa:100","status":"PASS","domain":"example.com"}]}}
            attach(v,pathlib.Path(tmp))
            x=v["qualification"]["candidates"][0]
            self.assertEqual(x["evidence"]["seo_upside"]["status"],"NEEDS_AUTHORITY_PROOF")
            self.assertEqual(x["category"],"DEFER")

    def test_bad_domain_or_symlink_fail_closed(self):
        self.assertEqual(evaluate("../bad",export())["status"],"BLOCKED_INVALID_DOMAIN")
        with tempfile.TemporaryDirectory() as tmp:
            a=pathlib.Path(tmp)/"a.json";a.write_text(json.dumps(export()))
            b=pathlib.Path(tmp)/"b.json";b.symlink_to(a)
            self.assertIsNone(read_export(b,"example.com"))

if __name__=="__main__":
    unittest.main(verbosity=2)
