#!/usr/bin/env python3
"""Offline gate/regression tests for the daily merger: no browser or API calls."""
import importlib.util, json, pathlib, tempfile, unittest
SCRIPT=str(pathlib.Path(__file__).resolve().parent/"opportunity_daily.py")
spec=importlib.util.spec_from_file_location("opportunity_daily",SCRIPT)
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
def save(path,data):path.write_text(json.dumps(data));return path
class DailyGates(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.d=pathlib.Path(self.tmp.name)
  self.oldids=[str(x) for x in range(10000000,10000500)]
  self.newids=self.oldids[1:]+["14451431"]
  self.cards={"14451431":{"id":"14451431","heading":"Small app","pt":"SaaS","p":9000,"pr":650,"vet":1,"title":"organic utility","raw_text":"organic calculator","href":"https://flippa.com/14451431"}}
  self.old={"first_done":True,"recent_done":True,"first_ids":["1"],"recent_ids":self.oldids,"pages":[{"status":200,"challenge":"NONE"}]*7}
  self.cur={"first_done":True,"recent_done":True,"first_ids":["1","2"],"recent_ids":self.newids,"recent_rows":self.cards,"pages":[{"status":200,"challenge":"NONE"}]*7}
  self.oldfile=save(self.d/"old.json",self.old)
  self.curfile=save(self.d/"current.json",self.cur)
 def tearDown(self):self.tmp.cleanup()
 def test_delta_and_no_sold_claim(self):
  r=m.read_flippa(self.curfile,self.oldfile)
  self.assertEqual(r["status"],"PASS")
  self.assertEqual(r["stats"]["entered_recent_window"],1)
  self.assertEqual(r["stats"]["exited_recent_window"],1)
  self.assertEqual(r["new"][0]["verdict"],"WATCH_RESEARCH")
 def test_no_prior_not_all_new(self):
  r=m.read_flippa(self.curfile)
  self.assertEqual(r["stats"]["entered_recent_window"],0)
  self.assertEqual(r["new"],[])
 def test_challenge_fails_closed(self):
  self.cur["pages"][-1]["challenge"]="TURNSTILE";save(self.curfile,self.cur)
  self.assertEqual(m.read_flippa(self.curfile,self.oldfile)["status"],"BLOCKED_SOURCE")
 def test_out_of_budget_reserve(self):
  deep=save(self.d/"deep.json",[{"id":"14451431","status":200,"challenge":"NONE","reserve":"15,000","subs":"80","churn":"0%"}])
  x=m.read_flippa(self.curfile,self.oldfile,deep)["new"][0]
  self.assertEqual(x["verdict"],"DROP_BUY_CAP")
 def test_small_n_not_buy(self):
  deep=save(self.d/"deep.json",[{"id":"14451431","status":200,"challenge":"NONE","reserve":"6,500","subs":"4","churn":"0%"}])
  x=m.read_flippa(self.curfile,self.oldfile,deep)["new"][0]
  self.assertEqual(x["verdict"],"WATCH_SMALL_N")
 def test_churn_not_buy(self):
  deep=save(self.d/"deep.json",[{"id":"14451431","status":200,"challenge":"NONE","reserve":"6,500","subs":"120","churn":"35%"}])
  x=m.read_flippa(self.curfile,self.oldfile,deep)["new"][0]
  self.assertEqual(x["verdict"],"WATCH_CHURN")
 def test_social_channel_not_buy(self):
  self.cards["14451431"]["pt"]="YouTube Channel";save(self.curfile,self.cur)
  self.assertEqual(m.read_flippa(self.curfile,self.oldfile)["new"],[])
 def test_semrush_error_no_zero_demand(self):
  self.assertTrue(m.auth_blocked({"reason":"BROKER_DPA:SEMRUSH_LIVE_AUTH_UNAVAILABLE"}))
  self.assertFalse(m.auth_blocked({"reason":"DPA:-32098 Limits exceeded"}))
 def test_normalizer(self):
  self.assertEqual(m.normalize_domain("https://www.Example.com/a"),"example.com")
 def test_report_has_safety(self):
  d={"date_vn":"2026-10-13","overall":"PARTIAL_BLOCKED","seo":{"scanned":206,"added":206,"items":[],"provider_status":"FAIL","terminal_status":"BLOCKED"},"flippa":{"stats":{"first_access":130,"recent":500,"entered_recent_window":23}},"research_queue":[]}
  self.assertIn("automated purchases/bids: 0",m.format_report(d))
 def test_seo_build_reference_no_profit(self):
  self.cards["14451431"]["pr"]=None
  self.cards["14451431"]["heading"]="HVACPlanner.com"
  self.cards["14451431"]["raw_text"]="42 interactive calculators, SEO organic"
  save(self.curfile,self.cur)
  v=m.read_flippa(self.curfile,self.oldfile)["new"][0]
  self.assertEqual(v["verdict"],"BUILD_REFERENCE")
  self.assertFalse(v["verified_detail"])
 def test_terminal_drop_not_watch(self):
  old=m.SEO
  try:
   m.SEO=self.d
   save(self.d/"2026-10-14-semrush-queue.json",{"items":[{"domain":"example.com","title":"Example","discovery_score":9}],"added_total":1,"scanned":1,"scan_terminal":True})
   save(self.d/"2026-10-14-semrush-results.json",{"status":"PASS","items":[{"domain":"example.com","status":"PASS"}]})
   save(self.d/"2026-10-14-terminal-verdicts.json",{"status":"PASS","verdicts":[{"domain":"example.com","verdict":"DROP","reason":"SATURATED"}]})
   v=m.read_seo("2026-10-14")["items"][0]
   self.assertEqual(v["verdict"],"DROP")
   self.assertEqual(v["reason"],"SATURATED")
  finally:m.SEO=old
 def test_low_traffic_unmonetized_drop(self):
  self.cards["14451431"]["pr"]=None
  self.cards["14451431"]["raw_text"]="organic traffic SEO calculators"
  save(self.curfile,self.cur)
  deep=save(self.d/"deep.json",[{"id":"14451431","status":200,"challenge":"NONE","pageviews":"114","bin":"599"}])
  v=m.read_flippa(self.curfile,self.oldfile,deep)["new"][0]
  self.assertEqual(v["verdict"],"DROP_TRAFFIC_WEAK")
  self.assertEqual(v["bin_verified"],599)
  self.assertEqual(v["pageviews_verified"],114)
 def test_auto_deep_reused_on_daily_timer(self):
  old=m.ROOT
  try:
   m.ROOT=self.d
   self.assertIsNone(m.resolve_deep("2026-10-14"))
   deep=save(self.d/"flippa-deep-20261014.json",[])
   self.assertEqual(m.resolve_deep("2026-10-14"),str(deep))
   self.assertEqual(m.resolve_deep("2026-10-14","manual.json"),"manual.json")
  finally:m.ROOT=old
if __name__=="__main__":unittest.main(verbosity=2)
