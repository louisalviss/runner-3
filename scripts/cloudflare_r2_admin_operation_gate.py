#!/usr/bin/env python3
"""Offline R2 admin workflow gate; no external calls and no credential access.

Requires independent approval of both cost release and each legacy workflow.
"""
import json
import pathlib
import sys
from cloudflare_r2_migration_gate import POLICY as COST_POLICY
from cloudflare_r2_migration_gate import SOURCE, TARGET, validate_policy

POLICY = pathlib.Path(__file__).resolve().parents[1] / (
    "ops/cloudflare-account-rehome/r2-admin-operations-policy.json"
)
OPERATIONS = frozenset((
    "cloudflare-rehome-r2-inventory",
    "clm-d1-to-r2-migration",
    "runner3-r2-bootstrap",
    "r2-media-bootstrap",
    "r2-lifecycle-30d",
))

def validate_admin_policy(raw, operation):
    if operation not in OPERATIONS:
        raise ValueError("R2_ADMIN_OPERATION_NOT_ALLOWLISTED")
    if not isinstance(raw, dict):
        raise ValueError("R2_ADMIN_POLICY_NOT_OBJECT")
    if raw.get("schema_version") != 1 or raw.get("gate_id") != "CLOUDFLARE-R2-ADMIN-OPERATIONS-001":
        raise ValueError("R2_ADMIN_POLICY_ID_MISMATCH")
    if raw.get("account_source") != SOURCE or raw.get("account_target") != TARGET:
        raise ValueError("R2_ADMIN_ACCOUNTS_MISMATCH")
    operations = raw.get("operations")
    if not isinstance(operations, dict) or set(operations) != OPERATIONS:
        raise ValueError("R2_ADMIN_ALLOWLIST_INCOMPLETE")
    if raw.get("status") != "USER_APPROVED" or raw.get("permit_admin_r2_operations") is not True:
        raise ValueError("R2_ADMIN_BILLING_HOLD")
    if operations.get(operation) is not True:
        raise ValueError("R2_ADMIN_OPERATION_NOT_RELEASED")
    if raw.get("source_retirement_permitted") is not False or raw.get("source_account_cutover_permitted") is not False:
        raise ValueError("R2_ADMIN_SOURCE_RETIREMENT_POLICY_CHANGED")
    return True

def main():
    try:
        if len(sys.argv) != 2 or sys.argv[1] not in OPERATIONS:
            raise ValueError("R2_ADMIN_OPERATION_ARGUMENT_INVALID")
        if not COST_POLICY.is_file() or not POLICY.is_file():
            raise ValueError("R2_ADMIN_POLICY_FILE_MISSING")
        validate_policy(json.loads(COST_POLICY.read_text(encoding="utf-8")))
        validate_admin_policy(json.loads(POLICY.read_text(encoding="utf-8")), sys.argv[1])
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        print("R2_ADMIN_OPERATION_STOPPED_BEFORE_R2_REQUEST:", str(exc) if isinstance(exc, ValueError) else "POLICY_READ_FAILURE")
        raise SystemExit(3)
    print("R2_ADMIN_OPERATION_INDEPENDENTLY_RELEASED", sys.argv[1])

if __name__ == "__main__":
    main()
