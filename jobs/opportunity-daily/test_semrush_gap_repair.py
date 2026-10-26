#!/usr/bin/env python3
"""No provider calls: safety gates for a historical backfill."""
import unittest,tempfile,pathlib,json,time,datetime,os
from unittest.mock import patch
import semrush_gap_repair as m

class SafeBackfill(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.root=pathlib.Path(self.tmp.name)
        self.old=(m.S,m.O,m.HANDOFF,m.LOCK,m.STATE,m.COOLDOWN)
        m.S=self.root/'scans';m.S.mkdir()
        m.O=self.root/'reports';m.O.mkdir()
        m.HANDOFF=self.root/'handoff.jsonl'
        m.LOCK=self.root/'lock'
        m.STATE=self.root/'state.json'
        m.COOLDOWN=self.root/'cooldown.json'
        self.day='2026-10-22'
        self.q=m.S/(self.day+'-semrush-queue.json')
        self.res=m.S/(self.day+'-semrush-results.json')
        self.term=m.S/(self.day+'-terminal-verdicts.json')
        self.q.write_text(json.dumps({'date':self.day,'scan_terminal':True,'scanned':120,'added_total':120,'count':1,'items':[{'domain':'example.com'}]}))
        self.res.write_text(json.dumps({'status':'BLOCKED','global_blocker':'RuntimeError:BROKER_DPA:NOX_DASHBOARD_CHALLENGE'}))
        self.term.write_text(json.dumps({'status':'BLOCKED'}))
    def tearDown(self):
        m.S,m.O,m.HANDOFF,m.LOCK,m.STATE,m.COOLDOWN=self.old
        self.tmp.cleanup()
    def test_missing_verified_handoff_denies(self):
        self.assertIsNone(m.handoff_ticket())
        self.assertEqual(m.process()['state'],'AWAITING_VERIFIED_HUMAN_AUTH')
    def test_valid_handoff_gated(self):
        event={'event':'HUMAN_HANDOFF_RESULT','ok':True,'status':'CAPTCHA_ACCEPTED',
               'same_session':True,'service':'semrush','profile':'noxtools-main','auth_verified':True}
        self.HANDOFF_path=m.HANDOFF
        m.HANDOFF.write_text(json.dumps(event)+'\n')
        self.assertTrue(m.handoff_ticket())
    def test_unverified_captcha_not_allowed(self):
        event={'event':'HUMAN_HANDOFF_RESULT','ok':True,'status':'CAPTCHA_ACCEPTED',
               'same_session':True,'service':'semrush','profile':'noxtools-main','auth_verified':False}
        m.HANDOFF.write_text(json.dumps(event)+'\n')
        self.assertIsNone(m.handoff_ticket())
    def test_existing_queue_eligible(self):
        self.assertEqual(m.eligible(self.day)['mode'],'EXPORT_THEN_SERP')
    def test_bad_queue_wont_run(self):
        v=json.loads(self.q.read_text());v['items']=[];self.q.write_text(json.dumps(v))
        self.assertIsNone(m.eligible(self.day))
    def test_expensive_queue_over_cap_not_run(self):
        v=json.loads(self.q.read_text());v['items']=[{'domain':f'{i}.com'} for i in range(26)];v['count']=26;self.q.write_text(json.dumps(v))
        self.assertIsNone(m.eligible(self.day))
    def test_passed_source_and_serp_not_repeated(self):
        self.res.write_text(json.dumps({'status':'PASS'}))
        self.term.write_text(json.dumps({'status':'PASS'}))
        self.assertIsNone(m.eligible(self.day))
    def test_partial_transient_one_failed_is_eligible(self):
        self.res.write_text(json.dumps({'status':'PARTIAL','items':[{'domain':'example.com','status':'FAIL','reason':'RuntimeError:BROKER_DPA:SEMRUSH_BROKER_RUNTIME_ERROR'}]}))
        x=m.eligible(self.day)
        self.assertIsNotNone(x)
        self.assertEqual(x['reason'],'PARTIAL_TRANSIENT_ONLY')
    def test_partial_provider_quota_must_not_replay(self):
        self.res.write_text(json.dumps({'status':'PARTIAL','items':[{'domain':'example.com','status':'FAIL','reason':"RuntimeError:BROKER_DPA:{'code': -32098, 'message': 'Limits exceeded'}"}]}))
        self.assertIsNone(m.eligible(self.day))
    def test_rate_limit_requires_expired_trustworthy_cooldown(self):
        self.res.write_text(json.dumps({'status':'BLOCKED','global_blocker':'RuntimeError:SEMRUSH_RATE_LIMIT:provider'}))
        # Missing authoritative expiry is not permission to retry.
        self.assertIsNone(m.eligible(self.day))
        m.COOLDOWN.write_text(json.dumps({'until_epoch':time.time()+3600}))
        self.assertIsNone(m.eligible(self.day))
        m.COOLDOWN.write_text(json.dumps({'until_epoch':time.time()-30}))
        v=m.eligible(self.day)
        self.assertEqual(v['reason'],'RATE_LIMIT_EXPIRED')
    def test_report_limit_is_not_a_rate_limit(self):
        self.res.write_text(json.dumps({'status':'BLOCKED','global_blocker':'SEMRUSH_REPORT_LIMIT'}))
        m.COOLDOWN.write_text(json.dumps({'until_epoch':time.time()-100}))
        self.assertIsNone(m.eligible(self.day))
    def test_interrupted_receipt_never_becomes_a_pass(self):
        now=datetime.datetime.now(m.TZ)
        entries={'2026-10-25':{'status':'ATTEMPT_STARTED','started_at':(now-datetime.timedelta(minutes=20)).isoformat(),'handoff_event':'ticket'},
                 '2026-10-26':{'status':'ATTEMPT_STARTED','started_at':now.isoformat(),'handoff_event':'ticket'}}
        self.assertTrue(m.reconcile_interrupted(entries,now))
        self.assertEqual(entries['2026-10-25']['status'],'INTERRUPTED_UNVERIFIED')
        self.assertEqual(entries['2026-10-25']['reason'],'NO_COMPLETION_RECEIPT')
        self.assertEqual(entries['2026-10-25']['handoff_event'],'ticket')
        self.assertEqual(entries['2026-10-26']['status'],'ATTEMPT_STARTED')
    def test_rate_limit_one_retry_per_verified_handoff(self):
        days=[{'day':'2026-10-26','reason':'RATE_LIMIT_EXPIRED','shortlist':17}]
        recent={'2026-10-26':{'handoff_event':'ticket','status':'NOT_RECOVERED','retry_after_cooldown_used':False}}
        first=m.choose_candidate(days,recent,'ticket')
        self.assertTrue(first['retry_after_cooldown_used'])
        recent['2026-10-26']['retry_after_cooldown_used']=True
        self.assertIsNone(m.choose_candidate(days,recent,'ticket'))
        # A newly confirmed user-authenticated handoff is a separate event.
        self.assertEqual(m.choose_candidate(days,recent,'new-ticket')['day'],'2026-10-26')
    def test_non_throttle_failure_requires_new_handoff(self):
        days=[{'day':'2026-10-19','reason':'PARTIAL_TRANSIENT_ONLY'}]
        prev={'2026-10-19':{'handoff_event':'ticket','status':'NOT_RECOVERED'}}
        self.assertIsNone(m.choose_candidate(days,prev,'ticket'))
    def test_provider_pass_but_serp_pending(self):
        self.res.write_text(json.dumps({'status':'PASS'}))
        self.assertEqual(m.eligible(self.day)['mode'],'SERP_ONLY')
    def test_other_errors_not_retried(self):
        self.res.write_text(json.dumps({'status':'BLOCKED','global_blocker':'QUOTA_LIMIT'}))
        self.assertIsNone(m.eligible(self.day))

if __name__=='__main__': unittest.main(verbosity=2)
