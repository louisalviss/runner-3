#!/usr/bin/env python3
import json,pathlib,tempfile,unittest
import flippa_deep_daily as detail
from flippa_deep_daily import (extract,candidates_for_daily,capture,existing_complete,
   safe_public_url,exact_asset_link,capture_public_site,choose_second_page,visible_flippa_session_state)
class FlippaDetailTests(unittest.TestCase):
 def setUp(self):self.t=tempfile.TemporaryDirectory();self.d=pathlib.Path(self.t.name)
 def tearDown(self):self.t.cleanup()
 def test_detail_is_bound_to_dedicated_flippa_profile(self):
  self.assertEqual(detail.PROFILE,'c97a7500-3b11-403f-ac43-2566cdcd3fa2')
  self.assertNotEqual(detail.PROFILE,'1de482cb-96ac-4b1b-a3f8-2beddc91b2e0')
 def test_exact_link_provenance_not_title_guess(self):
  listing='12345678'
  anchors=[{'text':'View Website','href':'https://example.com/'},
           {'text':'Privacy Policy','href':'https://other.example/privacy'}]
  proof=exact_asset_link(listing,'https://flippa.com/12345678-business-sale',anchors)
  self.assertTrue(proof['asset_domain_verified'])
  self.assertEqual(proof['verified_asset_domain'],'example.com')
  self.assertIn('asset-link-sha256:',proof['asset_domain_source_ref'])
  self.assertFalse(exact_asset_link(listing,'https://flippa.com/98765432',anchors))
  self.assertFalse(exact_asset_link(listing,'https://flippa.com/12345678',
                                   [{'text':'Example.com','href':'https://example.com'}]))
  anchors.append({'text':'Visit Website','href':'https://another.example/'})
  self.assertFalse(exact_asset_link(listing,'https://flippa.com/12345678',anchors))

 def test_public_listing_never_claims_authenticated(self):
  self.assertEqual(visible_flippa_session_state('Browse Log In Sign Up Sell Now'),'PUBLIC_ONLY')
  self.assertEqual(visible_flippa_session_state('Browse Danny My Watchlist'),'AUTHENTICATED')
  self.assertEqual(visible_flippa_session_state('Browse Sell Now'),'UNVERIFIED')
  a=[{'text':'Visit Website','href':'https://example.com/'}]
  public=exact_asset_link('12345678','https://flippa.com/12345678',a)
  self.assertEqual(public['asset_domain_source_kind'],'DIRECT_LISTING_CURRENT')
  account=exact_asset_link('12345678','https://flippa.com/12345678',a,
                           source_kind='AUTHENTICATED_LIVE')
  self.assertEqual(account['asset_domain_source_kind'],'AUTHENTICATED_LIVE')
  self.assertFalse(exact_asset_link('12345678','https://flippa.com/12345678',a,
                                   source_kind='UNVERIFIED'))
 def test_hidden_domain_and_unsafe_site_fail_closed(self):
  self.assertFalse(exact_asset_link('12345678','https://flippa.com/12345678',[]))
  self.assertFalse(safe_public_url('http://example.com/'))
  self.assertFalse(safe_public_url('https://127.0.0.1/'))
  self.assertFalse(safe_public_url('https://localhost.local/'))
  self.assertFalse(safe_public_url('https://flippa.com/12345678'))
  self.assertFalse(safe_public_url('https://example.com:8443/'))
  self.assertTrue(safe_public_url('https://example.com/'))

 def test_public_site_evidence_two_real_pages_but_no_auto_review(self):
  row={'id':'12345678','verified_asset_domain':'example.com',
       'verified_asset_url':'https://example.com/',
       'asset_domain_verified':True}
  visited=[]
  def fetch(url):
   visited.append(url)
   if url=='https://example.com/':
    return {'ok':True,'url':url,'title':'Example Product',
            'text':'A practical online business product for customers worldwide. ' * 3,
            'links':[{'href':'https://example.com/pricing','text':'Pricing'}]}
   return {'ok':True,'url':url,'title':'Pricing',
           'text':'Paid subscription plans for business customers. ' * 3,'links':[]}
  result=capture_public_site(row,'2026-11-05',fetch)
  self.assertEqual(result['status'],'CAPTURED_PUBLIC_PENDING_REVIEW')
  self.assertTrue(result['semantic_review_required'])
  self.assertEqual(len(visited),2)
  self.assertEqual(result['pages'][1]['kind'],'pricing')
  self.assertIn('site-sha256:',result['pages'][0]['source_ref'])
  self.assertFalse(result['financials_independently_verified'])

 def test_redirect_or_missing_page_not_marked_reviewed(self):
  row={'id':'12345678','verified_asset_domain':'example.com',
       'verified_asset_url':'https://example.com/',
       'asset_domain_verified':True}
  def offsite(_):
   return {'ok':True,'url':'https://unrelated.org/','text':'Other site text' * 10}
  self.assertEqual(capture_public_site(row,'2026-11-05',offsite)['status'],'PUBLIC_CAPTURE_BLOCKED')
  def homepage_only(url):
   if url.endswith('/'):
    return {'ok':True,'url':url,'text':'Public homepage with real information. '*3,
      'links':[{'text':'About','href':'https://example.com/about'}]}
   return {'ok':False,'reason':'HTTP_403'}
  self.assertEqual(capture_public_site(row,'2026-11-05',homepage_only)['status'],'PARTIAL_PUBLIC_CAPTURE')
  self.assertEqual(capture_public_site({**row,'asset_domain_verified':False},
                                      '2026-11-05',offsite)['status'],'DOMAIN_UNVERIFIED')

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
