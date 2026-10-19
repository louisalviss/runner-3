#!/usr/bin/env python3
"""Bounded, target-only D1 schema/primary-key encrypted manifest.

No row payload, COUNT(*), export, import, D1 mutation, Worker or R2 request.
No fallback to other account tokens. This is audit evidence, NOT row parity.
"""
import argparse
import base64
import secrets
import datetime as dt
import hashlib
import json
import os
import pathlib
import re
import sys
import urllib.error
import urllib.request

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

SOURCE = "7415a87f6bce7884e73ad7cfed5782df"
TARGET = "748a80810f77f447ee476543ef0e5014"
NAMES = ("clm-copilot-calibration", "clm-copilot-v1", "louis-task-context",
         "personal-library", "runner3-content-intelligence", "runner3-core",
         "runner3-opportunity-radar", "runner3-rss", "volamidle-rogue-data")
EXTRA_TARGET_REVIEW = "louis-context-index"
NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
SCHEMA_SQL = ("SELECT name,type,sql FROM sqlite_master "
              "WHERE type IN ('table','view','index','trigger') "
              "AND name NOT LIKE 'sqlite_%' ORDER BY type,name")
PRAGMA_SQL = re.compile(r'PRAGMA table_xinfo\("(?:[^"]|"")+"\)\Z')
MAX_DATABASES = 10
MAX_SCHEMA_OBJECTS = 256
MAX_TABLES_PER_DB = 80

class Blocked(Exception):
    pass

def ensure(ok, reason):
    if not ok:
        raise Blocked(reason)

def api(account, token, method, path, sql=None):
    ensure(account == TARGET, "TARGET_ACCOUNT_ONLY")
    ensure((method == "GET" and sql is None and
            path == "/d1/database?page=1&per_page=100") or
           (method == "POST" and isinstance(sql, str) and
            (sql == SCHEMA_SQL or PRAGMA_SQL.fullmatch(sql) is not None) and
            re.fullmatch(r"/d1/database/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/query", path) is not None),
           "NON_READ_ONLY_REQUEST")
    if method == "GET":
        ensure(path == "/d1/database?page=1&per_page=100", "GET_SCOPE_RESTRICTED")
    else:
        ensure(re.fullmatch(r'/d1/database/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/query', path) is not None,
               "POST_SCOPE_RESTRICTED")
    url = "https://api.cloudflare.com/client/v4/accounts/" + account + path
    req = urllib.request.Request(
        url, headers={"Authorization": "Bearer " + token,
                      "Content-Type": "application/json"},
        method=method,
        data=json.dumps({"sql": sql}).encode() if sql is not None else None)
    try:
        with urllib.request.urlopen(req, timeout=25) as response:
            ensure(response.status == 200, "HTTP_NON_200")
            body = response.read(1500001)
            ensure(len(body) <= 1500000, "RESPONSE_TOO_LARGE")
            result = json.loads(body)
    except urllib.error.HTTPError as e:
        raise Blocked("HTTP_" + str(e.code)) from None
    except (urllib.error.URLError, TimeoutError, ValueError):
        raise Blocked("NETWORK_OR_BAD_JSON") from None
    ensure(isinstance(result, dict) and result.get("success") is True,
           "API_NOT_SUCCESS")
    return result

def get_rows(response):
    result = response.get("result")
    ensure(isinstance(result, list) and len(result) == 1 and
           isinstance(result[0], dict) and
           result[0].get("success") is True and
           isinstance(result[0].get("results"), list), "BAD_QUERY_RESULT")
    meta = result[0].get("meta")
    ensure(meta is None or isinstance(meta, dict), "INVALID_QUERY_META")
    if meta is not None:
        ensure(("rows_written" not in meta or
                (type(meta["rows_written"]) is int and meta["rows_written"] == 0)) and
               ("changed_db" not in meta or meta["changed_db"] is False),
               "UNEXPECTED_DATABASE_MUTATION")
    return result[0]["results"]

