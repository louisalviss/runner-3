#!/usr/bin/env python3
"""Offline-only PRIVATE review bundle: 33 checked-in DDL + 6 applied DDL objects.

Requires exact one-day GitHub Actions artifact ZIP. Never requests Cloudflare,
uses credentials, reads any application row, writes to D1/R2 or deploys Workers.
The final six raw applied CREATE statements are written ONLY to a user-chosen
local, mode-0700 directory as mode-0600 review files; never to the repository.
"""
import argparse
import hashlib
import json
import os
import pathlib
import re
import sqlite3
import stat
import zipfile

from cloudflare_d1_final_six_source_ddl import (
    ACCOUNT, GAPS, KNOWN_CORE_TABLES, digest, table_metadata,
)
from cloudflare_d1_core_additive_schema import build as core_build
from cloudflare_d1_ci_source_matched_schema import build as ci_build

ARCHIVE_SHA256 = "7a3e2ce1ea57c26b6e0aee22f037c9ac4617ed3ad3839a88e6dfbbf7786a7a0d"
RECEIPT_MEMBER = "d1-final-six-source-applied-ddl.json"
RUN_ID = 39987228477
CORE = "runner3-core"
CONTENT = "runner3-content-intelligence"
MAX_ARCHIVE_BYTES = 100_000
MAX_RECEIPT_BYTES = 60_000
OBJECT_KEYS = frozenset(("kind", "name", "ddl", "object_id", "source_metadata_sha256"))
EXPECTED_CI = frozenset((
    ("table", "link_interest_events"),
    ("index", "idx_link_interest_platform"),
    ("index", "idx_link_interest_sent_at"),
))
OUTPUTS = {
    CORE: "runner3-core-source-matched-21.REVIEW.sql",
    CONTENT: "runner3-content-intelligence-source-matched-18.REVIEW.sql",
}


class Hold(ValueError):
    pass


def require(ok, reason):
    if not ok:
        raise Hold(reason)


def read_archive(path, expected_sha=ARCHIVE_SHA256):
    path = pathlib.Path(path)
    require(path.is_file() and not path.is_symlink() and
            0 < path.stat().st_size <= MAX_ARCHIVE_BYTES,
            "ARTIFACT_MISSING_OR_OVERSIZED")
    archive = path.read_bytes()
    require(hashlib.sha256(archive).hexdigest() == expected_sha,
            "ARTIFACT_SHA256_MISMATCH")
    try:
        with zipfile.ZipFile(path) as z:
            require(z.namelist() == [RECEIPT_MEMBER], "ARTIFACT_MEMBERS_INVALID")
            info = z.getinfo(RECEIPT_MEMBER)
            require(0 < info.file_size <= MAX_RECEIPT_BYTES,
                    "ARTIFACT_EXPANSION_OVERSIZED")
            body = z.read(info, pwd=None)
        return json.loads(body)
    except Hold:
        raise
    except (zipfile.BadZipFile, UnicodeError, ValueError, RuntimeError):
        raise Hold("ARTIFACT_JSON_OR_ZIP_INVALID") from None


def safe_object(record, wanted):
    require(type(record) is dict and set(record) == OBJECT_KEYS,
            "RAW_ROW_OR_UNEXPECTED_SCHEMA_FIELDS")
    kind, name, ddl = record["kind"], record["name"], record["ddl"]
    require(kind in ("table", "index") and
            isinstance(name, str) and
            re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,127}", name) and
            isinstance(ddl, str) and 15 <= len(ddl) <= 8192 and
            "\x00" not in ddl and ";" not in ddl and
            re.match(r"(?is)^CREATE\s+(?:UNIQUE\s+)?"+kind+r"\s+", ddl),
            "NON_CREATE_OR_UNSAFE_SCHEMA_SQL")
    oid = digest([kind, name])
    require(record["object_id"] == oid and
            oid in wanted and
            record["source_metadata_sha256"] == wanted[oid],
            "SOURCE_OBJECT_PIN_MISMATCH")
    return oid, kind, name, ddl


