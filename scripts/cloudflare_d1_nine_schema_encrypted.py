#!/usr/bin/env python3
"""Source-only D1 nine-database schema and PK audit; no table row scans.

This audit does not copy any database, read table payloads, or verify source->target
parity. Its result is an RSA/AES-encrypted receipt readable only by the
existing migration courier private key. GitHub Actions dispatch remains manual.
"""
import base64
import datetime
import hashlib
import json
import os
import pathlib
import re
import secrets
import urllib.error
import urllib.request

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

SOURCE_ACCOUNT = "7415a87f6bce7884e73ad7cfed5782df"
EXPECTED_DATABASES = frozenset((
    "clm-copilot-calibration", "clm-copilot-v1", "louis-task-context",
    "personal-library", "runner3-content-intelligence", "runner3-core",
    "runner3-opportunity-radar", "runner3-rss", "volamidle-rogue-data",
))
API_BASE = "https://api.cloudflare.com/client/v4"
PUBLIC_KEY_PATH = pathlib.Path("ops/cloudflare-account-rehome/courier-public-20261008.pem")
OUTPUT_PATH = pathlib.Path("courier-out/d1-nine-schema-source-envelope.json")
MAX_TABLES_PER_DB = 80
MAX_COLUMNS_PER_TABLE = 120
MAX_RESP_BYTES = 1_000_000
SCHEMA_SQL = ("SELECT type, name, tbl_name, sql FROM sqlite_master "
              "WHERE type IN ('table','view','index','trigger') "
              "AND name NOT LIKE 'sqlite_%' ORDER BY type, name")
UUID_RE = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\Z")

class AuditBlocked(Exception):
    pass

COLUMN_METADATA_FIELDS = ("cid", "name", "type", "notnull", "dflt_value", "pk", "hidden")

def column_schema_hash(columns):
    """Digest column metadata only; no table payload access."""
    if not isinstance(columns, list) or not 0 < len(columns) <= 120:
        raise AuditBlocked("BAD_COLUMN_SET")
    rows, seen_names, seen_cids = [], set(), set()
    for index, column in enumerate(columns):
        if not isinstance(column, dict):
            raise AuditBlocked("BAD_COLUMN_RECORD")
        row = {k: column.get(k) for k in COLUMN_METADATA_FIELDS}
        if row["cid"] is None:
            row["cid"] = index
        name, cid = row["name"], row["cid"]
        if (not isinstance(name, str) or not name or len(name) > 180 or
                "\x00" in name or name in seen_names or
                type(cid) is not int or cid < 0 or cid in seen_cids):
            raise AuditBlocked("BAD_COLUMN_IDENTITY")
        seen_names.add(name)
        seen_cids.add(cid)
        rows.append(row)
    rows.sort(key=lambda row: row["cid"])
    return hashlib.sha256(json.dumps(rows, sort_keys=True,
        separators=(",", ":"), ensure_ascii=False).encode("utf-8")).hexdigest()



def request_json(token, method, route, payload=None):
    if method not in ("GET", "POST") or not route.startswith("/accounts/" + SOURCE_ACCOUNT + "/"):
        raise AuditBlocked("UNAUTHORIZED_ROUTE")
    if method == "POST":
        # D1 query endpoint uses HTTP POST for read-only SQL. No generic SQL executor.
        if (re.fullmatch(r"/accounts/" + SOURCE_ACCOUNT + r"/d1/database/" +
                         r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/query",
                         route) is None or not isinstance(payload, dict)):
            raise AuditBlocked("UNAUTHORIZED_SQL_ROUTE")
        sql = payload.get("sql", "")
        if sql != SCHEMA_SQL and not re.fullmatch(r'PRAGMA table_xinfo\("(?:[^"]|"")+"\)', sql):
            raise AuditBlocked("UNAUTHORIZED_SQL")
    else:
        if payload is not None or route != "/accounts/" + SOURCE_ACCOUNT + "/d1/database?page=1&per_page=100":
            raise AuditBlocked("UNAUTHORIZED_GET")
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(API_BASE + route, data=data, method=method, headers={
        "Authorization": "Bearer " + token,
        "Accept": "application/json", "Content-Type": "application/json",
    })
    try:
        with urllib.request.urlopen(req, timeout=25) as response:
            if response.status != 200:
                raise AuditBlocked("NON_200")
            raw = response.read(MAX_RESP_BYTES + 1)
    except urllib.error.HTTPError as exc:
        raise AuditBlocked("HTTP_" + str(exc.code)) from None
    except (urllib.error.URLError, TimeoutError, OSError):
        raise AuditBlocked("REMOTE_UNAVAILABLE") from None
    if len(raw) > MAX_RESP_BYTES:
        raise AuditBlocked("RESPONSE_TOO_LARGE")
    try:
        value = json.loads(raw)
    except (ValueError, UnicodeError):
        raise AuditBlocked("BAD_API_JSON") from None
    if not isinstance(value, dict) or value.get("success") is not True:
        raise AuditBlocked("API_NOT_SUCCESS")
    return value


