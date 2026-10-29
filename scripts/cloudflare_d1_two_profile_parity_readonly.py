#!/usr/bin/env python3
"""Small, named two-table D1 keyed HMAC parity: SOURCE/TARGET READ ONLY.

Only two schema-identical profile tables. Hard cap 100 rows/table/account,
each read twice. Raw rows and cryptographic fingerprints never leave memory.
No D1 mutation/restore, R2, deployments, or production cutover.
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
ROWS_CAP=100
OUTPUT=pathlib.Path("migration-out/d1-two-interest-profiles-keyed-parity.json")
TABLES={
 "interest_family_profile":(
  ("family_key","weight","evidence_count","positive_count",
   "negative_count","confidence","updated_at"), ("family_key",)),
 "interest_profile":(
  ("feature_type","feature_key","weight","evidence_count",
   "positive_count","negative_count","confidence","updated_at"),
  ("feature_type","feature_key")),
}
META_SQL={
 t:'PRAGMA table_xinfo("'+t+'")' for t in TABLES
}
DATA_SQL={
 t:'SELECT '+','.join('"'+c+'"' for c in cols)+
    ' FROM "'+t+'" ORDER BY '+','.join('"'+c+'"' for c in pk)+
    " LIMIT 101"
 for t,(cols,pk) in TABLES.items()
}
class Hold(Exception): pass
def require(ok,code):
 if not ok:raise Hold(code)

def remote(token,account,uid,sql,opener=urllib.request.urlopen):
 require(type(token) is str and len(token)>=16,"AUDIT_CREDENTIAL_MISSING")
 require((account,uid) in ((SOURCE,SOURCE_D1),(TARGET,TARGET_D1))
         and sql in set(META_SQL.values())|set(DATA_SQL.values()),
         "ENDPOINT_OR_SQL_NOT_ALLOWLISTED")
 req=urllib.request.Request(
  "https://api.cloudflare.com/client/v4/accounts/"+account+
  "/d1/database/"+uid+"/query",
  method="POST",data=json.dumps({"sql":sql}).encode(),
  headers={"Authorization":"Bearer "+token,"Accept":"application/json",
           "Content-Type":"application/json"})
 try:
  with opener(req,timeout=25) as res:
   require(res.status==200,"NON_200")
   raw=res.read(300001)
 except urllib.error.HTTPError as e:
  raise Hold("D1_HTTP_"+str(int(e.code))) from None
 except (urllib.error.URLError,OSError,TimeoutError):
  raise Hold("D1_NETWORK_ERROR") from None
 require(len(raw)<=300000,"D1_RESPONSE_TOO_LARGE")
 try:o=json.loads(raw)
 except (ValueError,UnicodeError): raise Hold("D1_JSON_BAD") from None
 require(type(o) is dict and o.get("success") is True,"D1_API_UNSUCCESSFUL")
 items=o.get("result")
 require(type(items) is list and len(items)==1 and
         type(items[0]) is dict and items[0].get("success") is True and
         type(items[0].get("results")) is list,
         "D1_RESULT_INVALID")
 meta=items[0].get("meta") or {}
 require(type(meta) is dict and meta.get("rows_written",0)==0 and
         meta.get("changed_db",False) is False,"D1_WRITE_METADATA_DETECTED")
 return items[0]["results"]

def schema(rows,table):
 require(type(rows) is list and len(rows)==len(TABLES[table][0]),
         "COLUMN_SET_DRIFT")
 require(all(type(x) is dict and type(x.get("cid")) is int
             and type(x.get("name")) is str
             and type(x.get("pk")) is int and x["pk"]>=0
             for x in rows),"COLUMN_METADATA_BAD")
 arranged=sorted(rows,key=lambda x:x["cid"])
 cols,pk=TABLES[table]
 require(tuple(x["name"] for x in arranged)==cols and
         tuple(x["name"] for x in sorted(arranged,key=lambda r:r["pk"])
               if x["pk"]>0)==pk and
         len({x["cid"] for x in arranged})==len(rows),
         "SCHEMA_OR_PK_DRIFT")
 return hashlib.sha256(json.dumps(arranged,sort_keys=True,
        separators=(",",":"),ensure_ascii=False).encode()).digest()

def typed(v):
 if v is None:return ["null",None]
 if type(v) is str: return ["text",v]
 if type(v) is int:return ["int",v]
 if type(v) is float:
  require(v==v and abs(v)!=float("inf"),"NONFINITE_FLOAT")
  return ["real",repr(v)]
 raise Hold("UNSUPPORTED_SENSITIVE_ROW_VALUE")

def fingerprint(rows,table,key):
 require(type(rows) is list and len(rows)<=ROWS_CAP,"ROW_CAP_EXCEEDED")
 cols,pk=TABLES[table]
 out={}
 for r in rows:
  require(type(r) is dict and set(r)==set(cols),"ROW_SHAPE_DRIFT")
  values=[typed(r[c]) for c in cols]
  identity=[typed(r[c]) for c in pk]
  require(all(v[1] is not None for v in identity),"NULL_PK_REJECTED")
  prefix=("d1:"+table+":").encode()
  key_bytes=json.dumps(identity,separators=(",",":"),ensure_ascii=False).encode()
  value_bytes=json.dumps(values,separators=(",",":"),ensure_ascii=False).encode()
  idh=hmac.new(key,b"pk:v1:"+prefix+key_bytes,hashlib.sha256).digest()
  rowh=hmac.new(key,b"row:v1:"+prefix+value_bytes,hashlib.sha256).digest()
  require(idh not in out,"DUPLICATE_PK")
  out[idh]=rowh
 return out

def compare(source_token,target_token,reader=remote):
 require(type(source_token) is str and type(target_token) is str and
         len(source_token)>=16 and len(target_token)>=16 and
         source_token!=target_token,"SEPARATE_AUDIT_TOKENS_REQUIRED")
 session=secrets.token_bytes(32)
 results={}
 for table in TABLES:
  src_meta=schema(reader(source_token,SOURCE,SOURCE_D1,META_SQL[table]),table)
  tgt_meta=schema(reader(target_token,TARGET,TARGET_D1,META_SQL[table]),table)
  require(src_meta==tgt_meta,"SCHEMA_METADATA_NOT_EQUAL")
  s1=fingerprint(reader(source_token,SOURCE,SOURCE_D1,DATA_SQL[table]),table,session)
  t1=fingerprint(reader(target_token,TARGET,TARGET_D1,DATA_SQL[table]),table,session)
  s2=fingerprint(reader(source_token,SOURCE,SOURCE_D1,DATA_SQL[table]),table,session)
  t2=fingerprint(reader(target_token,TARGET,TARGET_D1,DATA_SQL[table]),table,session)
  require(s1==s2 and t1==t2,"SNAPSHOT_UNSTABLE")
  shared=s2.keys() & t2.keys()
  changed=sum(s2[k]!=t2[k] for k in shared)
  matching=len(shared)-changed
  source_only=len(s2.keys()-t2.keys())
  target_only=len(t2.keys()-s2.keys())
  results[table]={
   "source_rows_observed":len(s2),"target_rows_observed":len(t2),
   "matching_key_payload_pairs":matching,
   "source_only_keys":source_only,"target_only_keys":target_only,
   "changed_payloads":changed,
   "schema_equal":True,"snapshot_stable_during_probe":True,
   "bounded_complete_table":True,
   "status":"EQUAL_SNAPSHOT_NOT_CUTOVER" if not(
    changed or source_only or target_only) else "DIFFERENT_SNAPSHOT_HOLD"
  }
 return {
  "status":"TWO_BOUNDED_TABLES_READ_ONLY_NOT_ACCOUNTWIDE_PARITY",
  "databases": {"runner3-content-intelligence":results},
  "max_rows_per_table_account":ROWS_CAP,
  "sensitive_keys_and_values_exported":False,
  "fingerprints_exported":False,"atomic_snapshot":False,
  "writer_quiescence_proven":False,"accountwide_row_parity_verified":False,
  "deletion_parity_verified":False,"cutover_ready":False,
  "d1_writes":0,"r2_requests":0,"worker_deploys":0
 }

def main():
 try:
  require(os.getenv("GITHUB_REPOSITORY")=="louisalviss/runner-3"
          and os.getenv("GITHUB_REF")=="refs/heads/main"
          and os.getenv("GITHUB_EVENT_NAME")=="workflow_dispatch"
          and not os.getenv("CLOUDFLARE_TARGET_D1_WRITE_TOKEN"),
          "UNTRUSTED_CONTEXT")
  result=compare(os.getenv("CLOUDFLARE_API_TOKEN",""),
                 os.getenv("CLOUDFLARE_TARGET_AUDIT_TOKEN_NEW",""))
  OUTPUT.parent.mkdir(parents=True,exist_ok=True)
  OUTPUT.write_text(json.dumps(result,sort_keys=True,indent=2)+"\n")
  print("TWO_PROFILE_TABLES_BOUNDED_HMAC_AUDIT_PASS NO_D1_WRITES")
  return 0
 except (Hold,TypeError,ValueError,OSError):
  print("TWO_PROFILE_TABLES_BOUNDED_HMAC_AUDIT_HOLD NO_D1_WRITES")
  return 3
if __name__=="__main__":
 raise SystemExit(main())
