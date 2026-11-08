#!/usr/bin/env python3
"""Offline post-recovery proof: no browser, provider, duplicate scheduler or old-day replays."""
import datetime
import hashlib
import json
import os
import pathlib
import tempfile
import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from zoneinfo import ZoneInfo

import auth_resume as a


class PostRecoveryReconciliation(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=pathlib.Path(self.temp.name)
        self.today=datetime.datetime.now(ZoneInfo("Asia/Ho_Chi_Minh"))
        self.day=(self.today.date()-datetime.timedelta(days=1)).isoformat()
        names=["SEO","POST_ROOT","POST_OUT","MARKER","LOCK","POST_CHECKPOINT",
               "POST_ACCEPTANCE","POST_AUDIT"]
        self.saved={name:getattr(a,name) for name in names}
        self.addCleanup(lambda: [setattr(a,k,v) for k,v in self.saved.items()])
        a.SEO=self.root/"seo"
        a.POST_ROOT=self.root/"root"
        a.POST_OUT=self.root/"out"
        a.MARKER=self.root/"attempt.json"
        a.LOCK=self.root/"guard.lock"
        a.POST_CHECKPOINT=a.POST_ROOT/"opportunity_daily.py"
        a.POST_ACCEPTANCE=a.POST_ROOT/"daily_acceptance.py"
        a.POST_AUDIT=a.POST_ROOT/"audit_gap_ledger.py"
        for folder in (a.SEO,a.POST_ROOT,a.POST_OUT):folder.mkdir()
        self.q=a.SEO/(self.day+"-semrush-queue.json")
        self.sem=a.SEO/(self.day+"-semrush-results.json")
        self.term=a.SEO/(self.day+"-terminal-verdicts.json")
        self.manifest=a.POST_OUT/(self.day+"-manifest.json")
        self.receipt=a.POST_OUT/(self.day+"-acceptance.json")
        self.publisher=a.POST_OUT/(self.day+"-dropbox-publish.json")
        self.report=a.POST_OUT/(self.day+"-research-queue.json")
        self.ledger=a.POST_OUT/("gap-ledger-"+self.day+".json")
        stamp=self.day.replace("-","")
        self.flippa=a.POST_ROOT/("flippa-"+stamp+"-daily-state.json")
        self.detail=a.POST_ROOT/("flippa-deep-"+stamp+"-state.json")
        self.observed=a.POST_ROOT/("flippa-deep-"+stamp+".json")
        self.put(self.q,{"date":self.day,"scan_terminal":True,"count":1,
                         "added_total":2,"scanned":2,"pending":0,
                         "items":[{"domain":"example.com"}]})
        self.put(self.sem,{"date":self.day,"status":"PASS","queue_count":1,
                           "pass_count":1,"fail_count":0,"not_run_count":0,
                           "items":[{"domain":"example.com","status":"PASS"}]})
        self.put(self.term,{"date":self.day,"status":"PASS","semrush_status":"PASS",
                            "verdicts":[{"domain":"example.com","verdict":"WATCH"}]})
        self.put(self.flippa,{"profile_id":a.POST_PROFILE_ID,"first_done":True,
                              "recent_done":True,"recent_ids":list(map(str,range(500))),
                              "pages":[{"status":200,"challenge":"NONE"}]})
        self.put(self.detail,{"date":self.day,"status":"PASS",
                              "profile_id":a.POST_PROFILE_ID,"items":1})
        self.put(self.observed,[{"id":"111","profile_id":a.POST_PROFILE_ID,
                                 "status":200,"challenge":"NONE"}])
        self.put(self.report,{"date_vn":self.day,"overall":"RESEARCH_PENDING"})
        self.put(self.manifest,{"date":self.day,"status":"RESEARCH_PENDING"})
        self.put(self.receipt,self.accepted())
        self.put(self.publisher,{"day":self.day,"status":"PASS"})
        self.write_ledger()
        base=time.time()
        for x in (self.q,self.sem,self.term):os.utime(x,(base-80,base-80))
        os.utime(self.manifest,(base-50,base-50))
        os.utime(self.receipt,(base-20,base-20))

    def put(self,path,obj):
        path.write_text(json.dumps(obj,ensure_ascii=False)+"\n",encoding="utf8")

    def accepted(self):
        return {"date":self.day,"status":"PASS",
                "checks":{"check"+str(i):True for i in range(11)}}

    def write_ledger(self):
        hashes={"queue":a._sha(self.q),"semrush":a._sha(self.sem),
                "serp":a._sha(self.term),"daily":a._sha(self.report)}
        self.put(self.ledger,{"daily":[{"day":self.day,"acceptance":"PASS",
                                      "evidence_sha256":hashes}],"pending_semrush":[]})

    def test_synced_source_never_republishes(self):
        self.assertEqual(a.post_recovery_plan(self.day,self.today)["state"],
                         "ALREADY_RECONCILED")
        with patch.object(a.subprocess,"run",side_effect=AssertionError("unexpected side effect")):
            result=a.post_recovery(self.day,now=self.today)
        self.assertEqual(result["state"],"ALREADY_RECONCILED")

    def test_stale_gap_ledger_is_audit_only(self):
        self.put(self.ledger,{"daily":[],"pending_semrush":[{"day":self.day,"domain":"example.com"}]})
        self.assertEqual(a.post_recovery_plan(self.day,self.today)["state"],"AUDIT_REQUIRED")
        calls=[]
        def run(args,**kwargs):
            calls.append(args)
            self.write_ledger()
            return SimpleNamespace(returncode=0,stdout="ok")
        with patch.object(a.subprocess,"run",side_effect=run):
            result=a.post_recovery(self.day,now=self.today)
        self.assertEqual(result["state"],"RECONCILED_PASS")
        self.assertEqual(len(calls),1)
        self.assertEqual(calls[0][1],str(a.POST_AUDIT))
        self.assertFalse(a.MARKER.exists())
        self.assertEqual(a.post_recovery_plan(self.day,self.today)["state"],
                         "ALREADY_RECONCILED")

    def test_late_source_change_requires_checkpoint(self):
        os.utime(self.term,(time.time()+10,time.time()+10))
        self.assertEqual(a.post_recovery_plan(self.day,self.today)["state"],
                         "CHECKPOINT_REQUIRED")

    def test_old_profile_cannot_be_republished(self):
        self.put(self.receipt,{"date":self.day,"status":"PARTIAL_BLOCKED"})
        obj=json.loads(self.flippa.read_text())
        obj.pop("profile_id")
        self.put(self.flippa,obj)
        self.assertEqual(a.post_recovery_plan(self.day,self.today)["state"],
                         "FLIPPA_PROVENANCE_BLOCKED")

    def test_newer_published_day_blocks_backward_current(self):
        self.put(self.receipt,{"date":self.day,"status":"PARTIAL_BLOCKED"})
        other=self.today.date().isoformat()
        self.put(a.POST_OUT/(other+"-dropbox-publish.json"),
                 {"day":other,"status":"PASS"})
        x=a.post_recovery_plan(self.day,self.today)
        self.assertEqual(x["state"],"NEWER_DAILY_REPORT_ALREADY_PUBLISHED")

    def test_provider_not_pass_no_attempt_or_audit(self):
        self.put(self.sem,{"date":self.day,"status":"BLOCKED","pass_count":0})
        self.assertEqual(a.post_recovery_plan(self.day,self.today)["state"],
                         "SOURCE_NOT_INDEPENDENTLY_PASS")
        with patch.object(a.subprocess,"run",side_effect=AssertionError("provider access")):
            self.assertEqual(a.post_recovery(self.day,now=self.today)["state"],
                             "SOURCE_NOT_INDEPENDENTLY_PASS")

    def test_status_pass_without_matching_domain_identity_is_blocked(self):
        sem=json.loads(self.sem.read_text())
        sem["items"]=[{"domain":"other-domain.example","status":"PASS"}]
        self.put(self.sem,sem)
        self.assertEqual(a.post_recovery_plan(self.day,self.today)["state"],
                         "SOURCE_NOT_INDEPENDENTLY_PASS")

    def test_terminal_pass_with_blocked_verdict_is_not_proof(self):
        t=json.loads(self.term.read_text())
        t["verdicts"][0]["verdict"]="BLOCKED"
        self.put(self.term,t)
        self.assertEqual(a.post_recovery_plan(self.day,self.today)["state"],
                         "SOURCE_NOT_INDEPENDENTLY_PASS")

    def test_dry_run_does_not_modify_files_or_auth_state(self):
        self.put(self.receipt,{"date":self.day,"status":"PARTIAL_BLOCKED"})
        result=a.post_recovery(self.day,now=self.today,dry_run=True)
        self.assertEqual(result["state"],"DRY_RUN")
        self.assertEqual(result["would"],"CHECKPOINT_REQUIRED")
        self.assertFalse(a.MARKER.exists())

    def test_checkpoint_then_acceptance_then_audit_once(self):
        self.put(self.receipt,{"date":self.day,"status":"PARTIAL_BLOCKED"})
        self.put(self.ledger,{"daily":[],"pending_semrush":[{"day":self.day,"domain":"example.com"}]})
        calls=[]
        def run(cmd,**kwargs):
            calls.append(pathlib.Path(cmd[1]).name)
            if cmd[1]==str(a.POST_CHECKPOINT):
                self.put(self.manifest,{"date":self.day,"status":"RESEARCH_PENDING"})
            elif cmd[1]==str(a.POST_ACCEPTANCE):
                self.put(self.receipt,self.accepted())
            elif cmd[1]==str(a.POST_AUDIT):
                self.write_ledger()
            else:raise AssertionError("unexpected command")
            return SimpleNamespace(returncode=0,stdout="ok")
        with patch.object(a.subprocess,"run",side_effect=run):
            x=a.post_recovery(self.day,now=self.today)
        self.assertEqual(x["state"],"RECONCILED_PASS")
        self.assertTrue(x["verified"])
        self.assertEqual(calls,["opportunity_daily.py","daily_acceptance.py",
                                "audit_gap_ledger.py"])
        self.assertEqual(a.post_recovery_plan(self.day,self.today)["state"],
                         "ALREADY_RECONCILED")
        self.assertEqual(a.load(a.MARKER)["post_recovery"]["state"],
                         "RECONCILED_PASS")

    def test_failed_checkpoint_is_bounded_by_source_fingerprint(self):
        self.put(self.receipt,{"date":self.day,"status":"PARTIAL_BLOCKED"})
        calls=[]
        with patch.object(a.subprocess,"run",side_effect=lambda cmd,**kw:
                          (calls.append(cmd),SimpleNamespace(returncode=4,stdout=""))[1]):
            first=a.post_recovery(self.day,now=self.today)
            second=a.post_recovery(self.day,now=self.today)
        self.assertEqual(first["state"],"CHECKPOINT_FAILED")
        self.assertEqual(second["state"],"ALREADY_ATTEMPTED_THIS_EVIDENCE")
        self.assertEqual(len(calls),1)

    def test_cannot_repair_current_day_before_daily_window(self):
        now=self.today.replace(hour=9,minute=59)
        self.assertEqual(a.post_recovery_plan(now.date().isoformat(),now)["state"],
                         "WAIT_DAILY_ACCEPTANCE_WINDOW")

if __name__=="__main__":
    unittest.main(verbosity=2)
