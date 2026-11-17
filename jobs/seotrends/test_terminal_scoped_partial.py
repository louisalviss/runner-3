#!/usr/bin/env python3
"""A scoped SERP audit can use proven source exports, never promote a PARTIAL day."""
import contextlib
import io
import json
import pathlib
import sys
import tempfile
import unittest
from unittest.mock import patch
import terminal_funnel as m


class ScopedPartialSourceTest(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.root=pathlib.Path(self.temp.name)
        self.day='2026-11-16'
        self.proven=['a.example','b.example']
        self.failed='c.example'
        q={'date':self.day,'scan_terminal':True,'scanned':277,'added_total':277,
           'count':3,'items':[{'domain':x} for x in self.proven+[self.failed]]}
        r={'date':self.day,'status':'PARTIAL','queue_count':3,'pass_count':2,'fail_count':1,
           'items':[{'domain':x,'status':'PASS','metrics':{'organic_keywords':0,'estimated_traffic_sum':0}}
                    for x in self.proven]+[{'domain':self.failed,'status':'FAIL','reason':'SEMRUSH_REPORT_LIMIT'}]}
        (self.root/f'{self.day}-semrush-queue.json').write_text(json.dumps(q))
        (self.root/f'{self.day}-semrush-results.json').write_text(json.dumps(r))
        out=self.root/f'{self.day}-semrush';out.mkdir()
        for domain in self.proven:
            (out/f'{domain}.json').write_text(json.dumps({'domain':domain,'rows':[],'rows_fetched':0}))
    def tearDown(self):
        self.temp.cleanup()
    def call(self,domains='',suffix=''):
        args=['terminal','--date',self.day,'--serp-timeout','1']
        if domains:args+=['--domains',domains]
        if suffix:args+=['--suffix',suffix]
        out=io.StringIO()
        with patch.object(m,'SCANS',self.root),patch.object(sys,'argv',args), \\
             patch.object(m,'build_serp_queue',return_value={'status':'PENDING','date':self.day,'queue':[]}), \\
             contextlib.redirect_stdout(out):
            rc=m.main()
        path=self.root/(f'{self.day}-terminal-verdicts'+('-'+suffix if suffix else '')+'.json')
        return rc,json.loads(path.read_text()),out.getvalue()
    def test_proven_subset_pass_scoped_not_day(self):
        rc,payload,_=self.call('a.example,b.example','reviewed-pass')
        self.assertEqual(rc,0)
        self.assertEqual(payload['status'],'PASS_SCOPED')
        self.assertEqual(payload['semrush_status'],'PASS_SCOPED_SOURCE')
        self.assertEqual(payload['source_overall_status'],'PARTIAL')
        self.assertEqual(len(payload['verdicts']),2)
        self.assertFalse((self.root/f'{self.day}-terminal-verdicts.json').exists())
    def test_full_day_remains_blocked(self):
        rc,payload,_=self.call()
        self.assertEqual(rc,3)
        self.assertEqual(payload['status'],'BLOCKED')
        self.assertEqual(payload['reason'],'SEMRUSH_PARTIAL')
    def test_cannot_include_failed_domain(self):
        rc,payload,_=self.call('a.example,c.example','failed-source')
        self.assertEqual(rc,3)
        self.assertEqual(payload['status'],'BLOCKED')
        self.assertEqual(payload['reason'],'SCOPED_EXPORT_PROVENANCE_UNVERIFIED')
    def test_cannot_include_unknown_domain(self):
        rc,payload,_=self.call('a.example,unknown.example','unknown')
        self.assertEqual(rc,3)
        self.assertEqual(payload['status'],'BLOCKED')
    def test_missing_export_blocks_subset(self):
        (self.root/f'{self.day}-semrush'/'b.example.json').unlink()
        rc,payload,_=self.call('a.example,b.example','missing')
        self.assertEqual(rc,3)
        self.assertEqual(payload['reason'],'SCOPED_EXPORT_PROVENANCE_UNVERIFIED')
    def test_duplicate_identity_blocks_subset(self):
        qpath=self.root/f'{self.day}-semrush-queue.json'
        q=json.loads(qpath.read_text());q['items'][1]['domain']='a.example'
        qpath.write_text(json.dumps(q))
        rc,payload,_=self.call('a.example','duplicate')
        self.assertEqual(rc,3)
        self.assertEqual(payload['status'],'BLOCKED')
    def test_no_scoped_overwrite_without_suffix(self):
        out=io.StringIO()
        with patch.object(m,'SCANS',self.root),patch.object(sys,'argv',['terminal','--date',self.day,'--domains','a.example']), \\
             contextlib.redirect_stdout(out),self.assertRaises(SystemExit) as ctx:
            m.main()
        self.assertEqual(ctx.exception.code,2)
        self.assertFalse((self.root/f'{self.day}-terminal-verdicts.json').exists())


if __name__=='__main__':
    unittest.main()
