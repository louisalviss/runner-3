#!/usr/bin/env python3
"""No provider calls: regression of explicit, dated AI substitution risk."""
import unittest
from ai_substitution_gate import review_for_candidate
from build_buy_decision import flippa_qualification, seo_qualification


def resilient(identity):
    return {
        "status":"REVIEWED", "identity":identity, "review_date":"2026-11-12",
        "customer_job":"Execute a recurring transaction for a paying buyer",
        "risk":"RESILIENT_WORKFLOW", "ai_answer_completes_customer_job":False,
        "revenue_depends_on_answer_pageviews":False,
        "resilience_basis":"TRANSACTION", "non_answer_value_source_checked":True,
        "reason":"A customer must authorize and complete a paid transaction through the actual service.",
        "source_refs":["https://example.com/transaction-proof",
                       "https://example.net/independent-buyer-proof"],
    }


class AiSubstitutionGateTest(unittest.TestCase):
    def test_schoolcalendar_source_override_rejects_current_but_not_historical(self):
        old = review_for_candidate("flippa:13095813", as_of="2026-11-11")
        new = review_for_candidate("flippa:13095813", as_of="2026-11-12")
        self.assertEqual(old["status"], "UNREVIEWED")
        self.assertEqual(new["status"], "HIGH")
        self.assertTrue(new["reviewed"])

    def test_visited_site_only_does_not_mint_resilience(self):
        self.assertEqual(review_for_candidate("flippa:777", {"status":"REVIEWED", "identity":"flippa:777"},
                                              as_of="2026-11-12")["status"], "UNREVIEWED")

    def test_title_keywords_do_not_trigger_rejection(self):
        self.assertEqual(review_for_candidate("flippa:777", as_of="2026-11-12")["status"], "UNREVIEWED")

    def test_source_side_cannot_override_committed_negative_decision(self):
        self.assertEqual(review_for_candidate("flippa:13095813",
                         resilient("flippa:13095813"), as_of="2026-11-12")["status"], "HIGH")

    def test_identity_and_evidence_refs_checked(self):
        wrong = resilient("flippa:888")
        self.assertEqual(review_for_candidate("flippa:777", wrong, as_of="2026-11-12")["status"], "UNREVIEWED")
        low = resilient("flippa:777")
        low["source_refs"] = ["https://example.com/a", "https://example.com/a"]
        self.assertEqual(review_for_candidate("flippa:777", low, as_of="2026-11-12")["status"], "UNREVIEWED")
        self.assertEqual(review_for_candidate("flippa:777", resilient("flippa:777"),
                                              as_of="2026-11-12")["status"], "RESILIENT")

    def test_live_schoolcalendar_blocked_even_if_listing_not_deep_verified(self):
        row={"identity":"flippa:13095813","id":"13095813","title":"SchoolCalendar.net",
             "url":"https://flippa.com/13095813","verified_detail":False,
             "profit_card":265,"pageviews_verified":20695,
             "asking_verified":605,"verdict":"BUY_DD"}
        old=flippa_qualification(row, 10000, as_of="2026-11-11")
        new=flippa_qualification(row, 10000, as_of="2026-11-12")
        self.assertNotEqual(old["category"], "DROP")
        self.assertEqual(new["category"], "DROP")
        self.assertEqual(new["buy"]["state"], "DROP")
        self.assertEqual(new["build"]["state"], "DROP")
        self.assertEqual(new["evidence"]["ai_substitution_status"],"HIGH")
        self.assertFalse(new["evidence"]["profit_independently_verified"])

    def test_ordinary_deep_dd_requires_review_before_actionable(self):
        row={"identity":"flippa:777", "id":"777", "verified_detail":True,
             "title":"Genuine payment workflow", "url":"https://flippa.com/777",
             "profit_card":700, "pageviews_verified":600, "reserve_verified":2500,
             "verdict":"BUY_DD", "verified_asset_domain":"example.com",
             "asset_domain_verified":True, "asset_domain_source_kind":"DIRECT_LISTING_CURRENT",
             "asset_domain_source_ref":"flippa-777#sha256:website",
             "site_product_review":{
               "status":"REVIEWED","listing_id":"777","asset_domain":"example.com",
               "asset_type":"saas","buyer":"Paying account holders transacting monthly",
               "asset_offer":"A paid workflow and processed transaction for accounts",
               "actual_workflow":"End users submit and settle a real financial record",
               "observed_conversion_path":"A checkout form used for paid recurring access",
               "monetization_mechanism":"Recurring subscriptions for workflows",
               "operator_dependencies":"Hosted payment processing and scheduled reconciliation",
               "transfer_risks":"Code rights, billing permissions and account transfer",
               "pages":[{"kind":"home","url":"https://example.com/",
                         "finding":"A real transaction service landing page",
                         "source_ref":"site-home-sha256:fixture"},
                        {"kind":"product","url":"https://example.com/app",
                         "finding":"Service shows transaction workflow in a form",
                         "source_ref":"site-product-sha256:fixture"}]}}
        before=flippa_qualification(row,10000,as_of="2026-11-12")
        self.assertEqual(before["category"],"SITE_DD_PENDING")
        self.assertEqual(before["evidence"]["ai_substitution_status"],"UNREVIEWED")
        with_review=flippa_qualification({**row,"ai_substitution_review":resilient("flippa:777")},
                                         10000,as_of="2026-11-12")
        self.assertEqual(with_review["category"],"BUY_DD")
        self.assertFalse(with_review["evidence"]["profit_independently_verified"])

    def test_source_outage_still_blocks_even_if_resilience_reviewed(self):
        seo={"domain":"example.com","verdict":"BLOCKED_PROVIDER",
             "product_intent_checked":True}
        semantic={"ai_substitution_review":resilient("example.com")}
        self.assertEqual(seo_qualification(seo, semantic, False, as_of="2026-11-12")["category"],"BLOCKED")


if __name__=="__main__":
    unittest.main()
