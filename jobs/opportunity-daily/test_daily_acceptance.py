#!/usr/bin/env python3
import datetime,hashlib,json,pathlib,tempfile,unittest
from daily_acceptance import check
from daily_publish import render_current
DAY='2026-10-15'
class AcceptTests(unittest.TestCase):
 def setUp(self):
  self.t=tempfile.TemporaryDirectory()
  self.base=pathlib.Path(self.t.name)
  self.seo=self.base/'seo';self.root=self.base/'radar';self.out=self.base/'daily'
  for p in (self.seo,self.root,self.out):p.mkdir()
  self.put(self.seo/(DAY+'-semrush-queue.json'),{'date':DAY,'scan_terminal':True,'added_total':3,'scanned':3,'pending':0,'count':1,'items':[{'domain':'example.com'}]})
  self.put(self.seo/(DAY+'-semrush-results.json'),{'date':DAY,'status':'PASS','queue_count':1,'pass_count':1,'fail_count':0,'not_run_count':0})
  self.put(self.seo/(DAY+'-terminal-verdicts.json'),{'date':DAY,'status':'PASS','semrush_status':'PASS','verdicts':[{'domain':'example.com','verdict':'DROP'}]})
  self.put(self.out/(DAY+'-manifest.json'),{'date':DAY,'approved_buy':0,'approved_build':0})
  f={'first_done':True,'recent_done':True,'recent_ids':[str(x) for x in range(500)],'pages':[{'status':200,'challenge':'NONE'}]}
  self.put(self.root/'flippa-20261015-daily-state.json',f)
  self.payload={'schema':'opportunity-daily-v2','date_vn':DAY,'overall':'RESEARCH_PENDING','generated_at':'2026-10-15T09:15:00+07:00','seo':{'source_complete':True,'provider_status':'PASS','terminal_status':'PASS'},'flippa':{'status':'PASS','new':[]},'flippa_detail':{'status':'PASS_EMPTY'},'flippa_semrush':{'status':'PASS_EMPTY'},'qualification':{'approved_buy':0,'approved_build':0,'candidates':[{'title':'Example','source':'SEOTRENDS','category':'DROP','buy':{'state':'NOT_LISTED'},'build':{'state':'DROP'}}]}}
  self.report='# daily\n\n## qualification\nReady'
  (self.out/(DAY+'-report.md')).write_text(self.report*20)
  self.sync()
 def tearDown(self):self.t.cleanup()
 def put(self,p,val):p.write_text(json.dumps(val))
 def sync(self):
  self.put(self.out/(DAY+'-research-queue.json'),self.payload)
  current=render_current(self.payload,self.report)
  (self.out/(DAY+'-current.md')).write_text(current)
  self.put(self.out/(DAY+'-dropbox-publish.json'),{'day':DAY,'status':'PASS','sha256':hashlib.sha256(current.encode()).hexdigest(),'reason':'DROPBOX_SYNC_PASS'})
 def run_check(self):return check(DAY,seo=self.seo,root=self.root,out=self.out)
 def test_golden_pass(self):
  q=self.run_check()
  self.assertEqual(q['status'],'PASS')
  self.assertEqual(q['passed_checks'],q['total_checks'])
  self.assertFalse(q['scheduler_proven_unattended'])
 def test_semrush_block_fails(self):
  self.put(self.seo/(DAY+'-semrush-results.json'),{'date':DAY,'status':'BLOCKED'})
  self.assertFalse(self.run_check()['checks']['semrush_all_pass'])
 def test_semrush_partial_fails(self):
  self.put(self.seo/(DAY+'-semrush-results.json'),{'date':DAY,'status':'PASS','queue_count':1,'pass_count':0,'fail_count':1,'not_run_count':0})
  self.assertEqual(self.run_check()['status'],'PARTIAL_BLOCKED')
 def test_terminal_empty_fails(self):
  self.put(self.seo/(DAY+'-terminal-verdicts.json'),{'date':DAY,'status':'PASS','semrush_status':'PASS','verdicts':[]})
  self.assertFalse(self.run_check()['checks']['exact_serp_complete'])
 def test_missing_flippa_source_fails(self):
  (self.root/'flippa-20261015-daily-state.json').unlink()
  self.assertFalse(self.run_check()['checks']['flippa_daily_source'])
 def test_flippa_challenge_fails(self):
  f=json.loads((self.root/'flippa-20261015-daily-state.json').read_text());f['pages'][0]['challenge']='TURNSTILE'
  self.put(self.root/'flippa-20261015-daily-state.json',f)
  self.assertFalse(self.run_check()['checks']['flippa_daily_source'])
 def test_flippa_deep_missing_fails(self):
  self.payload.pop('flippa_detail');self.sync()
  self.assertFalse(self.run_check()['checks']['flippa_detail_stage'])
 def test_flippa_crosscheck_block_fails(self):
  self.payload['flippa_semrush']['status']='BLOCKED';self.sync()
  self.assertFalse(self.run_check()['checks']['flippa_semrush_stage'])
 def test_buy_approval_blocks(self):
  self.payload['qualification']['approved_buy']=1;self.sync()
  self.assertFalse(self.run_check()['checks']['buy_build_guard'])
 def test_missing_dropbox_marker_fails(self):
  (self.out/(DAY+'-dropbox-publish.json')).unlink()
  self.assertFalse(self.run_check()['checks']['dropbox_verified'])
 def test_modified_local_current_fails(self):
  p=self.out/(DAY+'-current.md');p.write_text(p.read_text()+'tamper')
  self.assertFalse(self.run_check()['checks']['dropbox_verified'])
 def test_false_day_fails(self):
  self.payload['date_vn']='2026-10-14';self.sync()
  self.assertFalse(self.run_check()['checks']['same_date'])
 def test_report_empty_fails(self):
  (self.out/(DAY+'-report.md')).write_text('x')
  self.assertFalse(self.run_check()['checks']['report_complete'])
if __name__=='__main__':unittest.main(verbosity=2)
