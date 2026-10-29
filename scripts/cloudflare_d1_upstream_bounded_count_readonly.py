#!/usr/bin/env python3
"""Bounded, source+target, THREE upstream D1 table count and schema preflight.

The 3 tables are base inputs to recomputeInterestProfile. Only allowlisted
PRAGMA table_xinfo and limited COUNT of SELECT constant; no application row
payloads, keys, row hashes, D1 mutations, Worker actions, R2, bookmarks.
Counts are NOT keyed parity, tombstones, stable snapshot, or migration approval.
"""
import datetime as dt
import hashlib
import json
import os
import pathlib
import urllib.error
import urllib.request

SOURCE = "7415a87f6bce7884e73ad7cfed5782df"
TARGET = "748a80810f77f447ee476543ef0e5014"
SOURCE_D1 = "9cbec4ec-c930-459d-9499-9c66166c9241"
TARGET_D1 = "82613659-8d08-455f-b6e7-f8f6e4312e22"
# The observed Oct-8 counts were ~2.9k/14.5k/5k. These fixed
# upper bounds cap rows scanned and cannot be adjusted at dispatch.
TABLES = {
    "content_items": {
        "columns": ("item_id","canonical_url","source_type","source_name",
                    "source_key","title","published_at","captured_at",
                    "language","raw_ref","content_hash","metadata_json",
                    "first_seen_at","last_seen_at"),
        "pk": ("item_id",), "limit": 6000,
    },
    "content_features": {
        "columns": ("item_id","feature_type","feature_key","feature_value",
                    "weight","confidence","model_version","updated_at"),
        "pk": ("item_id","feature_type","feature_key"), "limit": 19000,
    },
    "user_content_events": {
        "columns": ("id","item_id","render_id","event_type",
                    "assistant_recommended","assistant_rank",
                    "explicit_feedback","context_json","event_at"),
        "pk": ("id",), "limit": 9000,
    },
}
META_SQL = {name: 'PRAGMA table_xinfo("' + name + '")' for name in TABLES}
COUNT_SQL = {
    name: 'SELECT COUNT(*) AS n FROM (SELECT 1 FROM "' + name +
          '" LIMIT ' + str(config["limit"]) + ')'
    for name,config in TABLES.items()
}
ALLOWLIST = frozenset(META_SQL.values()) | frozenset(COUNT_SQL.values())
OUT = pathlib.Path("migration-out/d1-upstream-three-bounded-counts-readonly.json")
MAX_HTTP_BODY = 90000
MAX_METRIC_ROWS_READ = 40000

class Hold(Exception):
    pass

def ensure(value,reason):
    if not value:
        raise Hold(reason)

def query(token,account,uid,sql,opener=urllib.request.urlopen):
    ensure(type(token) is str and len(token)>=16 and
           (account,uid) in ((SOURCE,SOURCE_D1),(TARGET,TARGET_D1)) and
           sql in ALLOWLIST,"UNAPPROVED_CREDENTIAL_OR_QUERY")
    req = urllib.request.Request(
        "https://api.cloudflare.com/client/v4/accounts/" + account +
        "/d1/database/" + uid + "/query",
        method="POST",
        data=json.dumps({"sql":sql}).encode("utf-8"),
        headers={"Authorization":"Bearer " + token,
                 "Accept":"application/json",
                 "Content-Type":"application/json"})
    try:
        with opener(req,timeout=24) as res:
            ensure(res.status==200,"D1_HTTP_NON_200")
            body=res.read(MAX_HTTP_BODY+1)
    except urllib.error.HTTPError as err:
        raise Hold("D1_HTTP_"+str(int(err.code))) from None
    except (urllib.error.URLError,OSError,TimeoutError):
        raise Hold("D1_NETWORK_UNAVAILABLE") from None
    ensure(len(body)<=MAX_HTTP_BODY,"D1_RESPONSE_OVERSIZED")
    try: obj=json.loads(body)
    except (ValueError,UnicodeError): raise Hold("D1_INVALID_JSON") from None
    ensure(type(obj) is dict and obj.get("success") is True,"D1_API_UNSUCCESSFUL")
    roots=obj.get("result")
    ensure(type(roots) is list and len(roots)==1 and
           type(roots[0]) is dict and
           roots[0].get("success") is True and
           type(roots[0].get("results")) is list,
           "D1_QUERY_RESPONSE_INVALID")
    meta=roots[0].get("meta") or {}
    ensure(type(meta) is dict and
           meta.get("rows_written",0)==0 and
           meta.get("changed_db",False) is False,
           "D1_NON_READONLY_ACTIVITY")
    rows_read=meta.get("rows_read",None)
    ensure(rows_read is None or (type(rows_read) is int and
           0<=rows_read<=MAX_METRIC_ROWS_READ),
           "D1_UNEXPECTED_READ_COST")
    return roots[0]["results"], rows_read

def metadata(rows,name):
    expected=TABLES[name]
    ensure(type(rows) is list and len(rows)==len(expected["columns"]) and
           all(type(v) is dict and
               type(v.get("name")) is str and
               type(v.get("cid")) is int and
               type(v.get("pk")) is int and
               type(v.get("type")) is str and
               v.get("hidden",0)==0
               for v in rows),"COLUMN_METADATA_DRIFT")
    ordered=sorted(rows,key=lambda x:x["cid"])
    ensure(tuple(x["name"] for x in ordered)==expected["columns"] and
           [x["cid"] for x in ordered]==list(range(len(ordered))) and
           tuple(x["name"] for x in
                 sorted((x for x in ordered if x["pk"]>0),
                        key=lambda c:c["pk"]))==expected["pk"] and
           sorted(x["pk"] for x in ordered if x["pk"]>0)==list(
                range(1,len(expected["pk"])+1)),
           "EXPECTED_PK_OR_COLUMNS_CHANGED")
    # Calculate only inside CI memory: fingerprint not exported
    return hashlib.sha256(json.dumps(ordered,sort_keys=True,
         ensure_ascii=False,separators=(",",":")).encode()).digest()

