#!/usr/bin/env python3
"""Cross-account D1 schema-only comparison. No row scans, D1 writes, or R2 calls."""
import argparse
import hashlib
import json
import os
import pathlib
import re
import sys

REQUIRED = frozenset(("clm-copilot-calibration", "clm-copilot-v1",
    "louis-task-context", "personal-library", "runner3-content-intelligence",
    "runner3-core", "runner3-opportunity-radar", "runner3-rss",
    "volamidle-rogue-data"))
LEGACY = "louis-context-index"
SOURCE_ACCOUNT = "7415a87f6bce7884e73ad7cfed5782df"
TARGET_ACCOUNT = "748a80810f77f447ee476543ef0e5014"
SHA = re.compile(r"[0-9a-f]{64}\Z")


class Blocked(Exception):
    pass


def ensure(ok, code):
    if not ok:
        raise Blocked(code)


def digest(value):
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"),
                         ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def schema_digest(objects, tables):
    ensure(isinstance(objects, list) and len(objects) <= 256, "OBJECT_SET_BAD")
    ensure(isinstance(tables, dict) and len(tables) <= 80, "TABLE_SET_BAD")
    records = []
    seen = set()
    seen_tables = set()
    for entry in objects:
        ensure(isinstance(entry, dict), "OBJECT_BAD")
        name = entry.get("name")
        kind = entry.get("type", entry.get("kind"))
        ddl_hash = entry.get("ddl_sha256")
        ensure(kind in ("table", "view", "index", "trigger") and
               isinstance(name, str) and 0 < len(name) <= 180 and
               "\x00" not in name and (kind, name) not in seen and
               isinstance(ddl_hash, str) and SHA.fullmatch(ddl_hash),
               "OBJECT_BAD")
        seen.add((kind, name))
        item = {"type": kind, "name": name, "ddl_sha256": ddl_hash}
        if kind == "table" and name != "_cf_KV":
            meta = tables.get(name)
            ensure(isinstance(meta, dict), "TABLE_METADATA_MISSING")
            pk = meta.get("pk_columns")
            count = meta.get("column_count")
            ensure(isinstance(pk, list) and len(pk) <= 8 and
                   all(isinstance(x, str) and x for x in pk) and
                   len(set(pk)) == len(pk) and
                   type(count) is int and 0 < count <= 120, "PK_OR_COLUMNS_BAD")
            item.update(pk_columns=pk, column_count=count)
            seen_tables.add(name)
        records.append(item)
    ensure(set(tables) == seen_tables, "TABLE_SET_MISMATCH")
    return digest(sorted(records, key=lambda r: (r["type"], r["name"])))


def source_receipt(manifest):
    ensure(isinstance(manifest, dict) and
           manifest.get("account_id") == SOURCE_ACCOUNT and
           manifest.get("source_row_parity_verified") is False and
           manifest.get("target_row_parity_verified") is False and
           manifest.get("target_accessed") is False and
           manifest.get("cutover_ready") is False and
           manifest.get("r2_requests") == 0, "SOURCE_CONTRACT_BAD")
    dbs = manifest.get("databases")
    ensure(isinstance(dbs, dict) and set(dbs) == REQUIRED,
           "SOURCE_DATABASE_CENSUS_BAD")
    result = {}
    for name, data in dbs.items():
        ensure(isinstance(data, dict) and data.get("rows_scanned") == 0 and
               isinstance(data.get("tables"), dict) and
               data.get("table_count") == len(data["tables"]), "SOURCE_TABLES_BAD")
        tables = data["tables"]
        ensure(all(isinstance(t, dict) and t.get("row_count") is None and
                   t.get("payload_parity_verified") is False
                   for t in tables.values()), "SOURCE_PAYLOAD_READ")
        result[name] = schema_digest(data.get("objects"), tables)
    return {"format": "cross-d1-schema-v1", "role": "source",
            "databases": result, "count": len(result), "missing_required": [],
            "legacy_present": False, "row_parity": False, "cutover_ready": False}


def target_receipt(manifest):
    ensure(isinstance(manifest, dict) and
           manifest.get("account_id") == TARGET_ACCOUNT and
           manifest.get("role") == "target" and
           manifest.get("row_key_content_parity_verified") is False and
           manifest.get("source_delete_allowed") is False and
           manifest.get("cutover_ready") is False and
           manifest.get("r2_requests") == 0, "TARGET_CONTRACT_BAD")
    dbs = manifest.get("database_schemas")
    names = manifest.get("database_names")
    ensure(isinstance(dbs, dict) and isinstance(names, list) and
           len(names) == len(set(names)) and set(names) == set(dbs) and
           set(dbs) <= (REQUIRED | {LEGACY}) and len(dbs) <= 10,
           "TARGET_DATABASE_CENSUS_BAD")
    missing = sorted(REQUIRED - set(dbs))
    ensure(manifest.get("missing_required_names") == missing and
           manifest.get("historical_target_only_name_present") is (LEGACY in dbs),
           "TARGET_CENSUS_FLAGS_BAD")
    result = {}
    for name, data in dbs.items():
        ensure(isinstance(data, dict) and
               isinstance(data.get("schema_objects"), list), "TARGET_TABLES_BAD")
        objects = data["schema_objects"]
        tables = {o["name"]: o for o in objects if isinstance(o, dict)
                  and o.get("kind") == "table" and o.get("name") != "_cf_KV"}
        ensure(data.get("table_count") == len(tables) and
               data.get("schema_object_count") == len(objects), "TARGET_COUNTS_BAD")
        result[name] = schema_digest(objects, tables)
    return {"format": "cross-d1-schema-v1", "role": "target",
            "databases": result, "count": len(result), "missing_required": missing,
            "legacy_present": LEGACY in result, "row_parity": False,
            "cutover_ready": False}


