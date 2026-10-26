#!/usr/bin/env python3
"""Manual account-scoped D1 schema comparator. NO D1 mutations, no R2, no row data.

All schema definitions stay in process memory; only per-database counts leave.
This is NOT data, key, delete/tombstone or cutover parity verification.
"""
import json
import os
import pathlib
import urllib.error
import urllib.request

SOURCE="7415a87f6bce7884e73ad7cfed5782df"
TARGET="748a80810f77f447ee476543ef0e5014"
EXPECTED_NAMES=frozenset((
    "runner3-core", "runner3-opportunity-radar", "personal-library",
    "louis-task-context", "runner3-content-intelligence", "runner3-rss",
    "volamidle-rogue-data", "clm-copilot-v1", "clm-copilot-calibration",
    "louis-context-index",
))
MAX_D1=12
MAX_OBJECTS=256
MAX_BODY=1_200_000
SCHEMA_SQL=("SELECT type,name,sql FROM sqlite_master WHERE "
            "type IN ('table','index','trigger','view') "
            "AND name NOT LIKE 'sqlite_%' ORDER BY type,name")
OUTPUT=pathlib.Path("migration-out/d1-cross-account-schema-parity-readonly.json")

class Hold(Exception): pass

def require(ok,code):
    if not ok: raise Hold(code)

def api(token,account,database=None):
    require(account in (SOURCE,TARGET), "ACCOUNT_NOT_ALLOWLISTED")
    require(type(token) is str and len(token)>=16, "MISSING_READ_CREDENTIAL")
    import re
    if database is not None:
        require(type(database) is str and re.fullmatch(
            r"[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}",database),
            "BAD_DATABASE_ID")
    suffix=("/d1/database?page=1&per_page=100" if database is None
            else "/d1/database/"+database+"/query")
    payload=None if database is None else json.dumps({"sql":SCHEMA_SQL}).encode()
    req=urllib.request.Request(
        "https://api.cloudflare.com/client/v4/accounts/"+account+suffix,
        headers={"Authorization":"Bearer "+token,"Accept":"application/json",
                 "Content-Type":"application/json"},
        data=payload, method="GET" if database is None else "POST")
    try:
        with urllib.request.urlopen(req,timeout=25) as r:
            require(r.status==200,"CLOUDFLARE_HTTP_NON_200")
            raw=r.read(MAX_BODY+1)
    except urllib.error.HTTPError as e:
        raise Hold("CLOUDFLARE_HTTP_"+str(int(e.code))) from None
    except (urllib.error.URLError,OSError,TimeoutError):
        raise Hold("CLOUDFLARE_NETWORK_ERROR") from None
    require(len(raw)<=MAX_BODY, "API_RESPONSE_OVERSIZED")
    try: d=json.loads(raw)
    except (ValueError,UnicodeError): raise Hold("BAD_API_JSON") from None
    require(type(d) is dict and d.get("success") is True,"API_NOT_SUCCESS")
    return d

def inventory(token,account,transport=api):
    d=transport(token,account,None)
    rows=d.get("result")
    require(type(rows) is list and len(rows)<=MAX_D1,"BAD_D1_INVENTORY")
    info=d.get("result_info")
    require(type(info) is dict and info.get("page")==1 and
            info.get("total_count")==len(rows) and info.get("count")==len(rows)
            and info.get("total_pages",1)==1, "D1_INVENTORY_INCOMPLETE")
    result={}
    import re
    for r in rows:
        require(type(r) is dict and type(r.get("name")) is str and
                r["name"] in EXPECTED_NAMES and
                type(r.get("uuid")) is str and
                re.fullmatch(r"[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}",r["uuid"])
                and r["name"] not in result, "UNEXPECTED_D1_IDENTITY")
        result[r["name"]]=r["uuid"]
    return result

def schema(token,account,uid,transport=api):
    d=transport(token,account,uid)
    roots=d.get("result")
    require(type(roots) is list and len(roots)==1 and
            type(roots[0]) is dict and roots[0].get("success") is True
            and type(roots[0].get("results")) is list,"BAD_SCHEMA_QUERY")
    item=roots[0]
    meta=item.get("meta") or {}
    require(type(meta) is dict and
            meta.get("rows_written",0)==0 and
            meta.get("changed_db",False) is False, "NON_READ_ONLY_QUERY")
    objs=item["results"]
    require(len(objs)<=MAX_OBJECTS,"TOO_MANY_SCHEMA_OBJECTS")
    parsed={}
    for obj in objs:
        require(type(obj) is dict and
                obj.get("type") in ("table","index","trigger","view")
                and type(obj.get("name")) is str and
                0<len(obj["name"])<=256 and
                (obj.get("sql") is None or type(obj.get("sql")) is str),
                "BAD_SCHEMA_OBJECT")
    # Some automatically generated schema indexes have null SQL. These are
    # not in the retrieved schema because sqlite_ indexes are excluded.
    for obj in objs:
        require(type(obj.get("sql")) is str and
                len(obj["sql"])<=100_000,"UNSUPPORTED_SCHEMA_DEFINITION")
        key=(obj["type"],obj["name"])
        require(key not in parsed,"DUPLICATE_SCHEMA_OBJECT")
        parsed[key]=obj["sql"]
    return parsed

