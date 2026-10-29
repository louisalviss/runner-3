#!/usr/bin/env python3
"""Bounded read-only composite-key HMAC parity for D1 content_features.

No raw keys, values, tokens or HMACs exported. Never approves replay/cutover.
"""
import datetime as dt
import hashlib
import hmac
import json
import os
from pathlib import Path
import secrets
import urllib.error
import urllib.request

SOURCE = "7415a87f6bce7884e73ad7cfed5782df"
TARGET = "748a80810f77f447ee476543ef0e5014"
SOURCE_D1 = "9cbec4ec-c930-459d-9499-9c66166c9241"
TARGET_D1 = "82613659-8d08-455f-b6e7-f8f6e4312e22"
COLS = ("item_id","feature_type","feature_key","feature_value","weight",
        "confidence","model_version","updated_at")
KEY = COLS[:3]
PAYLOAD = COLS[3:]
PAGE = 250
CAP = 30000
MAX_PAGES = CAP // PAGE + 1
MAX_BODY = 2200000
PAGE_READ_CAP = 900
TOTAL_READ_CAP = 75000
SQL = ('SELECT '+','.join('"'+c+'"' for c in COLS)+
       ' FROM "content_features" WHERE ("item_id","feature_type","feature_key") > (?,?,?)'
       ' ORDER BY "item_id","feature_type","feature_key" LIMIT 250')
RECEIPT = Path("migration-out/d1-upstream-three-bounded-counts-readonly.json")
OUT = Path("migration-out/d1-content-features-keyed-parity-readonly.json")

class Hold(Exception): pass
def need(ok,reason):
    if not ok: raise Hold(reason)

def read(token,account,db,cursor,opener=urllib.request.urlopen):
    need(type(token) is str and len(token)>=16 and
         (account,db) in ((SOURCE,SOURCE_D1),(TARGET,TARGET_D1)) and
         type(cursor) is tuple and len(cursor)==3 and
         all(type(v) is str and len(v)<=256 and "\x00" not in v for v in cursor),
         "INVALID_CREDENTIAL_OR_CURSOR")
    req = urllib.request.Request(
        "https://api.cloudflare.com/client/v4/accounts/"+account+"/d1/database/"+db+"/query",
        method="POST",data=json.dumps({"sql":SQL,"params":list(cursor)}).encode("utf8"),
        headers={"Authorization":"Bearer "+token,"Accept":"application/json",
                 "Content-Type":"application/json"})
    try:
        with opener(req,timeout=25) as res:
            need(res.status==200,"D1_HTTP_NOT_200")
            raw=res.read(MAX_BODY+1)
    except urllib.error.HTTPError as err:
        raise Hold("D1_HTTP_"+str(int(err.code))) from None
    except (urllib.error.URLError,OSError,TimeoutError):
        raise Hold("D1_NETWORK_UNAVAILABLE") from None
    need(len(raw)<=MAX_BODY,"D1_PAGE_BYTES_CAP")
    try: obj=json.loads(raw)
    except (ValueError,UnicodeError): raise Hold("D1_RESPONSE_BAD_JSON") from None
    need(type(obj) is dict and obj.get("success") is True,"D1_API_FAILURE")
    roots=obj.get("result")
    need(type(roots) is list and len(roots)==1 and type(roots[0]) is dict and
         roots[0].get("success") is True and type(roots[0].get("results")) is list,
         "D1_RESPONSE_BAD_SHAPE")
    meta=roots[0].get("meta")
    need(type(meta) is dict and meta.get("rows_written",0)==0 and
         meta.get("changed_db",False) is False and
         type(meta.get("rows_read")) is int and
         0<=meta["rows_read"]<=PAGE_READ_CAP,"D1_READ_COST_OR_WRITE_HOLD")
    return roots[0]["results"],meta["rows_read"]

