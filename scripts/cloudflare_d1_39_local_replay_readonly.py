#!/usr/bin/env python3
"""Rehearse 39 source-pinned additive DDL objects in EMPTY local SQLite.

Inputs: live SOURCE six-object pinned DDL capture plus 33 pinned repo DDL;
live TARGET schema metadata for exactly two D1s. Never reads application rows
or writes to any Cloudflare account. Prints only sanitized counts/reasons.
"""
import datetime as dt
import hashlib
import json
import os
import pathlib
import re
import sqlite3
import urllib.error
import urllib.request

from cloudflare_d1_final_six_source_ddl import (
    capture as capture_six, query as source_query, SQL_MASTER, DATABASES,
)
from cloudflare_d1_final_39_private_bundle import build_review

TARGET_ACCOUNT = "748a80810f77f447ee476543ef0e5014"
TARGET_IDS = {
    "runner3-core":"477fc6b8-4dec-4e15-afa7-eefa3846fba1",
    "runner3-content-intelligence":"82613659-8d08-455f-b6e7-f8f6e4312e22",
}
EXPECTED_BEFORE = {"runner3-core":1,"runner3-content-intelligence":9}
EXPECTED_GAPS = {"runner3-core":21,"runner3-content-intelligence":18}
OUT = pathlib.Path("migration-out/cloudflare-d1-39-offline-ddl-replay.json")
MAX_BYTES = 350000
ALLOWED_TYPES = ("table","index","view","trigger")
CREATE_PREFIX = re.compile(r"(?is)^CREATE\s+(?:UNIQUE\s+)?(?:TABLE|INDEX|VIEW|TRIGGER)\s+")
SAFE_ID = re.compile(r"[A-Za-z_][A-Za-z0-9_]{0,127}\Z")

class Hold(Exception): pass

def require(ok, code):
    if not ok: raise Hold(code)

def target_api(token, name, kind):
    require(name in TARGET_IDS and kind in ("identity","schema")
            and type(token) is str and len(token) >= 16,"SCOPE_DENIED")
    root = ("https://api.cloudflare.com/client/v4/accounts/" +
            TARGET_ACCOUNT + "/d1/database/" + TARGET_IDS[name])
    path = root if kind == "identity" else root + "/query"
    method = "GET" if kind == "identity" else "POST"
    payload = None if kind == "identity" else json.dumps({"sql":SQL_MASTER}).encode()
    req = urllib.request.Request(path, data=payload, method=method,
        headers={"Authorization":"Bearer "+token,"Accept":"application/json",
                 "Content-Type":"application/json"})
    try:
        with urllib.request.urlopen(req, timeout=25) as res:
            require(res.status == 200,"TARGET_HTTP_NON_200")
            raw = res.read(MAX_BYTES+1)
    except urllib.error.HTTPError as err:
        raise Hold("TARGET_HTTP_"+str(int(err.code))) from None
    except (urllib.error.URLError,OSError,TimeoutError):
        raise Hold("TARGET_NETWORK_FAILURE") from None
    require(len(raw) <= MAX_BYTES,"TARGET_RESPONSE_OVERSIZED")
    try: obj = json.loads(raw)
    except (ValueError,UnicodeError): raise Hold("TARGET_JSON_BAD") from None
    require(type(obj) is dict and obj.get("success") is True,"TARGET_API_BAD")
    if kind == "identity":
        item = obj.get("result")
        require(type(item) is dict and item.get("uuid") == TARGET_IDS[name]
                and item.get("name") == name,"TARGET_DATABASE_CHANGED")
        return item
    return parse_catalog(obj)

def parse_catalog(api_result):
    roots = api_result.get("result")
    require(type(roots) is list and len(roots) == 1 and
            type(roots[0]) is dict and roots[0].get("success") is True and
            type(roots[0].get("results")) is list,"CATALOG_RESPONSE_BAD")
    meta = roots[0].get("meta") or {}
    require(type(meta) is dict and meta.get("rows_written",0) == 0 and
            meta.get("changed_db",False) is False,"CATALOG_WRITE_INDICATED")
    return normalize(roots[0]["results"])

