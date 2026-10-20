#!/usr/bin/env python3
"""Offline deterministic verification. No network, no provider calls, no browser."""
import json
import pathlib
import tempfile
import unittest
from build_buy_decision import qualify, read_semantic, seo_qualification, flippa_qualification

def sem(domain="example.com", verdict="WATCH_NARROW_GAP", product=True, gate="WATCH"):
    return {"domain":domain,"semantic_verdict":verdict,"terminal_verdict":gate,
            "business_reason":"Narrow gap not validated","product_intent_checked":product,
            "us_organic_estimate":1200}
def seo(domain="example.com", verdict="WATCH_DD"):
    return {"identity":domain,"source":"SEOTRENDS","domain":domain,"title":"Demo","verdict":verdict,
            "metrics":{"traffic":3000.0},"score":15}
def flippa(**kw):
    x={"identity":"flippa:10","title":"Tool","url":"https://flippa.com/10","source":"FLIPPA",
       "verified_detail":True,"asking_verified":1000,"bin_verified":None,
       "reserve_verified":None,"profit_card":None,"pageviews_verified":900,"verdict":"BUILD_REFERENCE"}
    x.update(kw)
    return x

def localized_market():
    return {
        "country": "ID", "language": "id",
        "native_keyword": "dari hp ke laptop",
        "literal_translation_keyword": "transfer dari pc",
        "native_volume": 3600, "literal_translation_volume": 20,
        "matches_product_intent": True,
        "unmet_need": "Top results fail to explain where transferred files are saved.",
        "keyword_source_ref": "semrush-id-keyword-export#sha256:fixture",
        "serp_source_ref": "google-id-exact-serp#sha256:fixture",
        "serp_checked_at": "2026-10-20",
        "serp_result_urls": [f"https://site{i}.example/tools" for i in range(5)],
    }

