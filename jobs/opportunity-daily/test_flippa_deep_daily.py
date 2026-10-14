#!/usr/bin/env python3
import json,pathlib,tempfile,unittest
from flippa_deep_daily import extract,candidates_for_daily,capture,existing_complete
class FlippaDetailTests(unittest.TestCase):
 def setUp(self):self.t=tempfile.TemporaryDirectory();self.d=pathlib.Path(self.t.name)
 def tearDown(self):self.t.cleanup()
 def test_parse_simple_valid(self):
  r=extract('12345678','SomeSite.com','Reserve: USD $1,000\nBuy It Now for USD $1,500\nPage Views\n300 p/mo',200,'NONE')
  self.assertEqual(r['reserve'],'1,000');self.assertEqual(r['bin'],'1,500');self.assertEqual(r['pageviews'],'300')
 def test_bounded_and_excludes_weak(self):
  rows=[{'id':str(11111111+x),'verdict':'WATCH_RESEARCH'} for x in range(5)]
  rows.append({'id':'22222222','verdict':'DROP_TRAFFIC_WEAK'})
  self.assertEqual(len(candidates_for_daily({'new':rows},limit=15)),3)
 def test_skip_invalid_ids(self):
  self.assertEqual(capture(['abc'],'2026-10-15',out=self.d)['reason'],'INVALID_IDS')
 def test_zero_candidate_no_browser(self):
  self.assertEqual(capture([],'2026-10-15',out=self.d)['status'],'PASS_EMPTY')
 def test_existing_complete_no_browser(self):
  p=self.d/'flippa-deep-20261015.json'
  p.write_text(json.dumps([{'id':'12345678','status':200,'challenge':'NONE'}]))
  self.assertTrue(existing_complete(p,['12345678']))
  self.assertEqual(capture(['12345678'],'2026-10-15',out=self.d)['source'],'VALID_CACHED_DEEP')
 def test_blocked_state_no_retry(self):
  (self.d/'flippa-deep-20261015-state.json').write_text(json.dumps({'date':'2026-10-15','status':'BLOCKED','items':0}))
  self.assertEqual(capture(['12345678'],'2026-10-15',out=self.d)['reason'],'ONE_ATTEMPT_PER_DAY')
 def test_incomplete_does_not_qualify(self):
  p=self.d/'flippa-deep-20261015.json'
  p.write_text(json.dumps([{'id':'12345678','status':403,'challenge':'TURNSTILE'}]))
  self.assertFalse(existing_complete(p,['12345678']))
if __name__=='__main__':unittest.main(verbosity=2)
