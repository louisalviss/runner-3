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


if __name__ == "__main__":
    unittest.main()