class BuildBuyDecisionGates(unittest.TestCase):
    def test_traffic_not_equal_build_ready(self):
        x=seo_qualification(seo(),sem(),True)
        self.assertEqual(x["build"]["state"],"WATCH_GAP")
        self.assertFalse(x["evidence"]["source_traffic_is_transferable"])
    def test_terminal_drop_overrides_semantic_watch(self):
        self.assertEqual(seo_qualification(seo(verdict="DROP"),sem(),True)["category"],"DROP")
    def test_semrush_blocker_not_zero_demand(self):
        x=seo_qualification(seo(),sem(),False)
        self.assertEqual(x["category"],"BLOCKED")
        self.assertIn("never infer zero",x["build"]["why"])
    def test_no_semantic_defer_not_promote(self):
        self.assertEqual(seo_qualification(seo(),{},True)["category"],"DEFER")
    def test_future_exact_serp_without_semantic_needs_dd(self):
        item=seo()
        item['product_intent_checked']=True
        item['terminal_verdict']='WATCH'
        item['serp_gate']='SERP_DD_PASS'
        x=seo_qualification(item,{},True)
        self.assertEqual(x['category'],'BUILD_DD')
        self.assertFalse(x['evidence']['semantic_review_completed'])
        self.assertFalse(x['evidence']['differentiated_solution_verified'])
        self.assertFalse(x['evidence']['revenue_verified'])
    def test_semantic_false_positive_is_drop(self):
        self.assertEqual(seo_qualification(seo(),sem(verdict="DROP_THIS_CYCLE"),True)["category"],"DROP")
    def test_flippa_listing_reference_not_buy(self):
        x=flippa_qualification(flippa(),10000)
        self.assertEqual(x["category"],"REFERENCE_ONLY")
        self.assertEqual(x["buy"]["state"],"DEFER")
        self.assertFalse(x["evidence"]["profit_independently_verified"])
    def test_unverified_flippa_detail_blocks_buy(self):
        self.assertEqual(flippa_qualification(flippa(verified_detail=False,profit_card=500),10000)["buy"]["state"],"DEFER")
    def test_over_cap_blocks_buy(self):
        self.assertEqual(flippa_qualification(flippa(asking_verified=12000,profit_card=500,verdict="BUY_DD"),10000)["buy"]["state"],"DROP")
    def test_profit_card_supports_dd_only(self):
        x=flippa_qualification(flippa(profit_card=500,verdict="BUY_DD"),10000)
        self.assertEqual(x["buy"]["state"],"DD_PENDING")
        self.assertEqual(x["category"],"DUAL_DD")
        self.assertFalse(x["evidence"]["profit_independently_verified"])
        self.assertFalse(x["evidence"]["buyer_transferability_verified"])
    def test_no_negative_profit_masquerades_as_valid(self):
        self.assertEqual(flippa_qualification(flippa(profit_card=-100,verdict="BUY_DD"),10000)["buy"]["state"],"DEFER")
    def test_shortlist_does_not_auto_approve(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=pathlib.Path(tmp)
            s={"date":"2026-10-14","status":"PASS_SOURCE_PLUS_SEMANTIC_SCREEN",
               "approved_build":0,"items":[sem("a.com")]}
            (root/"2026-10-14-semantic-business-dd.json").write_text(json.dumps(s))
            src={"provider_status":"PASS","terminal_status":"PASS","source_complete":True,
                 "items":[seo("a.com"),seo("other.com",verdict="DROP")]}
            fl={"status":"PASS","new":[flippa(profit_card=850,verdict="BUY_DD")]}
            q=qualify("2026-10-14",src,fl,root=root)
            self.assertEqual(q["status"],"PASS")
            self.assertEqual(q["approved_buy"],0)
            self.assertEqual(q["approved_build"],0)
            self.assertEqual(q["evaluated"],3)
            self.assertEqual(q["counts"]["DUAL_DD"],1)
            self.assertEqual(q["counts"]["WATCH_GAP"],1)
            self.assertEqual(q["counts"]["DROP"],1)
            self.assertEqual(q["actionable_dd"][0]["source"],"FLIPPA")
    def test_missing_semantic_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            s={"provider_status":"PASS","terminal_status":"PASS","source_complete":True,"items":[seo()]}
            q=qualify("2026-10-14",s,{"status":"PASS","new":[]},root=pathlib.Path(tmp))
            self.assertEqual(q["semantic_dd_status"],"MISSING")
            self.assertEqual(q["counts"],{"DEFER":1})
    def test_stale_semantic_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=pathlib.Path(tmp)/"2026-10-14-semantic-business-dd.json"
            p.write_text(json.dumps({"date":"2026-10-13","status":"PASS_SOURCE_PLUS_SEMANTIC_SCREEN","approved_build":0,"items":[sem()]}))
            self.assertEqual(read_semantic("2026-10-14",pathlib.Path(tmp))["status"],"INVALID_OR_STALE")
    def test_source_blocker_marks_partial(self):
        with tempfile.TemporaryDirectory() as tmp:
            s={"provider_status":"BLOCKED","terminal_status":"BLOCKED","source_complete":True,"items":[seo()]}
            q=qualify("2026-10-14",s,{"status":"PASS","new":[]},root=pathlib.Path(tmp))
            self.assertEqual(q["status"],"PARTIAL_BLOCKED")
            self.assertEqual(q["counts"]["BLOCKED"],1)

    def test_local_intent_requires_provenance_and_country_serp(self):
        source = sem()
        source["local_search_intent"] = {"markets": [localized_market()]}
        x = seo_qualification(seo(), source, True)
        review = x["evidence"]["local_search_intent"]
        self.assertEqual(review["status"], "REVIEW_READY")
        self.assertEqual(review["review_priority"], "EVIDENCE_REVIEW_ONLY")
        self.assertEqual(review["markets_review_ready"], 1)
        self.assertFalse(review["independently_validated"])
        self.assertEqual(x["category"], "WATCH_GAP")
        self.assertNotIn("native-language keyword and country-specific SERP evidence", x["missing"])

    def test_local_translation_alone_not_an_opportunity(self):
        m = localized_market()
        m["serp_result_urls"] = []
        x = seo_qualification(seo(), {**sem(), "local_search_intent": {"markets": [m]}}, True)
        self.assertEqual(x["evidence"]["local_search_intent"]["status"], "EVIDENCE_INCOMPLETE")
        self.assertIn("native-language keyword and country-specific SERP evidence", x["missing"])

    def test_local_intent_cannot_pass_on_high_volume_without_gap(self):
        m = localized_market()
        m["matches_product_intent"] = False
        self.assertEqual(seo_qualification(seo(), {**sem(), "local_search_intent": {"markets": [m]}}, True)
                         ["evidence"]["local_search_intent"]["status"], "EVIDENCE_INCOMPLETE")

    def test_live_serp_blocker_preserved_on_provider_pass(self):
        x = seo(verdict="BLOCKED_SERP")
        y = seo_qualification(x, sem(), True)
        self.assertEqual(y["category"], "BLOCKED")
        z = sem(gate="BLOCKED")
        self.assertEqual(seo_qualification(seo(), z, True)["category"], "BLOCKED")

    def test_local_intent_rejects_bad_source_serp(self):
        m = localized_market()
        m["serp_result_urls"] = ["https://same.example/page"] * 10 + ["http://bad.example"]
        m["serp_checked_at"] = "2099-01-01"
        x = seo_qualification(seo(), {**sem(), "local_search_intent": {"markets": [m]}}, True)
        self.assertEqual(x["evidence"]["local_search_intent"]["status"], "EVIDENCE_INCOMPLETE")

    def test_local_intent_not_checked_if_upstream_product_intent_missing(self):
        source = sem(product=False)
        source["local_search_intent"] = {"markets": [localized_market()]}
        x = seo_qualification(seo(), source, True)
        self.assertEqual(x["category"], "DEFER")
        self.assertEqual(x["evidence"]["local_search_intent"]["status"], "UPSTREAM_INTENT_UNVERIFIED")

    def test_local_intent_never_overrides_blocked_provider(self):
        source = sem()
        source["local_search_intent"] = {"markets": [localized_market()]}
        x = seo_qualification(seo(), source, False)
        self.assertEqual(x["category"], "BLOCKED")
        self.assertFalse(x["evidence"]["revenue_verified"])

if __name__=="__main__":
    unittest.main(verbosity=2)
