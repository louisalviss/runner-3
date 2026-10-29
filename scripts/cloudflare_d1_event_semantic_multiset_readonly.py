#!/usr/bin/env python3
"""Read-only semantic MULTISET parity for D1 user_content_events.

Numeric AUTOINCREMENT id belongs to each database, so never join ids across
accounts. Compare occurrence counts of typed entire semantic event payload
(without id) using a random per-run HMAC key in RAM, including duplicates.
No raw events, keys, event bodies, HMACs or row IDs exported; no D1 writes.
"""
import collections
import datetime as dt
import hashlib
import hmac
import json
import os
import pathlib
import secrets
import urllib.error
import urllib.request

SOURCE = "7415a87f6bce7884e73ad7cfed5782df"
TARGET = "748a80810f77f447ee476543ef0e5014"
SOURCE_D1 = "9cbec4ec-c930-459d-9499-9c66166c9241"
TARGET_D1 = "82613659-8d08-455f-b6e7-f8f6e4312e22"
COLUMNS=("id","item_id","render_id","event_type","assistant_recommended",
         "assistant_rank","explicit_feedback","context_json","event_at")
SEMANTIC=COLUMNS[1:]
SQL=('SELECT '+','.join('"'+c+'"' for c in COLUMNS)+
     ' FROM "user_content_events" WHERE "id" > ? ORDER BY "id" LIMIT 100')
PAGE=100
ROW_CAP=9000
PAGE_CAP=91
MAX_BODY=900000
MAX_PAGE_ROWS_READ=500
OUT=pathlib.Path("migration-out/d1-event-semantic-multiset-parity-readonly.json")

class Hold(Exception): pass
def require(condition,reason):
    if not condition:raise Hold(reason)

def remote(token,account,db,cursor,opener=urllib.request.urlopen):
    require(type(token) is str and len(token)>=16 and
            (account,db) in ((SOURCE,SOURCE_D1),(TARGET,TARGET_D1)) and
            type(cursor) is int and -(2**63)<=cursor<2**63,
            "WRONG_SCOPE_OR_CURSOR")
    request=urllib.request.Request(
      "https://api.cloudflare.com/client/v4/accounts/"+account+
      "/d1/database/"+db+"/query",method="POST",
      data=json.dumps({"sql":SQL,"params":[str(cursor)]}).encode(),
      headers={"Authorization":"Bearer "+token,"Accept":"application/json",
               "Content-Type":"application/json"})
    try:
        with opener(request,timeout=25) as res:
            require(res.status==200,"D1_HTTP_NON_200")
            raw=res.read(MAX_BODY+1)
    except urllib.error.HTTPError as err:
        raise Hold("D1_HTTP_"+str(int(err.code))) from None
    except (urllib.error.URLError,OSError,TimeoutError):
        raise Hold("D1_NETWORK_UNAVAILABLE") from None
    require(len(raw)<=MAX_BODY,"EVENT_PAGE_HTTP_SIZE_LIMIT")
    try:body=json.loads(raw)
    except (ValueError,UnicodeError):raise Hold("D1_BAD_JSON") from None
    require(type(body) is dict and body.get("success") is True,
            "D1_API_FAILURE")
    parts=body.get("result")
    require(type(parts) is list and len(parts)==1 and type(parts[0]) is dict
            and parts[0].get("success") is True and
            type(parts[0].get("results")) is list,"D1_RESPONSE_SHAPE")
    metadata=parts[0].get("meta") or {}
    read=metadata.get("rows_read")
    require(type(metadata) is dict and metadata.get("rows_written",0)==0
            and metadata.get("changed_db",False) is False and
            (read is None or (type(read) is int and
             0<=read<=MAX_PAGE_ROWS_READ)),"D1_READ_COST_OR_WRITE_HOLD")
    return parts[0]["results"]

def typed(value):
    if value is None:return ["null",None]
    if type(value) is str:return ["text",value]
    if type(value) is int:return ["integer",value]
    if type(value) is float:
        require(value==value and abs(value)!=float("inf"),"NONFINITE_VALUE")
        return ["real",repr(value)]
    raise Hold("UNSUPPORTED_EVENT_VALUE_TYPE")

def event_hmac(row,key):
    require(type(row) is dict and set(row)==set(COLUMNS)
            and type(row["id"]) is int
            and -(2**63)<row["id"]<2**63
            and type(row["item_id"]) is str
            and 0<len(row["item_id"])<=256
            and type(row["event_type"]) is str
            and 0<len(row["event_type"])<=128,
            "EVENT_ROW_INVALID")
    payload=json.dumps([typed(row[c]) for c in SEMANTIC],
                       ensure_ascii=False,separators=(",",":"),
                       allow_nan=False).encode("utf-8")
    return hmac.new(key,b"d1:user_content_events:semantic:v1:"+payload,
                    hashlib.sha256).digest()

