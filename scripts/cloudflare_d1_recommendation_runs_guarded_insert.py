#!/usr/bin/env python3
"""Explicitly approved, target-only, one-table additive D1 copier.

DANGEROUS OPERATION, NEVER AUTOMATIC. Guarded by a manual workflow input,
three distinct scoped credentials, fresh exact pre-apply Time Travel bookmark,
and explicit writer-quiescence / row-safe recovery attestations. No automatic
Time Travel RESTORE, source mutation, target DELETE/UPDATE, schema change or R2.

This tool is *not* authorized to run with only the existing audit tokens.
If a write fails midway, preserve successful additive rows and HOLD; never
delete unknown rows or restore unrelated data automatically.
"""
import argparse
import json
import os
import pathlib
import urllib.error
import urllib.request

from cloudflare_d1_first_live_table_parity import (
    SRC_ACCOUNT, DST_ACCOUNT, SRC_UUID, DST_UUID, DB, TABLE, COLUMNS,
    META_SQL, ROWS_SQL, Blocked, require, request_json, check_schema,
)
from cloudflare_d1_recommendation_runs_dryrun import (
    safe_map, canon, canon_after_sqlite_real_affinity,
    require_expected_columns, scratch_rehearsal,
)
from cloudflare_d1_solo_dryrun_proof import from_environment as require_recent_solo_dryrun
from cloudflare_d1_target_time_travel_readonly import (
    PATHS as BOOKMARK_URLS, get_json as get_target_bookmark,
)

APPROVAL = "APPROVE_TARGET_ONLY_RECOMMENDATION_RUNS_12_INSERTS"
OUT = pathlib.Path("migration-out/d1-recommendation-runs-apply-sanitized.json")
EXPECTED_MISSING = 12
MAX_MISSING = 12
MAX_WRITE_RESPONSE = 65_536
WRITE_URL = ("https://api.cloudflare.com/client/v4/accounts/" + DST_ACCOUNT +
             "/d1/database/" + DST_UUID + "/query")
# Exact column order and target table authority are pinned in imported modules.
COLUMNS_SQL = ",".join('"' + c + '"' for c in COLUMNS)
def params_and_sql(row):
    require(isinstance(row, dict) and set(row) == set(COLUMNS),
            "UNEXPECTED_WRITE_FIELDS")
    # SQLite NULL uses a static literal. Remaining values are bound; no raw
    # row value is ever concatenated into SQL. This respects documented
    # Cloudflare D1 query API params: string[].
    holders, params = [], []
    for col in COLUMNS:
        val = row[col]
        if val is None:
            holders.append("NULL")
        else:
            require(type(val) in (str, int, float), "UNSUPPORTED_BIND_TYPE")
            holders.append("?")
            params.append(str(val))
    sql = ('INSERT INTO "recommendation_runs" (' + COLUMNS_SQL +
           ") VALUES (" + ",".join(holders) + ")")
    require(sql.count("?") == len(params) and
            1 <= len(params) <= len(COLUMNS) and ";" not in sql and
            sql.startswith('INSERT INTO "recommendation_runs" ('),
            "WRITE_SQL_GUARD_FAILED")
    return sql, params


def write_one(token, sql, params, opener=urllib.request.urlopen):
    require(type(token) is str and len(token) >= 16,
            "TARGET_D1_WRITE_TOKEN_MISSING")
    require(type(params) is list and
            all(type(v) is str for v in params) and
            1 <= len(params) <= len(COLUMNS), "UNSAFE_WRITE_PARAMS")
    allowed_prefix = 'INSERT INTO "recommendation_runs" (' + COLUMNS_SQL + ") VALUES ("
    require(sql.startswith(allowed_prefix) and sql.endswith(")") and
            sql.count("?") == len(params) and ";" not in sql and
            all(h in ("?", "NULL") for h in
                sql[len(allowed_prefix):-1].split(",")),
            "WRITE_SQL_NOT_ALLOWLISTED")
    req = urllib.request.Request(WRITE_URL, method="POST", headers={
        "Authorization": "Bearer " + token,
        "Accept": "application/json",
        "Content-Type": "application/json",
    }, data=json.dumps({"sql": sql, "params": params},
                      separators=(",", ":")).encode("utf8"))
    try:
        with opener(req, timeout=25) as response:
            require(response.status == 200, "TARGET_WRITE_HTTP_NOT_200")
            body = response.read(MAX_WRITE_RESPONSE + 1)
    except urllib.error.HTTPError as ex:
        raise Blocked("TARGET_WRITE_HTTP_" + str(ex.code)) from None
    except (urllib.error.URLError, OSError, TimeoutError):
        # Network errors after a POST are *ambiguous* (row might be committed).
        raise Blocked("TARGET_WRITE_UNKNOWN_COMMIT_HOLD") from None
    require(len(body) <= MAX_WRITE_RESPONSE,
            "TARGET_WRITE_RESPONSE_OVERSIZED")
    try:
        payload = json.loads(body)
    except (ValueError, UnicodeError):
        raise Blocked("TARGET_WRITE_RESPONSE_INVALID") from None
    require(isinstance(payload, dict), "TARGET_INSERT_RESPONSE_NOT_OBJECT")
    result = payload.get("result")
    require(payload.get("success") is True and
            isinstance(result, list) and len(result) == 1 and
            isinstance(result[0], dict) and result[0].get("success") is True,
            "TARGET_INSERT_FAILED_HOLD")
    meta = result[0].get("meta")
    require(isinstance(meta, dict) and
            meta.get("changed_db") is True and
            type(meta.get("changes")) in (int, float) and
            meta.get("changes") == 1,
            "TARGET_INSERT_WRITE_COUNT_UNEXPECTED_HOLD")
    return True


