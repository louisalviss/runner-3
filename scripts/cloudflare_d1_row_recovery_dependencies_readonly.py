#!/usr/bin/env python3
"""Manual target-only D1 dependency footprint before any row-safe recovery design.

READ-ONLY Cloudflare D1 queries; no INSERT, DELETE, UPDATE, restore, R2,
row keys, row values, source account, or ciphertext/bookmark access.
This is a schema diagnostic, NOT approval to reverse any D1 write.
"""
import json
import os
import pathlib
import re
import sqlite3
import urllib.error
import urllib.request

TARGET_ACCOUNT = "748a80810f77f447ee476543ef0e5014"
TARGET_UUID = "82613659-8d08-455f-b6e7-f8f6e4312e22"
TABLE = "recommendation_runs"
DB = "runner3-content-intelligence"
ENDPOINT = ("https://api.cloudflare.com/client/v4/accounts/" + TARGET_ACCOUNT +
            "/d1/database/" + TARGET_UUID + "/query")
META_SQL = ("SELECT type,name,tbl_name,sql FROM sqlite_master "
            "WHERE type IN ('table','trigger','view') "
            "AND name NOT LIKE 'sqlite_%' ORDER BY type,name LIMIT 101")
COLUMN_SQL = 'PRAGMA table_xinfo("recommendation_runs")'
MAX_SQL_RESPONSE = 400_000
MAX_OBJECTS = 100
MAX_TABLES = 80
NAME = re.compile(r"[A-Za-z_][A-Za-z_0-9]{0,127}\Z")
OUT = pathlib.Path("migration-out/d1-row-recovery-dependency-footprint.json")

class Hold(Exception):
    pass

def ensure(condition, code):
    if not condition:
        raise Hold(code)

def allowed_sql(sql):
    # Only these two proven read-only D1 SQL shapes. In this account,
    # PRAGMA foreign_key_list returned HTTP 400 through the REST API.
    return sql in (META_SQL, COLUMN_SQL)

def query(token, sql, opener=urllib.request.urlopen):
    ensure(type(token) is str and len(token) >= 16, "MISSING_AUDIT_CREDENTIAL")
    ensure(allowed_sql(sql), "NON_READONLY_SQL_BLOCKED")
    req = urllib.request.Request(ENDPOINT,
        data=json.dumps({"sql": sql}).encode(), method="POST", headers={
          "Authorization": "Bearer " + token, "Content-Type": "application/json",
          "Accept": "application/json",
        })
    ensure(req.get_method() == "POST" and b'"sql"' in req.data,
           "QUERY_CONTRACT_INVALID")
    try:
        with opener(req,timeout=20) as response:
            ensure(response.status == 200, "CLOUDFLARE_HTTP_FAILURE")
            raw = response.read(MAX_SQL_RESPONSE + 1)
    except urllib.error.HTTPError as exc:
        # The original workflow suppressed the only information needed to
        # distinguish unsupported read-only SQL from a permissions failure.
        # Restrict reporting to Cloudflare HTTP status and static query type.
        kind = ("SCHEMA" if sql == META_SQL else
                "COLUMNS" if sql == COLUMN_SQL else "FOREIGN_KEY")
        raise Hold("CLOUDFLARE_HTTP_" + str(int(exc.code)) + "_" + kind) from None
    except (urllib.error.URLError, OSError, TimeoutError):
        kind = ("SCHEMA" if sql == META_SQL else
                "COLUMNS" if sql == COLUMN_SQL else "FOREIGN_KEY")
        raise Hold("CLOUDFLARE_NETWORK_" + kind) from None
    ensure(len(raw) <= MAX_SQL_RESPONSE, "D1_READ_TOO_LARGE")
    try:
        d = json.loads(raw)
    except (UnicodeError, ValueError):
        raise Hold("D1_INVALID_RESPONSE") from None
    ensure(type(d) is dict and d.get("success") is True, "D1_READ_UNSUCCESSFUL")
    results = d.get("result")
    ensure(type(results) is list and len(results) == 1 and
           type(results[0]) is dict and results[0].get("success") is True and
           type(results[0].get("results")) is list,
           "D1_RESULTS_MALFORMED")
    meta = results[0].get("meta") or {}
    ensure(type(meta) is dict and meta.get("rows_written", 0) == 0 and
           meta.get("changed_db", False) is False, "READ_ONLY_METADATA_FAILURE")
    return results[0]["results"]

