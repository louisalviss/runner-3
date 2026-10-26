#!/usr/bin/env python3
"""Bounded source-only D1 primary-key metadata for exactly 15 absent target tables.

No row reads, no table payload, no source DDL SQL emission, no D1 mutations,
no target API/Worker/R2 interaction. PRAGMA table_xinfo only.
"""
import datetime as dt
import json
import os
import pathlib
import re
import urllib.error
import urllib.request

SOURCE = "7415a87f6bce7884e73ad7cfed5782df"
BASE = "https://api.cloudflare.com/client/v4/accounts/" + SOURCE
EXPECTED = {
    "runner3-content-intelligence": (
        "checkpoints", "link_interest_events", "workflow_state",
    ),
    "runner3-core": (
        "artifact_library_auth", "artifact_library_magic_links",
        "artifact_library_pin_attempts", "checkpoints", "d1_migrations",
        "delivery_permalinks", "ebook_reader_trace_v113", "events",
        "r2_receipts", "typed_kv", "vps_mailbox_jobs", "workflow_state",
    ),
}
OUT = pathlib.Path("migration-out/d1-source-missing-tables-pk-readonly.json")
UUID = re.compile(r"[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}")
SAFE = re.compile(r"[A-Za-z_][A-Za-z0-9_]{0,127}")
MAX_BODY = 350000

class Hold(Exception):
    pass

def require(ok, reason):
    if not ok:
        raise Hold(reason)

def pragma(table):
    require(table in {t for values in EXPECTED.values() for t in values}
            and SAFE.fullmatch(table) is not None, "UNEXPECTED_TABLE")
    return 'PRAGMA table_xinfo("' + table + '")'

def api(token, database=None, sql=None):
    require(isinstance(token, str) and len(token) >= 16, "SOURCE_TOKEN_MISSING")
    if database is None:
        require(sql is None, "QUERY_NOT_ALLOWLISTED")
        method, path, payload = "GET", "/d1/database?per_page=100&page=1", None
    else:
        require(type(database) is str and UUID.fullmatch(database) is not None
                and type(sql) is str and sql in {
                    pragma(table) for values in EXPECTED.values() for table in values
                }, "QUERY_NOT_ALLOWLISTED")
        method, path = "POST", "/d1/database/" + database + "/query"
        payload = json.dumps({"sql":sql}).encode()
    req = urllib.request.Request(
        BASE + path, method=method, data=payload,
        headers={"Authorization":"Bearer " + token, "Accept":"application/json",
                 "Content-Type":"application/json"})
    try:
        with urllib.request.urlopen(req, timeout=22) as res:
            require(res.status == 200, "SOURCE_HTTP_NOT_200")
            raw = res.read(MAX_BODY + 1)
    except urllib.error.HTTPError as exc:
        raise Hold("SOURCE_HTTP_" + str(int(exc.code))) from None
    except (urllib.error.URLError, TimeoutError, OSError):
        raise Hold("SOURCE_NETWORK_ERROR") from None
    require(len(raw) <= MAX_BODY, "RESPONSE_OVERSIZED")
    try:
        obj = json.loads(raw)
    except (ValueError, UnicodeError):
        raise Hold("BAD_JSON") from None
    require(type(obj) is dict and obj.get("success") is True,
            "SOURCE_API_NOT_SUCCESS")
    return obj

def read_result(data):
    root = data.get("result")
    require(type(root) is list and len(root) == 1 and
            type(root[0]) is dict and root[0].get("success") is True and
            type(root[0].get("results")) is list, "BAD_PRAGMA_RESPONSE")
    meta = root[0].get("meta") or {}
    require(type(meta) is dict and meta.get("rows_written", 0) == 0 and
            meta.get("changed_db", False) is False, "NON_READONLY_RESULT")
    return root[0]["results"]

def inspect(token, transport=api):
    require(type(token) is str and len(token) >= 16, "SOURCE_TOKEN_MISSING")
    data = transport(token, None, None)
    arr = data.get("result")
    info = data.get("result_info")
    require(type(arr) is list and len(arr) == 9 and
            type(info) is dict and info.get("page") == 1 and
            info.get("count") == len(arr) and
            info.get("total_count") == len(arr) and
            info.get("total_pages", 1) == 1, "SOURCE_D1_INVENTORY_INCOMPLETE")
    names = {}
    ids = set()
    for db in arr:
        require(type(db) is dict and type(db.get("name")) is str and
                type(db.get("uuid")) is str and UUID.fullmatch(db["uuid"]) is not None
                and db["name"] not in names and db["uuid"] not in ids,
                "BAD_DATABASE_IDENTITY")
        names[db["name"]] = db["uuid"]
        ids.add(db["uuid"])
    require(set(EXPECTED) <= set(names), "REQUIRED_D1_MISSING")
    report = {"status":"SOURCE_ONLY_PK_METADATA_NOT_ROW_PARITY",
              "checked_utc":dt.datetime.now(dt.timezone.utc).isoformat(),
              "tables_scanned":0,"tables_with_declared_pk":0,
              "tables_without_declared_pk":[],
              "per_database":{},
              "sql_allowlist":["PRAGMA table_xinfo"],
              "d1_writes":0,"r2_requests":0,"target_requests":0,
              "row_reads":0,"cutover_ready":False}
    for db_name, table_names in EXPECTED.items():
        entries = []
        for table in table_names:
            rows = read_result(transport(token, names[db_name], pragma(table)))
            require(0 < len(rows) <= 128, "COLUMN_METADATA_INCOMPLETE")
            pks = []
            columns = set()
            for col in rows:
                require(type(col) is dict and type(col.get("name")) is str and
                        0 < len(col["name"]) <= 180 and col["name"] not in columns and
                        type(col.get("pk")) is int and 0 <= col["pk"] <= 32,
                        "BAD_COLUMN_OR_PK_METADATA")
                columns.add(col["name"])
                if col["pk"] > 0:
                    pks.append(col["pk"])
            require(len(pks) == len(set(pks)) and
                    sorted(pks) == list(range(1,len(pks)+1)),
                    "BAD_PK_ORDINALS")
            entry = {"table":table,"column_count":len(rows),
                     "declared_pk":bool(pks),"pk_column_count":len(pks)}
            entries.append(entry)
            report["tables_scanned"] += 1
            if pks:
                report["tables_with_declared_pk"] += 1
            else:
                report["tables_without_declared_pk"].append(
                    {"database":db_name,"table":table})
        report["per_database"][db_name] = entries
    require(report["tables_scanned"] == 15, "UNEXPECTED_SCAN_COUNT")
    return report

def main():
    try:
        require(os.getenv("GITHUB_REPOSITORY") == "louisalviss/runner-3"
                and os.getenv("GITHUB_REF") == "refs/heads/main"
                and os.getenv("GITHUB_EVENT_NAME") == "workflow_dispatch"
                and not os.getenv("CLOUDFLARE_TARGET_D1_WRITE_TOKEN"),
                "UNTRUSTED_JOB_CONTEXT")
        report = inspect(os.getenv("CLOUDFLARE_API_TOKEN", ""))
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
        print("SOURCE_ONLY_D1_PK_METADATA_PASS tables",
              report["tables_scanned"],"with_pk",
              report["tables_with_declared_pk"],"NO_WRITES")
        return 0
    except (Hold, ValueError, TypeError, OSError):
        print("SOURCE_ONLY_D1_PK_METADATA_HOLD NO_WRITES")
        return 3

if __name__ == "__main__":
    raise SystemExit(main())