def inventory(role, token, transport=api):
    ensure(role in ("source", "target"), "BAD_ROLE")
    account = SOURCE if role == "source" else TARGET
    ensure(isinstance(token, str) and len(token) >= 16, "TOKEN_UNAVAILABLE")
    response = transport(account, token, "GET",
                         "/d1/database?page=1&per_page=100")
    databases = response.get("result")
    info = response.get("result_info")
    ensure(isinstance(databases, list) and len(databases) <= MAX_DATABASES,
           "DATABASE_LIMIT_OR_FORMAT")
    ensure(isinstance(info, dict) and
           type(info.get("total_count")) is int and
           type(info.get("count")) is int and
           type(info.get("page")) is int and
           info["total_count"] == len(databases) and
           info["count"] == len(databases) and
           info["page"] == 1 and
           (info.get("total_pages") is None or
            (type(info["total_pages"]) is int and
             info["total_pages"] == 1)), "INCOMPLETE_D1_LIST")
    mapping = {}
    uuids = set()
    for item in databases:
        ensure(isinstance(item, dict), "BAD_D1_ITEM")
        name, uuid = item.get("name"), item.get("uuid")
        ensure(isinstance(name, str) and isinstance(uuid, str) and
               name not in mapping and uuid not in uuids and
               re.fullmatch(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", uuid), "DUPLICATE_OR_BAD_D1_ID")
        mapping[name] = uuid
        uuids.add(uuid)
    if role == "source":
        ensure(set(NAMES) <= set(mapping), "MISSING_SOURCE_D1")
    else:
        ensure(set(mapping) <= (set(NAMES) | {EXTRA_TARGET_REVIEW}),
               "UNREVIEWED_TARGET_DATABASE")
    report = {
        "evidence_class": "READ_ONLY_SCHEMA_ONLY_NOT_ROW_PARITY",
        "role": role, "account_id": account,
        "checked_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "database_names": sorted(mapping),
        "missing_required_names": sorted(set(NAMES) - set(mapping)),
        "historical_target_only_name_present": EXTRA_TARGET_REVIEW in mapping,
        "database_schemas": {},
        "row_key_content_parity_verified": False,
        "cutover_ready": False, "source_delete_allowed": False,
        "r2_requests": 0,
    }
    sql = SCHEMA_SQL
    for db_name in NAMES + ((EXTRA_TARGET_REVIEW,) if role == "target" else ()):
        if db_name not in mapping:
            continue
        path = "/d1/database/" + mapping[db_name] + "/query"
        objects = get_rows(transport(account, token, "POST", path, sql))
        ensure(len(objects) <= MAX_SCHEMA_OBJECTS, "TOO_MANY_SCHEMA_OBJECTS")
        schema = []
        seen = set()
        for entry in objects:
            ensure(isinstance(entry, dict), "BAD_SCHEMA_OBJECT")
            object_name, typ, definition = (entry.get("name"),
                                             entry.get("type"),
                                             entry.get("sql"))
            ensure(isinstance(object_name, str) and object_name and
                   len(object_name) <= 180 and "\x00" not in object_name and
                   object_name not in seen and
                   typ in ("table", "view", "index", "trigger"),
                   "UNSUPPORTED_SCHEMA_OBJECT")
            seen.add(object_name)
            ensure(definition is None or isinstance(definition, str), "BAD_DDL")
            schema.append({"name": object_name, "kind": typ,
                           "ddl_sha256": hashlib.sha256(
                               (definition or "").strip().encode("utf-8")).hexdigest()})
        tables = [x for x in schema if x["kind"] == "table" and x["name"] != "_cf_KV"]
        ensure(len(tables) <= MAX_TABLES_PER_DB, "TOO_MANY_TABLES")
        for table in tables:
            name = table["name"]
            cols = get_rows(transport(account, token, "POST", path,
                            'PRAGMA table_xinfo("' + name.replace('"', '""') + '")'))
            ensure(0 < len(cols) <= 120 and all(isinstance(x, dict) for x in cols),
                   "BAD_COLUMN_METADATA")
            pk_items = []
            for col in cols:
                ensure(isinstance(col.get("name"), str) and
                       type(col.get("pk")) is int and
                       0 <= col["pk"] <= 8, "BAD_PK_FIELD")
                if col["pk"] > 0:
                    ensure(bool(col["name"]) and len(col["name"]) <= 180 and
                           "\x00" not in col["name"], "BAD_PRIMARY_KEY_METADATA")
                    pk_items.append((col["pk"], col["name"]))
            pk_items.sort()
            ensure(len({rank for rank, _ in pk_items}) == len(pk_items),
                   "DUPLICATE_PK_ORDINAL")
            table["pk_columns"] = [v for _,v in pk_items]
            table["declared_pk_present"] = bool(pk_items)
            table["column_count"] = len(cols)
        report["database_schemas"][db_name] = {
            "schema_objects": schema, "schema_object_count": len(schema),
            "table_count": len(tables),
            "tables_without_declared_pk": [
                t["name"] for t in tables if not t["declared_pk_present"]],
        }
    return report

def self_test():
    def fake(account, token, method, path, sql=None):
        if method == "GET":
            return {"success": True, "result_info": {"page": 1,
                    "count": len(NAMES), "total_pages": 1,
                    "total_count": len(NAMES)},
                    "result": [{"name": n,
                    "uuid": "00000000-0000-0000-0000-" + format(i+1, "012x")}
                    for i,n in enumerate(NAMES)]}
        if sql.startswith("SELECT"):
            return {"success": True, "result": [{
                "success": True, "meta": {"rows_written": 0},
                "results": [{"name": "checkpoints", "type": "table",
                             "sql": "CREATE TABLE checkpoints (id INT PRIMARY KEY)"}]}]}
        return {"success": True, "result": [{"success": True,
                "meta": {"rows_written": 0},
                "results": [{"name": "id", "pk": 1}]}]}
    a = inventory("source", "dummy_token_for_offline", fake)
    b = inventory("target", "dummy_token_for_offline", fake)
    assert len(a["database_schemas"]) == len(NAMES) == 9
    assert all(x["table_count"] == 1
               for x in a["database_schemas"].values())
    assert a["cutover_ready"] is False and b["cutover_ready"] is False
    assert not a["missing_required_names"] and not b["missing_required_names"]
    try:
        inventory("target", "", fake)
        raise AssertionError("empty token accepted")
    except Blocked as e:
        assert str(e) == "TOKEN_UNAVAILABLE"
    # Reject incomplete target pagination without fetching anything beyond page 1.
    def incomplete(account, token, method, path, sql=None):
        d = fake(account, token, method, path, sql)
        if method == "GET":
            d["result_info"]["total_count"] += 1
        return d
    try:
        inventory("target", "dummy_token_for_offline", incomplete)
        raise AssertionError("truncated target list accepted")
    except Blocked as e:
        assert str(e) == "INCOMPLETE_D1_LIST"
    # Source census cannot silently skip one of nine authorities.
    def missing_source(account, token, method, path, sql=None):
        d = fake(account, token, method, path, sql)
        if method == "GET":
            d["result"].pop()
            d["result_info"]["total_count"] -= 1
            d["result_info"]["count"] -= 1
        return d
    try:
        inventory("source", "dummy_token_for_offline", missing_source)
        raise AssertionError("source missing one D1 was accepted")
    except Blocked as e:
        assert str(e) == "MISSING_SOURCE_D1"
    # Historic destination-only legacy context index gets schema audit too.
    def extra_target(account, token, method, path, sql=None):
        d = fake(account, token, method, path, sql)
        if method == "GET":
            d["result"].append({"name": EXTRA_TARGET_REVIEW,
                "uuid": "00000000-0000-0000-0000-000000000010"})
            d["result_info"]["total_count"] += 1
            d["result_info"]["count"] += 1
        return d
    extra = inventory("target", "dummy_token_for_offline", extra_target)
    assert EXTRA_TARGET_REVIEW in extra["database_schemas"]
    assert all(x['schema_objects'][0]['column_count'] == 1
               for x in extra['database_schemas'].values())
    assert PRAGMA_SQL.fullmatch('PRAGMA table_xinfo("Odd""Name")')
    assert not PRAGMA_SQL.fullmatch('PRAGMA table_xinfo("x"); DROP TABLE x')
    assert not PRAGMA_SQL.fullmatch('PRAGMA table_xinfo("x") ; SELECT 1')
    assert hashlib.sha256(b'CREATE TABLE x(id INT)').hexdigest() == hashlib.sha256(
        '  CREATE TABLE x(id INT)  '.strip().encode()).hexdigest()
    def internal_schema(account, token, method, path, sql=None):
        d = fake(account, token, method, path, sql)
        if sql and sql.startswith('SELECT'):
            d['result'][0]['results'].append({'name':'_cf_KV', 'type':'table',
                'sql':'CREATE TABLE _cf_KV(k TEXT)'})
        return d
    internal = inventory('target','dummy_token_for_offline',internal_schema)
    assert all(x['table_count']==1 for x in internal['database_schemas'].values())
    def unusual(account, token, method, path, sql=None):
        d = fake(account, token, method, path, sql)
        if sql and sql.startswith('SELECT'):
            d['result'][0]['results'][0]['name'] = 'Odd"Name'
        return d
    unusual_report = inventory('target','dummy_token_for_offline',unusual)
    assert all('Odd"Name' in [v['name'] for v in x['schema_objects']]
               for x in unusual_report['database_schemas'].values())
    def bad_count(account, token, method, path, sql=None):
        d = fake(account, token, method, path, sql)
        if method == 'GET': d['result_info']['count'] -= 1
        return d
    try:
        inventory('target','dummy_token_for_offline',bad_count)
        raise AssertionError('pagination count gap accepted')
    except Blocked as e:
        assert str(e) == 'INCOMPLETE_D1_LIST'
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pub = key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo)
    envelope = encrypt_manifest(extra, pub)
    sym = key.decrypt(base64.b64decode(envelope["wrapped_key"]),
        padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()),
                     algorithm=hashes.SHA256(), label=None))
    body = AESGCM(sym).decrypt(base64.b64decode(envelope["nonce"]),
        base64.b64decode(envelope["ciphertext"]),
        base64.b64decode(envelope["aad"]))
    assert json.loads(body)["role"] == "target"
    print("OFFLINE_D1_NINE_SCHEMA_CONTRACT: PASS (12 checks, 0 external requests)")

