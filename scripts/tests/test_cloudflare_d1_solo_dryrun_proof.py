"""Synthetic-only proof of a fresh same-actor same-commit manual Dry-Run."""
import copy
import datetime as dt
import importlib.util
import io
import json
import os
import pathlib
import sys
import unittest
from unittest.mock import patch

ROOT=pathlib.Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location(
    "solo",ROOT/"scripts/cloudflare_d1_solo_dryrun_proof.py")
m=importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
TOKEN="synthetic_github_actions_token_12345"
RUN="40091169404"
SHA="a"*40
NOW=dt.datetime(2026,10,24,12,1,0,tzinfo=dt.timezone.utc)

def make_run(**changes):
    v={
        "id":int(RUN),
        "name":"Cloudflare D1 Recommendation Runs Additive Dry-Run (Read Only)",
        "path":m.DRYRUN_WORKFLOW_PATH,
        "event":"workflow_dispatch",
        "head_branch":"main",
        "head_sha":SHA,
        "status":"completed",
        "conclusion":"success",
        "run_attempt":1,
        "actor":{"login":"operator"},
        "triggering_actor":{"login":"operator"},
        "created_at":"2026-10-24T11:45:24Z",
        "updated_at":"2026-10-24T11:45:42Z",
    }
    v.update(changes)
    return v

def verify_result(run=None, **kw):
    k=dict(run_id=RUN,token=TOKEN,repository=m.REPOSITORY,
           event="workflow_dispatch",ref="refs/heads/main",
           sha=SHA,actor="operator",now=NOW,
           getter=lambda token,run_id:copy.deepcopy(make_run() if run is None else run))
    k.update(kw)
    return m.verify(**k)

class SoloDryrunProof(unittest.TestCase):
    def test_recent_verified_same_actor_and_commit(self):
        result=verify_result()
        self.assertEqual(result["run_id"],int(RUN))
        self.assertEqual(result["cloudflare_queries"],0)
        self.assertEqual(result["r2_requests"],0)
        self.assertFalse(result["target_d1_write_authorized"])

    def test_stale_dryrun_rejected(self):
        with self.assertRaisesRegex(m.Hold,"STALE_OR_CLOCK"):
            verify_result(now=NOW+dt.timedelta(minutes=30))

    def test_wrong_actor_and_trigger_rejected(self):
        for key in ("actor","triggering_actor"):
            p=make_run(**{key:{"login":"someone_else"}})
            with self.subTest(key=key),self.assertRaisesRegex(
                m.Hold,"NOT_SAME_USER"):
                verify_result(run=p)

    def test_wrong_sha_rejected(self):
        with self.assertRaisesRegex(m.Hold,"NOT_SAME_USER"):
            verify_result(run=make_run(head_sha="b"*40))

    def test_failed_skipped_cancelled_in_progress_rejected(self):
        for status,conclusion in (
            ("completed","failure"),("completed","cancelled"),
            ("completed","skipped"),("in_progress",None)):
            with self.subTest(conclusion=conclusion),self.assertRaisesRegex(
                m.Hold,"NOT_SAME_USER"):
                verify_result(run=make_run(status=status,conclusion=conclusion))

    def test_wrong_workflow_or_push_event_rejected(self):
        for patchval in (
            {"path":".github/workflows/evil.yml"},
            {"name":"Different Workflow"},
            {"event":"push"},
            {"head_branch":"dev"},
            {"run_attempt":2},
            {"id":123456}):
            with self.subTest(patchval=patchval),self.assertRaisesRegex(
                m.Hold,"NOT_SAME_USER"):
                verify_result(run=make_run(**patchval))

    def test_wrong_repository_branch_event_context_blocks_no_http(self):
        for values in (
            {"repository":"another/repository"},
            {"event":"push"},
            {"ref":"refs/heads/dev"},
            {"sha":"invalid"},
            {"actor":""}):
            with self.subTest(values=values),self.assertRaisesRegex(
                m.Hold,"CONTEXT_NOT_MANUAL_MAIN"):
                verify_result(**values)

    def test_untrusted_run_id_rejected_before_http(self):
        for run_id in ("", "0", "3;DROP TABLE x", "../../123456",
                       "12345", "1234567890123456789012345"):
            with self.subTest(run_id=run_id),self.assertRaisesRegex(
                m.Hold,"RUN_ID_INVALID"):
                verify_result(run_id=run_id,getter=lambda *_:self.fail("no http"))

    def test_missing_github_token_rejected(self):
        with self.assertRaisesRegex(m.Hold,"READ_TOKEN_MISSING"):
            verify_result(token="")

    def test_invalid_timestamp_rejected(self):
        with self.assertRaisesRegex(m.Hold,"INVALID_TIMESTAMP"):
            verify_result(run=make_run(updated_at="not-a-date"))

    def test_run_end_after_current_time_blocks(self):
        with self.assertRaisesRegex(m.Hold,"STALE_OR_CLOCK"):
            verify_result(now=dt.datetime(2026,10,24,11,45,0,tzinfo=dt.timezone.utc))

    def test_github_api_get_only(self):
        seen=[]
        class Response:
            status=200
            def __enter__(self):return self
            def __exit__(self,*a):return False
            def read(self,n):return json.dumps(make_run()).encode()
        def opener(request,timeout):
            seen.append((request.full_url,request.get_method(),request.data,timeout))
            return Response()
        x=m.read_workflow_run(TOKEN,RUN,opener=opener)
        self.assertEqual(x["id"],int(RUN))
        self.assertEqual(seen,[(m.API_PREFIX+RUN,"GET",None,15)])

    def test_malformed_remote_result_fails(self):
        class Response:
            status=200
            def __enter__(self):return self
            def __exit__(self,*a):return False
            def read(self,n):return b'[]'
        with self.assertRaisesRegex(m.Hold,"BAD_GITHUB_RESULT"):
            m.read_workflow_run(TOKEN,RUN,opener=lambda *a,**k:Response())

    def test_solo_proof_does_not_export_credentials(self):
        raw=json.dumps(verify_result())
        for val in (TOKEN,SHA,"operator"):
            self.assertNotIn(val,raw)

    def test_workflow_is_separate_manual_two_stage(self):
        path=ROOT/".github/workflows/cloudflare-d1-recommendation-runs-guarded-insert.yml"
        text=path.read_text()
        self.assertIn("  recent-dryrun-gate:",text)
        self.assertIn("needs: recent-dryrun-gate",text)
        self.assertIn("D1_SOLO_DRYRUN_RUN_ID:",text)
        self.assertNotIn("environment: cloudflare-target-d1-writes",text)
        head=text.split("  recent-dryrun-gate:",1)[1].split("  additive-write:",1)[0]
        self.assertNotIn("CLOUDFLARE_",head)
        self.assertIn("github.ref == 'refs/heads/main'",text)
        self.assertNotIn("  push:",text)

if __name__=="__main__":
    unittest.main()
