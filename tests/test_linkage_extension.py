
import json,unittest,sys,copy
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import radar_bidirectional_handoff as h
L=json.loads(Path(__file__).with_name('linkage_fixture.json').read_text())
NOW="2026-11-24T09:00:00+07:00"
class Extension(unittest.TestCase):
 def test_legacy_unchanged(self):
  full=L['ledger'];a=h.eligible_global_events(full,as_of=NOW);b,s=h.review_global_events(full,as_of=NOW)
  self.assertEqual(a,b);self.assertTrue(all(x["symbol"] is None for x in s))
 def test_selected(self):
  f,s=h.review_global_events({'entries':L['picked']},as_of=NOW,reviews=L['reviews'],max_age_days=60)
  self.assertEqual(len(f),6);self.assertEqual(len(s),4)
  self.assertTrue(any('MYTHOS' in x['source_event_key'] and x['symbol'] is None for x in s))
  self.assertEqual(sum(x['intake_state']=='SOURCE_ONLY_PENDING_VERIFICATION' for x in s),3)
  self.assertEqual(sum(len(x['affected_securities']) for x in f),11)
  self.assertTrue(all(x['signal_state']=='NOT_AUTHORIZED' for x in f+s))
 def test_multiple_no_duplicate_parent(self):
  f,s=h.review_global_events({'entries':L['picked']},as_of=NOW,reviews=L['reviews'],max_age_days=60)
  x=next(x for x in f if x['symbol']=='ZS')
  self.assertEqual({z['symbol'] for z in x['affected_securities']},{'CRWD','ZS'})
  self.assertEqual(len({x['event_id'] for x in f}),len(f))
 def test_version_mismatch(self):
  r=copy.deepcopy(L['reviews'])
  for x in r.values():x['material_update_key']='wrong'
  self.assertEqual(h.review_global_events({'entries':L['picked']},as_of=NOW,reviews=r,max_age_days=60)[0],[])
 def test_future_review_rejected(self):
  r=copy.deepcopy(L['reviews'])
  for x in r.values():x['verified_at']='2026-11-25T00:00:00+07:00'
  self.assertEqual(h.review_global_events({'entries':L['picked']},as_of=NOW,reviews=r,max_age_days=60)[0],[])
 def test_unverified_alternative_url(self):
  f,s=h.review_global_events({'entries':L['picked']},as_of=NOW,max_age_days=60)
  self.assertEqual(f,[]);self.assertEqual(len(s),10);self.assertTrue(all(x['source_verified'] is False for x in s))
 def test_stale_event(self):
  f,s=h.review_global_events({'entries':L['picked']},as_of=NOW,reviews=L['reviews'])
  self.assertFalse(any(x['symbol']=='FTNT' for x in f))
  self.assertFalse(any(x['symbol']=='ANT' and 'MYTHOS' in x['source_event_key'] for x in f))
 def test_bad_exposure_not_route(self):
  r=copy.deepcopy(L['reviews'])
  for x in r.values():
   for t in x['affected_securities']:t['verified']=False
  f,s=h.review_global_events({'entries':L['picked']},as_of=NOW,reviews=r,max_age_days=60)
  self.assertEqual(len(f),0);self.assertEqual(len(s),10)
 def test_projection_nonloss_and_idempotence(self):
  f,s=h.review_global_events({'entries':L['picked']},as_of=NOW,reviews=L['reviews'],max_age_days=60)
  original={'cross_radar_handoff':{'global_to_opportunity':{'old':{'event_id':'old'}},'opportunity_to_global':{'oldp':{'event_id':'oldp'}}}}
  a,st=h.project_checkpoint(original,f,[],observed_at_vn=NOW)
  b,st2=h.project_checkpoint(a,f,[],observed_at_vn=NOW)
  self.assertEqual(st['forward_added'],6);self.assertEqual(st2['forward_added'],0);self.assertEqual(a,b)
  self.assertEqual(a['cross_radar_handoff']['opportunity_to_global'],original['cross_radar_handoff']['opportunity_to_global'])

 def test_runtime_consumer(self):
  import radar_handoff_runtime as runtime
  original={'cross_radar_handoff':{'global_event_linkage_reviews_v1':L['reviews'],'global_to_opportunity':{},'opportunity_to_global':{}}}
  ledger={'entries':L['picked']}
  a,stats,audit,changed=runtime.audit_projection(ledger,original,NOW,'test-fixture-sha')
  self.assertTrue(changed)
  self.assertNotEqual(audit['end_to_end_status'],'FULL_PASS')
  self.assertEqual(audit['source_only_events'],len(audit['source_only_event_statuses']))
  self.assertTrue(all(x['symbol'] is None for x in audit['source_only_event_statuses']))
  self.assertTrue(all(x['signal_state']=='NOT_AUTHORIZED' for x in a['cross_radar_handoff']['global_to_opportunity'].values()))
  b,stats2,audit2,changed2=runtime.audit_projection(ledger,a,NOW,'test-fixture-sha')
  self.assertEqual(stats2['forward_added'],0);self.assertFalse(changed2);self.assertEqual(a,b)

 def test_vn_date_only_not_fabricated(self):
  f,s=h.review_global_events({'entries':L['picked']},as_of=NOW,reviews=L['reviews'],max_age_days=60)
  x=next(x for x in s if x['source_event_key'].startswith('UK_GOVERNMENT|'))
  self.assertEqual(x['source_event_time_precision'],'DATE_ONLY_VN_SOURCE')
  self.assertEqual(x['source_event_time_vn'],'2026-10-24')
  self.assertIsNone(x['symbol'])