def compare(source, target):
    for role, result in (("source", source), ("target", target)):
        ensure(isinstance(result, dict) and
               result.get("format") == "cross-d1-schema-v1" and
               result.get("role") == role and result.get("row_parity") is False and
               result.get("cutover_ready") is False, "RECEIPT_CONTRACT_BAD")
        fingerprints = result.get("databases")
        ensure(isinstance(fingerprints, dict) and
               result.get("count") == len(fingerprints) and
               all(isinstance(k, str) and isinstance(v, str) and SHA.fullmatch(v)
                   for k, v in fingerprints.items()), "RECEIPT_DIGEST_BAD")
    s = source["databases"]
    t = target["databases"]
    ensure(set(s) == REQUIRED and set(t) <= REQUIRED | {LEGACY} and
           source.get("missing_required") == [] and
           source.get("legacy_present") is False and
           target.get("missing_required") == sorted(REQUIRED - set(t)) and
           target.get("legacy_present") is (LEGACY in t),
           "RECEIPT_CENSUS_BAD")
    missing = sorted(REQUIRED - set(t))
    matching = sorted(n for n in REQUIRED & set(t) if s[n] == t[n])
    differing = sorted(n for n in REQUIRED & set(t) if s[n] != t[n])
    legacy = LEGACY in t
    parity = not missing and not differing and legacy
    return {"status": "SCHEMA_SNAPSHOT_MATCH_NOT_ROW_PARITY" if parity else
            "SCHEMA_GAPS_FOUND", "source_count": len(s), "target_count": len(t),
            "missing_on_target": missing, "schema_mismatch": differing,
            "schema_matching": matching, "legacy_preserved": legacy,
            "row_parity": False, "deletion_parity": False,
            "cutover_ready": False, "r2_requests": 0}


def main(args=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--role", required=True,
                        choices=("source", "target", "compare"))
    parser.add_argument("--source", type=pathlib.Path)
    parser.add_argument("--target", type=pathlib.Path)
    parser.add_argument("--out", type=pathlib.Path, required=True)
    opts = parser.parse_args(args)
    if opts.role == "source":
        ensure(not os.getenv("CLOUDFLARE_TARGET_AUDIT_TOKEN"),
               "CROSS_ACCOUNT_TOKEN_SOURCE")
        from cloudflare_d1_nine_schema_encrypted import (
            SOURCE_ACCOUNT as verified_account, read_source_schema)
        ensure(verified_account == SOURCE_ACCOUNT and
               os.getenv("CLOUDFLARE_ACCOUNT_ID") == SOURCE_ACCOUNT,
               "SOURCE_ACCOUNT_BAD")
        token = os.getenv("CLOUDFLARE_API_TOKEN", "")
        ensure(len(token) >= 16, "SOURCE_TOKEN_ABSENT")
        report = source_receipt(read_source_schema(token))
    elif opts.role == "target":
        ensure(not os.getenv("CLOUDFLARE_API_TOKEN") and
               not os.getenv("CF_TOKEN"), "CROSS_ACCOUNT_TOKEN_TARGET")
        from cloudflare_d1_nine_schema_readonly import TARGET, inventory
        ensure(TARGET == TARGET_ACCOUNT, "TARGET_ACCOUNT_BAD")
        token = os.getenv("CLOUDFLARE_TARGET_AUDIT_TOKEN", "")
        ensure(len(token) >= 16, "TARGET_TOKEN_ABSENT")
        report = target_receipt(inventory("target", token))
    else:
        ensure(not any(os.getenv(x) for x in
                       ("CLOUDFLARE_API_TOKEN", "CLOUDFLARE_TARGET_AUDIT_TOKEN",
                        "CF_TOKEN")), "COMPARE_SECRETS_PRESENT")
        ensure(opts.source is not None and opts.target is not None,
               "COMPARE_FILES_MISSING")
        report = compare(json.loads(opts.source.read_text()),
                         json.loads(opts.target.read_text()))
    opts.out.parent.mkdir(parents=True, exist_ok=True)
    opts.out.write_text(json.dumps(report, sort_keys=True, indent=2) + "\n")
    if opts.role == "compare":
        print(json.dumps(report, sort_keys=True))
        return 0 if report["status"] == "SCHEMA_SNAPSHOT_MATCH_NOT_ROW_PARITY" else 2
    print("D1_SCHEMA_DIGEST_READY", opts.role, report["count"], "no_rows no_r2")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (Blocked, ValueError, TypeError, KeyError, OSError) as err:
        print("D1_CROSS_SCHEMA_BLOCKED",
              str(err) if isinstance(err, Blocked) else "SANITIZED_ERROR")
        raise SystemExit(3) from None