def check_receipt(receipt, pinned=GAPS):
    require(type(receipt) is dict and
            receipt.get("format") == "d1-six-applied-schema-source-v1" and
            receipt.get("source_account_id") == ACCOUNT and
            receipt.get("source_schema_reference_run") == 39826582807 and
            receipt.get("evidence") == "READ_ONLY_SQLITE_MASTER_AND_TABLE_XINFO_ONLY" and
            type(receipt.get("object_count")) is int and
            receipt["object_count"] == 6 and
            type(receipt.get("source_query_count")) is int and
            2 <= receipt["source_query_count"] <= 12 and
            all(receipt.get(key) == 0 for key in (
                "raw_application_rows_read", "source_d1_writes",
                "target_d1_queries", "target_d1_writes", "r2_requests",
                "worker_deploys")) and
            receipt.get("cutover_ready") is False and
            receipt.get("row_parity_verified") is False,
            "SOURCE_RECEIPT_CONTRACT_VIOLATION")
    groups = receipt.get("databases")
    require(type(groups) is dict and set(groups) == set(pinned) ==
            {CORE, CONTENT}, "WRONG_DATABASE_SET")
    selected = {}
    for dbname in (CORE, CONTENT):
        rows = groups[dbname]
        want = pinned[dbname]
        require(type(rows) is list and len(rows) == len(want) == 3,
                "SIX_OBJECT_CENSUS_INVALID")
        seen, values = set(), []
        for record in rows:
            oid, kind, name, ddl = safe_object(record, want)
            require(oid not in seen, "DUPLICATE_SOURCE_OBJECT")
            seen.add(oid)
            values.append((kind, name, ddl, want[oid]))
        require(seen == set(want), "MISSING_REQUIRED_SOURCE_OBJECT")
        if dbname == CORE:
            require({name for kind,name,_,_ in values} == KNOWN_CORE_TABLES and
                    all(kind == "table" for kind,_,_,_ in values),
                    "CORE_TABLE_CENSUS_DRIFT")
        else:
            require({(kind,name) for kind,name,_,_ in values} == EXPECTED_CI,
                    "CONTENT_INTELLIGENCE_OBJECT_CENSUS_DRIFT")
        # CREATE on empty, isolated SQLite only: confirms complete dependencies
        # and typed source SHA proofs; no target/database API is contacted.
        with sqlite3.connect(":memory:") as db:
            db.row_factory = sqlite3.Row
            values.sort(key=lambda row: (0 if row[0] == "table" else 1, row[1]))
            for kind, name, ddl, expected in values:
                try:
                    db.execute(ddl)
                except sqlite3.Error:
                    raise Hold("SCRATCH_CREATE_REJECTED") from None
                obj = db.execute(
                    "SELECT type, sql FROM sqlite_master WHERE name=?", (name,)
                ).fetchone()
                require(obj is not None and obj["type"] == kind and
                        table_metadata(kind, name, obj["sql"],
                          [dict(x) for x in db.execute(
                            'PRAGMA table_xinfo("' + name + '")')]
                          if kind == "table" else None) == expected,
                        "SCRATCH_SOURCE_DDL_FINGERPRINT_MISMATCH")
            names = {(r["type"], r["name"]) for r in db.execute(
                "SELECT type,name FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'")}
            require(names == {(kind,name) for kind,name,_,_ in values},
                    "SCRATCH_EXTRA_SCHEMA_OBJECT")
        selected[dbname] = values
    return selected


def build_review(root, receipt, pinned=GAPS):
    selected = check_receipt(receipt, pinned)
    # Revalidate all other 33 CREATE-only declarations against their
    # authenticated source fingerprints on every generation, not from stale
    # contents in GitHub or guessed DDL.
    core_base = core_build(root)
    ci_base = ci_build(root)
    require(core_base.count("CREATE TABLE IF NOT EXISTS") == 9 and
            core_base.count("CREATE INDEX IF NOT EXISTS") == 9 and
            ci_base.count("CREATE TABLE IF NOT EXISTS") == 2 and
            ci_base.count("CREATE TRIGGER IF NOT EXISTS") == 1,
            "EXISTING_33_SOURCE_CANDIDATE_DRIFT")
    original = {CORE: core_base, CONTENT: ci_base}
    combined = {}
    for dbname, values in selected.items():
        additions = "\n\n".join(ddl.rstrip() + ";" for _,_,ddl,_ in values)
        combined[dbname] = (
            "-- PRIVATE REVIEW ONLY. NEVER AUTO-APPLY OR DEPLOY.\n"
            "-- Source DDL provenance: run #39987228477, six/6 verified.\n"
            "-- Other 33 CREATE objects revalidated offline against original source.\n"
            "-- Missing objects here are additions to existing target schema; "
            "existing-target compatibility/uniqueness and row parity NOT PROVEN.\n"
            "-- No data transfer. R2 COST_HOLD rev28. cutover=false.\n\n"
            + original[dbname].rstrip() + "\n\n"
            + "-- Final applied source DDL objects from restricted receipt.\n"
            + additions + "\n"
        )
    return combined


def store_private(outdir, generated):
    outdir = pathlib.Path(outdir)
    if not outdir.exists():
        outdir.mkdir(parents=True, mode=0o700)
    require(outdir.is_dir() and not outdir.is_symlink() and
            stat.S_IMODE(outdir.stat().st_mode) & 0o077 == 0,
            "OUTPUT_DIRECTORY_INVALID")
    # Files are created EXCLUSIVELY to avoid changing reviewed prior exports.
    paths = [outdir / name for name in OUTPUTS.values()]
    require(all(not path.exists() and not path.is_symlink() for path in paths),
            "OUTPUT_ALREADY_EXISTS")
    for dbname, filename in OUTPUTS.items():
        path = outdir / filename
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        fd = os.open(path, flags, stat.S_IRUSR | stat.S_IWUSR)
        with os.fdopen(fd, "w", encoding="utf-8") as out:
            out.write(generated[dbname])
    return len(paths)


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--artifact", type=pathlib.Path, required=True)
    p.add_argument("--root", type=pathlib.Path, default=pathlib.Path("."))
    p.add_argument("--outdir", type=pathlib.Path, required=True)
    opts = p.parse_args(argv)
    try:
        data = read_archive(opts.artifact)
        candidate = build_review(opts.root, data)
        store_private(opts.outdir, candidate)
    except (Hold, OSError, UnicodeError, sqlite3.Error, ValueError, TypeError):
        print("D1_39_REVIEW_BUNDLE_HOLD no_d1_writes no_r2_requests")
        return 3
    print("D1_39_PRIVATE_REVIEW_READY Core=21/21 ContentIntelligence=18/18"
          " writes=0 r2=0 no_cutover")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
