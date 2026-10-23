#!/usr/bin/env python3
"""Build *review-only* additive Core schema DDL from locally proven source SQL.

No Cloudflare access, key, token, migration execution, network, D1 row read,
D1 write, R2 or Worker interaction. Metadata fingerprints were compared to the
authenticated source-only Cloudflare D1 receipt from run 39826582807.
"""
import argparse
import hashlib
import json
import pathlib
import re
import sqlite3

CORE_DIR = pathlib.Path("cloudflare/runner3-core/migrations")
OUTPUT = pathlib.Path("ops/cloudflare-account-rehome/staging/runner3-core-additive-proven-16.sql")
INPUTS = (
    "0001_init.sql",
    "0002_state_checkpoints.sql",
    "0010_artifact_library_magic_links.sql",
    "0010_vps_mailbox_jobs.sql",
    "0011_artifact_library_pin_auth.sql",
    "0012_delivery_permalinks.sql",
)
# (object kind, [kind,name] ID SHA-256, source object's full metadata SHA-256).
# Verified offline against Oct 22 authenticated SOURCE digest artifact:
# run 39826582807 / artifact 12447225966 / zip SHA256
# df5a8e29f3c99ffcd72679c5aaa0db43baa7173982c642b45c5ecc0f0975b7f8
EXPECTED = {
    "events": ("table", "3007471e8db5c9f138121871abd6e83eb25d2490421d6511acc83f44fc6d1535", "7276b503345953d0fc80780825b39652b8d8ac4cb9cefb713c8001e55d036e17"),
    "idx_events_created_at": ("index", "79b0d51701ea5f779fe0e9cc9eaf1ab893cc0cd6870c58499f412c4c654d0430", "c582162fe436b907c2029a042a499508daf6b3fcf91176c43607f6401e12ae9c"),
    "idx_events_source": ("index", "446b4a7906e3ed49719eae83c198e7cd4946aec92c1fb256185949306f1f0000", "cf17120787d4b1680955722bfa22f7f9530bb3aa965b46e0ffbc27c3962a8ec4"),
    "workflow_state": ("table", "52f32320738bbfdb0a6f30febd6c47de2cd843c16dac0c5b6e53b722b0f9e560", "5cf69ed645ab73991bb961e949fdc96e5b45b56dccb54dce9d4f68ba64bb263b"),
    "checkpoints": ("table", "e3a7c3607c37447eeb535ffd45f2c55404effa491c2d679df70fa97d98b5506e", "28f7bf55be4d5330ce68fddc074b146ab81576c9576fc999238e908434881d6d"),
    "idx_checkpoints_source": ("index", "e4df1ffc4fbbabc6ab714ad92bda8d79746ccca8d4268fd5d52d8261d69fbc28", "ff434e988db833ef4579696383f51c5f4f5eda1e313223c0b37d0fdc08be33f9"),
    "artifact_library_magic_links": ("table", "b6fe3515935a5112da744ae17752cf7c63a201b3f634caa1d46db33f34c7a312", "0f01e425952e3d74f26d7b317f0bf625e4a6825623bf330aa84513311f3f8afb"),
    "idx_artifact_library_magic_links_expires_at": ("index", "76125d69da3a0e2c5bcb4815abc30a234059ae5173a9e6cf7dee214e8d5605d4", "aa8f93a4c834a2f90d025c6c972be0f40166a657ea4ce689111a37a9fa5edf90"),
    "vps_mailbox_jobs": ("table", "9df016a7e0c539e3f3ab853217537aa6ba8d48cb38f33f93c9742f966372ed97", "3cb529f8e2ca06b1f7cac1ebe76e7dd30c0175680dbfcfca0cbc7498991cdb91"),
    "idx_vps_mailbox_jobs_claim": ("index", "edf930d2ca87ad9c2363b4a71d985f312e63cd83597169bb00e89313f624d5ae", "d3e5a84e8058835cb17202c2cabc7a6852dc3dad40ae27e8b9a4fdbb986557af"),
    "artifact_library_auth": ("table", "945aaaabc2eda9dafb35237469c007001e8ca7f9237fa17323498f4a35dfe5e0", "480e7a020675ecaa2323390e0220e614cae37caa469af5dbf73acab33f4b9dc9"),
    "artifact_library_pin_attempts": ("table", "b45359c3c3e92f3c670cda0afc501c62a708dad80eb3eb1e7c8c9cb343c2a5f2", "795cc18a8171b11784a7bf0ee6e87696e0ca76aa7ff11b03aa7bc788ebb25293"),
    "idx_artifact_library_pin_attempts_blocked_until": ("index", "595ee714d6f801938deaddb49391c925703f64177fa2ab58749f6956ead6b4cc", "85d82359839bb40d2b3e6b06b5cfda4b57484dd002e61b25a22810d4d9a47d28"),
    "delivery_permalinks": ("table", "a476e19380930a0f11e1063f26df5b37794f3a95b1dca8c48c6b8613962d7bba", "e9be6c78a86091bfb9dfcdec7b003cc84e7c144e88152e37d60e6af1ed60c1a2"),
    "idx_delivery_permalinks_object_key": ("index", "d52e86f2354542cd5cf52be53ecdbbae0d9fd25adc7f991f7030833e6f1e0237", "114bc6fb63c3c91319583e41ae50a7efa929a9b6859ababa740acbbec13ee17a"),
    "idx_delivery_permalinks_active": ("index", "d1ed7ec2b9940f1ff7fedbf60f07ccb420582b9e39f4026343866b5b49e9ace3", "407205e06389714d3220bee062ad628418a3706123c72e6e9c2a102de29bc4d0"),
}

