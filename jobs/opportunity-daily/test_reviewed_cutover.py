#!/usr/bin/env python3
"""87-entry user cutover: no resurrection, no history rewrite, no false SOLD."""
import tempfile
import pathlib
import json
import unittest
import acquisition_backlog as backlog
from reviewed_cutover import reviewed_processed_ids, is_reviewed_prior_listing
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


if __name__ == "__main__":
    unittest.main()
