#!/usr/bin/env python3
"""Offline two-factor policy for scheduled R2 jobs. Never queries Cloudflare.

Requires BOTH general user-approved R2 billing release and a separate
per-workflow scheduled release. No environment or GitHub input override.
"""
import json
import pathlib
import sys
from cloudflare_r2_migration_gate import POLICY as BASE_POLICY
from cloudflare_r2_migration_gate import SOURCE, TARGET, validate_policy

POLICY = pathlib.Path(__file__).resolve().parents[1] / (
    "ops/cloudflare-account-rehome/r2-scheduled-jobs-policy.json"
)
JOBS = frozenset({
    "runner3-artifact-test-cleanup",
    "reader-r2-catalog-enrich",
    "audio-library-chatgpt-inbox",
    "audio-library-chatgpt-packets",
})

def validate_scheduled_policy(raw, job):
    if job not in JOBS:
        raise ValueError("R2_SCHEDULED_JOB_NOT_ALLOWLISTED")
    if not isinstance(raw, dict):
        raise ValueError("R2_SCHEDULED_POLICY_INVALID")
    if raw.get("schema_version") != 1 or raw.get("gate_id") != "CLOUDFLARE-R2-SCHEDULED-JOBS-001":
        raise ValueError("R2_SCHEDULED_POLICY_ID_INVALID")
    if raw.get("account_source") != SOURCE or raw.get("account_target") != TARGET:
        raise ValueError("R2_SCHEDULED_ACCOUNT_MISMATCH")
    if raw.get("status") != "USER_APPROVED" or raw.get("permit_scheduled_r2_jobs") is not True:
        raise ValueError("R2_SCHEDULED_BILLING_HOLD")
    jobs = raw.get("jobs")
    if not isinstance(jobs, dict) or set(jobs) != JOBS:
        raise ValueError("R2_SCHEDULED_JOB_POLICY_INCOMPLETE")
    if jobs.get(job) is not True:
        raise ValueError("R2_SCHEDULED_JOB_NOT_RELEASED")
    return True

def main(argv=None):
    args = list(sys.argv[1:] if argv is None else argv)
    try:
        if len(args) != 1 or args[0] not in JOBS:
            raise ValueError("R2_SCHEDULED_JOB_ARGUMENT_INVALID")
        if not BASE_POLICY.is_file() or not POLICY.is_file():
            raise ValueError("R2_SCHEDULED_GATE_FILE_MISSING")
        validate_policy(json.loads(BASE_POLICY.read_text(encoding="utf-8")))
        validate_scheduled_policy(json.loads(POLICY.read_text(encoding="utf-8")), args[0])
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        print("R2_SCHEDULED_JOB_BLOCKED_BEFORE_CLOUDFLARE_REQUEST:", type(exc).__name__,
              str(exc) if isinstance(exc, ValueError) else "GATE_READ_FAILED")
        raise SystemExit(3)
    print("R2_SCHEDULED_JOB_EXPLICITLY_RELEASED:", args[0])

if __name__ == "__main__":
    main()
