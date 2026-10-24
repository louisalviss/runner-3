#!/usr/bin/env python3
"""Manual read-only D1 recommendation_runs reconciliation + SQLite dry-run.

Reads source/target only, builds an ephemeral bounded missing-row plan, tests
INSERT+readback in a *local in-memory SQLite database only*. NEVER sends an
INSERT or data-changing SQL to Cloudflare. Never exports raw keys or rows.
A DRY_RUN_READY status is not permission or a mechanism for target D1 writes.
"""
import json
import os
import pathlib
import sqlite3

from cloudflare_d1_first_live_table_parity import (
    SRC_ACCOUNT, DST_ACCOUNT, SRC_UUID, DST_UUID, DB, TABLE, COLUMNS,
    MAX_ROWS, META_SQL, ROWS_SQL, Blocked, require, request_json,
    check_schema, typed,
)

OUT = pathlib.Path("migration-out/d1-recommendation-runs-additive-dryrun.json")
COLUMN_TYPES = ("TEXT", "TEXT", "INTEGER", "INTEGER", "REAL", "TEXT", "TEXT", "TEXT")
SCHEMA_SQL = """CREATE TABLE recommendation_runs (
  render_id TEXT PRIMARY KEY,
  source_scope TEXT,
  item_count INTEGER DEFAULT 0,
  recommended_count INTEGER DEFAULT 0,
  exploration_ratio REAL,
  model_version TEXT,
  created_at TEXT DEFAULT CURRENT_TIMESTAMP,
  metadata_json TEXT
)"""
INSERT_SQL = (
    'INSERT INTO "recommendation_runs" (' +
    ",".join('"' + c + '"' for c in COLUMNS) +
    ') VALUES (' + ",".join("?" for _ in COLUMNS) + ')'
)
READ_SQL = (
    'SELECT ' + ",".join('"' + c + '"' for c in COLUMNS) +
    ' FROM "recommendation_runs" ORDER BY "render_id"'
)
MAX_MISSING = 50


def safe_map(rows):
    require(isinstance(rows, list) and len(rows) <= MAX_ROWS,
            "DRYRUN_ROW_BUDGET_EXCEEDED")
    mapping = {}
    for row in rows:
        require(isinstance(row, dict) and set(row) == set(COLUMNS),
                "DRYRUN_ROW_FIELDS_CHANGED")
        key = row["render_id"]
        require(type(key) is str and 0 < len(key) <= 500 and key not in mapping,
                "DRYRUN_BAD_OR_DUPLICATE_PK")
        for col in COLUMNS:
            typed(row[col])  # reject booleans, blobs, objects, non-finite floats
        mapping[key] = row
    return mapping


def canon(row):
    return json.dumps([typed(row[c]) for c in COLUMNS],
                      ensure_ascii=False, separators=(",", ":"),
                      allow_nan=False).encode("utf8")


def require_expected_columns(meta):
    check_schema(meta)
    sorted_rows = sorted(meta, key=lambda r: r["cid"])
    require(tuple(str(x["type"]).upper() for x in sorted_rows) == COLUMN_TYPES,
            "DRYRUN_SCHEMA_AFFINITY_CHANGED")


def scratch_rehearsal(source, target, missing):
    """Only SQLite :memory:, not a remote D1 operation or a persisted backup."""
    with sqlite3.connect(":memory:") as db:
        db.row_factory = sqlite3.Row
        db.execute(SCHEMA_SQL)
        # Seed the synthetic mirror of *existing target* first, not the source.
        for k in sorted(target):
            db.execute(INSERT_SQL, tuple(target[k][c] for c in COLUMNS))
        baseline = safe_map([dict(row) for row in db.execute(READ_SQL)])
        require(set(baseline) == set(target) and
                all(canon(baseline[k]) == canon(target[k]) for k in target),
                "DRYRUN_BASELINE_ROUNDTRIP_MISMATCH")
        for k in missing:
            require(db.execute(
                'SELECT COUNT(*) FROM "recommendation_runs" WHERE render_id=?', (k,)
            ).fetchone()[0] == 0, "DRYRUN_PK_RACE_HOLD")
            db.execute(INSERT_SQL, tuple(source[k][c] for c in COLUMNS))
            record = db.execute(
                'SELECT ' + ",".join('"' + c + '"' for c in COLUMNS) +
                ' FROM "recommendation_runs" WHERE render_id=?', (k,)
            ).fetchone()
            require(record is not None and canon(dict(record)) == canon(source[k]),
                    "DRYRUN_INSERT_READBACK_MISMATCH")
        after = safe_map([dict(row) for row in db.execute(READ_SQL)])
        require(set(after) == set(source) and
                all(canon(after[k]) == canon(source[k]) for k in source) and
                all(canon(after[k]) == canon(baseline[k]) for k in baseline),
                "DRYRUN_WHOLE_TABLE_OR_EXISTING_TARGET_CHANGED")
        require(len(after) == len(target) + len(missing),
                "DRYRUN_ROW_COUNT_NOT_CONSERVED")