def assess(token, reader=query):
    entries = reader(token, META_SQL)
    ensure(type(entries) is list and len(entries) <= MAX_OBJECTS, "SCHEMA_TOO_LARGE")
    ensure(all(type(x) is dict and
               x.get("type") in ("table","trigger","view") and
               type(x.get("name")) is str and
               NAME.fullmatch(x["name"]) is not None and
               type(x.get("tbl_name")) is str and
               type(x.get("sql")) is str
               for x in entries), "UNKNOWN_SCHEMA_OBJECT")
    ensure(len({x["name"] for x in entries}) == len(entries), "DUPLICATE_SCHEMA_OBJECT")
    tables = [x for x in entries if x["type"] == "table"]
    ensure(0 < len(tables) <= MAX_TABLES and any(x["name"] == TABLE for x in tables),
           "TARGET_TABLE_OR_SCHEMA_NOT_FOUND")
    columns = reader(token, COLUMN_SQL)
    ensure(type(columns) is list and len(columns) == 8 and
           [x.get("name") for x in sorted(columns, key=lambda c:c.get("cid",-1))] ==
           ["render_id","source_scope","item_count","recommended_count",
            "exploration_ratio","model_version","created_at","metadata_json"] and
           any(x.get("name") == "render_id" and x.get("pk") == 1 for x in columns),
           "TARGET_COLUMN_PK_MISMATCH")
    # The D1 REST endpoint returned HTTP 400 for PRAGMA foreign_key_list,
    # despite Cloudflare documenting the SQL statement. Do not guess at
    # foreign-key counts or loosen write/restore gates. A fail-closed
    # inspection of CREATE TABLE statements is sufficient to identify whether
    # additional FK review is required without executing a second SQL query.
    possible_fk_tables = 0
    for item in tables:
        ddl = item["sql"].strip()
        ensure(ddl.upper().startswith("CREATE TABLE "),
               "UNSUPPORTED_TABLE_DDL_REQUIRE_REVIEW")
        # SQLite CREATE TABLE FK constraints must contain REFERENCES, either
        # column-level or table-level. A mention in comments/strings will
        # conservatively produce a false-positive HOLD, never a false PASS.
        if re.search(r"\bREFERENCES\b|\bFOREIGN\s+KEY\b", ddl, re.I):
            possible_fk_tables += 1
    # Reconstruct only the metadata CREATE TABLE statements inside SQLite
    # :memory:. Each execute() accepts exactly one statement. This never
    # writes to Cloudflare, and never imports target row content or scripts.
    # An unsupported/ambiguous DDL fails closed.
    inbound = outbound = sqlite_fk_tables = 0
    try:
        with sqlite3.connect(":memory:") as scratch:
            scratch.enable_load_extension(False)
            scratch.setlimit(sqlite3.SQLITE_LIMIT_SQL_LENGTH, 50000)
            for item in tables:
                ddl = item["sql"].strip()
                ensure(len(ddl) <= 40_000 and ";" not in ddl and
                       " AS SELECT" not in ddl.upper(),
                       "UNSAFE_OR_OVERSIZED_TABLE_DDL")
                scratch.execute(ddl)
            for item in tables:
                # Item names already passed strict identifier validation.
                rows = scratch.execute(
                    'PRAGMA foreign_key_list("' + item["name"] + '")').fetchall()
                ensure(len(rows) <= 300, "TOO_MANY_LOCAL_FOREIGN_KEYS")
                by_id = {}
                for fk in rows:
                    ensure(len(fk) >= 3 and type(fk[0]) is int and
                           type(fk[2]) is str, "INVALID_LOCAL_FK_RESULT")
                    by_id[fk[0]] = fk[2]
                if by_id:
                    sqlite_fk_tables += 1
                if item["name"].casefold() == TABLE.casefold():
                    outbound += len(by_id)
                else:
                    inbound += sum(ref.casefold() == TABLE.casefold()
                                   for ref in by_id.values())
    except (sqlite3.Error, AttributeError, ValueError, TypeError):
        raise Hold("LOCAL_DDL_REPLAY_FAILED_HOLD") from None

    triggers = [x for x in entries if x["type"] == "trigger"]
    related_views = sum(TABLE.lower() in x["sql"].lower()
                        for x in entries if x["type"] == "view")
    # Fail closed on DDL text markers not understood by local SQLite.
    markers_match = possible_fk_tables == sqlite_fk_tables
    recovery_schema_clear = (markers_match and inbound == 0 and outbound == 0
                             and not triggers and not related_views)
    return {
        "format": "target-d1-recommendation-runs-row-recovery-dependency-audit-v1",
        "database": DB, "table": TABLE,
        "schema_object_count": len(entries),
        "tables_checked_for_foreign_keys": len(tables),
        "inbound_foreign_key_count": inbound,
        "outbound_foreign_key_count": outbound,
        "possible_foreign_key_table_count": possible_fk_tables,
        "local_sqlite_foreign_key_table_count": sqlite_fk_tables,
        "ddl_fk_marker_and_local_sqlite_agree": markers_match,
        "foreign_key_detection_method": "isolated_in_memory_sqlite_ddl_replay",
        "exact_foreign_key_relationships_verified": markers_match,
        "trigger_count_any_table": len(triggers),
        "views_referencing_table_count": related_views,
        "target_pk_columns_verified": True,
        "schema_local_dependency_clear": recovery_schema_clear,
        "independent_writer_quiescence_verified": False,
        "row_safe_recovery_rehearsed": False,
        "bookmark_escrow_installed": False,
        "cloudflare_write_requests": 0, "restore_requests": 0,
        "r2_requests": 0, "cutover_ready": False,
        "status": ("SCHEMA_FOOTPRINT_CLEAR_BUT_ROLLBACK_NOT_READY" if recovery_schema_clear
                   else "SCHEMA_DEPENDENCIES_REQUIRE_MANUAL_REVIEW_HOLD"),
    }

