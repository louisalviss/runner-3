#!/usr/bin/env python3
"""87-entry user cutover: no resurrection, no history rewrite, no false SOLD."""
import tempfile
import pathlib
import json
import unittest
import acquisition_backlog as backlog
from reviewed_cutover import reviewed_processed_ids, is_reviewed_prior_listing, is_manual_review_duplicate
from build_buy_decision import qualify


class ReviewedCutoverTests(unittest.TestCase):
    def test_manifest_complete_and_dated(self):
        self.assertEqual(len(reviewed_processed_ids("2026-11-12")),87)
        self.assertEqual(len(reviewed_processed_ids("2026-11-11")),0)
        self.assertIn("13095813",reviewed_processed_ids("2026-11-12"))
        self.assertTrue(is_reviewed_prior_listing("flippa:13095813","2026-11-12"))
        self.assertFalse(is_reviewed_prior_listing("flippa:13095813","2026-11-11"))
        self.assertFalse(is_reviewed_prior_listing("schoolcalendar.net","2026-11-12"))
        self.assertTrue(is_reviewed_prior_listing("flippa:14595704","2026-11-12"))
        self.assertFalse(is_reviewed_prior_listing("flippa:14595704","2026-11-11"))

    def test_archived_in_old_cohort_preserves_source_and_new_candidate(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=pathlib.Path(tmp)
            (root/'FLIPPA-INVENTORY-CURRENT-20261006.json').write_text(json.dumps({'main':{}}))
            old={"identity":"flippa:13095813","title":"SchoolCalendar",
                 "source":"FLIPPA","category":"BUY_DD"}
            new={"identity":"flippa:98765123","title":"Genuine new candidate",
                 "source":"FLIPPA","category":"BUILD_DD"}
            historic=backlog.build_backlog("2026-11-11",root=root,report_root=root,
                                          current_candidates=[old,new],
                                          reviewed_override={"13095813"})
            self.assertIn("13095813",{x['id'] for x in historic['active']})
            future=backlog.build_backlog("2026-11-12",root=root,report_root=root,
                                        current_candidates=[old,new],
                                        reviewed_override={"13095813"})
            self.assertEqual(future['active_count'],historic['active_count']-1)
            self.assertIn("98765123",{x['id'] for x in future['active']})
            self.assertNotIn("13095813",{x['id'] for x in future['active']})
            self.assertEqual(future['reviewed_archived_count'],1)
            self.assertEqual(future['reviewed_archived'][0]['id'],"13095813")
            self.assertNotIn("13095813",{x['id'] for x in future['closed_historical']})
            self.assertEqual(future['approved_buy'],0)
            self.assertEqual(future['approved_build'],0)
            self.assertIn("reviewed and archived",backlog.summarize(future).lower())

    def test_new_only_qualification_preserves_source_checks(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=pathlib.Path(tmp)
            seo={"provider_status":"PASS","terminal_status":"PASS","source_complete":True,"items":[]}
            fl={"status":"PASS","new":[
                {"identity":"flippa:13095813","source":"FLIPPA","verified_detail":True,
                 "title":"Old case","asking_verified":1000,"profit_card":900},
                {"identity":"flippa:98765123","source":"FLIPPA","verified_detail":True,
                 "title":"New case","asking_verified":1000,"profit_card":900}
            ]}
            prior=qualify("2026-11-11",seo,fl,root=root)
            now=qualify("2026-11-12",seo,fl,root=root)
            self.assertEqual(prior['evaluated'],2)
            self.assertEqual(now['evaluated'],1)
            self.assertEqual(now['archived_reviewed_suppressed'],1)
            self.assertEqual([x['identity'] for x in now['candidates']],["flippa:98765123"])
            self.assertEqual((now['approved_buy'],now['approved_build']),(0,0))
            self.assertEqual(now['status'],"PASS")

    def test_old_listing_absence_is_not_sold(self):
        self.assertNotIn("00000000",reviewed_processed_ids("2026-11-12"))
        self.assertFalse(is_reviewed_prior_listing("flippa:98765123","2026-11-12"))



    def test_manual_review_date_scope_and_reopen(self):
        app={"identity":"flippa:13817253","ask_card":0,"profit_card":648}
        y={"identity":"flippa:14903899","ask_card":699}
        self.assertFalse(is_manual_review_duplicate(app,"2026-11-24"))
        self.assertTrue(is_manual_review_duplicate(app,"2026-11-25"))
        self.assertTrue(is_manual_review_duplicate(y,"2026-11-26"))
        self.assertTrue(is_manual_review_duplicate(dict(app,ask_card=4000),"2026-11-26"))
        self.assertFalse(is_manual_review_duplicate(dict(app,verified_detail=True,asking_verified=4000),"2026-11-26"))
        self.assertTrue(is_manual_review_duplicate(dict(app,verified_detail=True,asking_verified=14000),"2026-11-26"))
        self.assertFalse(is_manual_review_duplicate(dict(app,verified_detail=True,asking_verified=4000,profit_independently_verified=True),"2026-11-26"))
        self.assertTrue(is_manual_review_duplicate(dict(y,verified_detail=True,asset_domain_verified=True,independent_build_gap={"source":"fixture"}),"2026-11-26"))
        self.assertFalse(is_manual_review_duplicate({"identity":"flippa:99999999"},"2026-11-26"))
        self.assertEqual(len(reviewed_processed_ids("2026-11-26")),87)

    def test_manual_review_suppressed_in_qualification(self):
        with tempfile.TemporaryDirectory() as tmp:
            seo={"provider_status":"PASS","terminal_status":"PASS","source_complete":True,"items":[]}
            fl={"status":"BLOCKED_SOURCE","new":[{"identity":"flippa:13817253"},{"identity":"flippa:14903899"},{"identity":"flippa:99999999"}]}
            v=qualify("2026-11-25",seo,fl,root=pathlib.Path(tmp))
            self.assertEqual(v["archived_reviewed_suppressed"],2)
            self.assertEqual(v["evaluated"],1)
            self.assertEqual(v["status"],"PARTIAL_BLOCKED")
            self.assertEqual((v["approved_buy"],v["approved_build"]),(0,0))



    def test_gap_audit_preserves_history_and_excludes_resolved_flippa(self):
        from audit_gap_ledger import reconcile_dd
        def row(identity, source, day, category="BUILD_DD"):
            return dict(identity=identity, source=source, day=day, category=category)
        history = [
            row("flippa:111", "FLIPPA", "2026-11-01"),
            row("flippa:222", "FLIPPA", "2026-11-02"),
            row("flippa:333", "FLIPPA", "2026-11-03"),
            row("example.test", "SEOTRENDS", "2026-11-01"),
            row("example.test", "SEOTRENDS", "2026-11-02", "DUAL_DD"),
        ]
        original = json.dumps(history)
        pending, resolved = reconcile_dd(history, {
            "reviewed_archived": [{"id": "111"}],
            "closed_historical": [{"id": "222"}],
        })
        self.assertEqual({x["identity"] for x in pending}, {"flippa:333", "example.test"})
        self.assertEqual({x["resolution"] for x in resolved}, {"REVIEWED_ARCHIVED", "CONFIRMED_CLOSED"})
        self.assertEqual(next(x for x in pending if x["identity"] == "example.test")["category"], "DUAL_DD")
        self.assertEqual(json.dumps(history), original)
        self.assertEqual(len(reconcile_dd(history, {})[0]), 4)



    def test_manual_review_does_not_consume_fresh_watch_quota(self):
        from unittest.mock import patch
        import opportunity_daily as daily
        def row(identity):
            return dict(identity="flippa:"+identity,source="FLIPPA",verdict="WATCH_RESEARCH")
        rows=[row("13817253"),row("14903899")]+[row(str(99000000+i)) for i in range(5)]
        seo={"items":[]}
        flippa={"new":rows,"status":"PASS"}
        with patch.object(daily,"read_seo",return_value=seo), patch.object(daily,"read_flippa",return_value=flippa), patch.object(daily,"qualify",return_value={"status":"PASS","candidates":[]}), patch.object(daily,"build_backlog",return_value={}):
            data=daily.build("2026-11-25",None)
        self.assertEqual(len(data["research_queue"]),5)
        self.assertEqual(data["reviewed_source_watch_suppressed"],2)
        self.assertEqual(len(data["flippa"]["new"]),7)



    def test_preliminary_triage_is_source_bound_and_not_resolution(self):
        import audit_gap_ledger as audit
        from unittest.mock import patch
        self.assertEqual(len(audit.SEO64_TRIAGE),64)
        with tempfile.TemporaryDirectory() as tmp:
            root=pathlib.Path(tmp)
            ident="deciphertools.com"
            day,sha,group=audit.SEO64_TRIAGE[ident]
            row=dict(identity=ident,source="SEOTRENDS",day=day,category="BUILD_DD",approved=False)
            hashes={day:audit.SEO64_REPORT_HASHES[day]}
            with patch.object(audit,"sourcehash",return_value=sha):
                result=audit.annotate_preliminary_triage([row],"2026-11-25",root,hashes)[0]
                self.assertEqual(result["preliminary_triage"]["group"],group)
                self.assertFalse(result["preliminary_triage"]["semantic_dd_complete"])
                self.assertEqual(result["category"],"BUILD_DD")
                self.assertFalse(result["approved"])
                self.assertNotIn("preliminary_triage",row)
                for changed,end,hs in [
                    (row,"2026-11-24",hashes),
                    (dict(row,day="2026-11-26"),"2026-11-26",hashes),
                    (dict(row,source="FLIPPA"),"2026-11-25",hashes),
                    (row,"2026-11-25",{day:"changed"}),
                    (row,"2026-11-25",{}),
                ]:
                    self.assertNotIn("preliminary_triage",audit.annotate_preliminary_triage([changed],end,root,hs)[0])
            with patch.object(audit,"sourcehash",return_value="changed"):
                self.assertNotIn("preliminary_triage",audit.annotate_preliminary_triage([row],"2026-11-25",root,hashes)[0])



    def test_semantic_cycle_receipt_separates_drop_defer_and_pending(self):
        import audit_gap_ledger as a
        with tempfile.TemporaryDirectory() as tmp:
            root=pathlib.Path(tmp)
            day="2026-10-15"; end="2026-11-25"
            evidence={day:{"daily":"report","queue":"queue","serp":"serp"}}
            def row(domain):
                return dict(day=day,identity=domain,source="SEOTRENDS",category="BUILD_DD",
                            approved=False,preliminary_triage={"status":"SCREENED_PRELIMINARY","source_export_sha256":"export"})
            def item(domain,verdict):
                return dict(domain=domain,semantic_verdict=verdict,terminal_verdict="WATCH",
                            product_intent_checked=True,review_scope="historical_build_dd_current_cycle_disposition_only",
                            reviewed_at="2026-11-25T21:00:00+07:00",source_report_sha256="report",
                            source_queue_sha256="queue",source_terminal_sha256="serp",
                            source_export_sha256="export",approved_build=False,
                            full_positive_business_dd_complete=False,business_reason="source-based reason")
            rows=[row("drop.test"),row("defer.test"),row("new.test")]
            items=[item("drop.test","DROP_THIS_CYCLE"),item("defer.test","DEFER_GAP_UNPROVEN")]
            path=root/(day+"-semantic-business-dd.json")
            data=dict(date=day,source="derived-semantic-dd-v1",status="PASS_SOURCE_PLUS_SEMANTIC_SCREEN",
                      coverage_scope="selected_legacy_build_dd_identities_only_not_full_daily_shortlist",
                      approved_build=0,buy_now=0,items=items)
            def run():
                return a.reconcile_semantic_cycle(rows,end,root,evidence)
            path.write_text(json.dumps(data))
            active,dropped,deferred=run()
            self.assertEqual([x["identity"] for x in active],["new.test"])
            self.assertEqual([x["identity"] for x in dropped],["drop.test"])
            self.assertEqual([x["identity"] for x in deferred],["defer.test"])
            self.assertFalse(deferred[0]["full_positive_business_dd_complete"])
            self.assertFalse(deferred[0]["approved"])
            self.assertNotIn("cycle_disposition",rows[0])
            for invalid in [dict(items[0],source_export_sha256="drift"),
                            dict(items[0],source_report_sha256="drift"),
                            dict(items[0],source_queue_sha256="drift"),
                            dict(items[0],source_terminal_sha256="drift"),
                            dict(items[0],reviewed_at="2026-11-26T00:00:00+07:00"),
                            dict(items[0],approved_build=True),
                            dict(items[0],semantic_verdict="QUALIFIED_DD")]:
                path.write_text(json.dumps(dict(data,items=[invalid,items[1]])))
                self.assertEqual([x["identity"] for x in run()[0]],["drop.test","new.test"])
                self.assertEqual(len(run()[1]),0)
            path.write_text(json.dumps(dict(data,items=[items[0],items[0],items[1]])))
            self.assertEqual(len(run()[1]),0)
            path.write_text("[]")
            self.assertEqual(len(run()[0]),3)
            path.unlink()
            self.assertEqual(len(run()[0]),3)



    def test_six_reference_reviews_are_dated_and_separate(self):
        from reviewed_cutover import REFERENCE_REVIEWS, reference_review
        self.assertEqual(len(REFERENCE_REVIEWS),6)
        with tempfile.TemporaryDirectory() as tmp:
            root=pathlib.Path(tmp)
            candidates=[dict(identity="flippa:"+i,source="FLIPPA",category="REFERENCE_ONLY",title=i) for i in REFERENCE_REVIEWS]
            original=json.dumps(candidates)
            before=backlog.build_backlog("2026-11-24",root=root,report_root=root,current_candidates=candidates)
            after=backlog.build_backlog("2026-11-25",root=root,report_root=root,current_candidates=candidates)
            ids=set(REFERENCE_REVIEWS)
            self.assertEqual({x["id"] for x in before["active"]}&ids,ids)
            self.assertEqual({x["id"] for x in after["active"]}&ids,{"14803487"})
            self.assertEqual({x["id"] for x in after["reference_dropped"]},{"14742170","14784037","14809474","14816607"})
            self.assertEqual({x["id"] for x in after["reference_deferred"]},{"14773340"})
            self.assertFalse({x["id"] for x in after["closed_historical"]}&ids)
            self.assertEqual(after["manual_reference_reviewed_count"],6)
            self.assertEqual(json.dumps(candidates),original)
            self.assertEqual((after["approved_buy"],after["approved_build"]),(0,0))
            self.assertEqual(before["manual_reference_reviewed_count"],0)
            self.assertIsNone(reference_review("flippa:14742170","2026-11-24"))
            self.assertEqual(len(reviewed_processed_ids("2026-11-25")),87)
            reopened=dict(candidates[0],category="BUILD_DD",evidence=dict(
                verified_direct_listing=True,asset_site_review_complete=True,
                asset_domain_identity_verified=True,build_serp_gap_verified=True))
            (root/"2026-11-24-research-queue.json").write_text(json.dumps({"qualification":{"candidates":candidates}}))
            later=backlog.build_backlog("2026-11-26",root=root,report_root=root,current_candidates=[reopened])
            row=next(x for x in later["active"] if x["id"]==reopened["identity"].split(":")[1])
            self.assertEqual(row["reference_reopened_on"],"2026-11-26")
            self.assertEqual(row["research_lane"],"BUILD_DD")
            self.assertEqual(later["reference_dropped_count"],3)
            self.assertEqual(later["manual_reference_reviewed_count"],6)

    def test_reference_dedup_does_not_block_later_verified_gap(self):
        from reviewed_cutover import REFERENCE_REVIEWS
        from unittest.mock import patch
        for i in REFERENCE_REVIEWS:
            row={"identity":"flippa:"+i,"ask_card":1}
            self.assertFalse(is_manual_review_duplicate(row,"2026-11-24"))
            self.assertTrue(is_manual_review_duplicate(row,"2026-11-25"))
            self.assertTrue(is_manual_review_duplicate(dict(row,verified_detail=True,asking_verified=10),"2026-11-26"))
            with patch("build_buy_decision.verified_flippa_site_review",return_value=True),patch("build_buy_decision.verified_flippa_build_gap",return_value=True):
                self.assertFalse(is_manual_review_duplicate(dict(row,verified_detail=True),"2026-11-26"))
                self.assertTrue(is_manual_review_duplicate(dict(row,verified_detail=True),"2026-11-25"))
        self.assertFalse(is_manual_review_duplicate({"identity":"flippa:99999999"},"2026-11-26"))


if __name__ == "__main__":
    unittest.main()