def execute(source_token, target_token, reader=request_json):
    require(type(source_token) is str and len(source_token) >= 16 and
            type(target_token) is str and len(target_token) >= 16 and
            source_token != target_token,
            "DRYRUN_SEPARATE_READ_TOKENS_REQUIRED")
    src_meta = reader(source_token, SRC_ACCOUNT, SRC_UUID, META_SQL)
    dst_meta = reader(target_token, DST_ACCOUNT, DST_UUID, META_SQL)
    require_expected_columns(src_meta)
    require_expected_columns(dst_meta)
    require(check_schema(src_meta) == check_schema(dst_meta),
            "DRYRUN_SOURCE_TARGET_SCHEMA_DRIFT")
    s1 = safe_map(reader(source_token, SRC_ACCOUNT, SRC_UUID, ROWS_SQL))
    t1 = safe_map(reader(target_token, DST_ACCOUNT, DST_UUID, ROWS_SQL))
    s2 = safe_map(reader(source_token, SRC_ACCOUNT, SRC_UUID, ROWS_SQL))
    t2 = safe_map(reader(target_token, DST_ACCOUNT, DST_UUID, ROWS_SQL))
    require(set(s1) == set(s2) and
            all(canon(s1[k]) == canon(s2[k]) for k in s1) and
            set(t1) == set(t2) and
            all(canon(t1[k]) == canon(t2[k]) for k in t1),
            "DRYRUN_UNSTABLE_SOURCE_OR_TARGET")
    common = set(s2) & set(t2)
    different = sum(canon(s2[k]) != canon(t2[k]) for k in common)
    target_only = len(set(t2) - set(s2))
    source_only = sorted(set(s2) - set(t2))
    require(not different and not target_only,
            "DRYRUN_CONFLICT_OR_UNEXPLAINED_TARGET_ONLY_HOLD")
    require(len(source_only) <= MAX_MISSING, "DRYRUN_TOO_MANY_NEW_ROWS_HOLD")
    scratch_rehearsal(s2, t2, source_only)
    return {
        "format": "d1-recommendation-runs-additive-dryrun-v1",
        "status": ("ADDITIVE_REHEARSAL_PASS_NOT_AUTHORIZED" if source_only
                   else "NO_DELTA_NOT_CUTOVER_PROOF"),
        "database": DB, "table": TABLE,
        "source_account_id": SRC_ACCOUNT, "target_account_id": DST_ACCOUNT,
        "source_rows": len(s2), "target_rows": len(t2),
        "matching_existing_rows": len(common),
        "would_insert_rows": len(source_only),
        "changed_payloads": different,
        "target_only_unresolved": target_only,
        "source_and_target_stable_during_probe": True,
        "schema_equal": True,
        "in_memory_sqlite_rehearsal_passed": True,
        "no_raw_values_or_keys_exported": True,
        "live_d1_writes": 0, "r2_requests": 0,
        "target_d1_write_token_used": False,
        "writer_quiescence_proven": False,
        "atomic_cross_account_snapshot": False,
        "rollback_readiness_proven": False,
        "source_delete_allowed": False,
        "cutover_ready": False,
    }


def main():
    # Intentionally NO --apply/--write modes; read-only tokens ONLY.
    try:
        require(not os.getenv("CLOUDFLARE_TARGET_WRITE_TOKEN") and
                not os.getenv("CLOUDFLARE_TARGET_D1_WRITE_TOKEN"),
                "DRYRUN_WRITE_TOKEN_MUST_NOT_BE_PRESENT")
        report = execute(os.environ.get("CLOUDFLARE_API_TOKEN", ""),
                         os.environ.get("CLOUDFLARE_TARGET_AUDIT_TOKEN", ""))
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(json.dumps(report, sort_keys=True, indent=2) + "\n",
                       encoding="utf8")
    except Blocked as exc:
        print("D1_RECONCILIATION_DRYRUN_HOLD", str(exc))
        return 3
    except (OSError, ValueError, sqlite3.Error):
        print("D1_RECONCILIATION_DRYRUN_HOLD INTERNAL_OR_IO_ERROR")
        return 3
    print("D1_RECONCILIATION_DRYRUN", report["status"],
          "would_insert", report["would_insert_rows"],
          "live_writes=0", "r2=0", "cutover=false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