def normalize(rows):
    require(type(rows) is list and len(rows) <= 64,"CATALOG_COUNT_BAD")
    values={}
    for row in rows:
        require(type(row) is dict,"CATALOG_ENTRY_BAD")
        kind,name,ddl=row.get("type"),row.get("name"),row.get("sql")
        require(kind in ALLOWED_TYPES and type(name) is str and
                SAFE_ID.fullmatch(name) is not None and
                type(ddl) is str and 12 <= len(ddl) <= 60000
                and "\x00" not in ddl and CREATE_PREFIX.match(ddl)
                and (kind,name) not in values,"CATALOG_DDL_INVALID")
        values[(kind,name)] = ddl.strip().rstrip(";")
    return values

def local_execute(db, statement):
    sql=statement.strip().rstrip(";")
    require(type(sql) is str and 12 <= len(sql) <= 60000
            and CREATE_PREFIX.match(sql) is not None,
            "NON_ADDITIVE_DDL")
    try:
        db.execute(sql)
    except sqlite3.Error:
        raise Hold("LOCAL_CREATE_FAILED") from None

def split_create_only(script):
    require(type(script) is str and len(script) <= 160000,"CANDIDATE_BAD")
    # Remove whole-line SQL comments; no string interpolations, no sqlite shell.
    body="".join(line for line in script.splitlines(keepends=True)
                 if not line.lstrip().startswith("--"))
    out, pending=[], ""
    for line in body.splitlines(keepends=True):
        pending+=line
        if sqlite3.complete_statement(pending):
            statement=pending.strip().rstrip(";")
            require(bool(CREATE_PREFIX.match(statement)),"UNSAFE_CANDIDATE")
            out.append(statement)
            pending=""
    require(not pending.strip() and len(out) <= 40,"INCOMPLETE_CANDIDATE")
    return out

def order_catalog(values):
    return sorted(values.items(),key=lambda x: (
        {"table":0,"index":1,"view":2,"trigger":3}[x[0][0]],x[0][1]))

def local_catalog(db):
    entries=db.execute("SELECT type,name,sql FROM sqlite_master "
                       "WHERE type IN ('table','index','view','trigger') "
                       "AND name NOT LIKE 'sqlite_%'").fetchall()
    return normalize([{"type":a,"name":b,"sql":c} for a,b,c in entries])

def replay(target_catalog, source_catalog, candidate):
    require(set(target_catalog) <= set(source_catalog),"TARGET_ONLY_OBJECT_HOLD")
    for key in target_catalog:
        require(target_catalog[key].strip() == source_catalog[key].strip(),
                "COMMON_OBJECT_DIFFERENCE_HOLD")
    absent=set(source_catalog)-set(target_catalog)
    source_names=set(absent)
    statements=split_create_only(candidate)
    require(len(statements)==len(absent) and len(absent) <= 25,
            "ADDITIVE_OBJECT_COUNT_DRIFT")
    with sqlite3.connect(":memory:") as db:
        db.enable_load_extension(False)
        db.setlimit(sqlite3.SQLITE_LIMIT_SQL_LENGTH, 90000)
        for (_,ddl) in order_catalog(target_catalog):
            local_execute(db,ddl)
        baseline=local_catalog(db)
        require(set(baseline)==set(target_catalog),
                "TARGET_LOCAL_BASELINE_REPLAY_FAILED")
        before={key:baseline[key] for key in baseline}
        # Candidate statements may include CREATE IF NOT EXISTS. Confirm every
        # statement creates one NEW object; never trust IF NOT EXISTS alone.
        for statement in statements:
            count_before=len(local_catalog(db))
            local_execute(db,statement)
            require(len(local_catalog(db)) == count_before+1,
                    "NOOP_OR_EXTRA_CREATE_HOLD")
        final=local_catalog(db)
        require(set(final)==set(source_catalog) and
                len(final)==len(source_catalog),
                "FINAL_SCHEMA_IDENTITY_MISMATCH")
        require(all(final[k]==before[k] for k in before),
                "PREEXISTING_TARGET_OBJECT_MUTATED")
        # The local SQLite schema DDL must match live SOURCE DDL text exactly.
        # Re-check using the already tested sqlite_master lexical normalization.
        require(all(final[k].strip()==source_catalog[k].strip()
                    for k in source_catalog),
                "SOURCE_DDL_TEXT_MISMATCH")
        fk_count=0
        for key in final:
            if key[0] == "table":
                row=db.execute('PRAGMA foreign_key_list("'+key[1]+'")').fetchall()
                require(len(row) <= 100,"FK_COUNT_TOO_LARGE")
                fk_count+=len({r[0] for r in row})
        # These checks do NOT exercise uniqueness/FKs on populated target rows.
        integrity=db.execute("PRAGMA integrity_check").fetchone()
        require(integrity and integrity[0]=="ok","SCRATCH_INTEGRITY_FAILURE")
    return {"baseline_object_count":len(target_catalog),
            "source_object_count":len(source_catalog),
            "simulated_create_count":len(source_names),
            "source_table_count":sum(k[0]=="table" for k in source_catalog),
            "foreign_key_constraints":fk_count,
            "source_d1_row_parity_proven":False,
            "target_existing_row_constraints_tested":False}

