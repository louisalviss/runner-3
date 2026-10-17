#!/usr/bin/env python3
"""Bounded, read-only D1 schema/primary-key manifest for the two fixed accounts.

No row payload, COUNT(*), export, import, D1 mutation, Worker or R2 request.
No fallback to other account tokens. This is audit evidence, NOT row parity.
"""
import argparse
import datetime as dt
import hashlib
import json
import os
import pathlib
import re
import sys
import urllib.error
import urllib.request

SOURCE = "7415a87f6bce7884e73ad7cfed5782df"
TARGET = "748a80810f77f447ee476543ef0e5014"
NAMES = ("clm-copilot-calibration", "clm-copilot-v1", "louis-task-context",
         "personal-library", "runner3-content-intelligence", "runner3-core",
         "runner3-opportunity-radar", "runner3-rss", "volamidle-rogue-data")
EXTRA_TARGET_REVIEW = "louis-context-index"
NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
MAX_DATABASES = 10
MAX_SCHEMA_OBJECTS = 256
MAX_TABLES_PER_DB = 80

class Blocked(Exception):
    pass

def ensure(ok, reason):
    if not ok:
        raise Blocked(reason)

def api(account, token, method, path, sql=None):
    ensure(method == "GET" or (method == "POST" and
           path.endswith("/query") and isinstance(sql, str) and
           (sql.startswith("SELECT name,type,sql FROM sqlite_master ") or
            sql.startswith('PRAGMA table_xinfo("'))), "NON_READ_ONLY_REQUEST")
    url = "https://api.cloudflare.com/client/v4/accounts/" + account + path
    req = urllib.request.Request(
        url, headers={"Authorization": "Bearer " + token,
                      "Content-Type": "application/json"},
        method=method,
        data=json.dumps({"sql": sql}).encode() if sql is not None else None)
    try:
        with urllib.request.urlopen(req, timeout=25) as response:
            ensure(response.status == 200, "HTTP_NON_200")
            body = response.read(1500001)
            ensure(len(body) <= 1500000, "RESPONSE_TOO_LARGE")
            result = json.loads(body)
    except urllib.error.HTTPError as e:
        raise Blocked("HTTP_" + str(e.code)) from None
    except (urllib.error.URLError, TimeoutError, ValueError):
        raise Blocked("NETWORK_OR_BAD_JSON") from None
    ensure(isinstance(result, dict) and result.get("success") is True,
           "API_NOT_SUCCESS")
    return result

def get_rows(response):
    result = response.get("result")
    ensure(isinstance(result, list) and len(result) == 1 and
           isinstance(result[0], dict) and
           result[0].get("success") is True and
           isinstance(result[0].get("results"), list), "BAD_QUERY_RESULT")
    meta = result[0].get("meta") or {}
    ensure(not meta.get("changed_db") and
           int(meta.get("rows_written") or 0) == 0,
           "UNEXPECTED_DATABASE_MUTATION")
    return result[0]["results"]

def inventory(role, token, transport=api):
    ensure(role in ("source", "target"), "BAD_ROLE")
    account = SOURCE if role == "source" else TARGET
    ensure(isinstance(token, str) and len(token) >= 16, "TOKEN_UNAVAILABLE")
    response = transport(account, token, "GET",
                         "/d1/database?page=1&per_page=100")
    databases = response.get("result")
    info = response.get("result_info")
    ensure(isinstance(databases, list) and len(databases) <= MAX_DATABASES,
           "DATABASE_LIMIT_OR_FORMAT")
    ensure(isinstance(info, dict) and
           type(info.get("total_count")) is int and
           info["total_count"] == len(databases) and
           info.get("page") == 1, "INCOMPLETE_D1_LIST")
    mapping = {}
    uuids = set()
    for item in databases:
        ensure(isinstance(item, dict), "BAD_D1_ITEM")
        name, uuid = item.get("name"), item.get("uuid")
        ensure(isinstance(name, str) and isinstance(uuid, str) and
               name not in mapping and uuid not in uuids and
               re.fullmatch(r"[0-9a-f-]{36}", uuid), "DUPLICATE_OR_BAD_D1_ID")
        mapping[name] = uuid
        uuids.add(uuid)
    if role == "source":
        ensure(set(NAMES) <= set(mapping), "MISSING_SOURCE_D1")
    report = {
        "evidence_class": "READ_ONLY_SCHEMA_ONLY_NOT_ROW_PARITY",
        "role": role, "account_id": account,
        "checked_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "database_names": sorted(mapping),
        "missing_required_names": sorted(set(NAMES) - set(mapping)),
        "historical_target_only_name_present": EXTRA_TARGET_REVIEW in mapping,
        "database_schemas": {},
        "row_key_content_parity_verified": False,
        "cutover_ready": False, "source_delete_allowed": False,
        "r2_requests": 0,
    }
    sql = ("SELECT name,type,sql FROM sqlite_master "
           "WHERE type IN ('table','view','index','trigger') "
           "AND name NOT LIKE 'sqlite_%' ORDER BY type,name")
    for db_name in NAMES + ((EXTRA_TARGET_REVIEW,) if role == "target" else ()):
        if db_name not in mapping:
            continue
        path = "/d1/database/" + mapping[db_name] + "/query"
        objects = get_rows(transport(account, token, "POST", path, sql))
        ensure(len(objects) <= MAX_SCHEMA_OBJECTS, "TOO_MANY_SCHEMA_OBJECTS")
        schema = []
        seen = set()
        for entry in objects:
            ensure(isinstance(entry, dict), "BAD_SCHEMA_OBJECT")
            object_name, typ, definition = (entry.get("name"),
                                             entry.get("type"),
                                             entry.get("sql"))
            ensure(isinstance(object_name, str) and NAME.fullmatch(object_name)
                   and object_name not in seen and
                   typ in ("table", "view", "index", "trigger"),
                   "UNSUPPORTED_SCHEMA_OBJECT")
            seen.add(object_name)
            schema.append({"name": object_name, "kind": typ,
                           "ddl_sha256": hashlib.sha256(
                               (definition or "").encode("utf-8")).hexdigest()})
        tables = [x for x in schema if x["kind"] == "table"]
        ensure(len(tables) <= MAX_TABLES_PER_DB, "TOO_MANY_TABLES")
        for table in tables:
            name = table["name"]
            cols = get_rows(transport(account, token, "POST", path,
                            'PRAGMA table_xinfo("' + name + '")'))
            ensure(len(cols) <= 100 and all(isinstance(x, dict) for x in cols),
                   "BAD_COLUMN_METADATA")
            pk_items = []
            for col in cols:
                ensure(isinstance(col.get("name"), str) and
                       isinstance(col.get("pk"), int), "BAD_PK_FIELD")
                if col["pk"] > 0:
                    ensure(NAME.fullmatch(col["name"]) is not None,
                           "BAD_PRIMARY_KEY_METADATA")
                    pk_items.append((col["pk"], col["name"]))
            pk_items.sort()
            ensure(len({rank for rank, _ in pk_items}) == len(pk_items),
                   "DUPLICATE_PK_ORDINAL")
            table["pk_columns"] = [v for _,v in pk_items]
            table["declared_pk_present"] = bool(pk_items)
        report["database_schemas"][db_name] = {
            "schema_objects": schema, "schema_object_count": len(schema),
            "table_count": len(tables),
            "tables_without_declared_pk": [
                t["name"] for t in tables if not t["declared_pk_present"]],
        }
    return report