def typed(value):
    if value is None:return ["null",None]
    if type(value) is str:return ["text",value]
    if type(value) is int:return ["integer",value]
    if type(value) is float:
        need(value==value and abs(value)!=float("inf"),"NONFINITE_FLOAT")
        return ["real",repr(value)]
    raise Hold("UNSUPPORTED_SQL_VALUE")

def fingerprint(row,secret):
    need(type(row) is dict and set(row)==set(COLS) and
         all(type(row[k]) is str and 0<len(row[k])<=256 for k in KEY),
         "FEATURE_ROW_SCHEMA_OR_KEY_INVALID")
    pk=tuple(row[k] for k in KEY)
    def mac(domain,values):
        packed=json.dumps([typed(v) for v in values],ensure_ascii=False,
                          separators=(",",":"),allow_nan=False).encode("utf8")
        return hmac.new(secret,b"d1:content_features:"+domain+packed,
                        hashlib.sha256).digest()
    identity=mac(b"pk:v1:",pk)
    value=mac(b"payload:v1:",tuple(row[k] for k in PAYLOAD))
    cols={c:mac(b"col:v1:"+c.encode()+b":",(row[c],)) for c in PAYLOAD}
    return pk,identity,(value,cols)

def capture(token,account,db,secret,reader=read):
    cursor=("","","")
    found={}
    cost=0
    for _ in range(MAX_PAGES):
        rows,rows_read=reader(token,account,db,cursor)
        need(type(rows) is list and len(rows)<=PAGE and
             type(rows_read) is int and 0<=rows_read<=PAGE_READ_CAP,
             "PAGE_RESPONSE_OR_READ_METRIC_INVALID")
        cost+=rows_read
        need(cost<=TOTAL_READ_CAP,"ACCOUNT_READ_BUDGET_EXCEEDED")
        prev=cursor
        for row in rows:
            pk,identity,payload=fingerprint(row,secret)
            need(pk>prev,"NONMONOTONIC_COMPOSITE_PK")
            need(identity not in found,"DUPLICATE_PK_FINGERPRINT")
            found[identity]=payload
            need(len(found)<=CAP,"FEATURE_TOTAL_ROW_CAP")
            prev=pk
        if len(rows)<PAGE:return found,cost
        cursor=prev
    raise Hold("PAGE_CAP_EXCEEDED")

