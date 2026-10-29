#!/usr/bin/env python3
"""Read-only GraphQL D1 write-query metric diagnostic for the TARGET account.

Exactly two known target D1s and four recent UTC calendar dates. No D1 SQL,
Worker, R2 or mutation. Never outputs token, GraphQL errors, database UUIDs,
query strings, tenant data, or credential values.
"""
import datetime as dt
import json
import os
import pathlib
import urllib.error
import urllib.request

ACCOUNT = "748a80810f77f447ee476543ef0e5014"
D1S = {
    "runner3-content-intelligence":"82613659-8d08-455f-b6e7-f8f6e4312e22",
    "runner3-core":"477fc6b8-4dec-4e15-afa7-eefa3846fba1",
}
GRAPHQL = "https://api.cloudflare.com/client/v4/graphql"
OUT = pathlib.Path("migration-out/target-d1-recent-write-metrics-readonly.json")
QUERY = """query TargetD1WriteMetrics($account: string!, $from: Date, $to: Date, $db: string) {
 viewer {
   accounts(filter: {accountTag: $account}) {
     d1AnalyticsAdaptiveGroups(
       limit: 12,
       filter: {date_geq: $from, date_leq: $to, databaseId: $db},
       orderBy: [date_DESC]
     ) {
       dimensions { date databaseId }
       sum { writeQueries }
     }
   }
 }
}"""

class Hold(Exception):
    pass

def require(ok,reason):
    if not ok: raise Hold(reason)

def read(token, name, start, end, opener=urllib.request.urlopen):
    require(name in D1S and isinstance(token,str) and len(token)>=16,
            "TOKEN_OR_DATABASE_MISSING")
    require(isinstance(start,dt.date) and isinstance(end,dt.date) and
            0 <= (end-start).days <= 4,"WINDOW_INVALID")
    payload={"query":QUERY,"variables":{
        "account":ACCOUNT,"from":start.isoformat(),"to":end.isoformat(),
        "db":D1S[name],
    }}
    request=urllib.request.Request(
        GRAPHQL, method="POST", data=json.dumps(payload).encode("utf-8"),
        headers={"Authorization":"Bearer "+token,
                 "Accept":"application/json","Content-Type":"application/json"})
    try:
        with opener(request,timeout=22) as response:
            status=response.status
            raw=response.read(100001)
    except urllib.error.HTTPError as error:
        # Never serialize error body, because upstream may return privileges.
        raise Hold("HTTP_"+str(int(error.code))) from None
    except (urllib.error.URLError,OSError,TimeoutError):
        raise Hold("NETWORK_UNAVAILABLE") from None
    require(status==200 and len(raw)<=100000,"HTTP_OR_SIZE_FAILURE")
    try:
        doc=json.loads(raw)
    except (ValueError,UnicodeError):
        raise Hold("BAD_API_JSON") from None
    require(type(doc) is dict and not doc.get("errors"),
            "GRAPHQL_UNAUTHORIZED_OR_SCHEMA_FAILURE")
    try:
        accounts=doc["data"]["viewer"]["accounts"]
        require(type(accounts) is list and len(accounts)==1,
                "TARGET_ACCOUNT_ANALYTICS_UNAVAILABLE")
        groups=accounts[0]["d1AnalyticsAdaptiveGroups"]
    except (KeyError,TypeError,IndexError):
        raise Hold("GRAPHQL_RESPONSE_INCOMPLETE") from None
    require(type(groups) is list and len(groups)<=12,"METRIC_GROUP_LIMIT")
    seen_dates=set()
    result=[]
    for group in groups:
        require(type(group) is dict and type(group.get("dimensions")) is dict
                and type(group.get("sum")) is dict,
                "BAD_ANALYTICS_RECORD")
        dims=group["dimensions"]; totals=group["sum"]
        day=dims.get("date")
        try: parsed=dt.date.fromisoformat(day)
        except (TypeError,ValueError): raise Hold("BAD_DATE") from None
        q=totals.get("writeQueries")
        require(start<=parsed<=end and dims.get("databaseId")==D1S[name]
                and day not in seen_dates and type(q) in (int,float) and
                q>=0 and q==int(q),"INVALID_METRIC")
        seen_dates.add(day)
        result.append({"date_utc":day,"write_queries":int(q)})
    return sorted(result,key=lambda x:x["date_utc"])

def assess(token,now=None,reader=read):
    require(isinstance(token,str) and len(token)>=16,"AUDIT_SECRET_MISSING")
    now=now or dt.datetime.now(dt.timezone.utc)
    require(now.tzinfo is not None,"UNZONED_NOW")
    end=now.astimezone(dt.timezone.utc).date()
    start=end-dt.timedelta(days=3)
    reports={}
    for name in sorted(D1S):
        day_metrics=reader(token,name,start,end)
        require(type(day_metrics) is list and len(day_metrics)<=4,
                "BAD_READER_RESULT")
        total=sum(x["write_queries"] for x in day_metrics)
        reports[name]={"days_returned":len(day_metrics),
                       "write_queries_in_returned_groups":total,
                       "days":day_metrics,
                       "write_activity_detected":total>0}
    return {
        "status":"D1_TARGET_HISTORICAL_WRITE_QUERY_METRICS_ONLY",
        "calendar_window_utc":{"from":start.isoformat(),"to":end.isoformat()},
        "databases":reports,
        "analytics_api_available":True,
        "live_writer_identity_verified":False,
        "writer_quiescence_proven":False,
        "queries_reflect_ongoing_inflight_requests":False,
        "data_row_parity_verified":False,"cutover_ready":False,
        "cloudflare_http_methods":["POST_READONLY_GRAPHQL"],
        "d1_sql_requests":0,"d1_writes":0,"r2_requests":0,
        "worker_deploys":0
    }

def main():
    try:
        require(os.getenv("GITHUB_REPOSITORY")=="louisalviss/runner-3"
                and os.getenv("GITHUB_REF")=="refs/heads/main"
                and os.getenv("GITHUB_EVENT_NAME")=="workflow_dispatch"
                and not os.getenv("CLOUDFLARE_TARGET_D1_WRITE_TOKEN"),
                "UNTRUSTED_WORKFLOW")
        result=assess(os.getenv("CLOUDFLARE_TARGET_AUDIT_TOKEN_NEW",""))
        OUT.parent.mkdir(parents=True,exist_ok=True)
        OUT.write_text(json.dumps(result,sort_keys=True,indent=2)+"\n")
        print("D1_TARGET_WRITE_METRICS_READ_ONLY_PASS, quiescence=false")
        return 0
    except (Hold,TypeError,ValueError,KeyError,OverflowError):
        print("D1_TARGET_WRITE_METRICS_UNAVAILABLE_OR_HOLD")
        return 3

if __name__=="__main__":
    raise SystemExit(main())