def capture(token,account,db,key,reader=remote):
    counter=collections.Counter()
    n=0
    cursor=-(2**63)
    for page in range(PAGE_CAP):
        rows=reader(token,account,db,cursor)
        require(type(rows) is list and len(rows)<=PAGE,
                "EVENT_PAGE_ROWS_LIMIT")
        for row in rows:
            require(type(row) is dict and type(row.get("id")) is int and
                    row["id"]>cursor,"EVENT_PK_NOT_ORDERED")
            cursor=row["id"]
            counter[event_hmac(row,key)]+=1
            n+=1
            require(n<=ROW_CAP,"EVENT_TOTAL_ROW_CAP")
        if len(rows)<PAGE:
            return counter,n
    raise Hold("EVENT_PAGINATION_CAP")

def compare(source_token,target_token,reader=remote):
    require(type(source_token) is str and type(target_token) is str and
            len(source_token)>=16 and len(target_token)>=16 and
            source_token!=target_token,"SEPARATE_AUDIT_TOKENS")
    ephemeral=secrets.token_bytes(32)
    sa,nsa=capture(source_token,SOURCE,SOURCE_D1,ephemeral,reader)
    ta,nta=capture(target_token,TARGET,TARGET_D1,ephemeral,reader)
    sb,nsb=capture(source_token,SOURCE,SOURCE_D1,ephemeral,reader)
    tb,ntb=capture(target_token,TARGET,TARGET_D1,ephemeral,reader)
    require(sa==sb and ta==tb and nsa==nsb and nta==ntb,
            "EVENT_SEQUENTIAL_SNAPSHOTS_UNSTABLE")
    shared=sum((sb & tb).values())
    only_source=sum((sb-tb).values())
    only_target=sum((tb-sb).values())
    require(shared+only_source==nsb and shared+only_target==ntb,
            "MULTISET_ACCOUNTING_FAILED")
    return {
        "status":"EVENT_SEMANTIC_MULTISET_READONLY_NOT_CUTOVER",
        "checked_utc":dt.datetime.now(dt.timezone.utc).isoformat(),
        "database":"runner3-content-intelligence",
        "table":"user_content_events",
        "source_events_observed":nsb,
        "target_events_observed":ntb,
        "semantically_matching_event_occurrences":shared,
        "source_only_event_occurrences":only_source,
        "target_only_event_occurrences_preserve":only_target,
        "duplicate_semantic_occurrences_source":sum(v-1 for v in sb.values()),
        "duplicate_semantic_occurrences_target":sum(v-1 for v in tb.values()),
        "event_id_joined_across_accounts":False,
        "semantic_fields_compared":list(SEMANTIC),
        "sequential_reads_stable":True,
        "atomic_cross_account_snapshot":False,
        "event_occurrence_identity_proven":False,
        "safe_event_replay_approved":False,
        "deletion_lineage_verified":False,
        "writer_quiescence_verified":False,
        "rollback_ready":False,
        "raw_keys_events_hmacs_exported":False,
        "max_event_rows_per_account":ROW_CAP,
        "d1_writes":0,"r2_requests":0,"worker_deploys":0,
        "cutover_ready":False,
    }

def main():
    try:
        require(os.getenv("GITHUB_REPOSITORY")=="louisalviss/runner-3"
                and os.getenv("GITHUB_REF")=="refs/heads/main"
                and os.getenv("GITHUB_EVENT_NAME")=="workflow_dispatch"
                and not os.getenv("CLOUDFLARE_TARGET_D1_WRITE_TOKEN"),
                "UNTRUSTED_RUN_CONTEXT")
        result=compare(os.getenv("CLOUDFLARE_API_TOKEN",""),
                       os.getenv("CLOUDFLARE_TARGET_AUDIT_TOKEN_NEW",""))
        OUT.parent.mkdir(parents=True,exist_ok=True)
        OUT.write_text(json.dumps(result,sort_keys=True,indent=2)+"\n")
        print("EVENT_SEMANTIC_MULTISET_AUDIT_PASS matches",
              result["semantically_matching_event_occurrences"],
              "source_only",result["source_only_event_occurrences"],
              "target_only",result["target_only_event_occurrences_preserve"],
              "NO_WRITES")
        return 0
    except Hold as err:
        print("EVENT_SEMANTIC_MULTISET_AUDIT_HOLD",str(err),"NO_WRITES")
        return 3
    except (TypeError,ValueError,OSError,UnicodeError):
        print("EVENT_SEMANTIC_MULTISET_AUDIT_HOLD INTERNAL_FAILURE NO_WRITES")
        return 3

if __name__=="__main__":
    raise SystemExit(main())
