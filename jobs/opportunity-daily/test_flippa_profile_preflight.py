#!/usr/bin/env python3
"""Offline Flippa profile provenance and transport checks: no browser/provider calls."""
import io,json,unittest,pathlib,tempfile
from unittest.mock import patch

import opportunity_daily as app

DEDICATED='c97a7500-3b11-403f-ac43-2566cdcd3fa2'
LEGACY='1de482cb-96ac-4b1b-a3f8-2beddc91b2e0'

class Conn:
    def __enter__(self):return self
    def __exit__(self,*args):return False

def response(name='flippa-main',ident=DEDICATED,proxy='http://172.18.0.1:18889'):
    return io.BytesIO(json.dumps({'profile':{'name':name,'id':ident,'proxy':proxy}}).encode())

class FlippaProfilePreflightTests(unittest.TestCase):
    def test_valid_dedicated_profile_and_reachable_configured_proxy(self):
        with patch.object(app.urllib.request,'urlopen',return_value=response()) as urlopen, \
             patch.object(app.socket,'create_connection',return_value=Conn()) as conn:
            result=app.flippa_profile_preflight()
        self.assertEqual(result['profile'],'flippa-main')
        self.assertTrue(result['proxy_reachable'])
        self.assertIn(DEDICATED,urlopen.call_args.args[0])
        conn.assert_called_once_with(('172.18.0.1',18889),timeout=4)

    def test_legacy_gmail_profile_rejected_before_socket(self):
        with patch.object(app.urllib.request,'urlopen',return_value=response(name='gmail-otp-main',ident=LEGACY)), \
             patch.object(app.socket,'create_connection',side_effect=AssertionError('must not connect')):
            with self.assertRaisesRegex(RuntimeError,'FLIPPA_DEDICATED_OWNER_IDENTITY_MISMATCH'):
                app.flippa_profile_preflight()

    def test_wrong_name_for_dedicated_id_rejected(self):
        with patch.object(app.urllib.request,'urlopen',return_value=response(name='gmail-otp-main')), \
             patch.object(app.socket,'create_connection',side_effect=AssertionError('must not connect')):
            with self.assertRaisesRegex(RuntimeError,'FLIPPA_DEDICATED_OWNER_IDENTITY_MISMATCH'):
                app.flippa_profile_preflight()

    def test_wrong_id_for_dedicated_name_rejected(self):
        with patch.object(app.urllib.request,'urlopen',return_value=response(ident=LEGACY)), \
             patch.object(app.socket,'create_connection',side_effect=AssertionError('must not connect')):
            with self.assertRaisesRegex(RuntimeError,'FLIPPA_DEDICATED_OWNER_IDENTITY_MISMATCH'):
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

    def test_scan_profile_guard_accepts_only_dedicated_id(self):
        app.assert_flippa_scan_profile('PROFILE="c97a7500-3b11-403f-ac43-2566cdcd3fa2"\n')

    def test_scan_profile_guard_rejects_missing_legacy_and_duplicate(self):
        for source in (
            'PROFILE="1de482cb-96ac-4b1b-a3f8-2beddc91b2e0"\n',
            'PROFILE="c97a7500-3b11-403f-ac43-2566cdcd3fa2"\nPROFILE="1de482cb-96ac-4b1b-a3f8-2beddc91b2e0"\n',
            'OTHER="c97a7500-3b11-403f-ac43-2566cdcd3fa2"\n',
        ):
            with self.subTest(source=source), self.assertRaisesRegex(RuntimeError,'FLIPPA_SCAN_PROFILE_DRIFT'):
                app.assert_flippa_scan_profile(source)

    def test_legacy_cached_script_is_rejected_before_browser(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=pathlib.Path(tmp)
            template=root/'flippa-daily-stage-20261013.py'
            script=root/'flippa-daily-stage-20261106-daily.py'
            template.write_text('PROFILE="c97a7500-3b11-403f-ac43-2566cdcd3fa2"\n# 20261013\n')
            script.write_text('PROFILE="1de482cb-96ac-4b1b-a3f8-2beddc91b2e0"\n')
            with patch.object(app,'ROOT',root), patch.object(app,'TEMPLATE',template), \
                 patch.object(app,'flippa_profile_preflight',return_value={'profile':'flippa-main'}), \
                 patch.object(app.subprocess,'run',side_effect=AssertionError('must not execute browser')):
                with self.assertRaisesRegex(RuntimeError,'FLIPPA_SCAN_PROFILE_DRIFT'):
                    app.run_flippa('2026-11-06')

    def test_legacy_template_is_rejected_before_browser(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=pathlib.Path(tmp)
            template=root/'flippa-daily-stage-20261013.py'
            template.write_text('PROFILE="1de482cb-96ac-4b1b-a3f8-2beddc91b2e0"\n# 20261013\n')
            with patch.object(app,'ROOT',root), patch.object(app,'TEMPLATE',template), \
                 patch.object(app,'flippa_profile_preflight',return_value={'profile':'flippa-main'}), \
                 patch.object(app.subprocess,'run',side_effect=AssertionError('must not execute browser')):
                with self.assertRaisesRegex(RuntimeError,'FLIPPA_SCAN_PROFILE_DRIFT'):
                    app.run_flippa('2026-11-06')

    def test_completed_state_rejects_legacy_lineage_before_cache_return(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=pathlib.Path(tmp)
            template=root/'flippa-daily-stage-20261013.py'
            script=root/'flippa-daily-stage-20261106-daily.py'
            state=root/'flippa-20261106-daily-state.json'
            template.write_text('PROFILE="c97a7500-3b11-403f-ac43-2566cdcd3fa2"\n# 20261013\n')
            script.write_text('PROFILE="c97a7500-3b11-403f-ac43-2566cdcd3fa2"\n')
            state.write_text(json.dumps({'first_done':True,'recent_done':True}))
            with patch.object(app,'ROOT',root), patch.object(app,'TEMPLATE',template), \
                 patch.object(app,'flippa_profile_preflight',return_value={'profile':'flippa-main'}), \
                 patch.object(app.subprocess,'run',side_effect=AssertionError('must not execute browser')):
                with self.assertRaisesRegex(RuntimeError,'FLIPPA_STATE_PROFILE_UNVERIFIED'):
                    app.run_flippa('2026-11-06')

    def test_completed_state_with_matching_lineage_can_return_cache(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=pathlib.Path(tmp)
            template=root/'flippa-daily-stage-20261013.py'
            script=root/'flippa-daily-stage-20261106-daily.py'
            state=root/'flippa-20261106-daily-state.json'
            template.write_text('PROFILE="c97a7500-3b11-403f-ac43-2566cdcd3fa2"\n# 20261013\n')
            script.write_text('PROFILE="c97a7500-3b11-403f-ac43-2566cdcd3fa2"\n')
            state.write_text(json.dumps({'first_done':True,'recent_done':True,'profile_id':DEDICATED}))
            with patch.object(app,'ROOT',root), patch.object(app,'TEMPLATE',template), \
                 patch.object(app,'flippa_profile_preflight',return_value={'profile':'flippa-main'}), \
                 patch.object(app.subprocess,'run',side_effect=AssertionError('must not execute browser')):
                self.assertEqual(app.run_flippa('2026-11-06'),state)

    def test_existing_state_without_executable_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=pathlib.Path(tmp)
            template=root/'flippa-daily-stage-20261013.py'
            template.write_text('PROFILE="c97a7500-3b11-403f-ac43-2566cdcd3fa2"\n# 20261013\n')
            (root/'flippa-20261106-daily-state.json').write_text(json.dumps({'profile_id':DEDICATED}))
            with patch.object(app,'ROOT',root), patch.object(app,'TEMPLATE',template), \
                 patch.object(app,'flippa_profile_preflight',return_value={'profile':'flippa-main'}), \
                 patch.object(app.subprocess,'run',side_effect=AssertionError('must not execute browser')):
                with self.assertRaisesRegex(RuntimeError,'FLIPPA_CACHED_SCRIPT_MISSING'):
                    app.run_flippa('2026-11-06')

    def test_template_state_loader_carries_profile_lineage(self):
        source=(pathlib.Path(__file__).parent/'flippa-daily-stage-20261013.py').read_text(encoding='utf-8')
        self.assertIn('"profile_id":PROFILE',source)
        self.assertIn('saved.get("profile_id") != PROFILE',source)


    def test_recent_overlap_bounded_fresh_capture_preserves_old_cards(self):
        import ast, os, copy
        from datetime import datetime, timezone, timedelta
        source=(pathlib.Path(__file__).parent/'flippa-daily-stage-20261013.py').read_text()
        names={"recent_completed_pages","recent_capture_complete","mark_recent_overlap","prepare_recent_capture"}
        module=ast.parse(source)
        funcs=ast.Module(body=[x for x in module.body if isinstance(x,ast.FunctionDef) and x.name in names],type_ignores=[])
        now=datetime(2026,11,25,14,0,tzinfo=timezone.utc)
        writes=[]
        env=dict(os=os,datetime=datetime,timezone=timezone,timedelta=timedelta,
                 STATE="/tmp/flippa-20261125-daily-state.json",atomic=lambda p,s:writes.append(copy.deepcopy(s)))
        exec(compile(funcs,"recent-fixture","exec"),env)
        prep=env["prepare_recent_capture"]
        first={"lane":"first_access","page":1,"status":200,"challenge":"NONE","count":100}
        recent=[{"lane":"recent","page":i,"status":200,"challenge":"NONE","count":100} for i in range(1,6)]
        ids=[str(i) for i in range(498)]
        state={"pages":[first]+recent,"recent_ids":ids.copy(),"recent_rows":{i:{"id":i} for i in ids},
               "recent_done":False,"first_done":True,"first_ids":["10000"],"errors":[]}
        self.assertEqual(prep(dict(state,pages=[first]+recent[:4]),now),{1,2,3,4})
        with self.assertRaisesRegex(RuntimeError,"COOLDOWN"):
            prep(state,now)
        self.assertEqual(len(state["recent_ids"]),498)
        self.assertEqual(state["errors"][-1]["reason"],"RECENT_CROSS_PAGE_OVERLAP_OR_ID_MISMATCH")
        with self.assertRaisesRegex(RuntimeError,"COOLDOWN"):
            prep(state,now+timedelta(minutes=14))
        self.assertEqual(prep(state,now+timedelta(minutes=15)),set())
        self.assertEqual(state["pages"],[first])
        self.assertEqual(state["first_ids"],["10000"])
        self.assertEqual(state["recent_attempt_history"][0]["recent_ids"],ids)
        self.assertEqual(state["recent_attempt_history"][0]["pages"],recent)
        self.assertEqual(len(state["recent_attempt_history"][0]["recent_rows"]),498)
        self.assertEqual(state["recent_ids"],[])
        self.assertEqual(state["recent_rows"],{})
        self.assertFalse(state["recent_done"])
        state.update(pages=[first]+recent,recent_ids=ids,recent_rows={i:{"id":i} for i in ids})
        with self.assertRaisesRegex(RuntimeError,"RESTART_EXHAUSTED"):
            prep(state,now+timedelta(minutes=30))
        self.assertEqual(len(state["recent_attempt_history"]),1)
        self.assertEqual(len(state["recent_ids"]),498)
        env["STATE"]="/tmp/flippa-20261124-daily-state.json"
        with self.assertRaisesRegex(RuntimeError,"HISTORICAL_CAPTURE_INCOMPLETE"):
            prep(state,now+timedelta(minutes=30))
        full=[str(i) for i in range(500)]
        state.update(recent_ids=full,recent_rows={i:{"id":i} for i in full})
        self.assertTrue(env["recent_capture_complete"](state,set(range(1,6))))
        self.assertEqual(prep(state,now),set(range(1,6)))
        state["recent_rows"].pop("499")
        self.assertFalse(env["recent_capture_complete"](state,set(range(1,6))))


if __name__=='__main__':
    unittest.main()
