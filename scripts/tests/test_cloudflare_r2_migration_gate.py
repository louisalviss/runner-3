#!/usr/bin/env python3
"""Purely offline contract checks. No Cloudflare network calls."""
import copy
import json
from pathlib import Path
from cloudflare_r2_migration_gate import validate_policy, SOURCE, TARGET

policy_path = Path(__file__).resolve().parents[2] / "ops/cloudflare-account-rehome/r2-migration-operation-gate.json"
current = json.loads(policy_path.read_text())
assert current["permit_r2_migration"] is False
assert current["status"] == "HOLD"

def blocked(data):
    try:
        validate_policy(data)
    except ValueError:
        return True
    return False

assert blocked(current)
for mut in (
    {"permit_r2_migration": "true"},
    {"permit_r2_migration": 1},
    {"permit_r2_migration": False},
    {"account_source": TARGET},
    {"account_target": SOURCE},
    {"schema_version": 2},
    {"gate_id": "UNKNOWN"},
    {"status": "HOLD", "permit_r2_migration": True},
    {"status": "USER_APPROVED", "permit_r2_migration": False},
):
    d = copy.deepcopy(current)
    d.update(mut)
    assert blocked(d), mut
approved = copy.deepcopy(current)
approved["permit_r2_migration"] = True
approved["status"] = "USER_APPROVED"
assert validate_policy(approved)
print("PASS: billing hold blocks offline migration; user-approved two-part release only")
