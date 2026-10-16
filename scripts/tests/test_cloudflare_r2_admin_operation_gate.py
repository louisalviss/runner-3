#!/usr/bin/env python3
"""Offline policy-only regression tests. No Cloudflare API calls."""
from copy import deepcopy
from cloudflare_r2_admin_operation_gate import OPERATIONS, POLICY, validate_admin_policy
from cloudflare_r2_migration_gate import POLICY as BASE_POLICY, validate_policy
import json

general=json.loads(BASE_POLICY.read_text(encoding="utf-8"))
policy=json.loads(POLICY.read_text(encoding="utf-8"))
assert len(OPERATIONS)==5
for op in OPERATIONS:
    try:
        validate_admin_policy(policy,op)
        raise AssertionError("Held per-operation policy accepted "+op)
    except ValueError as e:
        assert str(e)=="R2_ADMIN_BILLING_HOLD"
assert general["permit_r2_migration"] is False
print("PASS current billing and five admin operations HOLD")

released=deepcopy(policy)
released["status"]="USER_APPROVED"
released["permit_admin_r2_operations"]=True
for op in OPERATIONS:
    p=deepcopy(released)
    p["operations"][op]=True
    assert validate_admin_policy(p,op) is True
    for other in OPERATIONS - {op}:
        try:
            validate_admin_policy(p,other)
            raise AssertionError("Approved unrelated operation "+other)
        except ValueError as e:
            assert str(e)=="R2_ADMIN_OPERATION_NOT_RELEASED"
print("PASS narrow per-operation release cannot enable unrelated operations")

for mutation in (
    ("account_source","wrong"),
    ("account_target","wrong"),
    ("gate_id","wrong"),
    ("source_retirement_permitted",True),
    ("source_account_cutover_permitted",True),
):
    p=deepcopy(released)
    p["operations"][next(iter(OPERATIONS))]=True
    p[mutation[0]]=mutation[1]
    try:
        validate_admin_policy(p,next(iter(OPERATIONS)))
        raise AssertionError("Fail-open on "+mutation[0])
    except ValueError:
        pass
print("PASS fail-closed identity and source-preservation invariants")

try:
    validate_policy(general)
    raise AssertionError("Current general billing HOLD accepted")
except ValueError as e:
    assert str(e)=="R2_MIGRATION_BILLING_HOLD"
print("PASS independent general hold blocks all R2 admin operations")
