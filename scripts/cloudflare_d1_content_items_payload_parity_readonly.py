#!/usr/bin/env python3
"""Read-only content_items payload HMAC parity, bounded PK-cursor pages.

No D1 writes, R2, Worker deploy, raw key/value or fingerprint artifacts.
Both accounts reread once to detect changes during audit; still not atomic.
"""
import datetime as dt
import hashlib
import hmac
import json
import os
import pathlib
import secrets
import urllib.error
import urllib.request

from cloudflare_d1_upstream_bounded_count_readonly import TABLES

SOURCE = "7415a87f6bce7884e73ad7cfed5782df"
TARGET = "748a80810f77f447ee476543ef0e5014"
SOURCE_D1 = "9cbec4ec-c930-459d-9499-9c66166c9241"
TARGET_D1 = "82613659-8d08-455f-b6e7-f8f6e4312e22"
COLUMNS = TABLES["content_items"]["columns"]
MAX_KEYS = 5000
PAGE_SIZE = 100
MAX_PAGES = 51
MAX_BODY = 1500000
MAX_ROWS_READ_PER_PAGE = 400
QUERY = ('SELECT ' + ','.join('"'+c+'"' for c in COLUMNS) +
         ' FROM "content_items" WHERE "item_id" > ? ORDER BY "item_id" LIMIT 100')
COUNT_RECEIPT = pathlib.Path("migration-out/d1-upstream-three-bounded-counts-readonly.json")
PK_RECEIPT = pathlib.Path("migration-out/d1-content-items-pk-presence-readonly.json")
OUT = pathlib.Path("migration-out/d1-content-items-payload-parity-readonly.json")

class Hold(Exception): pass
def require(ok,reason):
    if not ok: raise Hold(reason)

def remote(token,account,database,cursor,opener=urllib.request.urlopen):
    require(type(token) is str and len(token)>=16 and
            (account,database) in ((SOURCE,SOURCE_D1),(TARGET,TARGET_D1)) and
            type(cursor) is str and len(cursor)<=256 and "\x00" not in cursor,
            "INVALID_CREDENTIAL_ROUTE_OR_CURSOR")
    req=urllib.request.Request(
        "https://api.cloudflare.com/client/v4/accounts/"+account+
        "/d1/database/"+database+"/query",
        method="POST",
        data=json.dumps({"sql":QUERY,"params":[cursor]}).encode("utf-8"),
        headers={"Authorization":"Bearer "+token,
                 "Accept":"application/json","Content-Type":"application/json"})
    try:
        with opener(req,timeout=22) as res:
            require(res.status==200,"HTTP_NOT_200")
            raw=res.read(MAX_BODY+1)
    except urllib.error.HTTPError as e:
        raise Hold("D1_HTTP_"+str(int(e.code))) from None
    except (urllib.error.URLError,OSError,TimeoutError):
        raise Hold("D1_NETWORK_UNAVAILABLE") from None
    require(len(raw)<=MAX_BODY,"D1_PAGE_OVERSIZED")
    try:o=json.loads(raw)
    except (ValueError,UnicodeError):raise Hold("D1_JSON_BAD") from None
    require(type(o) is dict and o.get("success") is True,"D1_API_FAILED")
    roots=o.get("result")
    require(type(roots) is list and len(roots)==1 and
            type(roots[0]) is dict and roots[0].get("success") is True and
            type(roots[0].get("results")) is list,
            "D1_RESULT_FAILED")
    meta=roots[0].get("meta") or {}
    rr=meta.get("rows_read")
    require(type(meta) is dict and meta.get("rows_written",0)==0 and
            meta.get("changed_db",False) is False and
            (rr is None or (type(rr) is int and
             0<=rr<=MAX_ROWS_READ_PER_PAGE)),
            "QUERY_NOT_BOUNDED_READ")
    return roots[0]["results"]

def encode(value):
    if value is None: return ["NULL",None]
    if type(value) is str:return ["TEXT",value]
    if type(value) is int:return ["INT",value]
    if type(value) is float:
        require(value==value and abs(value)!=float("inf"),"NONFINITE_SQL_FLOAT")
        return ["REAL",repr(value)]
    raise Hold("UNSUPPORTED_FIELD_TYPE")

