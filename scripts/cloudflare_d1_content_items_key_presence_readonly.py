#!/usr/bin/env python3
"""Compare ONLY content_items primary-key presence using bounded HMAC in memory.

Reads 1 fixed SQL statement per account (max 5001 result rows), no payload
columns, no row IDs or fingerprints in artifacts/logs, no writes or R2.
Not an atomic snapshot or an authorization to delete/copy data.
"""
import hashlib
import hmac
import json
import os
import pathlib
import secrets
import urllib.error
import urllib.request

SOURCE="7415a87f6bce7884e73ad7cfed5782df"
TARGET="748a80810f77f447ee476543ef0e5014"
SOURCE_D1="9cbec4ec-c930-459d-9499-9c66166c9241"
TARGET_D1="82613659-8d08-455f-b6e7-f8f6e4312e22"
TABLE="content_items"
MAX_KEYS=5000
SQL='SELECT "item_id" FROM "content_items" ORDER BY "item_id" LIMIT 5001'
COUNTS=pathlib.Path("migration-out/d1-upstream-three-bounded-counts-readonly.json")
OUT=pathlib.Path("migration-out/d1-content-items-pk-presence-readonly.json")
MAX_BYTES=850000

class Hold(Exception):pass
def require(v,msg):
    if not v:raise Hold(msg)

def reader(token,account,uid,sql,opener=urllib.request.urlopen):
    require(type(token) is str and len(token)>=16
            and (account,uid) in ((SOURCE,SOURCE_D1),(TARGET,TARGET_D1))
            and sql==SQL, "UNAPPROVED_READ_CREDENTIAL_OR_SQL")
    req=urllib.request.Request(
        "https://api.cloudflare.com/client/v4/accounts/"+account+
        "/d1/database/"+uid+"/query", method="POST",
        data=json.dumps({"sql":SQL}).encode("utf8"),
        headers={"Authorization":"Bearer "+token,
                 "Accept":"application/json","Content-Type":"application/json"})
    try:
        with opener(req,timeout=25) as response:
            require(response.status==200,"D1_HTTP_NON_200")
            raw=response.read(MAX_BYTES+1)
    except urllib.error.HTTPError as e:
        raise Hold("D1_HTTP_"+str(int(e.code))) from None
    except (urllib.error.URLError,TimeoutError,OSError):
        raise Hold("D1_NETWORK_UNAVAILABLE") from None
    require(len(raw)<=MAX_BYTES,"D1_KEY_RESULT_TOO_LARGE")
    try:obj=json.loads(raw)
    except (ValueError,UnicodeError):
        raise Hold("D1_INVALID_JSON") from None
    require(type(obj) is dict and obj.get("success") is True,"D1_API_UNSUCCESSFUL")
    results=obj.get("result")
    require(type(results) is list and len(results)==1 and
            type(results[0]) is dict and
            results[0].get("success") is True and
            type(results[0].get("results")) is list,"D1_RESULT_INVALID")
    meta=results[0].get("meta") or {}
    require(type(meta) is dict and meta.get("rows_written",0)==0
            and meta.get("changed_db",False) is False,"WRITE_METADATA_HOLD")
    rows_read=meta.get("rows_read")
    require(rows_read is None or
            (type(rows_read) is int and 0<=rows_read<=MAX_KEYS+1),
            "UNEXPECTED_QUERY_READ_COST")
    return results[0]["results"]

def digest_ids(rows,key):
    require(type(rows) is list and len(rows)<=MAX_KEYS,"KEY_CAP_REACHED_HOLD")
    found=set()
    prev=None
    for row in rows:
        require(type(row) is dict and set(row)=={"item_id"} and
                type(row["item_id"]) is str and
                0<len(row["item_id"])<=256, "BAD_KEY_ROW")
        value=row["item_id"]
        require(prev is None or prev<value,"DUPLICATE_OR_UNORDERED_KEY")
        prev=value
        digest=hmac.new(key,b"d1:content_items:pk:v1:"+value.encode("utf8"),
                        hashlib.sha256).digest()
        require(digest not in found,"KEY_DIGEST_COLLISION")
        found.add(digest)
    return found

