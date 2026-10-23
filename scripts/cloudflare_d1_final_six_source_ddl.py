#!/usr/bin/env python3
"""Explicitly manual SOURCE-only, bounded D1 applied-DDL capture for six gaps.

Never reads application rows, copies D1 data, writes SQL, requests R2, handles
courier keys, edits Workers, or contacts TARGET. Output is sensitive operational
schema: keep the private Actions artifact restricted and short-lived.
"""
import datetime as dt
import hashlib
import json
import os
import pathlib
import re
import urllib.error
import urllib.request

ACCOUNT = "7415a87f6bce7884e73ad7cfed5782df"
DATABASES = {
    "runner3-core": "514a2c61-3f7a-44d0-a51b-e07525d32a5d",
    "runner3-content-intelligence": "9cbec4ec-c930-459d-9499-9c66166c9241",
}
# Exact authenticated source-only object ID -> full DDL+PRAGMA metadata hash,
# paired against target-absent IDs in Oct 22 run #39826582807.
GAPS = {
    "runner3-core": {
        "bacfd8bda79da42d7bb97e40771d7c2aa2b73ef1ff11dd03a39812e7a495c85d": "15c92b75dd064ac6fe24e8fa52e42c9b2ce4a3e09c370bb985df2ee9cf12a5f3",  # typed_kv
        "ac6aacf633978a782d237ad1a59457699b40ca46f81d282fb793c1118e1c83a1": "ff01018641b71ce8146b5608ad6c33f6c5cad145499b016a49740a599651bf52",  # r2_receipts
        "5c8a020e2f8385e1a4aad4bbc62cb1d3f6779a7351b261e032183ca36499e306": "71934da0930b70a93130fe061ac6a4409385a64421ebc801b27e546956fa39dd",  # d1_migrations
    },
    "runner3-content-intelligence": {
        "35073a14230f9b77433409815f719cf322914f2aaaf1cbddb960f668164566cf": "c08818201cfd6d8fb3a26e14f6bed40a131e8abaa9f84c5f0f574b3c2c734456",  # link_interest_events
        "051949606d6f5fada917fdf190f98379802546af2829a17845076323e3d577a8": "ed16a1355648942c6d653cc647f3d275a734cf06148260d1bf2a8b0e4129eb50",  # unknown kind/name
        "7217ecdaa220de7e8cd00527f462853b9269c228eb4e49a35b450eda1ebefd02": "3cea11590e7b405451d54efab10179d095242166acddb5a686652391909a92ee",  # unknown kind/name
    },
}
KNOWN_CORE_TABLES = frozenset(("typed_kv", "r2_receipts", "d1_migrations"))
SQL_MASTER = ("SELECT type,name,sql FROM sqlite_master WHERE "
              "type IN ('table','index','trigger','view') AND "
              "name NOT LIKE 'sqlite_%' ORDER BY type,name")
MAX_BYTES = 250_000
MAX_OBJECTS_PER_DB = 150
MAX_QUERY_CALLS = 12
OUT = pathlib.Path("migration-out/d1-final-six-source-applied-ddl.json")
HEX64 = re.compile(r"[0-9a-f]{64}\Z")
NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]{0,127}\Z")
FIELDS = ("cid", "name", "type", "notnull", "dflt_value", "pk", "hidden")


class Hold(ValueError):
    pass


def require(ok, code):
    if not ok:
        raise Hold(code)


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False,
        sort_keys=True, separators=(",", ":")).encode("utf8")).hexdigest()


def pragma(name):
    require(isinstance(name, str) and NAME.fullmatch(name), "UNSAFE_TABLE_NAME")
    return 'PRAGMA table_xinfo("' + name + '")'


def parse_api(raw):
    require(isinstance(raw, dict) and raw.get("success") is True,
            "SOURCE_QUERY_API_FAILURE")
    rows = raw.get("result")
    require(isinstance(rows, list) and len(rows) == 1 and
            isinstance(rows[0], dict) and rows[0].get("success") is True and
            isinstance(rows[0].get("results"), list), "SOURCE_QUERY_RESULT_INVALID")
    meta = rows[0].get("meta")
    require(isinstance(meta, dict) and
            type(meta.get("rows_written", 0)) is int and
            meta.get("rows_written", 0) == 0 and
            meta.get("changed_db", False) is False,
            "UNEXPECTED_MUTATION_OR_MISSING_METADATA")
    return rows[0]["results"]


