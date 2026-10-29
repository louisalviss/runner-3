#!/usr/bin/env python3
"""Fail-closed DERIVED-profile migration gate from sanitized read-only audit.

No Cloudflare API, D1 SQL, row data, secret, row hashes, R2 or Workers.
Never authorizes D1 writes. The computed profile tables are projections of
content_features + user_content_events, NOT authoritative migration inputs.
"""
import json
import os
import pathlib

INPUT = pathlib.Path("migration-out/d1-two-interest-profiles-keyed-parity.json")
OUTPUT = pathlib.Path("migration-out/d1-derived-profile-reconcile-gate.json")
EXPECTED = ("interest_family_profile", "interest_profile")
UPSTREAM = ("content_items", "content_features", "user_content_events")
SCHEMA_SOURCE = pathlib.Path("cloudflare/runner3-core/src/content-personalization.js")
MAX_BYTES = 20000

class Hold(Exception):
    pass

def require(value, reason):
    if not value:
        raise Hold(reason)

def verify_projection_source(script):
    require(isinstance(script, str) and
            "export function profileProjectionCte()" in script and
            "export async function recomputeInterestProfile(" in script,
            "RECOMPUTE_SOURCE_NOT_FOUND")
    # These are source-code markers, not executable SQL from any runtime input.
    required = (
        "FROM user_content_events",
        "JOIN normalized_features",
        "FROM content_features f",
        "INSERT INTO interest_profile(",
        "DELETE FROM interest_profile",
        "INSERT INTO interest_family_profile(",
        "DELETE FROM interest_family_profile",
    )
    require(all(s in script for s in required), "DERIVED_PROFILE_DEPENDENCY_DRIFT")
    return True

def nonnegative_int(value):
    return type(value) is int and 0 <= value <= 100

def assess(receipt, script):
    verify_projection_source(script)
    require(type(receipt) is dict and
            receipt.get("status") ==
                "TWO_BOUNDED_TABLES_READ_ONLY_NOT_ACCOUNTWIDE_PARITY" and
            receipt.get("sensitive_keys_and_values_exported") is False and
            receipt.get("fingerprints_exported") is False and
            receipt.get("atomic_snapshot") is False and
            receipt.get("accountwide_row_parity_verified") is False and
            receipt.get("deletion_parity_verified") is False and
            receipt.get("d1_writes") == 0 and
            receipt.get("cutover_ready") is False,
            "AUDIT_CONTRACT_UNTRUSTED")
    root = receipt.get("databases")
    require(type(root) is dict and set(root) ==
            {"runner3-content-intelligence"}, "DATABASE_SCOPE_DRIFT")
    tables = root["runner3-content-intelligence"]
    require(type(tables) is dict and set(tables) == set(EXPECTED),
            "TABLE_SET_DRIFT")
    out = {}
    for table in EXPECTED:
        entry=tables[table]
        require(type(entry) is dict and
                entry.get("schema_equal") is True and
                entry.get("snapshot_stable_during_probe") is True and
                entry.get("bounded_complete_table") is True,
                "SCHEMA_OR_CAPTURE_NOT_PROVEN")
        fields=("source_rows_observed","target_rows_observed",
                "matching_key_payload_pairs","changed_payloads",
                "source_only_keys","target_only_keys","common_keys_compared")
        require(all(nonnegative_int(entry.get(n)) for n in fields),
                "COUNTS_INVALID")
        s,t=entry["source_rows_observed"],entry["target_rows_observed"]
        shared=entry["common_keys_compared"]
        matched=entry["matching_key_payload_pairs"]
        changed=entry["changed_payloads"]
        only_s,only_t=entry["source_only_keys"],entry["target_only_keys"]
        require(shared==matched+changed and
                s==shared+only_s and t==shared+only_t,
                "PK_CENSUS_INCONSISTENT")
        diffs=entry.get("common_pk_column_difference_counts")
        require(type(diffs) is dict and
                set(diffs)==({"weight","evidence_count","positive_count",
                              "negative_count","confidence","updated_at"}) and
                all(nonnegative_int(n) and n<=shared for n in diffs.values()) and
                (changed==0 or sum(diffs.values())>=changed),
                "COLUMN_COUNTS_INVALID")
        # Both profile tables are MATERIALIZED DERIVED STATE, so row-copy
        # status cannot become PASS from this summary regardless of counts.
        out[table]={
            "source_rows":s,
            "target_rows":t,
            "matched":matched,
            "payload_conflicts":changed,
            "source_only":only_s,
            "target_only_preserve_for_review":only_t,
            "column_difference_counts":diffs,
            "direct_copy_authorized":False,
            "automatic_target_only_delete_authorized":False,
            "recompute_authorized":False,
        }
    return {
        "status":"DERIVED_PROFILE_RECOMPUTE_BLOCKED_UPSTREAM_PARITY_AND_RECOVERY",
        "database":"runner3-content-intelligence",
        "profile_tables":out,
        "upstream_table_parity_required":list(UPSTREAM),
        "upstream_row_parity_verified":False,
        "upstream_delete_semantics_verified":False,
        "writer_quiescence_verified":False,
        "recovery_bookmark_installed":False,
        "safe_sequence":[
            "RECONCILE_BASE_CONTENT_ITEMS_FEATURES_EVENTS_WITH_DELETE_POLICY",
            "PROVE_TARGET_ONLY_ROW_PRESERVATION_AND_WRITE_QUIESCENCE",
            "INSTALL_AND_TEST_PREAPPLY_RECOVERY_WITH_AUTHORIZED_PROCESS",
            "RECOMPUTE_DERIVED_PROFILES_ONLY_AFTER_SEPARATE_APPROVAL",
            "VERIFY_RECOMPUTED_PROFILE_AND_DEPENDENT_SCORES",
        ],
        "production_target_changes":0,
        "d1_writes":0,
        "r2_requests":0,
        "cutover_ready":False,
    }

def main():
    try:
        require(os.getenv("GITHUB_REPOSITORY")=="louisalviss/runner-3"
                and os.getenv("GITHUB_REF")=="refs/heads/main"
                and os.getenv("GITHUB_EVENT_NAME")=="workflow_dispatch"
                and not os.getenv("CLOUDFLARE_TARGET_D1_WRITE_TOKEN"),
                "UNTRUSTED_JOB_CONTEXT")
        require(INPUT.is_file() and not INPUT.is_symlink() and
                0<INPUT.stat().st_size<=MAX_BYTES,
                "AUDIT_FILE_NOT_SAFE")
        require(SCHEMA_SOURCE.is_file() and
                not SCHEMA_SOURCE.is_symlink() and
                SCHEMA_SOURCE.stat().st_size<=100000,
                "PROJECTION_SOURCE_UNAVAILABLE")
        receipt=json.loads(INPUT.read_text(encoding="utf-8"))
        source=SCHEMA_SOURCE.read_text(encoding="utf-8")
        plan=assess(receipt,source)
        OUTPUT.parent.mkdir(parents=True,exist_ok=True)
        OUTPUT.write_text(json.dumps(plan,sort_keys=True,indent=2)+"\n",
                          encoding="utf-8")
        print("D1_DERIVED_PROFILE_RECONCILE_GATE_HOLD"
              " upstream_parity=false recovery=false no_writes")
        return 0
    except (Hold,ValueError,TypeError,OSError,UnicodeError):
        print("D1_DERIVED_PROFILE_RECONCILE_GATE_REJECTED no_writes")
        return 3

if __name__=="__main__":
    raise SystemExit(main())