def parse_db_inventory(value):
    items = value.get("result")
    info = value.get("result_info")
    if not isinstance(items, list) or len(items) > 100 or not isinstance(info, dict):
        raise AuditBlocked("D1_INVENTORY_SHAPE")
    if (type(info.get("page")) is not int or info["page"] != 1 or
        type(info.get("count")) is not int or info["count"] != len(items) or
        type(info.get("total_count")) is not int or info["total_count"] != len(items)):
        raise AuditBlocked("D1_INVENTORY_PAGINATION_INCOMPLETE")
    total_pages = info.get("total_pages")
    if total_pages is not None and (type(total_pages) is not int or total_pages != 1):
        raise AuditBlocked("D1_INVENTORY_PAGINATION_INCOMPLETE")
    names = {}
    for entry in items:
        if not isinstance(entry, dict):
            raise AuditBlocked("D1_INVENTORY_ENTRY")
        name, uid = entry.get("name"), entry.get("uuid")
        if not isinstance(name, str) or not isinstance(uid, str) or not UUID_RE.fullmatch(uid):
            raise AuditBlocked("D1_IDENTITY_INVALID")
        if name in names:
            raise AuditBlocked("D1_DUPLICATE_NAME")
        names[name] = uid
    if not EXPECTED_DATABASES.issubset(names):
        raise AuditBlocked("SOURCE_REQUIRED_DATABASE_MISSING")
    if set(names) != EXPECTED_DATABASES:
        raise AuditBlocked("SOURCE_UNEXPECTED_DATABASE")
    if len(set(names.values())) != len(names):
        raise AuditBlocked("SOURCE_DUPLICATE_UUID")
    return names


def results(value):
    raw = value.get("result")
    if not isinstance(raw, list) or len(raw) != 1 or not isinstance(raw[0], dict):
        raise AuditBlocked("D1_SQL_RESULT_SHAPE")
    body = raw[0]
    if body.get("success") is not True or not isinstance(body.get("results"), list):
        raise AuditBlocked("D1_SQL_RESULT_FAILED")
    meta = body.get("meta")
    if meta is not None:
        if not isinstance(meta, dict):
            raise AuditBlocked("D1_SQL_META_INVALID")
        if ("rows_written" in meta and
            (type(meta["rows_written"]) is not int or meta["rows_written"] != 0)):
            raise AuditBlocked("D1_SQL_UNEXPECTED_MUTATION")
        if ("changed_db" in meta and meta["changed_db"] is not False):
            raise AuditBlocked("D1_SQL_UNEXPECTED_MUTATION")
    return body["results"]


def quoted_pragma(table):
    if not isinstance(table, str) or not table or len(table) > 180 or "\x00" in table:
        raise AuditBlocked("UNSAFE_TABLE_NAME")
    return 'PRAGMA table_xinfo("' + table.replace('"', '""') + '")'