def count(rows,name):
    ensure(name in TABLES and type(rows) is list and len(rows)==1 and
           type(rows[0]) is dict and set(rows[0])=={"n"} and
           type(rows[0]["n"]) is int and 0<=rows[0]["n"],
           "COUNT_RESPONSE_INVALID_"+name)
    # Equal to LIMIT is a safe lower bound, not an exact count. Never
    # extend the scan or infer row parity from a bounded aggregate.
    ensure(rows[0]["n"]<=TABLES[name]["limit"],
           "COUNT_EXCEEDS_ALLOWLIST_LIMIT_"+name)
    return rows[0]["n"], rows[0]["n"]==TABLES[name]["limit"]

def assess(source_token,target_token,reader=query):
    ensure(type(source_token) is str and type(target_token) is str and
           len(source_token)>=16 and len(target_token)>=16 and
           source_token!=target_token,"SEPARATE_READ_CREDENTIALS_REQUIRED")
    report={
        "status":"UPSTREAM_THREE_TABLES_BOUNDED_COUNTS_NOT_KEYED_PARITY",
        "any_count_capped":False,
        "capped_tables":[],
        "checked_utc":dt.datetime.now(dt.timezone.utc).isoformat(),
        "database":"runner3-content-intelligence",
        "tables":{},
        "rows_read_budget_per_account":MAX_METRIC_ROWS_READ,
        "d1_sql_calls":12,"read_only_sql_allowlist":True,
        "application_row_values_exported":False,
        "schema_details_exported":False,
        "pk_values_exported":False,
        "keyed_row_parity_verified":False,
        "deletion_semantics_verified":False,
        "snapshot_atomic":False,
        "source_writers_stopped":False,
        "target_writers_stopped":False,
        "bookmark_recovery_ready":False,
        "production_writes":0,
        "worker_deploys":0,"r2_requests":0,
        "cutover_ready":False
    }
    costs={"source":0,"target":0}
    for name in TABLES:
        sm,sr=reader(source_token,SOURCE,SOURCE_D1,META_SQL[name])
        tm,tr=reader(target_token,TARGET,TARGET_D1,META_SQL[name])
        ensure(metadata(sm,name)==metadata(tm,name),
               "SOURCE_TARGET_SCHEMA_DIFFERENCE")
        sc,scr=reader(source_token,SOURCE,SOURCE_D1,COUNT_SQL[name])
        tc,tcr=reader(target_token,TARGET,TARGET_D1,COUNT_SQL[name])
        s,s_capped=count(sc,name)
        t,t_capped=count(tc,name)
        if s_capped or t_capped:
            report["any_count_capped"]=True
            report["capped_tables"].append(name)
        for role,items in (("source",(sr,scr)),("target",(tr,tcr))):
            for v in items:
                if v is not None:
                    costs[role]+=v
            ensure(costs[role]<=MAX_METRIC_ROWS_READ,
                   "ACCOUNT_READ_BUDGET_EXCEEDED")
        report["tables"][name]={
            "source_count":None if s_capped else s,
            "target_count":None if t_capped else t,
            "source_lower_bound":s,
            "target_lower_bound":t,
            "source_at_cap":s_capped,
            "target_at_cap":t_capped,
            "source_minus_target":None if s_capped or t_capped else s-t,
            "schema_columns_and_pk_equal":True,
            "count_below_strict_cap":not (s_capped or t_capped),
            "max_limit_per_account":TABLES[name]["limit"],
            "source_only_keys_verified":False,
            "target_only_keys_verified":False,
            "matching_payloads_verified":False
        }
    if report["any_count_capped"]:
        report["status"]="UPSTREAM_PARTIAL_COUNTS_CAPPED_HOLD_NO_EXTRA_SCAN"
    return report

def main():
    try:
        ensure(os.getenv("GITHUB_REPOSITORY")=="louisalviss/runner-3" and
               os.getenv("GITHUB_REF")=="refs/heads/main" and
               os.getenv("GITHUB_EVENT_NAME")=="workflow_dispatch" and
               not os.getenv("CLOUDFLARE_TARGET_D1_WRITE_TOKEN"),
               "UNTRUSTED_ACTION_CONTEXT")
        result=assess(os.getenv("CLOUDFLARE_API_TOKEN",""),
                      os.getenv("CLOUDFLARE_TARGET_AUDIT_TOKEN_NEW",""))
        OUT.parent.mkdir(parents=True,exist_ok=True)
        OUT.write_text(json.dumps(result,indent=2,sort_keys=True)+"\n",
                       encoding="utf8")
        print("D1_UPSTREAM_COUNT_PREFLIGHT",result["status"],
              "capped_tables",len(result["capped_tables"]),
              "no_writes no_row_values")
        return 0
    except Hold as err:
        # All Hold reasons are static identifiers authored here or numeric
        # Cloudflare HTTP codes. No upstream response or exception text.
        print("D1_UPSTREAM_COUNT_PREFLIGHT_HOLD",str(err),
              "no_writes no_row_values")
        return 3
    except (TypeError,ValueError,OSError,UnicodeError):
        print("D1_UPSTREAM_COUNT_PREFLIGHT_HOLD INTERNAL_FAILURE"
              " no_writes no_row_values")
        return 3

if __name__=="__main__":
    raise SystemExit(main())
