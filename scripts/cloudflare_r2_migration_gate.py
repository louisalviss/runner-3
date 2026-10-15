#!/usr/bin/env python3
"""Fail-closed OFFLINE gate for manually dispatched Cloudflare R2 migration.

Place immediately after actions/checkout and before ANY network-calling step.
Changes to environment variables, workflow inputs or GitHub secrets cannot
authorize a held operation. Do not auto-release.
"""
import json
from pathlib import Path

POLICY = Path(__file__).resolve().parents[1] / (
    "ops/cloudflare-account-rehome/r2-migration-operation-gate.json"
)
SOURCE = "7415a87f6bce7884e73ad7cfed5782df"
TARGET = "748a80810f77f447ee476543ef0e5014"

def validate_policy(raw):
    if not isinstance(raw, dict):
        raise ValueError("GATE_POLICY_INVALID")
    if raw.get("schema_version") != 1 or raw.get("gate_id") != "CLOUDFLARE-R2-COST-001":
        raise ValueError("GATE_POLICY_ID_INVALID")
    if raw.get("account_source") != SOURCE or raw.get("account_target") != TARGET:
        raise ValueError("GATE_ACCOUNT_MISMATCH")
    if raw.get("permit_r2_migration") is not True:
        raise ValueError("R2_MIGRATION_BILLING_HOLD")
    if raw.get("status") != "USER_APPROVED":
        raise ValueError("R2_MIGRATION_NO_EXPLICIT_RELEASE")
    return True

def main():
    try:
        if not POLICY.is_file():
            raise ValueError("R2_MIGRATION_GATE_MISSING")
        raw = json.loads(POLICY.read_text(encoding="utf-8"))
        validate_policy(raw)
    except (ValueError, OSError) as exc:
        reason = str(exc) if isinstance(exc, ValueError) else "R2_MIGRATION_GATE_READ_FAILED"
        print("R2_MIGRATION_STOPPED_BEFORE_CLOUDFLARE_REQUEST:", reason)
        raise SystemExit(3)
    print("R2_MIGRATION_RELEASE_POLICY_ACCEPTED")

if __name__ == "__main__":
    main()
