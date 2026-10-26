#!/usr/bin/env python3
"""Offline safety checks for archived Flippa DD cross-recovery."""
import json,pathlib,tempfile,unittest,time
from unittest.mock import patch
import flippa_semrush_repair as f
class TestArchivedCross(unittest.TestCase):
 def setUp(self):
  self.t=tempfile.TemporaryDirectory()
  self.r=pathlib.Path(self.t.name)/'data';self.r.mkdir()
  self.o=pathlib.Path(self.t.name)/'reports';self.o.mkdir()
  self.day='2026-10-24'
  self.details=[{'id':'12345678','status':200,'challenge':'NONE','title':'Example.com | Flippa'}]
  self.payload={'date_vn':self.day,'schema':'opportunity-daily-v2','seo':{'provider_status':'PASS','terminal_status':'PASS'},'flippa':{'status':'PASS','new':[{'id':'12345678','identity':'flippa:12345678','verdict':'BUILD_REFERENCE','verified_detail':True}]},'flippa_detail':{'status':'PASS'},'flippa_semrush':{'status':'PARTIAL'}}
  self.save()
 def tearDown(self):self.t.cleanup()
 def save(self):
  (self.o/(self.day+'-research-queue.json')).write_text(json.dumps(self.payload))
  (self.r/'flippa-deep-20261024.json').write_text(json.dumps(self.details))
 def state(self):return f.eligible(self.day,root=self.r,out=self.o)
 def test_needs_cross_check(self):
  self.assertEqual(self.state()['old_status'],'PARTIAL')
 def test_success_no_repeat(self):
  self.payload['flippa_semrush']['status']='PASS';self.save()
  self.assertIsNone(self.state())
 def test_auth_broken_source_excluded(self):
  self.payload['seo']['provider_status']='BLOCKED';self.save()
  self.assertIsNone(self.state())
 def test_flippa_not_observed_excluded(self):
  self.payload['flippa']['status']='BLOCKED';self.save()
  self.assertIsNone(self.state())
 def test_unverified_detail_excluded(self):
  self.details[0]['challenge']='TURNSTILE';self.save()
  self.assertIsNone(self.state())
 def test_bad_date_excluded(self):
  self.payload['date_vn']='2026-10-23';self.save()
  self.assertIsNone(self.state())
 def test_no_human_auth_no_provider(self):
  with patch.object(f.sem,'handoff_ticket',return_value=None):
   self.assertEqual(f.process()['state'],'AWAITING_VERIFIED_HUMAN_AUTH')
 def test_protected_cooldown_no_provider(self):
  with patch.object(f.sem,'handoff_ticket',return_value='verified'),patch.object(f.sem,'COOLDOWN',self.r/'rate.json'):
   (self.r/'rate.json').write_text(json.dumps({'until_epoch':time.time()+120}))
   self.assertEqual(f.process()['state'],'PROVIDER_COOLDOWN')
if __name__=='__main__':unittest.main(verbosity=2)