def same_as_inserted_storage(actual_row, original_source_row):
    """Allow ONLY SQLite REAL-affinity representation differences.

    A source JSON integer in exploration_ratio may round-trip as a SQLite
    REAL/JSON float after the insert, depending on API serialization. Never
    normalize existing source/target rows or TEXT/INTEGER values.
    """
    return (canon(actual_row) == canon(original_source_row) or
            canon(actual_row) ==
            canon_after_sqlite_real_affinity(original_source_row))


def observe_pair(source_read, target_read):
    source_meta = source_read(META_SQL)
    target_meta = target_read(META_SQL)
    require_expected_columns(source_meta)
    require_expected_columns(target_meta)
    require(check_schema(source_meta) == check_schema(target_meta),
            "WRITE_PREFLIGHT_SCHEMA_DRIFT")
    s1, t1 = safe_map(source_read(ROWS_SQL)), safe_map(target_read(ROWS_SQL))
    s2, t2 = safe_map(source_read(ROWS_SQL)), safe_map(target_read(ROWS_SQL))
    require(set(s1) == set(s2) and
            all(canon(s1[k]) == canon(s2[k]) for k in s1) and
            set(t1) == set(t2) and
            all(canon(t1[k]) == canon(t2[k]) for k in t1),
            "WRITE_PREFLIGHT_UNSTABLE")
    require(not (set(t2) - set(s2)) and
            all(canon(s2[k]) == canon(t2[k]) for k in t2),
            "WRITE_PREFLIGHT_CONFLICT")
    missing = sorted(set(s2) - set(t2))
    require(len(missing) == EXPECTED_MISSING, "WRITE_EXPECTED_12_DELTA_CHANGED")
    # Independently repeat complete scratch rehearsal even after preceding
    # manual workflow. This reads no source/target row artifacts.
    scratch_rehearsal(s2, t2, missing)
    return s2, t2, missing