def read_source_schema(token):
    list_route = f"/accounts/{SOURCE_ACCOUNT}/d1/database?page=1&per_page=100"
    inventory = parse_db_inventory(request_json(token, "GET", list_route))
    result = {"account_id": SOURCE_ACCOUNT, "time_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
              "evidence": "SOURCE_ONLY_SCHEMA_PK_NO_ROWS", "schema_version": 1,
              "databases": {}, "source_row_parity_verified": False, "target_row_parity_verified": False,
              "target_accessed": False, "cutover_ready": False, "r2_requests": 0}
    for db_name in sorted(EXPECTED_DATABASES):
        uid = inventory[db_name]
        route = f"/accounts/{SOURCE_ACCOUNT}/d1/database/{uid}/query"
        entries = results(request_json(token, "POST", route, {"sql": SCHEMA_SQL}))
        if len(entries) > 200 or not all(isinstance(e, dict) for e in entries):
            raise AuditBlocked("SCHEMA_ENTRIES_EXCESSIVE_OR_INVALID")
        seen = set()
        tables = {}
        objects = []
        for entry in entries:
            kind, name, ddl = entry.get("type"), entry.get("name"), entry.get("sql")
            if not isinstance(kind, str) or kind not in ("table", "view", "index", "trigger"):
                raise AuditBlocked("SCHEMA_OBJECT_TYPE")
            if not isinstance(name, str) or len(name) > 180 or (kind, name) in seen:
                raise AuditBlocked("SCHEMA_OBJECT_ID")
            seen.add((kind, name))
            if kind == "table" and name != "_cf_KV":
                if len(tables) >= MAX_TABLES_PER_DB:
                    raise AuditBlocked("TABLES_LIMIT_EXCEEDED")
                cols = results(request_json(token, "POST", route, {"sql": quoted_pragma(name)}))
                if not cols or len(cols) > MAX_COLUMNS_PER_TABLE:
                    raise AuditBlocked("TABLE_COLUMNS_MISSING_OR_EXCESSIVE")
                identifiers = set()
                pks = []
                for col in cols:
                    if not isinstance(col, dict) or not isinstance(col.get("name"), str):
                        raise AuditBlocked("TABLE_COLUMN_INVALID")
                    cname, order = col["name"], col.get("pk")
                    if cname in identifiers or type(order) is not int or not 0 <= order <= 8:
                        raise AuditBlocked("TABLE_COLUMN_DUPLICATE_OR_PK_INVALID")
                    identifiers.add(cname)
                    if order:
                        pks.append((order, cname))
                if len({order for order, _ in pks}) != len(pks):
                    raise AuditBlocked("TABLE_PK_ORDER_DUPLICATE")
                tables[name] = {
                    "ddl_sha256": hashlib.sha256((ddl or "").strip().encode()).hexdigest(),
                    "pk_columns": [name for _, name in sorted(pks)],
                    "column_count": len(cols), "columns_sha256": column_schema_hash(cols),
                    "row_count": None,
                    "payload_parity_verified": False,
                }
            objects.append({"type": kind, "name": name,
                            "ddl_sha256": hashlib.sha256((ddl or "").strip().encode()).hexdigest()})
        result["databases"][db_name] = {"uuid": uid, "tables": tables,
                                        "objects": objects, "rows_scanned": 0,
                                        "table_count": len(tables)}
    if len(result["databases"]) != 9:
        raise AuditBlocked("MISSING_SOURCE_DATABASE")
    return result


def encrypt_result(manifest, public_key_bytes):
    public = serialization.load_pem_public_key(public_key_bytes)
    symkey = secrets.token_bytes(32)
    nonce = secrets.token_bytes(12)
    aad = b"cf-d1-nine-source-schema-pk-v1"
    ciphertext = AESGCM(symkey).encrypt(nonce, json.dumps(manifest, separators=(",", ":")).encode(), aad)
    wrapped = public.encrypt(symkey, padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None))
    return {"version": 1, "kind": "source-nine-schema-pk-no-rows",
            "wrapped_key": base64.b64encode(wrapped).decode(),
            "nonce": base64.b64encode(nonce).decode(),
            "aad": base64.b64encode(aad).decode(),
            "ciphertext": base64.b64encode(ciphertext).decode()}


def main():
    token = os.environ.get("CF_TOKEN", "")
    account = os.environ.get("CF_ACCOUNT", "")
    if account != SOURCE_ACCOUNT or len(token) < 16:
        raise SystemExit("SOURCE_ACCOUNT_OR_TOKEN_PRECONDITION_FAILED")
    try:
        manifest = read_source_schema(token)
        public_data = PUBLIC_KEY_PATH.read_bytes()
        envelope = encrypt_result(manifest, public_data)
    except (AuditBlocked, OSError, ValueError, TypeError) as exc:
        # No sensitive API response or token in stdout/stderr, including on errors.
        reason = str(exc) if isinstance(exc, AuditBlocked) else "SCHEMA_AUDIT_ERROR"
        raise SystemExit("SOURCE_NINE_SCHEMA_AUDIT_BLOCKED: " + reason) from None
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(envelope, separators=(",", ":")) + "\n", encoding="utf-8")
    print("SOURCE_NINE_SCHEMA_PK_ENCRYPTED_PASS", len(manifest["databases"]),
          "databases; 0 COUNT(*), 0 row payload reads, 0 target queries, 0 R2 calls")


if __name__ == "__main__":
    main()