def audit(src_token,dst_token,counts,reader=read):
    need(type(src_token) is str and type(dst_token) is str and
         len(src_token)>=16 and len(dst_token)>=16 and src_token!=dst_token,
         "SEPARATE_AUDIT_CREDENTIALS_REQUIRED")
    need(type(counts) is dict and
         counts.get("database")=="runner3-content-intelligence" and
         counts.get("production_writes")==0 and
         counts.get("cutover_ready") is False and
         type(counts.get("tables")) is dict and
         type(counts["tables"].get("content_features")) is dict,
         "BOUNDED_COUNT_RECEIPT_INVALID")
    cf=counts["tables"]["content_features"]
    need(cf.get("schema_columns_and_pk_equal") is True and
         type(cf.get("source_lower_bound")) is int and
         type(cf.get("target_lower_bound")) is int and
         0<=cf["source_lower_bound"]<=CAP and
         0<=cf["target_lower_bound"]<=CAP and
         type(cf.get("source_at_cap")) is bool and
         type(cf.get("target_at_cap")) is bool,"FEATURE_COUNT_RECEIPT_INVALID")
    secret=secrets.token_bytes(32)
    src1,sc1=capture(src_token,SOURCE,SOURCE_D1,secret,reader)
    dst1,tc1=capture(dst_token,TARGET,TARGET_D1,secret,reader)
    src2,sc2=capture(src_token,SOURCE,SOURCE_D1,secret,reader)
    dst2,tc2=capture(dst_token,TARGET,TARGET_D1,secret,reader)
    need(sc1+sc2<=TOTAL_READ_CAP and tc1+tc2<=TOTAL_READ_CAP,
         "TWO_PASS_ACCOUNT_READ_BUDGET_EXCEEDED")
    need(src1==src2 and dst1==dst2,"FEATURE_SNAPSHOTS_UNSTABLE")
    for name,data in (("source",src2),("target",dst2)):
        exact=cf.get(name+"_count")
        need(len(data)>=cf[name+"_lower_bound"] and
             (cf[name+"_at_cap"] or (type(exact) is int and len(data)==exact)),
             "BOUNDED_COUNT_RECEIPT_CHANGED")
    sk=set(src2); tk=set(dst2); common=sk&tk
    conflicts=sum(src2[k][0]!=dst2[k][0] for k in common)
    diffs={c:sum(src2[k][1][c]!=dst2[k][1][c] for k in common)
           for c in PAYLOAD}
    need(sum(diffs.values())>=conflicts,"COLUMN_DIFF_ACCOUNTING_FAILED")
    return {
        "status":"CONTENT_FEATURES_KEYED_PAYLOAD_READONLY_HOLD_NOT_CUTOVER",
        "checked_utc":dt.datetime.now(dt.timezone.utc).isoformat(),
        "table":"content_features","pk_fields":list(KEY),
        "source_rows":len(sk),"target_rows":len(tk),
        "common_keys":len(common),"common_payload_matches":len(common)-conflicts,
        "common_payload_conflicts":conflicts,
        "source_only_keys":len(sk-tk),"target_only_keys_preserve":len(tk-sk),
        "payload_difference_column_counts":diffs,
        "read_cost_source_rows":sc1+sc2,"read_cost_target_rows":tc1+tc2,
        "read_cap_per_account":TOTAL_READ_CAP,
        "max_rows_per_account":CAP,"two_sequential_passes_stable":True,
        "cross_account_atomic_snapshot":False,
        "source_writer_quiescence_proven":False,
        "target_writer_quiescence_proven":False,
        "deletion_lineage_verified":False,"safe_merge_policy_approved":False,
        "rollback_ready":False,"raw_rows_keys_hmacs_exported":False,
        "d1_writes":0,"r2_requests":0,"worker_deploys":0,
        "cutover_ready":False,
    }

def main():
    try:
        need(os.getenv("GITHUB_REPOSITORY")=="louisalviss/runner-3" and
             os.getenv("GITHUB_REF")=="refs/heads/main" and
             os.getenv("GITHUB_EVENT_NAME")=="workflow_dispatch" and
             not os.getenv("CLOUDFLARE_TARGET_D1_WRITE_TOKEN"),
             "UNTRUSTED_RUN_CONTEXT")
        need(RECEIPT.is_file() and not RECEIPT.is_symlink() and
             0<RECEIPT.stat().st_size<=20000,"COUNT_RECEIPT_MISSING")
        result=audit(os.getenv("CLOUDFLARE_API_TOKEN",""),
                     os.getenv("CLOUDFLARE_TARGET_AUDIT_TOKEN_NEW",""),
                     json.loads(RECEIPT.read_text(encoding="utf8")))
        OUT.parent.mkdir(parents=True,exist_ok=True)
        OUT.write_text(json.dumps(result,sort_keys=True,indent=2)+"\n",encoding="utf8")
        print("D1_CONTENT_FEATURES_KEYED_AUDIT_PASS",
              "source",result["source_rows"],"target",result["target_rows"],
              "common",result["common_keys"],"conflicts",result["common_payload_conflicts"],
              "NO_D1_WRITES_NO_CUTOVER")
        return 0
    except Hold as err:
        print("D1_CONTENT_FEATURES_AUDIT_HOLD",str(err),"NO_WRITES")
        return 3
    except (TypeError,ValueError,OSError,UnicodeError):
        print("D1_CONTENT_FEATURES_AUDIT_HOLD INTERNAL_FAILURE NO_WRITES")
        return 3

if __name__=="__main__":
    raise SystemExit(main())
