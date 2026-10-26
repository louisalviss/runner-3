#!/usr/bin/env python3
"""Bounded source D1 table existence probe: SELECT constant 1 LIMIT 1.

For exact 15 target-absent tables ONLY. No row values, counts or DDL,
no writes or R2, no target operations. Output: boolean nonempty table status.
"""
import datetime as dt
import json
import os
import pathlib
import re
import urllib.error
import urllib.request
from cloudflare_d1_source_missing_table_pk_readonly import EXPECTED

SOURCE="7415a87f6bce7884e73ad7cfed5782df"
BASE="https://api.cloudflare.com/client/v4/accounts/"+SOURCE
OUTPUT=pathlib.Path("migration-out/d1-15-source-table-existence-readonly.json")
UUID=re.compile(r"[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}")
MAX_RESPONSE=20000
MAX_ROW_READS=100

class Hold(Exception): pass
def require(value,reason):
    if not value:raise Hold(reason)

def table_sql(name):
    require(type(name) is str and name in {
        n for tables in EXPECTED.values() for n in tables}, "TABLE_NOT_ALLOWLISTED")
    return 'SELECT 1 AS present FROM "'+name+'" LIMIT 1'

def request(token,path,payload=None):
    require(type(token) is str and len(token)>=16,"MISSING_SOURCE_AUDIT_TOKEN")
    inventory=path=="/d1/database?per_page=100&page=1" and payload is None
    bounded_query=bool(re.fullmatch(r"/d1/database/[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}/query",path))
    if not inventory:
        require(bounded_query and type(payload) is dict and
                set(payload)=={"sql"} and payload["sql"] in {
                    table_sql(n) for tables in EXPECTED.values() for n in tables},
                "NON_ALLOWLISTED_API_CALL")
    req=urllib.request.Request(BASE+path, data=None if inventory else json.dumps(payload).encode(),
        method="GET" if inventory else "POST",
        headers={"Authorization":"Bearer "+token,"Accept":"application/json",
                 "Content-Type":"application/json"})
    try:
        with urllib.request.urlopen(req,timeout=20) as response:
            require(response.status==200,"SOURCE_HTTP_BAD")
            raw=response.read(MAX_RESPONSE+1)
    except urllib.error.HTTPError as exc:
        raise Hold("SOURCE_HTTP_"+str(int(exc.code))) from None
    except (urllib.error.URLError,OSError,TimeoutError):
        raise Hold("SOURCE_NETWORK_UNAVAILABLE") from None
    require(len(raw)<=MAX_RESPONSE,"SOURCE_RESPONSE_OVERSIZED")
    try:doc=json.loads(raw)
    except (ValueError,UnicodeError):raise Hold("SOURCE_JSON_INVALID") from None
    require(type(doc) is dict and doc.get("success") is True,
            "SOURCE_QUERY_UNSUCCESSFUL")
    return doc

def run(token,api=request):
    require(type(token) is str and len(token)>=16,"SOURCE_TOKEN_MISSING")
    data=api(token,"/d1/database?per_page=100&page=1")
    items=data.get("result"); info=data.get("result_info")
    require(type(items) is list and len(items)==9 and type(info) is dict and
            info.get("page")==1 and info.get("count")==9 and
            info.get("total_count")==9 and info.get("total_pages",1)==1,
            "SOURCE_LIST_INCOMPLETE")
    ids={}
    for obj in items:
        require(type(obj) is dict and type(obj.get("name")) is str and
                type(obj.get("uuid")) is str and UUID.fullmatch(obj["uuid"]) is not None
                and obj["name"] not in ids,"INVALID_SOURCE_D1")
        ids[obj["name"]]=obj["uuid"]
    require(set(EXPECTED) <= set(ids),"REQUIRED_SOURCE_D1_MISSING")
    result={"status":"SOURCE_TABLE_BOUNDED_NONEMPTY_AUDIT_NOT_ROW_PARITY",
            "checked_utc":dt.datetime.now(dt.timezone.utc).isoformat(),
            "query_budget":15,"queries_executed":0,"nonempty_tables":0,
            "empty_tables":0,"per_database":{},"source_d1_writes":0,
            "target_d1_requests":0,"application_row_values_read":0,
            "r2_requests":0,"cutover_ready":False}
    for db_name,tables in EXPECTED.items():
        flags={}
        for table in tables:
            result["queries_executed"]+=1
            response=api(token,"/d1/database/"+ids[db_name]+"/query",
                         {"sql":table_sql(table)})
            roots=response.get("result")
            require(type(roots) is list and len(roots)==1 and
                    type(roots[0]) is dict and roots[0].get("success") is True and
                    type(roots[0].get("results")) is list,"BAD_QUERY_RESULT")
            entry=roots[0]
            meta=entry.get("meta") or {}
            require(type(meta) is dict and
                    meta.get("rows_written",0)==0 and
                    meta.get("changed_db",False) is False,"WRITE_INDICATED")
            n=meta.get("rows_read",None)
            require(n is None or (type(n) is int and 0<=n<=MAX_ROW_READS),
                    "UNEXPECTED_ROW_READ_COST")
            rows=entry["results"]
            require(len(rows)<=1 and all(type(row) is dict and
                    set(row)=={"present"} and row["present"]==1
                    for row in rows),"NONCONSTANT_ROW_RESULT")
            flags[table]={"has_any_row":len(rows)==1}
            if rows:result["nonempty_tables"]+=1
            else:result["empty_tables"]+=1
        result["per_database"][db_name]=flags
    require(result["queries_executed"]==15 and
            result["empty_tables"]+result["nonempty_tables"]==15,
            "TABLE_PROBE_COUNT_MISMATCH")
    return result

def main():
    try:
        require(os.getenv("GITHUB_REPOSITORY")=="louisalviss/runner-3" and
                os.getenv("GITHUB_REF")=="refs/heads/main" and
                os.getenv("GITHUB_EVENT_NAME")=="workflow_dispatch" and
                not os.getenv("CLOUDFLARE_TARGET_D1_WRITE_TOKEN"),
                "UNTRUSTED_WORKFLOW_CONTEXT")
        outcome=run(os.getenv("CLOUDFLARE_API_TOKEN",""))
        OUTPUT.parent.mkdir(parents=True,exist_ok=True)
        OUTPUT.write_text(json.dumps(outcome,indent=2,sort_keys=True)+"\n")
        print("SOURCE_15_TABLE_NONEMPTY_AUDIT_PASS",outcome["queries_executed"],
              "nonempty",outcome["nonempty_tables"],
              "empty",outcome["empty_tables"],"NO_WRITES")
        return 0
    except (Hold,TypeError,ValueError,OSError):
        print("SOURCE_15_TABLE_NONEMPTY_AUDIT_HOLD NO_WRITES")
        return 3
if __name__=="__main__":
    raise SystemExit(main())
