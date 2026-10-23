#!/usr/bin/env python3
"""Source preservation + CAPTCHA human completion guard; offline only."""
import json, pathlib, tempfile, unittest, datetime, os
from unittest.mock import patch
import auth_resume as a
from zoneinfo import ZoneInfo
DAY=datetime.datetime.now(ZoneInfo('Asia/Ho_Chi_Minh')).date().isoformat()

class SafeAuthResumeGates(unittest.TestCase):
 def setUp(self):
  self.t=tempfile.TemporaryDirectory();self.root=pathlib.Path(self.t.name)
  self.orig=(a.SEO,a.LOG,a.MARKER)
  a.SEO=self.root;a.LOG=self.root/'handoff.jsonl';a.MARKER=self.root/'attempt.json'
  self.q=self.root/(DAY+'-semrush-queue.json')
  self.r=self.root/(DAY+'-semrush-results.json')
  self.q.write_text(json.dumps({'date':DAY,'scan_terminal':True,'count':1,'added_total':217,'scanned':217,'items':[{'domain':'example.com'}]}))
  self.r.write_text(json.dumps({'status':'BLOCKED','global_blocker':'RuntimeError:BROKER_DPA:SEMRUSH_LIVE_AUTH_UNAVAILABLE'}))
  accepted={'event':'HUMAN_HANDOFF_RESULT','ok':True,'status':'CAPTCHA_ACCEPTED','same_session':True,'service':'semrush','profile':'noxtools-main','auth_verified':True}
  self.log=accepted
  self.write_log(accepted)
 def write_log(self,event):
  self.LOG_path=a.LOG
  a.LOG.write_text(json.dumps(event)+'\n')
  # mtime only affects the temporal gate; no source data overwritten.
  self.blocked_time=(datetime.datetime.now(ZoneInfo('Asia/Ho_Chi_Minh'))-datetime.timedelta(minutes=5)).timestamp()
  self.handoff_time=datetime.datetime.now(ZoneInfo('Asia/Ho_Chi_Minh')).timestamp()
  os.utime(self.r,(self.blocked_time,self.blocked_time))
  os.utime(a.LOG,(self.handoff_time,self.handoff_time))
 def tearDown(self):
  a.SEO,a.LOG,a.MARKER=self.orig
  self.t.cleanup()
 def test_accepted_same_day_ready(self):
  self.assertEqual(a.decision(DAY)['state'],'READY')
 def test_never_restart_after_pass(self):
  self.r.write_text(json.dumps({'status':'PASS'}))
  (self.root/(DAY+'-terminal-verdicts.json')).write_text(json.dumps({'status':'PASS'}))
  self.assertEqual(a.decision(DAY)['state'],'ALREADY_PASS')
 def test_no_human_checkbox_event_not_ready(self):
  self.write_log({'event':'HUMAN_HANDOFF_RESULT','ok':False,'status':'TIMEOUT','same_session':True})
  self.assertEqual(a.decision(DAY)['state'],'NO_ACCEPTED_SAME_SESSION_HANDOFF')
 def test_first_error_not_auth_must_not_resume(self):
  self.r.write_text(json.dumps({'status':'BLOCKED','global_blocker':'DPA_QUOTA_LIMIT'}))
  self.assertEqual(a.decision(DAY)['state'],'NOT_HUMAN_AUTH_BLOCKER')
 def test_empty_queue_not_resumed(self):
  j=json.loads(self.q.read_text());j['items']=[];self.q.write_text(json.dumps(j))
  self.assertEqual(a.decision(DAY)['state'],'NO_COMPLETE_SAME_DAY_QUEUE')
 def test_same_day_replay_guard(self):
  ticket=a.decision(DAY)['ticket']
  a.MARKER.write_text(json.dumps({'ticket':ticket,'state':'ATTEMPT_STARTED'}))
  self.assertEqual(a.decision(DAY)['state'],'ALREADY_ATTEMPTED_AFTER_HANDOFF')
 def test_stale_handoff_does_not_retry(self):
  daybefore=(datetime.datetime.now(ZoneInfo('Asia/Ho_Chi_Minh'))-datetime.timedelta(days=1)).timestamp()
  os.utime(a.LOG,(daybefore,daybefore))
  self.assertEqual(a.decision(DAY)['state'],'NO_NEW_HUMAN_HANDOFF')
 def test_dry_run_never_mutates(self):
  self.assertEqual(a.resume(DAY,dry_run=True)['state'],'READY')
  self.assertFalse(a.MARKER.exists())

if __name__=='__main__':unittest.main(verbosity=2)