def assess(source_token,target_token,capture=capture_six,
           source_reader=source_query,target_reader=target_api,
           builder=build_review):
    require(type(source_token) is str and len(source_token)>=16 and
            type(target_token) is str and len(target_token)>=16 and
            source_token != target_token,"CREDENTIAL_SCOPE_HOLD")
    captured=capture(source_token)
    # Pinned 6 DDL + pinned 33 local CREATE statements; strictly in-memory.
    scripts=builder(pathlib.Path("."),captured)
    require(set(scripts)==set(TARGET_IDS),"REVIEW_BUNDLE_SCOPE_DRIFT")
    results={}
    for name in TARGET_IDS:
        target_reader(target_token,name,"identity")
        target=target_reader(target_token,name,"schema")
        src=normalize(source_reader(source_token,name,SQL_MASTER))
        require(len(target)==EXPECTED_BEFORE[name] and
                len(src)-len(target)==EXPECTED_GAPS[name],
                "LIVE_D1_CENSUS_CHANGED")
        results[name]=replay(target,src,scripts[name])
        require(results[name]["simulated_create_count"]==EXPECTED_GAPS[name],
                "FINAL_GAP_COUNT_CHANGED")
    return {"status":"LOCAL_39_DDL_REPLAY_ONLY_NO_PRODUCTION_APPLY",
            "checked_utc":dt.datetime.now(dt.timezone.utc).isoformat(),
            "databases":results,
            "simulated_create_total":sum(v["simulated_create_count"]
                                         for v in results.values()),
            "app_data_rows_read":0,"cloudflare_ddl_writes":0,
            "target_d1_writes":0,"source_d1_writes":0,
            "r2_requests":0,"worker_deploys":0,
            "writer_quiescence_proven":False,
            "recovery_bookmark_installed":False,
            "target_data_row_parity_proven":False,"cutover_ready":False}

def main():
    try:
        require(os.getenv("GITHUB_REPOSITORY")=="louisalviss/runner-3"
                and os.getenv("GITHUB_REF")=="refs/heads/main"
                and os.getenv("GITHUB_EVENT_NAME")=="workflow_dispatch"
                and not os.getenv("CLOUDFLARE_TARGET_D1_WRITE_TOKEN"),
                "UNTRUSTED_RUN_CONTEXT")
        result=assess(os.getenv("CLOUDFLARE_API_TOKEN",""),
                      os.getenv("CLOUDFLARE_TARGET_AUDIT_TOKEN_NEW",""))
        OUT.parent.mkdir(exist_ok=True,parents=True)
        OUT.write_text(json.dumps(result,sort_keys=True,indent=2)+"\n")
        print("D1_39_LOCAL_DDL_REPLAY_PASS",
              result["simulated_create_total"],"NO_PRODUCTION_WRITES")
        return 0
    except (Hold, ValueError, TypeError, OSError, sqlite3.Error):
        print("D1_39_LOCAL_DDL_REPLAY_HOLD NO_PRODUCTION_WRITES")
        return 3

if __name__ == "__main__":
    raise SystemExit(main())