class Hold(Exception):
    pass

def sha_json(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                             ensure_ascii=False).encode("utf-8")).hexdigest()

def statements(sql):
    out = []
    for part in sql.split(";"):
        stmt = re.sub(r"(?m)^[ \t]*--[^\n]*(?:\n|$)", "", part).strip()
        if not stmt:
            continue
        if not re.fullmatch(r"(?is)CREATE\s+(?:UNIQUE\s+)?(?:TABLE|INDEX)\s+IF\s+NOT\s+EXISTS\s+.+", stmt):
            raise Hold("NON_ADDITIVE_SQL_REJECTED")
        out.append(stmt)
    return out

def metadata(connection, kind, name, ddl):
    obj = {"ddl_sha256": hashlib.sha256((ddl or "").strip().encode()).hexdigest()}
    if kind == "table":
        rows = [dict(row) for row in connection.execute(
            "PRAGMA table_xinfo(" + json.dumps(name) + ")")]
        if not rows:
            raise Hold("TABLE_HAS_NO_COLUMNS")
        obj.update(pk_columns=[r["name"] for r in sorted(rows,key=lambda r:r["pk"]) if r["pk"]],
                   column_count=len(rows),
                   columns_sha256=sha_json([{k:r.get(k) for k in
                     ("cid", "name", "type", "notnull", "dflt_value", "pk", "hidden")} for r in rows]))
    return obj

def build(root):
    sql = []
    for path in INPUTS:
        source = root / CORE_DIR / path
        sql.extend(statements(source.read_text(encoding="utf-8")))
    if len(sql) != len(EXPECTED):
        raise Hold("STATEMENT_COUNT_DRIFT")
    with sqlite3.connect(":memory:") as db:
        db.row_factory = sqlite3.Row
        for stmt in sql:
            db.execute(stmt)
        objects = list(db.execute("SELECT type, name, sql FROM sqlite_master "
                                  "WHERE type IN ('table', 'index') AND name NOT LIKE 'sqlite_%'"))
        if len(objects) != len(EXPECTED):
            raise Hold("SCRATCH_SCHEMA_COUNT_DRIFT")
        seen = set()
        for obj in objects:
            kind, name, ddl = obj
            if name not in EXPECTED or name in seen:
                raise Hold("SCRATCH_UNEXPECTED_SCHEMA_OBJECT")
            expected_kind, expected_id, expected_meta = EXPECTED[name]
            if kind != expected_kind or sha_json([kind, name]) != expected_id:
                raise Hold("SOURCE_OBJECT_ID_MISMATCH")
            if sha_json(metadata(db,kind,name,ddl)) != expected_meta:
                raise Hold("SOURCE_DDL_OR_COLUMN_FINGERPRINT_MISMATCH_" + name)
            seen.add(name)
        if seen != set(EXPECTED):
            raise Hold("SCRATCH_SCHEMA_INCOMPLETE")
    header = (
        "-- REVIEW CANDIDATE ONLY: DO NOT EXECUTE on Cloudflare without "
        "fresh target sqlite_master preflight, safety review, and authorization.\n"
        "-- Authenticated source DDL+PK/column fingerprint matches: 16/16 "
        "(run 39826582807). SOURCE is production authority.\n"
        "-- Covers 8 Core tables + 8 indexes. Does NOT cover "
        "typed_kv, r2_receipts, d1_migrations, ebook_reader_trace_v113 "
        "or the remaining source-only index.\n"
        "-- No rows, auth material, Worker, cron, R2 or deployment in this file.\n\n"
    )
    return header + ";\n\n".join(sql) + ";\n"

def main(argv=None):
    p=argparse.ArgumentParser()
    p.add_argument("--check",action="store_true")
    p.add_argument("--root",type=pathlib.Path,default=pathlib.Path("."))
    args=p.parse_args(argv)
    try:
        output=build(args.root)
        destination=args.root/OUTPUT
        if args.check:
            if not destination.is_file() or destination.read_text(encoding="utf-8") != output:
                raise Hold("REVIEW_SQL_NOT_SYNCHRONIZED")
        else:
            destination.parent.mkdir(parents=True,exist_ok=True)
            destination.write_text(output,encoding="utf-8")
    except (Hold,OSError,sqlite3.Error,ValueError) as e:
        print("CORE_SCHEMA_REVIEW_HOLD",str(e) if isinstance(e,Hold) else "OFFLINE_INPUT_ERROR")
        return 3
    print("CORE_SCHEMA_SOURCE_FINGERPRINT_PASS 16/16; offline only; target D1 writes=0")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