def digest_row(row,key):
    require(type(row) is dict and set(row)==set(COLUMNS) and
            type(row["item_id"]) is str and
            0<len(row["item_id"])<=256,"CONTENT_ITEM_ROW_INVALID")
    prefix=b"cloudflare:d1:content_items:"
    identity=hmac.new(key,b"identity:v1:"+prefix+row["item_id"].encode("utf-8"),
                      hashlib.sha256).digest()
    typed={c:encode(row[c]) for c in COLUMNS}
    value=hmac.new(key,b"row:v1:"+prefix+json.dumps(
         [typed[c] for c in COLUMNS],ensure_ascii=False,
         separators=(",",":"),allow_nan=False).encode("utf-8"),
         hashlib.sha256).digest()
    columns={c:hmac.new(key,b"column:v1:"+prefix+c.encode("utf-8")+b":"+
          json.dumps(typed[c],ensure_ascii=False,separators=(",",":"),
                     allow_nan=False).encode("utf-8"),
          hashlib.sha256).digest() for c in COLUMNS if c!="item_id"}
    return identity,{"row":value,"columns":columns}

def capture(token,account,database,key,reader=remote):
    records={}
    cursor=""
    pages=0
    while pages<MAX_PAGES:
        data=reader(token,account,database,cursor)
        require(type(data) is list and len(data)<=PAGE_SIZE,
                "PAGE_RESULT_EXCEEDED_LIMIT")
        previous=cursor
        for row in data:
            require(type(row) is dict and type(row.get("item_id")) is str and
                    previous<row["item_id"],"DUPLICATE_OR_UNORDERED_PKS")
            previous=row["item_id"]
            identity,payload=digest_row(row,key)
            require(identity not in records,"DUPLICATE_PK_HMAC")
            records[identity]=payload
            require(len(records)<=MAX_KEYS,"TOTAL_PK_BUDGET_EXCEEDED")
        pages+=1
        if len(data)<PAGE_SIZE:
            return records
        cursor=previous
    raise Hold("PAGE_BUDGET_EXCEEDED")