def apply_gate(source_token, target_read_token, target_write_token,
               expected_bookmark, approval, writer_ack, recovery_ack,
               source_reader=request_json, target_reader=request_json,
               bookmark_reader=get_target_bookmark, writer=write_one):
    tokens = (source_token, target_read_token, target_write_token)
    require(all(type(t) is str and len(t) >= 16 for t in tokens) and
            len(set(tokens)) == 3, "THREE_DISTINCT_ACCOUNT_TOKENS_REQUIRED")
    require(approval == APPROVAL and writer_ack == "YES" and
            recovery_ack == "YES", "EXPLICIT_TARGET_WRITE_APPROVAL_REQUIRED")
    require(type(expected_bookmark) is str and
            12 <= len(expected_bookmark) <= 256 and
            all(33 <= ord(c) <= 126 for c in expected_bookmark),
            "PRESERVED_PREAPPLY_BOOKMARK_REQUIRED")

    def source_read(sql):
        require(sql in (META_SQL, ROWS_SQL), "SOURCE_READ_SCOPE_VIOLATION")
        return source_reader(source_token, SRC_ACCOUNT, SRC_UUID, sql)

    def target_read(sql):
        require(sql in (META_SQL, ROWS_SQL), "TARGET_READ_SCOPE_VIOLATION")
        return target_reader(target_read_token, DST_ACCOUNT, DST_UUID, sql)

    source, target, missing = observe_pair(source_read, target_read)
    # Check live current bookmark against an independently, privately
    # preserved exact pre-apply bookmark, not a public SHA or old receipt.
    book = bookmark_reader(target_read_token, BOOKMARK_URLS[1])
    require(isinstance(book, dict) and book.get("bookmark") ==
            expected_bookmark, "TARGET_BOOKMARK_MOVED_OR_NOT_PRESERVED")

    applied = {}
    for index, key in enumerate(missing):
        observed = safe_map(target_read(ROWS_SQL))
        expected = {**target, **applied}
        require(set(observed) == set(expected) and
                all(canon(observed[k]) == canon(target[k]) for k in target) and
                all(same_as_inserted_storage(observed[k], applied[k])
                    for k in applied),
                "TARGET_CHANGED_DURING_APPLY_HOLD")
        require(key not in observed, "TARGET_PK_RACE_BEFORE_INSERT")
        sql, params = params_and_sql(source[key])
        writer(target_write_token, sql, params)
        check = safe_map(target_read(ROWS_SQL))
        require(set(check) == (set(expected) | {key}) and
                all(canon(check[k]) == canon(target[k]) for k in target) and
                all(same_as_inserted_storage(check[k], applied[k])
                    for k in applied) and
                same_as_inserted_storage(check[key], source[key]),
                "TARGET_POST_INSERT_READBACK_HOLD")
        applied[key] = source[key]
    # Mandatory end-to-end catch-up check; if production adds or edits rows,
    # fail closed with safe additive partial state. Never erase target records.
    end_source = safe_map(source_read(ROWS_SQL))
    end_target = safe_map(target_read(ROWS_SQL))
    require(set(end_source) == set(end_target) and
            set(end_target) == set(source) and
            all(canon(end_source[k]) == canon(source[k]) for k in source) and
            all(canon(end_target[k]) == canon(target[k]) for k in target) and
            all(same_as_inserted_storage(end_target[k], source[k])
                for k in missing),
            "FINAL_SOURCE_CATCHUP_DRIFT_HOLD")
    strict_changed = sum(canon(end_source[k]) != canon(end_target[k])
                         for k in source)
    return {
        "format": "d1-recommendation-runs-additive-target-insert-v1",
        "status": ("ONE_TABLE_ADDITIVE_INSERTS_VERIFIED_NOT_CUTOVER"
                   if strict_changed == 0 else
                   "ONE_TABLE_AFFINITY_EQUIVALENT_NOT_STRICT_PARITY_HOLD"),
        "database": DB, "table": TABLE,
        "new_rows_inserted": len(missing),
        "source_rows_at_end": len(end_source),
        "target_rows_at_end": len(end_target),
        "all_observed_rows_equal": strict_changed == 0,
        "real_affinity_equivalent_inserted_rows_verified": True,
        "strict_payload_difference_count_after_copy": strict_changed,
        "strict_row_parity_proven": strict_changed == 0,
        "raw_rows_or_keys_exported": False,
        "target_write_token_exported": False,
        "preserved_bookmark_exported": False,
        "whole_database_restore_executed": False,
        "r2_requests": 0, "source_writes": 0,
        "source_writer_quiescence_proven": False,
        "all_d1_tables_verified": False, "cutover_ready": False,
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--apply", action="store_true")
    args = p.parse_args()
    if not args.apply:
        print("TARGET_ADDITIVE_WRITE_DISABLED_EXPLICIT_APPLY_REQUIRED")
        return 3
    try:
        # Same-actor, same-commit, <=30-minute manual read-only Dry-Run is
        # required before *any* Cloudflare mutation in solo operation.
        require_recent_solo_dryrun()
        report = apply_gate(
            os.getenv("CLOUDFLARE_API_TOKEN", ""),
            os.getenv("CLOUDFLARE_TARGET_AUDIT_TOKEN", ""),
            os.getenv("CLOUDFLARE_TARGET_D1_WRITE_TOKEN", ""),
            os.getenv("CLOUDFLARE_TARGET_PREAPPLY_BOOKMARK", ""),
            os.getenv("D1_APPLY_APPROVAL", ""),
            os.getenv("D1_TARGET_WRITERS_QUIESCED_ACK", ""),
            os.getenv("D1_ROW_SAFE_RECOVERY_ACK", ""),
        )
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(json.dumps(report, sort_keys=True, indent=2) + "\n",
                       encoding="utf8")
    except Blocked as ex:
        # No raw identifiers, bookmark, token or SQL params on failure.
        print("D1_TARGET_ADDITIVE_HOLD", str(ex))
        return 3
    except (OSError, ValueError, TypeError):
        print("D1_TARGET_ADDITIVE_HOLD INTERNAL_OR_IO_ERROR")
        return 3
    if not report["strict_row_parity_proven"]:
        print("D1_TARGET_ADDITIVE_HOLD AFFINITY_EQUIVALENT_NOT_STRICT_TYPED_PARITY",
              "inserted", report["new_rows_inserted"],
              "strict_differences", report["strict_payload_difference_count_after_copy"],
              "no_r2 no_restore cutover=false")
        return 2
    print("D1_TARGET_ADDITIVE_ONE_TABLE_VERIFIED new_rows",
          report["new_rows_inserted"],"no_r2 no_restore cutover=false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
