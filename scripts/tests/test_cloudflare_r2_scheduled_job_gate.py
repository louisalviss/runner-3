#!/usr/bin/env python3
"""Offline-only scheduled R2 hold regression; no provider requests."""
import copy
import json
from contextlib import redirect_stdout
from io import StringIO
from unittest.mock import patch

import cloudflare_r2_scheduled_job_gate as scheduled
import cloudflare_r2_migration_gate as base

original = json.loads(scheduled.POLICY.read_text(encoding="utf-8"))
assert original["status"] == "HOLD"
assert original["permit_scheduled_r2_jobs"] is False
assert set(original["jobs"]) == scheduled.JOBS
assert all(value is False for value in original["jobs"].values())

def rejected(raw, job, expected):
    try:
        scheduled.validate_scheduled_policy(raw, job)
    except ValueError as exc:
        assert str(exc) == expected, (str(exc), expected)
    else:
        raise AssertionError("Unsafe R2 scheduled policy accepted")

for job in sorted(scheduled.JOBS):
    rejected(original, job, "R2_SCHEDULED_BILLING_HOLD")

assert base.validate_policy({"schema_version": 1, "gate_id": "CLOUDFLARE-R2-COST-001",
        "account_source": base.SOURCE, "account_target": base.TARGET,
        "permit_r2_migration": True, "status": "USER_APPROVED"})

approved = copy.deepcopy(original)
approved["status"] = "USER_APPROVED"
approved["permit_scheduled_r2_jobs"] = True
for job in sorted(scheduled.JOBS):
    rejected(approved, job, "R2_SCHEDULED_JOB_NOT_RELEASED")
approved["jobs"]["reader-r2-catalog-enrich"] = True
assert scheduled.validate_scheduled_policy(approved, "reader-r2-catalog-enrich")
for job in sorted(scheduled.JOBS - {"reader-r2-catalog-enrich"}):
    rejected(approved, job, "R2_SCHEDULED_JOB_NOT_RELEASED")
rejected(approved, "not-allowlisted", "R2_SCHEDULED_JOB_NOT_ALLOWLISTED")
bad = copy.deepcopy(approved)
bad["permit_scheduled_r2_jobs"] = 1
rejected(bad, "reader-r2-catalog-enrich", "R2_SCHEDULED_BILLING_HOLD")
bad = copy.deepcopy(approved)
bad["account_target"] = base.SOURCE
rejected(bad, "reader-r2-catalog-enrich", "R2_SCHEDULED_ACCOUNT_MISMATCH")
bad = copy.deepcopy(approved)
del bad["jobs"]["audio-library-chatgpt-inbox"]
rejected(bad, "reader-r2-catalog-enrich", "R2_SCHEDULED_JOB_POLICY_INCOMPLETE")
with redirect_stdout(StringIO()) as captured:
    try:
        scheduled.main(["reader-r2-catalog-enrich"])
    except SystemExit as exc:
        assert exc.code == 3
    else:
        raise AssertionError("Current global cost HOLD did not block CLI")
assert "BLOCKED_BEFORE_CLOUDFLARE_REQUEST" in captured.getvalue()
print("PASS separate job-specific schedule release required even after general release")
print("PASS all four scheduled R2 jobs remain HOLD and CLI blocks before any request")
