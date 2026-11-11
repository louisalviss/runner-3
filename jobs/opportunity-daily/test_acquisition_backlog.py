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
    def test_full_report_and_dropbox_current_carry_backlog(self):
        import opportunity_daily as daily
        from daily_publish import render_current
        backlog=self.load()
        value={
            'date_vn':'2026-10-17','generated_at':'2026-10-17T12:00:00+07:00',
            'overall':'RESEARCH_PENDING','cumulative_flippa':backlog,
            'seo':{'scanned':0,'added':0,'items':[], 'provider_status':'PASS','terminal_status':'PASS'},
            'flippa':{'status':'PASS','stats':{}}, 'research_queue':[],
            'qualification':{'status':'PASS','evaluated':0,'counts':{},'actionable_dd':[],
                             'study_queue':[],'candidates':[]}
        }
        report=daily.format_report(value)
        current=render_current(value,report)
        expected_count = (str(backlog['active_count']) + '; historical confirmed closed: ' +
                          str(backlog['closed_historical_count']))
        for marker in ('Cumulative Flippa', 'N8Nitro', 'Inbox Verifyer', expected_count):
            self.assertIn(marker,report)
            self.assertIn(marker,current)
        self.assertIn('Missing from Recent-500 is **not** SOLD/ENDED',current)

    def test_historical_card_persists_when_outside_latest_recent(self):
        b16=json.loads((self.root/'flippa-20261016-daily-state.json').read_text())
        b16['recent_rows']['90009999']={'p':1900,'pr':99,'href':'https://flippa.com/90009999'}
        b16['recent_ids'][1]='90009999'
        (self.root/'flippa-20261016-daily-state.json').write_text(json.dumps(b16))
        with patch.object(b,'SEEDS',b.SEEDS+[('90009999','Historical watch','WATCH',60,
                                               'Verify historical economics','2026-10-16')]):
            data=self.load()
        row=next(x for x in data['active'] if x['id']=='90009999')
        self.assertEqual(row['last_card_observation_on'],'2026-10-16')
        self.assertEqual(row['recent_500_presence'],'NOT_SEEN')
        self.assertEqual(row['card']['card_price_usd'],1900)
        self.assertEqual(row['current_listing_status'],'CURRENT_AVAILABILITY_UNVERIFIED')

    def test_current_day_candidates_are_not_lost_before_first_report_write(self):
        candidate={'source':'FLIPPA','category':'DUAL_DD','identity':'flippa:99999992',
                   'title':'Today new DD','missing':['processor','GSC']}
        d=b.build_backlog('2026-10-17',root=self.root,report_root=self.root,current_candidates=[candidate])
        row=next(x for x in d['active'] if x['id']=='99999992')
        self.assertEqual(row['research_lane'],'DUAL_DD')
        self.assertEqual(row['source_decision_as_of'],'2026-10-17')
        self.assertFalse(row['approved_buy'])
    def test_nov8_direct_recheck_closes_only_proven_listings(self):
        today=self.load('2026-11-08')
        direct={x['id']:x for x in today['closed_historical']
                if x['last_direct_confirmation_as_of']=='2026-11-08'}
        self.assertEqual(set(direct),{'12661644','14277870','14421384',
                                      '14447876','14564050','13650492'})
        self.assertEqual(direct['13650492']['last_direct_status'],'ENDED')
        self.assertTrue(all(x.get('direct_listing_recheck',{}).get('http_status')==200
                            for x in direct.values()))
        self.assertFalse(any(x['id'] in direct for x in today['active']))
        self.assertEqual((today['approved_buy'],today['approved_build']),(0,0))
        self.assertTrue(today['policy']['dated_direct_closure_only'])

    def test_direct_recheck_never_rewrites_historical_day(self):
        historic=self.load('2026-11-07')
        closed={x['id'] for x in historic['closed_historical']}
        active={x['id'] for x in historic['active']}
        self.assertNotIn('12661644',closed)
        self.assertIn('12661644',active)
        self.assertNotIn('14215867',
                         {x['id'] for x in historic['closed_historical']})
        self.assertEqual(next(x['current_listing_status'] for x in historic['active']
                              if x['id']=='14215867'),'CURRENT_AVAILABILITY_UNVERIFIED')

    def test_redirect_preserves_original_identity_but_uses_new_live_id(self):
        d=self.load('2026-11-08')
        r=next(x for x in d['active'] if x['id']=='14215867')
        self.assertEqual(r['identity'],'flippa:14215867')
        self.assertEqual(r['current_listing_status'],'REDIRECTED_TO_NEW_LISTING')
        self.assertEqual(r['effective_listing_id'],'14595704')
        self.assertEqual(r['url'],'https://flippa.com/14595704')
        self.assertEqual(r['direct_listing_recheck']['status'],'REDIRECTED')
        self.assertEqual(r['research_lane'],'BUY_DD')
        self.assertNotIn('14215867',{x['id'] for x in d['closed_historical']})

    def test_redirect_target_not_duplicated_from_daily_candidate(self):
        candidate={'source':'FLIPPA','category':'DUAL_DD',
                   'identity':'flippa:14595704','title':'Inbox Verifyer new ID',
                   'missing':['processor proof']}
        d=b.build_backlog('2026-11-08',root=self.root,report_root=self.root,
                          current_candidates=[candidate])
        self.assertFalse(any(x['id']=='14595704' for x in d['active']))
        self.assertEqual(sum(x.get('effective_listing_id')=='14595704'
                             for x in d['active']),1)

    def add_naditaalim_fixture(self):
        (self.root/'2026-11-01-research-queue.json').write_text(json.dumps({
            'qualification':{'candidates':[{'identity':'flippa:14674707',
                'source':'FLIPPA','title':'Naditaalim',
                'category':'BUILD_DD','missing':['seller accounting proof']}]}
        }))

    def test_nov8_unpublished_and_current_ask_deferred(self):
        self.add_naditaalim_fixture()
        d=self.load('2026-11-08')
        rows={x['id']:x for x in d['active']}
        self.assertEqual(d['closed_historical_count'],11)
        self.assertNotIn('14405223',{x['id'] for x in d['closed_historical']})
        for ident in ('14405223','14674707'):
            row=rows[ident]
            self.assertEqual(row['status'],'WATCH_OR_REFERENCE')
            self.assertEqual(row['current_listing_status'],'DIRECT_UNPUBLISHED')
            self.assertEqual(row['direct_listing_recheck']['http_status'],200)
            self.assertFalse(row['direct_recheck_due'])
        expensive=rows['13880956']
        self.assertEqual(expensive['status'],'WATCH_OR_REFERENCE')
        self.assertEqual(expensive['observed_ask_usd'],12999)
        self.assertEqual(expensive['buy_budget_status'],'LAST_DIRECT_ASK_ABOVE_CAP')
        self.assertEqual(expensive['current_listing_status'],'DIRECT_ASK_ABOVE_BUY_CAP')
        self.assertNotIn('13880956',{x['id'] for x in d['closed_historical']})
        self.assertEqual((d['approved_buy'],d['approved_build']),(0,0))

    def test_nov8_nonterminal_observations_expire(self):
        self.add_naditaalim_fixture()
        fresh=self.load('2026-11-15')
        stale=self.load('2026-11-16')
        for ident in ('14405223','14674707','13880956'):
            f=next(x for x in fresh['active'] if x['id']==ident)
            z=next(x for x in stale['active'] if x['id']==ident)
            self.assertEqual(f['status'],'WATCH_OR_REFERENCE')
            self.assertEqual(z['status'],'DD_PENDING')
            self.assertEqual(z['current_listing_status'],'DIRECT_EVIDENCE_STALE_RECHECK')
            self.assertTrue(z['direct_recheck_due'])
            self.assertEqual(z['direct_recheck_age_days'],8)

    def test_prior_snapshot_does_not_apply_nov8_price(self):
        self.add_naditaalim_fixture()
        d=self.load('2026-11-07')
        rows={x['id']:x for x in d['active']}
        self.assertEqual(rows['13880956']['status'],'DD_PENDING')
        self.assertNotIn('observed_ask_usd',rows['13880956'])
        self.assertEqual(rows['14674707']['status'],'DD_PENDING')
        self.assertEqual(rows['14405223']['status'],'DD_PENDING')

    def test_no_future_candidates_in_historical_day(self):
        d=self.load('2026-10-16')
        self.assertFalse(any(x['id']=='14494999' for x in d['active']))
        self.assertTrue(any(x['id']=='99999991' for x in d['active']))

    def test_dated_ai_substitution_drops_schoolcalendar_without_marking_sold(self):
        before=self.load('2026-11-11')
        old=next((x for x in before['active'] if x['id']=='13095813'),None)
        # The fixture may not contain a real school-calendar candidate; seed
        # it through the same current-candidates path used by the live job.
        candidate={'identity':'flippa:13095813','source':'FLIPPA','title':'SchoolCalendar.net',
                   'category':'BUILD_DD','missing':['seller GA data']}
        historic=b.build_backlog('2026-11-11',root=self.root,report_root=self.root,
                                  current_candidates=[candidate])
        live=b.build_backlog('2026-11-12',root=self.root,report_root=self.root,
                              current_candidates=[candidate])
        oldrow=next(x for x in historic['active'] if x['id']=='13095813')
        row=next(x for x in live['active'] if x['id']=='13095813')
        self.assertEqual(oldrow['ai_substitution_status'],'UNREVIEWED')
        self.assertEqual(row['ai_substitution_status'],'HIGH')
        self.assertEqual(row['status'],'AI_SUBSTITUTION_REJECTED')
        self.assertEqual(row['research_lane'],'BUILD_DD')  # historical identity preserved
        self.assertNotIn('13095813',{x['id'] for x in live['closed_historical']})
        self.assertEqual((live['approved_buy'],live['approved_build']),(0,0))
        self.assertIn('AI substitution rejected',b.summarize(live))

if __name__=='__main__':
    unittest.main()
