#!/usr/bin/env python3
"""Manual, bounded, read-only cross-account D1 probe for one small table.

Never writes, persists, logs or publishes raw rows, primary keys, row hashes
or credentials. Repeated small snapshots are not an atomic cutover proof.
"""
import hashlib
import hmac
import json
import os
import pathlib
import secrets
import urllib.error
import urllib.request

SRC_ACCOUNT = "7415a87f6bce7884e73ad7cfed5782df"
DST_ACCOUNT = "748a80810f77f447ee476543ef0e5014"
SRC_UUID = "9cbec4ec-c930-459d-9499-9c66166c9241"
DST_UUID = "82613659-8d08-455f-b6e7-f8f6e4312e22"
DB = "runner3-content-intelligence"
TABLE = "recommendation_runs"
COLUMNS = ("render_id", "source_scope", "item_count", "recommended_count",
           "exploration_ratio", "model_version", "created_at", "metadata_json")
MAX_ROWS = 250
MAX_RESPONSE_BYTES = 1_500_000
META_SQL = 'PRAGMA table_xinfo("recommendation_runs")'
ROWS_SQL = ('SELECT ' + ','.join('"'+c+'"' for c in COLUMNS) +
            ' FROM "recommendation_runs" ORDER BY "render_id" LIMIT 251')
OUTPUT = pathlib.Path("migration-out/d1-first-live-table-parity-summary.json")

class Blocked(Exception):
    pass

def require(ok, code):
    if not ok:
        raise Blocked(code)

def request_json(token, account, uid, sql):
    require((account,uid) in ((SRC_ACCOUNT,SRC_UUID),(DST_ACCOUNT,DST_UUID))
            and sql in (META_SQL, ROWS_SQL), "ROUTE_OR_SQL_NOT_ALLOWLISTED")
    request = urllib.request.Request(
        f"https://api.cloudflare.com/client/v4/accounts/{account}/d1/database/{uid}/query",
        data=json.dumps({"sql":sql}).encode("utf8"), method="POST",
        headers={"Authorization":"Bearer "+token,"Content-Type":"application/json",
                 "Accept":"application/json"})
    try:
        with urllib.request.urlopen(request,timeout=25) as response:
            require(response.status==200,"REMOTE_HTTP_NOT_200")
            raw=response.read(MAX_RESPONSE_BYTES+1)
    except urllib.error.HTTPError as e:
        raise Blocked("REMOTE_HTTP_"+str(e.code)) from None
    except (urllib.error.URLError,TimeoutError,OSError):
        raise Blocked("REMOTE_UNAVAILABLE") from None
    require(len(raw)<=MAX_RESPONSE_BYTES,"REMOTE_RESPONSE_TOO_LARGE")
    try:
        value=json.loads(raw)
    except (ValueError,UnicodeError):
        raise Blocked("REMOTE_JSON_INVALID") from None
    require(isinstance(value,dict) and value.get("success") is True,"REMOTE_API_FAILED")
    records=value.get("result")
    require(isinstance(records,list) and len(records)==1 and isinstance(records[0],dict)
            and records[0].get("success") is True and
            isinstance(records[0].get("results"),list),"D1_QUERY_FAILED")
    meta=records[0].get("meta") or {}
    require(isinstance(meta,dict) and meta.get("rows_written",0)==0 and
            meta.get("changed_db",False) is False,"NON_READ_ONLY_SQL")
    return records[0]["results"]

def check_schema(rows):
    require(isinstance(rows,list) and len(rows)==len(COLUMNS),"SCHEMA_COLUMN_COUNT_DRIFT")
    indexed=sorted(rows,key=lambda r:r.get("cid",-1) if isinstance(r,dict) else -1)
    require(tuple(r.get("name") for r in indexed)==COLUMNS,"SCHEMA_COLUMNS_DRIFT")
    require(all(type(r.get("hidden",0)) is int and r.get("hidden",0)==0 for r in indexed),
            "SCHEMA_HIDDEN_COLUMNS")
    require(indexed[0].get("pk")==1 and all(r.get("pk")==0 for r in indexed[1:]),
            "SCHEMA_PRIMARY_KEY_DRIFT")
    return hashlib.sha256(json.dumps(indexed,sort_keys=True,
        separators=(",",":"),ensure_ascii=False).encode()).hexdigest()

def typed(value):
    if value is None: return ["null",None]
    if isinstance(value,bool): raise Blocked("UNEXPECTED_BOOLEAN_FROM_SQL")
    if type(value) is int: return ["int",value]
    if type(value) is float:
        require(value==value and abs(value)!=float("inf"),"NONFINITE_REAL")
        return ["float",repr(value)]
    if type(value) is str: return ["text",value]
    raise Blocked("UNSUPPORTED_BLOB_OR_SQL_TYPE")