def encrypt_manifest(report, public_key_pem):
    public = serialization.load_pem_public_key(public_key_pem)
    key = secrets.token_bytes(32)
    nonce = secrets.token_bytes(12)
    aad = b"cf-d1-target-nine-schema-pk-v1"
    data = json.dumps(report, sort_keys=True, separators=(",", ":")).encode()
    encrypted = AESGCM(key).encrypt(nonce, data, aad)
    wrapped = public.encrypt(key,
        padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()),
                     algorithm=hashes.SHA256(), label=None))
    return {"version": 1, "kind": "target-nine-schema-pk-no-rows",
            "wrapped_key": base64.b64encode(wrapped).decode(),
            "nonce": base64.b64encode(nonce).decode(),
            "aad": base64.b64encode(aad).decode(),
            "ciphertext": base64.b64encode(encrypted).decode()}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--role", choices=("source", "target"))
    parser.add_argument("--self-test", action="store_true")
    options = parser.parse_args()
    if options.self_test:
        self_test()
        return 0
    ensure(options.role == "target", "TARGET_ONLY_NO_SOURCE_DUPLICATION")
    token = os.environ.get("CLOUDFLARE_TARGET_AUDIT_TOKEN", "")
    report = inventory("target", token)
    public_pem = pathlib.Path(
        "ops/cloudflare-account-rehome/courier-public-20261008.pem").read_bytes()
    encrypted = encrypt_manifest(report, public_pem)
    path = pathlib.Path("courier-out/d1-target-nine-schema-envelope.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(encrypted, sort_keys=True) + "\n")
    print("D1_TARGET_NINE_SCHEMA_ENCRYPTED_READY",
          "databases=" + str(len(report["database_schemas"])))
    return 0

if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (Blocked, OSError, ValueError, TypeError) as err:
        reason = str(err) if isinstance(err, Blocked) else "AUDIT_PROCESSING_ERROR"
        print("D1_SCHEMA_AUDIT_BLOCKED", reason)
        raise SystemExit(3) from None