def query(token, database, sql):
    require(database in DATABASES and
            (sql == SQL_MASTER or
             re.fullmatch(r'PRAGMA table_xinfo\("[A-Za-z_][A-Za-z0-9_]{0,127}"\)', sql)),
            "SQL_NOT_ALLOWLISTED")
    url = ("https://api.cloudflare.com/client/v4/accounts/" + ACCOUNT +
           "/d1/database/" + DATABASES[database] + "/query")
    req = urllib.request.Request(url, method="POST",
        data=json.dumps({"sql": sql}).encode("utf8"), headers={
        "Authorization": "Bearer " + token,
        "Content-Type": "application/json", "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=25) as response:
            require(response.status == 200, "HTTP_NON_200")
            raw = response.read(MAX_BYTES + 1)
    except urllib.error.HTTPError as error:
        raise Hold("SOURCE_HTTP_" + str(error.code)) from None
    except (urllib.error.URLError, TimeoutError, OSError):
        raise Hold("SOURCE_UNAVAILABLE") from None
    require(len(raw) <= MAX_BYTES, "RESPONSE_TOO_LARGE")
    try:
        data = json.loads(raw)
    except (ValueError, UnicodeError):
        raise Hold("API_JSON_INVALID") from None
    return parse_api(data)


def table_metadata(kind, name, ddl, column_rows):
    payload = {"ddl_sha256": hashlib.sha256(ddl.strip().encode("utf8")).hexdigest()}
    if kind == "table":
        require(isinstance(column_rows, list) and 1 <= len(column_rows) <= 120,
                "TABLE_COLUMNS_NOT_BOUNDED")
        cols, names, cids, pks = [], set(), set(), []
        for c in column_rows:
            require(isinstance(c, dict), "TABLE_COLUMN_INVALID")
            row = {f: c.get(f) for f in FIELDS}
            if row["cid"] is None:
                row["cid"] = len(cols)
            require(isinstance(row["name"], str) and bool(row["name"]) and
                    type(row["cid"]) is int and row["cid"] >= 0 and
                    row["name"] not in names and row["cid"] not in cids and
                    type(row["pk"]) is int and 0 <= row["pk"] <= 8,
                    "TABLE_COLUMN_IDENTITY_INVALID")
            names.add(row["name"])
            cids.add(row["cid"])
            if row["pk"]:
                pks.append((row["pk"], row["name"]))
            cols.append(row)
        require(len({n for n, _ in pks}) == len(pks), "PRIMARY_KEY_ORDER_DUPLICATE")
        cols.sort(key=lambda c: c["cid"])
        payload.update(pk_columns=[n for _, n in sorted(pks)],
                       column_count=len(cols), columns_sha256=digest(cols))
    return digest(payload)


def capture(token, reader=query):
    require(isinstance(token, str) and len(token) >= 16,
            "SOURCE_TOKEN_UNAVAILABLE")
    # Six data-independent DDL objects maximum; reject a drifted source catalog.
    result = {}
    calls = 0
    for database, wanted in GAPS.items():
        objects = reader(token, database, SQL_MASTER)
        calls += 1
        require(isinstance(objects, list) and len(objects) <= MAX_OBJECTS_PER_DB,
                "SOURCE_OBJECT_SET_OVERSIZED")
        selected = {}
        for o in objects:
            require(isinstance(o, dict), "SOURCE_OBJECT_INVALID")
            kind, name, ddl = o.get("type"), o.get("name"), o.get("sql")
            require(kind in ("table","index","trigger","view") and
                    isinstance(name, str) and bool(NAME.fullmatch(name)),
                    "SOURCE_OBJECT_IDENTITY_INVALID")
            object_id = digest([kind, name])
            if object_id not in wanted:
                continue
            require(isinstance(ddl, str) and 15 <= len(ddl) <= 8192 and
                    "\x00" not in ddl and
                    re.match(r"(?is)^CREATE\s+(?:UNIQUE\s+)?"+kind+r"\s+", ddl) and
                    object_id not in selected, "SOURCE_DDL_INVALID_OR_DUPLICATE")
            cols = None
            if kind == "table":
                cols = reader(token, database, pragma(name))
                calls += 1
            actual = table_metadata(kind, name, ddl, cols)
            require(actual == wanted[object_id], "SOURCE_SCHEMA_METADATA_DRIFT")
            selected[object_id] = {"kind": kind, "name": name, "ddl": ddl,
                                   "object_id": object_id,
                                   "source_metadata_sha256": actual}
        require(set(selected) == set(wanted), "SOURCE_GAP_OBJECT_CENSUS_DRIFT")
        if database == "runner3-core":
            require({v["name"] for v in selected.values()} == KNOWN_CORE_TABLES and
                    all(v["kind"] == "table" for v in selected.values()),
                    "SOURCE_CORE_NAMES_OR_TYPES_DRIFT")
        result[database] = [selected[oid] for oid in sorted(selected)]
    require(calls <= MAX_QUERY_CALLS and sum(map(len, result.values())) == 6,
            "READ_BUDGET_OR_SCOPE_EXCEEDED")
    return {"format": "d1-six-applied-schema-source-v1",
            "checked_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
            "source_account_id": ACCOUNT,
            "source_schema_reference_run": 39826582807,
            "evidence": "READ_ONLY_SQLITE_MASTER_AND_TABLE_XINFO_ONLY",
            "databases": result, "object_count": 6, "source_query_count": calls,
            "raw_application_rows_read": 0, "source_d1_writes": 0,
            "target_d1_queries": 0, "target_d1_writes": 0, "r2_requests": 0,
            "worker_deploys": 0, "row_parity_verified": False,
            "cutover_ready": False}


def main():
    # Workflow must only expose its source-scoped read-only account token.
    if os.environ.get("CLOUDFLARE_TARGET_AUDIT_TOKEN") or os.environ.get("CF_TOKEN"):
        print("SOURCE_SCHEMA_GAP_BLOCKED UNEXPECTED_CROSS_ACCOUNT_TOKEN")
        return 3
    try:
        output = capture(os.environ.get("CLOUDFLARE_API_TOKEN", ""))
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(json.dumps(output, ensure_ascii=False, sort_keys=True,
                                  indent=2) + "\n", encoding="utf8")
    except Hold as error:
        print("SOURCE_SCHEMA_GAP_BLOCKED", str(error))
        return 3
    except (OSError, UnicodeError, TypeError, ValueError):
        print("SOURCE_SCHEMA_GAP_BLOCKED INTERNAL_OR_IO_ERROR")
        return 3
    print("SOURCE_SCHEMA_GAP_PROOF 6/6 METADATA_MATCH no_rows no_d1_writes no_r2")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
