#!/usr/bin/env python3
"""Offline Flippa profile provenance and transport checks: no browser/provider calls."""
import io,json,unittest
from unittest.mock import patch

import opportunity_daily as app

CORRECT='1de482cb-96ac-4b1b-a3f8-2beddc91b2e0'
UNVERIFIED_VAULT='c97a7500-3b11-403f-ac43-2566cdcd3fa2'

class Conn:
    def __enter__(self):return self
    def __exit__(self,*args):return False

def response(name='gmail-otp-main',ident=CORRECT,proxy='http://172.18.0.1:18889'):
    return io.BytesIO(json.dumps({'profile':{'name':name,'id':ident,'proxy':proxy}}).encode())

class FlippaProfilePreflightTests(unittest.TestCase):
    def test_valid_named_profile_and_reachable_configured_proxy(self):
        with patch.object(app.urllib.request,'urlopen',return_value=response()) as urlopen, \
             patch.object(app.socket,'create_connection',return_value=Conn()) as conn:
            result=app.flippa_profile_preflight()
        self.assertEqual(result['profile'],'original-flippa-scanner-owner')
        self.assertTrue(result['proxy_reachable'])
        self.assertIn(CORRECT,urlopen.call_args.args[0])
        conn.assert_called_once_with(('172.18.0.1',18889),timeout=4)

    def test_wrong_gmail_profile_must_fail_before_any_socket(self):
        with patch.object(app.urllib.request,'urlopen',return_value=response(name='gmail-otp-main',ident=UNVERIFIED_VAULT)), \
             patch.object(app.socket,'create_connection',side_effect=AssertionError('must not connect')):
            with self.assertRaisesRegex(RuntimeError,'FLIPPA_LEGACY_OWNER_IDENTITY_MISMATCH'):
                app.flippa_profile_preflight()

    def test_absent_proxy_fail_fast(self):
        with patch.object(app.urllib.request,'urlopen',return_value=response(proxy='')), \
             patch.object(app.socket,'create_connection',side_effect=AssertionError('must not connect')):
            with self.assertRaisesRegex(RuntimeError,'FLIPPA_PROXY_CONFIG_MISSING'):
                app.flippa_profile_preflight()

    def test_proxy_offline_fail_fast(self):
        with patch.object(app.urllib.request,'urlopen',return_value=response()), \
             patch.object(app.socket,'create_connection',side_effect=OSError('connection refused')):
            with self.assertRaisesRegex(RuntimeError,'FLIPPA_PROXY_UNAVAILABLE'):
                app.flippa_profile_preflight()

if __name__=='__main__':
    unittest.main()