def fingerprints(rows,key):
    require(isinstance(rows,list) and len(rows)<=MAX_ROWS,"ROW_CAP_EXCEEDED")
    data={}
    for r in rows:
        require(isinstance(r,dict) and set(r)==set(COLUMNS),"ROW_COLUMNS_DRIFT")
        pk=r["render_id"]
        require(isinstance(pk,str) and 0<len(pk)<=500,"INVALID_PRIMARY_KEY")
        canon=json.dumps([typed(r[c]) for c in COLUMNS],separators=(",",":"),
                         ensure_ascii=False,allow_nan=False).encode("utf8")
        ident=hmac.new(key,b"key:v1:"+pk.encode("utf8"),hashlib.sha256).digest()
        digest=hmac.new(key,b"row:v1:"+canon,hashlib.sha256).digest()
        require(ident not in data,"DUPLICATE_PRIMARY_KEY")
        data[ident]=digest
    return data

def probe(source_token,target_token,request=request_json):
    require(isinstance(source_token,str) and len(source_token)>=16 and
            isinstance(target_token,str) and len(target_token)>=16 and
            source_token!=target_token,"ACCOUNT_TOKENS_UNAVAILABLE_OR_IDENTICAL")
    src_meta=check_schema(request(source_token,SRC_ACCOUNT,SRC_UUID,META_SQL))
    dst_meta=check_schema(request(target_token,DST_ACCOUNT,DST_UUID,META_SQL))
    require(src_meta==dst_meta,"SCHEMA_METADATA_DIFFERENT")
    key=secrets.token_bytes(32)
    s1=fingerprints(request(source_token,SRC_ACCOUNT,SRC_UUID,ROWS_SQL),key)
    t1=fingerprints(request(target_token,DST_ACCOUNT,DST_UUID,ROWS_SQL),key)
    s2=fingerprints(request(source_token,SRC_ACCOUNT,SRC_UUID,ROWS_SQL),key)
    t2=fingerprints(request(target_token,DST_ACCOUNT,DST_UUID,ROWS_SQL),key)
    src_stable,dst_stable=s1==s2,t1==t2
    shared=s2.keys() & t2.keys()
    source_only=len(s2.keys()-t2.keys())
    target_only=len(t2.keys()-s2.keys())
    different=sum(s2[k]!=t2[k] for k in shared)
    matched=len(shared)-different
    status=("UNSTABLE_WRITERS_HOLD" if not src_stable or not dst_stable else
            "ROW_DIFFERENCES_HOLD" if source_only or target_only or different else
            "ONE_TABLE_SNAPSHOT_EQUAL_NOT_CUTOVER_PROOF")
    return {
        "format":"d1-first-table-hmac-live-v1","database":DB,"table":TABLE,
        "source_account_id":SRC_ACCOUNT,"target_account_id":DST_ACCOUNT,
        "status":status,"bounded_row_cap":MAX_ROWS,
        "source_rows_observed":len(s2),"target_rows_observed":len(t2),
        "source_stable_within_probe":src_stable,"target_stable_within_probe":dst_stable,
        "source_only_keys":source_only,"target_only_keys_unresolved":target_only,
        "changed_payloads":different,"matching_key_payload_pairs":matched,
        "schema_column_metadata_equal":True,"compared_complete_small_table":True,
        "sensitive_values_exported":False,"fingerprints_exported":False,
        "source_delete_proven":False,"row_parity_verified_all_d1":False,
        "cutover_ready":False,"r2_requests":0,"d1_writes":0,
        "confidence":"bounded repeated snapshots; account reads are not atomic",
    }

def main():
    try:
        result=probe(os.environ.get("CLOUDFLARE_API_TOKEN",""),
                     os.environ.get("CLOUDFLARE_TARGET_AUDIT_TOKEN",""))
        OUTPUT.parent.mkdir(parents=True,exist_ok=True)
        OUTPUT.write_text(json.dumps(result,indent=2,sort_keys=True)+"\n",encoding="utf8")
        print("D1_ONE_TABLE_READ_ONLY",result["status"],
              "source_rows",result["source_rows_observed"],
              "target_rows",result["target_rows_observed"],
              "changed",result["changed_payloads"])
        return 0
    except Blocked as exc:
        print("D1_ONE_TABLE_BLOCKED",str(exc))
        return 3
    except Exception:
        # No repr/traceback that may expose secrets or raw API responses.
        print("D1_ONE_TABLE_BLOCKED INTERNAL_ERROR")
        return 3

if __name__=="__main__":
    raise SystemExit(main())