def self_test():
    def fake(account, token, method, path, sql=None):
        if method == "GET":
            return {"success": True, "result_info": {"page": 1,
                    "total_count": len(NAMES)},
                    "result": [{"name": n,
                    "uuid": "00000000-0000-0000-0000-" + format(i+1, "012x")}
                    for i,n in enumerate(NAMES)]}
        if sql.startswith("SELECT"):
            return {"success": True, "result": [{
                "success": True, "meta": {"rows_written": 0},
                "results": [{"name": "checkpoints", "type": "table",
                             "sql": "CREATE TABLE checkpoints (id INT PRIMARY KEY)"}]}]}
        return {"success": True, "result": [{"success": True,
                "meta": {"rows_written": 0},
                "results": [{"name": "id", "pk": 1}]}]}
    a = inventory("source", "dummy_token_for_offline", fake)
    b = inventory("target", "dummy_token_for_offline", fake)
    assert len(a["database_schemas"]) == len(NAMES) == 9
    assert all(x["table_count"] == 1
               for x in a["database_schemas"].values())
    assert a["cutover_ready"] is False and b["cutover_ready"] is False
    assert not a["missing_required_names"] and not b["missing_required_names"]
    try:
        inventory("target", "", fake)
        raise AssertionError("empty token accepted")
    except Blocked as e:
        assert str(e) == "TOKEN_UNAVAILABLE"
    # Reject incomplete target pagination without fetching anything beyond page 1.
    def incomplete(account, token, method, path, sql=None):
        d = fake(account, token, method, path, sql)
        if method == "GET":
            d["result_info"]["total_count"] += 1
        return d
    try:
        inventory("target", "dummy_token_for_offline", incomplete)
        raise AssertionError("truncated target list accepted")
    except Blocked as e:
        assert str(e) == "INCOMPLETE_D1_LIST"
    # Source census cannot silently skip one of nine authorities.
    def missing_source(account, token, method, path, sql=None):
        d = fake(account, token, method, path, sql)
        if method == "GET":
            d["result"].pop()
            d["result_info"]["total_count"] -= 1
        return d
    try:
        inventory("source", "dummy_token_for_offline", missing_source)
        raise AssertionError("source missing one D1 was accepted")
    except Blocked as e:
        assert str(e) == "MISSING_SOURCE_D1"
    # Historic destination-only legacy context index gets schema audit too.
    def extra_target(account, token, method, path, sql=None):
        d = fake(account, token, method, path, sql)
        if method == "GET":
            d["result"].append({"name": EXTRA_TARGET_REVIEW,
                "uuid": "00000000-0000-0000-0000-000000000010"})
            d["result_info"]["total_count"] += 1
        return d
    extra = inventory("target", "dummy_token_for_offline", extra_target)
    assert EXTRA_TARGET_REVIEW in extra["database_schemas"]
    print("OFFLINE_D1_NINE_SCHEMA_CONTRACT: PASS (8 checks, 0 external requests)")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--role", choices=("source", "target"))
    parser.add_argument("--self-test", action="store_true")
    options = parser.parse_args()
    if options.self_test:
        self_test()
        return 0
    ensure(options.role is not None, "ROLE_REQUIRED")
    if options.role == "source":
        ensure(os.environ.get("CLOUDFLARE_ACCOUNT_ID") == SOURCE,
               "SOURCE_ACCOUNT_ID_MISMATCH")
        token = os.environ.get("CLOUDFLARE_API_TOKEN", "")
    else:
        token = os.environ.get("CLOUDFLARE_TARGET_AUDIT_TOKEN", "")
    result = inventory(options.role, token)
    path = pathlib.Path("migration-out") / (
        "d1-schema-" + options.role + "-readonly.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, sort_keys=True, indent=2) + "\n")
    print("D1_SCHEMA_READ_ONLY_DONE", options.role,
          "databases=" + str(len(result["database_schemas"])))
    return 0

if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Blocked as err:
        print("D1_SCHEMA_AUDIT_BLOCKED", str(err))
        raise SystemExit(3) from None
