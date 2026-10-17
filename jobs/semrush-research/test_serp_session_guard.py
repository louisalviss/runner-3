#!/usr/bin/env python3
"""Strictly offline regression checks for Semrush SERP session renewal."""
import json
import pathlib
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = pathlib.Path(__file__).parent
sys.path.insert(0, str(ROOT))
import serp_dd_live as serp
import runtime_recovery as recovery

class SerpSessionGuardTests(unittest.TestCase):
    def setUp(self):
        for func in ('rpc_many', 'refresh_expired_proxy_session', 'broker_call'):
            stub=patch.object(serp,func,side_effect=AssertionError('unexpected live action: '+func))
            stub.start();self.addCleanup(stub.stop)

    def test_expired_proxy_refresh_once_and_retry(self):
        calls=[{'tag':'a\tkeyword'}]
        expired=[{'tag':'a\tkeyword','error':{'message':'NON_JSON','sample':'Session expired, access again from Dashboard'}}]
        good=[{'tag':'a\tkeyword','result':[{'url':'https://example.com'}],'error':None,'status':200}]
        with patch.object(serp,'rpc_many',side_effect=[expired,good]) as rpc,\
             patch.object(serp,'refresh_expired_proxy_session',return_value={'ok':True,'state':'SHARD_REFRESHED'}) as refresher:
            vals,used,receipt=serp.rpc_many_with_one_shard_refresh(calls)
        self.assertEqual(vals,good);self.assertTrue(used)
        self.assertEqual(receipt['state'],'SHARD_REFRESHED')
        self.assertEqual(rpc.call_count,2);refresher.assert_called_once()

    def test_second_expiry_never_refreshes_again(self):
        expired=[{'error':{'message':'Session expired, access again from Dashboard'}}]
        with patch.object(serp,'rpc_many',return_value=expired),\
             patch.object(serp,'refresh_expired_proxy_session',side_effect=AssertionError('must not renew')):
            with self.assertRaises(serp.SerpAuthBlocked):
                serp.rpc_many_with_one_shard_refresh([{'tag':'a\tkw'}],refresh_used=True)

    def test_challenge_after_renewal_blocks_without_further_retry(self):
        expired=[{'error':{'message':'Session expired, access again from Dashboard'}}]
        with patch.object(serp,'rpc_many',return_value=expired) as rpc,\
             patch.object(serp,'refresh_expired_proxy_session',return_value={'ok':False,'state':'NOX_DASHBOARD_CHALLENGE'}) as refresher:
            with self.assertRaises(serp.SerpAuthBlocked):
                serp.rpc_many_with_one_shard_refresh([{'tag':'a\tkw'}])
        self.assertEqual(rpc.call_count,1);refresher.assert_called_once()

    def test_no_refresh_for_quota(self):
        quota=[{'tag':'a\tkw','error':{'code':-2004,'message':'Report limit reached'}}]
        with patch.object(serp,'rpc_many',return_value=quota),\
             patch.object(serp,'refresh_expired_proxy_session',side_effect=AssertionError('must not renew')):
            vals,used,receipt=serp.rpc_many_with_one_shard_refresh([{'tag':'a\tkw'}])
        self.assertEqual(vals,quota);self.assertFalse(used);self.assertIsNone(receipt)

    def _run_scoped_main(self, fake_results=None, auth_error=None):
        with tempfile.TemporaryDirectory() as td:
            root=pathlib.Path(td)
            queue=root/'queue.json'
            queue.write_text(json.dumps({'queue':[{'cluster_id':'a','top_keywords':[{'keyword':'keyword'}]}]}))
            out=root/'serps'
            with patch.object(sys,'argv',['serp_dd_live.py','--queue',str(queue),'--output-dir',str(out)]),\
                 patch.object(serp,'cooldown_remaining',return_value=0),\
                 patch.object(serp,'require_semrush_preflight',return_value={'shallow':{'payload':{'checks':{'broker':{'ok':True}}}}}),\
                 patch.object(serp,'ensure_with_one_shot_recovery',return_value=({'ok':True,'server':'test'},{})),\
                 patch.object(serp,'rpc_many_with_one_shard_refresh',
                    side_effect=serp.SerpAuthBlocked(auth_error) if auth_error else None,
                    return_value=(fake_results,False,None)):
                rc=serp.main()
            state=json.loads((out/'state.json').read_text())
            cache=out/'raw-serps.jsonl'
            return rc,state,cache.read_text() if cache.exists() else ''

    def test_rpc_error_never_sealed_as_completed(self):
        rc,state,cache=self._run_scoped_main([{'tag':'a\tkeyword','error':{'message':'Not verified'}}])
        self.assertEqual(rc,8);self.assertEqual(state['stage'],'BLOCKED_PROVIDER_RPC')
        self.assertEqual(cache,'')

    def test_missing_tag_never_sealed_as_completed(self):
        rc,state,cache=self._run_scoped_main([])
        self.assertEqual(rc,8);self.assertEqual(state['stage'],'BLOCKED_PROVIDER_RPC')
        self.assertEqual(cache,'')

    def test_expired_session_never_sealed_as_completed(self):
        rc,state,cache=self._run_scoped_main(auth_error='PROXY_REFRESH_FAILED:NOX_DASHBOARD_CHALLENGE')
        self.assertEqual(rc,3);self.assertEqual(state['stage'],'BLOCKED_LIVE_AUTH')
        self.assertEqual(cache,'')

    def test_nox_login_required_is_recoverable_before_serp(self):
        calls=[]
        def broker(req,timeout):
            calls.append(req['action'])
            return {'ok':False,'state':'NOX_LOGIN_REQUIRED'} if len(calls)==1 else {'ok':True,'server':'test'}
        with patch.object(recovery,'_run_recovery',return_value={'ok':True,'state':'RECOVERED'}):
            response,evidence=recovery.ensure_with_one_shot_recovery(broker,timeout=10)
        self.assertEqual(calls,['ensure','ensure'])
        self.assertTrue(response['ok']);self.assertTrue(evidence['attempted'])

    def test_cloudflare_challenge_does_not_attempt_login(self):
        with patch.object(recovery,'_run_recovery',side_effect=AssertionError('must not relogin')):
            response,evidence=recovery.ensure_with_one_shot_recovery(
                lambda req,timeout:{'ok':False,'state':'NOX_DASHBOARD_CHALLENGE'})
        self.assertEqual(response['state'],'NOX_DASHBOARD_CHALLENGE')
        self.assertFalse(evidence['attempted'])

    def test_expired_refresh_requests_dashboard_flag(self):
        with patch.object(recovery,'_run_recovery',return_value={'ok':True,'state':'SHARD_REFRESHED'}) as fn:
            v=recovery.refresh_expired_proxy_session(timeout=20)
        self.assertTrue(v['ok'])
        fn.assert_called_once_with(timeout=20,refresh_shard=True)

if __name__ == '__main__':
    unittest.main()
