#!/usr/bin/env python3
"""Offline regression checks for cumulative Flippa carry-forward semantics."""
import json
import pathlib
import tempfile
import unittest
from unittest.mock import patch

import acquisition_backlog as b

class BacklogRegression(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root=pathlib.Path(self.tmp.name)
        (self.root/'FLIPPA-INVENTORY-CURRENT-20261006.json').write_text(json.dumps({
            'main':{'12661644':['Historical product',None,1780,1950,'SaaS','',1,'https://flippa.com/12661644']}}))
        self.make_recent('20261016',{'14414582':{'p':5000,'pr':631,'rev':631,'href':'https://flippa.com/14414582'}},400)
        self.make_recent('20261017',{'14414582':{'p':5000,'pr':631,'rev':631,'href':'https://flippa.com/14414582'}},500)
        (self.root/'2026-10-16-research-queue.json').write_text(json.dumps({
            'qualification':{'candidates':[{'identity':'flippa:99999991','source':'FLIPPA',
                  'title':'Old candidate','category':'BUY_DD','missing':['processor proof','GSC']} ]}}))
    def make_recent(self,day,rows,count):
        ids=list(rows.keys())+[str(80000000+i) for i in range(count-len(rows))]
        (self.root/('flippa-'+day+'-daily-state.json')).write_text(json.dumps({
            'recent_done':True,'recent_ids':ids,'recent_rows':rows}))
    def load(self,day='2026-10-17'):
        return b.build_backlog(day,root=self.root,report_root=self.root)
    def test_carry_old_priority_outside_recent(self):
        d=self.load();rows={x['id']:x for x in d['active']}
        self.assertEqual(rows['12661644']['research_lane'],'FORENSIC_DD')
        self.assertEqual(rows['12661644']['recent_500_presence'],'NOT_SEEN')
        self.assertEqual(rows['12661644']['current_listing_status'],'CURRENT_AVAILABILITY_UNVERIFIED')
        self.assertEqual(rows['12661644']['card']['card_profit_usd_month'],1780)
    def test_seen_recent_preserves_old_dd_priority(self):
        d=self.load();x=next(x for x in d['active'] if x['id']=='14414582')
        self.assertEqual(x['recent_500_presence'],'SEEN')
        self.assertEqual(x['research_lane'],'BUY_DD')
        self.assertEqual(x['card']['card_price_usd'],5000)
        self.assertEqual(x['last_card_observation_on'],'2026-10-17')
    def test_old_daily_dd_is_carried(self):
        d=self.load()
        x=next(x for x in d['active'] if x['id']=='99999991')
        self.assertEqual(x['origin'],'HISTORICAL_DAILY_DD')
        self.assertEqual(x['source_decision_as_of'],'2026-10-16')
    def test_not_in_latest_recent_does_not_mean_sold(self):
        d=self.load()
        self.assertFalse(any(x['status']=='SOLD' for x in d['active']))
        self.assertEqual(len(set(x['id'] for x in d['active'])),len(d['active']))
        self.assertTrue(d['policy']['no_dropping_on_recent_absence'])
    def test_closed_evidence_kept_separate(self):
        d=self.load()
        self.assertEqual(next(x['last_direct_status'] for x in d['closed_historical']
                              if x['id']=='14265493'),'SOLD')
        self.assertFalse(any(x['id']=='14265493' for x in d['active']))
    def test_no_buy_promotion(self):
        d=self.load()
        self.assertEqual((d['approved_buy'],d['approved_build']),(0,0))
        self.assertTrue(all(not x['approved_buy'] and not x['approved_build'] for x in d['active']))
    def test_deterministic(self):
        self.assertEqual(self.load(),self.load())
    def test_no_future_candidates_in_historical_day(self):
        d=self.load('2026-10-16')
        self.assertFalse(any(x['id']=='14494999' for x in d['active']))
        self.assertTrue(any(x['id']=='99999991' for x in d['active']))

if __name__=='__main__':
    unittest.main()
