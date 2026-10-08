#!/usr/bin/env python3
import datetime
import json
import os
import sys
import urllib.error
import urllib.request

BASE = "https://api.cloudflare.com/client/v4"
HARD_LIMIT = 100000
READ_HARD_LIMIT = 5000000
READ_SAFE_CEILING = 4000000

def request_json(url, headers, method="GET", payload=None):
    body = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            return response.status, json.loads(response.read().decode())
    except urllib.error.HTTPError as exc:
        try:
            data = json.loads(exc.read().decode())
        except Exception:
            data = {}
        return exc.code, data

def main():
    token = os.environ["CF_TOKEN"]
    account = os.environ["CF_ACCOUNT"]
    planned = int(os.environ.get("D1_PLANNED_ROWS", "0"))
    ceiling = int(os.environ.get("D1_SAFE_CEILING", "70000"))
    planned_reads = int(os.environ.get("D1_PLANNED_READ_ROWS", "0"))
    read_ceiling = int(os.environ.get("D1_READ_SAFE_CEILING", "4000000"))
    if planned < 0:
        raise SystemExit("D1_PLANNED_ROWS must be >= 0")
    if not (1 <= ceiling < HARD_LIMIT):
        raise SystemExit("D1_SAFE_CEILING must be between 1 and 99999")
    if planned_reads < 0 or not (1 <= read_ceiling <= READ_SAFE_CEILING):
        raise SystemExit("Invalid D1 read budget")

    headers = {
        "Authorization": "Bearer " + token,
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    code, db_data = request_json(f"{BASE}/accounts/{account}/d1/database?page=1&per_page=1000", headers)
    if code != 200:
        raise SystemExit(f"D1 inventory failed: HTTP {code}")
    inventory = {
        str(x.get("uuid")): str(x.get("name") or x.get("uuid"))
        for x in db_data.get("result", [])
        if x.get("uuid")
    }

    today = datetime.datetime.now(datetime.timezone.utc).date().isoformat()
    query = """query Usage($accountTag: string, $dateStart: Date, $dateEnd: Date) {
      viewer { accounts(filter: {accountTag: $accountTag}) {
        d1AnalyticsAdaptiveGroups(limit: 10000, filter: {date_geq: $dateStart, date_leq: $dateEnd}) {
          dimensions { databaseId }
          sum { readQueries writeQueries rowsRead rowsWritten }
        }
      }}
    }"""
    code, data = request_json(
        BASE + "/graphql",
        headers,
        "POST",
        {"query": query, "variables": {"accountTag": account, "dateStart": today, "dateEnd": today}},
    )
    if code != 200 or data.get("errors"):
        raise SystemExit(f"Cloudflare GraphQL failed: HTTP {code} errors={data.get('errors', [])[:2]}")

    rows = data["data"]["viewer"]["accounts"][0]["d1AnalyticsAdaptiveGroups"]
    per_db = {}
    for row in rows:
        dbid = str((row.get("dimensions") or {}).get("databaseId") or "")
        if not dbid:
            continue
        sums = row.get("sum") or {}
        cur = per_db.setdefault(
            dbid,
            {"databaseId": dbid, "database": inventory.get(dbid, dbid), "rowsWritten": 0, "writeQueries": 0},
        )
        cur["rowsWritten"] += int(sums.get("rowsWritten") or 0)
        cur["writeQueries"] += int(sums.get("writeQueries") or 0)

    databases = sorted(per_db.values(), key=lambda x: x["rowsWritten"], reverse=True)
    current = sum(x["rowsWritten"] for x in databases)
    projected = current + planned
    allowed = projected <= ceiling
    result = {
        "ok": allowed,
        "dateUtc": today,
        "currentRowsWritten": current,
        "plannedRows": planned,
        "projectedRowsWritten": projected,
        "safeCeiling": ceiling,
        "hardLimit": HARD_LIMIT,
        "headroomToSafeCeiling": ceiling - current,
        "headroomToHardLimit": HARD_LIMIT - current,
        "databases": databases,
    }
    print(json.dumps(result, indent=2))
    if not allowed:
        print(
            f"::error::D1_BUDGET_BLOCKED current={current} planned={planned} "
            f"projected={projected} ceiling={ceiling}",
            file=sys.stderr,
        )
        raise SystemExit(3)
    print(f"D1_BUDGET_PASS current={current} planned={planned} projected={projected} ceiling={ceiling}")

if __name__ == "__main__":
    main()