def analyze(source_token,target_token,counts,pk,reader=remote):
    require(type(source_token) is str and type(target_token) is str and
            len(source_token)>=16 and len(target_token)>=16 and
            source_token!=target_token,"SEPARATE_AUDIT_TOKENS_REQUIRED")
    require(type(counts) is dict and
            counts.get("database")=="runner3-content-intelligence" and
            counts.get("production_writes")==0 and
            counts.get("cutover_ready") is False and
            type(counts.get("tables")) is dict and
            counts["tables"].get("content_items",{}).get("schema_columns_and_pk_equal") is True,
            "BOUNDED_COUNT_RECEIPT_INVALID")
    count=counts["tables"]["content_items"]
    require(count.get("source_at_cap") is False and
            count.get("target_at_cap") is False and
            type(count.get("source_count")) is int and
            type(count.get("target_count")) is int and
            0<=count["target_count"]<=count["source_count"]<MAX_KEYS,
            "CONTENT_ITEMS_NOT_EXACTLY_BOUNDED")
    require(type(pk) is dict and
            pk.get("status")=="CONTENT_ITEMS_PK_PRESENCE_SNAPSHOT_ONLY_HOLD" and
            pk.get("payload_fingerprints_compared") is False and
            pk.get("d1_write_requests")==0 and
            pk.get("source_keys")==count["source_count"] and
            pk.get("target_keys")==count["target_count"],
            "KEYED_PK_RECEIPT_UNTRUSTED")
    key=secrets.token_bytes(32)
    source1=capture(source_token,SOURCE,SOURCE_D1,key,reader)
    target1=capture(target_token,TARGET,TARGET_D1,key,reader)
    source2=capture(source_token,SOURCE,SOURCE_D1,key,reader)
    target2=capture(target_token,TARGET,TARGET_D1,key,reader)
    require(source1==source2 and target1==target2,
            "CONTENT_ITEM_SNAPSHOT_UNSTABLE")
    require(len(source2)==count["source_count"] and
            len(target2)==count["target_count"],
            "COUNT_RECEIPT_STALE_OR_INCOMPLETE")
    shared=set(source2)&set(target2)
    source_only=set(source2)-set(target2)
    target_only=set(target2)-set(source2)
    require(len(shared)==pk.get("shared_keys") and
            len(source_only)==pk.get("source_only_keys") and
            len(target_only)==pk.get("target_only_keys_preserve"),
            "PK_CENSUS_CHANGED")
    changed=sum(source2[k]["row"]!=target2[k]["row"] for k in shared)
    diff_columns={col:sum(source2[k]["columns"][col]!=target2[k]["columns"][col]
                          for k in shared)
                  for col in COLUMNS if col!="item_id"}
    require(changed==0 or sum(diff_columns.values())>=changed,
            "COLUMN_PAYLOAD_DIFFERENCE_INCONSISTENT")
    return {
        "status":"CONTENT_ITEMS_BOUNDED_PAYLOAD_PARITY_HOLD_NOT_CUTOVER",
        "checked_utc":dt.datetime.now(dt.timezone.utc).isoformat(),
        "source_rows_observed":len(source2),
        "target_rows_observed":len(target2),
        "common_pk_count":len(shared),
        "source_only_keys":len(source_only),
        "target_only_keys_preserve":len(target_only),
        "common_pk_payload_matches":len(shared)-changed,
        "common_pk_payload_mismatches":changed,
        "common_pk_column_difference_counts":diff_columns,
        "source_and_target_stable_during_repeat":True,
        "upstream_accountwide_parity_proven":False,
        "atomic_cross_account_snapshot":False,
        "deletion_lineage_verified":False,
        "target_writer_quiescence_verified":False,
        "rollback_ready":False,
        "source_data_values_or_keys_exported":False,
        "fingerprints_exported":False,
        "actual_target_insert_authorized":False,
        "d1_write_requests":0,"r2_requests":0,"worker_deploys":0,
        "cutover_ready":False,
    }

def main():
    try:
        require(os.getenv("GITHUB_REPOSITORY")=="louisalviss/runner-3" and
                os.getenv("GITHUB_REF")=="refs/heads/main" and
                os.getenv("GITHUB_EVENT_NAME")=="workflow_dispatch" and
                not os.getenv("CLOUDFLARE_TARGET_D1_WRITE_TOKEN"),
                "UNTRUSTED_RUN_CONTEXT")
        for path in (COUNT_RECEIPT,PK_RECEIPT):
            require(path.is_file() and not path.is_symlink() and
                    0<path.stat().st_size<=20000,
                    "SANITIZED_COUNT_OR_KEY_RECEIPT_MISSING")
        result=analyze(os.getenv("CLOUDFLARE_API_TOKEN",""),
                       os.getenv("CLOUDFLARE_TARGET_AUDIT_TOKEN_NEW",""),
                       json.loads(COUNT_RECEIPT.read_text()),
                       json.loads(PK_RECEIPT.read_text()))
        OUT.parent.mkdir(parents=True,exist_ok=True)
        OUT.write_text(json.dumps(result,sort_keys=True,indent=2)+"\n")
        print("D1_CONTENT_ITEMS_PAYLOAD_AUDIT_HOLD_NO_WRITES"
              " common",result["common_pk_count"],
              "matching",result["common_pk_payload_matches"],
              "conflicts",result["common_pk_payload_mismatches"])
        return 0
    except Hold as err:
        print("D1_CONTENT_ITEMS_PAYLOAD_AUDIT_STOP",str(err),
              "NO_D1_WRITES_NO_SENSITIVE_OUTPUT")
        return 3
    except (TypeError,ValueError,UnicodeError,OSError):
        print("D1_CONTENT_ITEMS_PAYLOAD_AUDIT_STOP INTERNAL_FAILURE"
              " NO_D1_WRITES_NO_SENSITIVE_OUTPUT")
        return 3

if __name__=="__main__":
    raise SystemExit(main())
