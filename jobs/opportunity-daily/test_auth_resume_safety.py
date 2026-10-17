#!/usr/bin/env python3
"""Offline checks for bounded, handoff-gated Semrush recovery classification."""
import datetime
import importlib.util
import json
import pathlib
import tempfile
import unittest
from unittest.mock import patch
from zoneinfo import ZoneInfo

P = pathlib.Path(__file__).with_name('auth_resume.py')
spec=importlib.util.spec_from_file_location('handoff_auth_resume_offline',P)
app=importlib.util.module_from_spec(spec)
spec.loader.exec_module(app)

class ResumeTriggerTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=pathlib.Path(self.temp.name)
        self.day=datetime.datetime.now(ZoneInfo('Asia/Ho_Chi_Minh')).date().isoformat()
        for name,value in [('SEO',self.root),('LOG',self.root/'never-existing-handoff-log.jsonl'),
                           ('MARKER',self.root/'never-existing-marker.json')]:
            p=patch.object(app,name,value);p.start();self.addCleanup(p.stop)
        self.write('semrush-queue',{'date':self.day,'scan_terminal':True,'count':1,
                                   'added_total':1,'scanned':1,'items':[{'domain':'example.com'}]})
    def write(self,suffix,data):
        (self.root/(self.day+'-'+suffix+'.json')).write_text(json.dumps(data))
    def test_serp_expired_shard_requires_verified_new_handoff(self):
        self.write('semrush-results',{'status':'PASS'})
        self.write('terminal-verdicts',{'status':'DEGRADED','serp_run':{
            'state':{'stage':'BLOCKED_LIVE_AUTH','blocker':'SEMRUSH_PROXY_SESSION_EXPIRED'}}})
        self.assertEqual(app.decision(self.day)['state'],'NO_NEW_HUMAN_HANDOFF')
    def test_export_refresh_failure_recognized(self):
        self.write('semrush-results',{'status':'BLOCKED',
            'global_blocker':'SEMRUSH_AUTO_RECOVERY_FAILED:NOX_DASHBOARD_CHALLENGE'})
        self.write('terminal-verdicts',{'status':'BLOCKED'})
        self.assertEqual(app.decision(self.day)['state'],'NO_NEW_HUMAN_HANDOFF')
    def test_export_repeat_expiry_recognized(self):
        self.write('semrush-results',{'status':'BLOCKED',
            'global_blocker':'SEMRUSH_AUTO_RECOVERY_RETRY_FAILED:Session expired, access again from Dashboard'})
        self.write('terminal-verdicts',{'status':'BLOCKED'})
        self.assertEqual(app.decision(self.day)['state'],'NO_NEW_HUMAN_HANDOFF')
    def test_provider_quota_not_auth_handoff(self):
        self.write('semrush-results',{'status':'BLOCKED','global_blocker':'SEMRUSH_RATE_LIMIT'})
        self.write('terminal-verdicts',{'status':'BLOCKED'})
        self.assertEqual(app.decision(self.day)['state'],'NOT_HUMAN_AUTH_BLOCKER')
    def test_completed_batch_skips_recovery(self):
        self.write('semrush-results',{'status':'PASS'})
        self.write('terminal-verdicts',{'status':'PASS'})
        self.assertEqual(app.decision(self.day)['state'],'ALREADY_PASS')

if __name__=='__main__':
    unittest.main()