def compare(source_token,target_token,transport=api):
    require(source_token!=target_token,"SEPARATE_CREDENTIALS_REQUIRED")
    src=inventory(source_token,SOURCE,transport)
    dst=inventory(target_token,TARGET,transport)
    common=sorted(src.keys() & dst.keys())
    require(len(common)>0 and len(common)<=MAX_D1,"NO_SHARED_D1")
    output=[]
    for name in common:
        a=schema(source_token,SOURCE,src[name],transport)
        b=schema(target_token,TARGET,dst[name],transport)
        sa,sb=set(a),set(b)
        changed=sum(a[k]!=b[k] for k in sa&sb)
        source_only=sa-sb
        target_only=sb-sa
        known_types=("table","index","view","trigger")
        source_type_counts={
            typ:sum(key[0]==typ for key in source_only)
            for typ in known_types
        }
        target_type_counts={
            typ:sum(key[0]==typ for key in target_only)
            for typ in known_types
        }
        # Emit only normal table identifiers, never source CREATE statements
        # or index/trigger/view SQL. Unusual table names require manual review.
        import re
        table_name=re.compile(r"[A-Za-z_][A-Za-z0-9_]{0,127}")
        source_tables=sorted(key[1] for key in source_only
                             if key[0]=="table" and table_name.fullmatch(key[1]))
        target_tables=sorted(key[1] for key in target_only
                             if key[0]=="table" and table_name.fullmatch(key[1]))
        output.append({"name":name,"source_objects":len(a),
                       "target_objects":len(b),"source_only_objects":len(source_only),
                       "target_only_objects":len(target_only),
                       "source_only_types":source_type_counts,
                       "target_only_types":target_type_counts,
                       "source_only_table_names":source_tables,
                       "target_only_table_names":target_tables,
                       "nonstandard_source_only_table_name_count":source_type_counts["table"]-len(source_tables),
                       "nonstandard_target_only_table_name_count":target_type_counts["table"]-len(target_tables),
                       "common_object_definition_differences":changed,
                       "schema_exact_equal":not(sa^sb) and changed==0})
    return {"status":"SCHEMA_ONLY_NO_ROW_PARITY_NOT_CUTOVER_READY",
            "shared_databases_compared":len(common),
            "source_database_count":len(src),"target_database_count":len(dst),
            "source_only_database_names":sorted(src.keys()-dst.keys()),
            "target_only_database_names":sorted(dst.keys()-src.keys()),
            "per_database":output,
            "all_shared_schema_exact_equal":all(x["schema_exact_equal"] for x in output),
            "data_row_parity_verified":False,"delete_tombstone_parity_verified":False,
            "writer_quiescence_verified":False,"cutover_ready":False,
            "d1_writes":0,"r2_requests":0,"worker_deploys":0}

def main():
    try:
        require(os.getenv("GITHUB_REPOSITORY")=="louisalviss/runner-3"
                and os.getenv("GITHUB_EVENT_NAME")=="workflow_dispatch"
                and os.getenv("GITHUB_REF")=="refs/heads/main",
                "UNTRUSTED_GITHUB_CONTEXT")
        require(not os.getenv("CLOUDFLARE_TARGET_D1_WRITE_TOKEN"),
                "WRITE_TOKEN_FORBIDDEN")
        r=compare(os.getenv("CLOUDFLARE_API_TOKEN",""),
                  os.getenv("CLOUDFLARE_TARGET_AUDIT_TOKEN",""))
        OUTPUT.parent.mkdir(parents=True,exist_ok=True)
        OUTPUT.write_text(json.dumps(r,sort_keys=True,indent=2)+"\n")
        print("D1_SCHEMA_COMPARISON_PASS shared",r["shared_databases_compared"],
              "exact",sum(x["schema_exact_equal"] for x in r["per_database"]),
              "no_d1_writes no_r2 not_cutover")
        return 0
    except (Hold,OSError,ValueError,TypeError):
        print("D1_SCHEMA_COMPARISON_HOLD no_d1_writes no_r2")
        return 3
if __name__=="__main__": raise SystemExit(main())
