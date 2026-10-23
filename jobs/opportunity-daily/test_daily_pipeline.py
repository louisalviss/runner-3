#!/usr/bin/env python3
"""Network-free regression for Flippa independent Semrush and daily Dropbox auto publish."""
import json,pathlib,sys,tempfile,unittest
from unittest.mock import patch
from flippa_semrush_bridge import inspect, domain_from_verified_listing
from daily_publish import publish, render_current

class DailyPipelineGates(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.d=pathlib.Path(self.tmp.name)
  self.x={"id":"14459714","identity":"flippa:14459714","verdict":"BUILD_REFERENCE","verified_detail":True,"title":"HVAC Planner"}
  self.deep=[{"id":"14459714","status":200,"challenge":"NONE","title":"HVAC Planner: HVACPlanner.com — 42 calculators | Website for Sale on Flippa"}]
  (self.d/'deep.json').write_text(json.dumps(self.deep))
  self.flippa={"status":"PASS","new":[self.x]}
  self.val={"date_vn":"2026-10-14","generated_at":"2026-10-14T09:15:00+07:00","overall":"RESEARCH_PENDING","seo":{"provider_status":"PASS","terminal_status":"PASS"},"flippa":{"status":"PASS"},"qualification":{"status":"PASS"}}
 def tearDown(self):self.tmp.cleanup()
 def test_domain_from_actual_verified_listing_only(self):
  self.assertEqual(domain_from_verified_listing(self.x,{"14459714":self.deep[0]}),"hvacplanner.com")
 def test_unverified_detail_not_crosschecked(self):
  self.assertIsNone(domain_from_verified_listing({**self.x,"verified_detail":False},{"14459714":self.deep[0]}))
 def test_multiple_domains_ambiguous_skipped(self):
  p={**self.deep[0],"title":"Site: Alpha.com and Beta.net | Flippa"}
  self.assertIsNone(domain_from_verified_listing(self.x,{"14459714":p}))
 def test_no_blind_flippa_slug_source(self):
  p={**self.deep[0],"title":"Website for sale on Flippa"}
  self.assertIsNone(domain_from_verified_listing(self.x,{"14459714":p}))
 def test_empty_no_provider_calls(self):
  v=inspect("2026-10-14",{"status":"PASS","new":[]},output_root=self.d)
  self.assertEqual(v["status"],"PASS_EMPTY")
  self.assertEqual(v["eligible"],0)
 def test_cached_valid_no_export(self):
  d=self.d/'flippa-sem-20261014';d.mkdir()
  (d/'hvacplanner.com.json').write_text(json.dumps({"domain":"hvacplanner.com","total_reported":3,"rows":[{"phrase":"hvac cost","traffic":12}]}))
  v=inspect("2026-10-14",self.flippa,self.d/'deep.json',output_root=self.d,exporter=self.d/'missing.py')
  self.assertEqual(v["status"],"PASS")
  self.assertEqual(v["items"][0]["metrics"]["estimated_us_organic_visits"],12)
  self.assertEqual(v["items"][0]["source"],"cached-existing-export")
 def test_bounded_provider_one_and_no_repeat(self):
  f=self.d/'fake.py'
  f.write_text("import json,sys,pathlib\np=pathlib.Path(sys.argv[sys.argv.index('--output')+1]);p.write_text(json.dumps({'domain':'hvacplanner.com','total_reported':2,'rows':[{'phrase':'hvac cost','traffic':15}]}));print(json.dumps({'status':'PASS'}))\n")
  v=inspect("2026-10-14",self.flippa,self.d/'deep.json',output_root=self.d,exporter=f,timeout=10)
  self.assertEqual(v["status"],"PASS")
  self.assertEqual(v["counts"]["PASS"],1)
  v2=inspect("2026-10-14",self.flippa,self.d/'deep.json',output_root=self.d,exporter=self.d/'missing.py')
  self.assertEqual(v2["items"][0]["source"],"fresh-export")
 def test_auth_failure_blocks_and_no_zero_demand(self):
  f=self.d/'fake_block.py'
  f.write_text("import json\nprint(json.dumps({'status':'FAIL','reason':'BROKER_DPA:SEMRUSH_LIVE_AUTH_UNAVAILABLE'}))\n")
  v=inspect("2026-10-14",self.flippa,self.d/'deep.json',output_root=self.d,exporter=f,timeout=10)
  self.assertEqual(v["status"],"BLOCKED")
  self.assertEqual(v["items"][0]["status"],"BLOCKED")
  self.assertNotIn("metrics",v["items"][0])
 def test_render_current_explicit_status(self):
  txt=render_current(self.val,"## Evidence\n- zero promotions")
  self.assertIn("STATUS: DAILY_CHECK_PASS_NO_BUY_NO_BUILD",txt)
  self.assertIn("LAST_SCAN: 2026-10-14 09:15 +07:00",txt)
  self.assertIn("zero promotions",txt)
 def test_render_keeps_every_scoped_candidate(self):
  x={**self.val,'qualification':{'status':'PASS','candidates':[{'identity':'alpha.com','title':'Alpha','source':'SEOTRENDS','buy':{'state':'NOT_LISTED'},'build':{'state':'DROP'},'category':'DROP'},{'identity':'flippa:10','title':'Beta','source':'FLIPPA','buy':{'state':'DEFER'},'build':{'state':'REFERENCE_ONLY'},'category':'REFERENCE_ONLY'}]}}
  t=render_current(x,'Evidence')
  self.assertIn('Alpha | SEOTRENDS | NOT_LISTED | DROP | DROP',t)
  self.assertIn('Beta | FLIPPA | DEFER | REFERENCE_ONLY | REFERENCE_ONLY',t)
 def test_historical_replay_cannot_become_newer_current(self):
  value={**self.val,'date_vn':'2026-10-18','generated_at':'2026-10-23T14:30:00+07:00'}
  s=render_current(value,'Historical evidence')
  self.assertIn('LAST_SCAN: 2026-10-18 09:15 +07:00',s)
  self.assertNotIn('LAST_SCAN: 2026-10-23 14:30',s)
 def test_render_blocked_not_claim_pass(self):
  x={**self.val,"overall":"PARTIAL_BLOCKED"}
  self.assertIn("STATUS: DAILY_PARTIAL_BLOCKED_NEEDS_REVIEW",render_current(x,"blocked"))
 def test_publisher_success_idempotent(self):
  f=self.d/'publisher'
  f.write_text("#!/bin/sh\necho 'DROPBOX_SYNC_PASS label=demo'\n")
  f.chmod(0o700)
  a=publish("2026-10-14",self.val,"Evidence",out=self.d,runner=f)
  b=publish("2026-10-14",self.val,"Evidence",out=self.d,runner=self.d/'missing')
  self.assertEqual(a['status'],"PASS")
  self.assertEqual(b['status'],"ALREADY_PUBLISHED")
 def test_publish_failure_is_pending(self):
  f=self.d/'publisher';f.write_text("#!/bin/sh\nexit 4\n");f.chmod(0o700)
  a=publish("2026-10-14",self.val,"Evidence",out=self.d,runner=f)
  self.assertEqual(a["status"],"PENDING_RETRY")
  self.assertTrue((self.d/"2026-10-14-dropbox-publish.json").exists())

if __name__=='__main__':unittest.main(verbosity=2)