def assess(source_token,target_token,receipt,read=reader):
    require(type(source_token) is str and type(target_token) is str and
            len(source_token)>=16 and len(target_token)>=16 and
            source_token!=target_token,"INDEPENDENT_READ_TOKENS_REQUIRED")
    require(type(receipt) is dict and
            receipt.get("database")=="runner3-content-intelligence" and
            receipt.get("status") in (
                "UPSTREAM_PARTIAL_COUNTS_CAPPED_HOLD_NO_EXTRA_SCAN",
                "UPSTREAM_THREE_TABLES_BOUNDED_COUNTS_NOT_KEYED_PARITY")
            and receipt.get("production_writes")==0 and
            receipt.get("snapshot_atomic") is False and
            receipt.get("cutover_ready") is False,
            "COUNT_RECEIPT_UNTRUSTED")
    row=receipt.get("tables",{}).get("content_items",{})
    require(type(row) is dict and
            row.get("schema_columns_and_pk_equal") is True and
            row.get("source_at_cap") is False and
            row.get("target_at_cap") is False and
            type(row.get("source_count")) is int and
            type(row.get("target_count")) is int and
            0<=row["source_count"]<MAX_KEYS and
            0<=row["target_count"]<MAX_KEYS,
            "CONTENT_ITEM_COUNT_NOT_EXACT_OR_EXCEEDS_CAP")
    key=secrets.token_bytes(32)
    s=digest_ids(read(source_token,SOURCE,SOURCE_D1,SQL),key)
    t=digest_ids(read(target_token,TARGET,TARGET_D1,SQL),key)
    require(len(s)==row["source_count"] and
            len(t)==row["target_count"],
            "COUNT_TO_PK_READ_DRIFT_HOLD")
    shared=len(s&t)
    only_s=len(s-t)
    only_t=len(t-s)
    require(shared+only_s==len(s) and shared+only_t==len(t),
            "KEY_SET_ACCOUNTING_FAILURE")
    return {
        "status":"CONTENT_ITEMS_PK_PRESENCE_SNAPSHOT_ONLY_HOLD",
        "database":"runner3-content-intelligence",
        "table":TABLE,
        "source_keys":len(s),"target_keys":len(t),
        "shared_keys":shared,
        "source_only_keys":only_s,
        "target_only_keys_preserve":only_t,
        "pk_snapshot_consistent_with_recent_counts":True,
        "payload_fingerprints_compared":False,
        "key_material_exported":False,
        "key_hmac_exported":False,
        "atomic_snapshot":False,"repeat_capture_stability_proven":False,
        "delete_tombstone_lineage_verified":False,
        "writer_quiescence_proven":False,
        "rollback_ready":False,
        "application_row_values_exported":False,
        "d1_reads_max_per_account":MAX_KEYS+1,
        "d1_write_requests":0,"r2_requests":0,
        "cutover_ready":False,
    }

def main():
    try:
        require(os.getenv("GITHUB_REPOSITORY")=="louisalviss/runner-3"
                and os.getenv("GITHUB_REF")=="refs/heads/main"
                and os.getenv("GITHUB_EVENT_NAME")=="workflow_dispatch"
                and not os.getenv("CLOUDFLARE_TARGET_D1_WRITE_TOKEN"),
                "UNTRUSTED_CONTEXT")
        require(COUNTS.is_file() and not COUNTS.is_symlink() and
                0<COUNTS.stat().st_size<=16000,
                "UPSTREAM_COUNT_RECEIPT_MISSING_OR_UNSAFE")
        count_receipt=json.loads(COUNTS.read_text())
        result=assess(os.getenv("CLOUDFLARE_API_TOKEN",""),
                      os.getenv("CLOUDFLARE_TARGET_AUDIT_TOKEN_NEW",""),
                      count_receipt)
        OUT.parent.mkdir(parents=True,exist_ok=True)
        OUT.write_text(json.dumps(result,indent=2,sort_keys=True)+"\n")
        print("D1_CONTENT_ITEMS_PK_READONLY_HOLD summary_saved_no_rows_exported")
        return 0
    except (Hold,TypeError,ValueError,UnicodeError,OSError):
        print("D1_CONTENT_ITEMS_PK_READONLY_REJECTED no_write_no_key_export")
        return 3

if __name__=="__main__":
    raise SystemExit(main())