def main():
    try:
        ensure(os.environ.get("GITHUB_REPOSITORY") == "louisalviss/runner-3"
               and os.environ.get("GITHUB_REF") == "refs/heads/main"
               and os.environ.get("GITHUB_EVENT_NAME") == "workflow_dispatch",
               "UNTRUSTED_WORKFLOW")
        ensure(not os.environ.get("CLOUDFLARE_TARGET_D1_WRITE_TOKEN"),
               "WRITE_CREDENTIAL_NOT_ALLOWED")
        r = assess(os.environ.get("CLOUDFLARE_TARGET_AUDIT_TOKEN", ""))
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(json.dumps(r,sort_keys=True,indent=2)+"\n")
        print("D1_RECOVERY_SCHEMA_AUDIT",r["status"],
              "tables",r["tables_checked_for_foreign_keys"],
              "inbound_fk",r["inbound_foreign_key_count"],
              "outbound_fk",r["outbound_foreign_key_count"],
              "fk_ddl_agreement",r["ddl_fk_marker_and_local_sqlite_agree"],
              "triggers",r["trigger_count_any_table"],
              "NO_WRITES NO_RESTORE ROLLBACK_NOT_READY")
        return 0
    except Hold as exc:
        # Hold codes are static, internally authored labels only. Never
        # print Cloudflare responses, SQL contents, table names or secrets.
        print("D1_RECOVERY_SCHEMA_AUDIT_HOLD", str(exc), "NO_WRITES")
        return 3
    except (OSError, ValueError, TypeError):
        print("D1_RECOVERY_SCHEMA_AUDIT_HOLD INTERNAL_FAILURE NO_WRITES")
        return 3

if __name__ == "__main__":
    raise SystemExit(main())
