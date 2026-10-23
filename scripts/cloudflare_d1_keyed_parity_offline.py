#!/usr/bin/env python3
"""Offline-only D1 keyed fingerprint receipt comparator.

Input receipts must be produced separately by an approved read-only capture,
using HMAC-SHA256 with one shared secret per capture window. This module does
NOT collect D1 rows, contact providers, handle HMAC keys, or write to D1.
It CANNOT attest complete capture, deletion parity, or cutover readiness.
"""

import argparse
import json
import pathlib
import re

VERSION = "d1-hmac-keyed-snapshot-v1"
SHA256 = re.compile(r"[a-f0-9]{64}\Z")
KEY_ID = re.compile(r"[a-zA-Z0-9][a-zA-Z0-9._:-]{7,127}\Z")
DB_NAME = re.compile(r"[a-z][a-z0-9-]{2,79}\Z")
IDENTIFIER = re.compile(r"[a-zA-Z_][a-zA-Z0-9_]{0,127}\Z")
WINDOW = re.compile(r"[a-zA-Z0-9][a-zA-Z0-9_-]{7,127}\Z")
MAX_ROWS = 100_000
MAX_BYTES = 35_000_000
RECEIPT_KEYS = frozenset((
    "format", "role", "database", "table", "pk_columns", "schema_sha256",
    "capture_window", "hmac_key_id", "capture_complete", "rows",
))
ROW_KEYS = frozenset(("key_hmac", "payload_hmac"))


class Blocked(ValueError):
    """Input is unsafe, ambiguous, or mismatched; fail closed."""


def require(condition, reason):
    if not condition:
        raise Blocked(reason)


def validated(receipt, role):
    """Reject unrecognized fields to keep secrets/plaintext out of receipts."""
    require(type(receipt) is dict and set(receipt) == RECEIPT_KEYS,
            "INVALID_RECEIPT_FIELDS")
    require(receipt["format"] == VERSION and receipt["role"] == role,
            "ROLE_OR_FORMAT_MISMATCH")
    require(isinstance(receipt["database"], str) and
            DB_NAME.fullmatch(receipt["database"]) is not None and
            isinstance(receipt["table"], str) and
            IDENTIFIER.fullmatch(receipt["table"]) is not None,
            "INVALID_SCOPE")
    require(isinstance(receipt["capture_window"], str) and
            WINDOW.fullmatch(receipt["capture_window"]) is not None and
            isinstance(receipt["hmac_key_id"], str) and
            KEY_ID.fullmatch(receipt["hmac_key_id"]) is not None,
            "INVALID_CAPTURE_ID")
    require(isinstance(receipt["schema_sha256"], str) and
            SHA256.fullmatch(receipt["schema_sha256"]) is not None,
            "INVALID_SCHEMA_HASH")
    pk = receipt["pk_columns"]
    require(type(pk) is list and 1 <= len(pk) <= 8 and
            all(isinstance(p, str) and IDENTIFIER.fullmatch(p) for p in pk) and
            len(pk) == len(set(pk)), "INVALID_PRIMARY_KEY")
    require(type(receipt["capture_complete"]) is bool, "INVALID_COMPLETENESS")
    rows = receipt["rows"]
    require(type(rows) is list and len(rows) <= MAX_ROWS,
            "INVALID_ROW_SET")
    fingerprint_map = {}
    for row in rows:
        require(type(row) is dict and set(row) == ROW_KEYS and
                all(isinstance(row[k], str) and SHA256.fullmatch(row[k])
                    for k in ROW_KEYS), "RAW_OR_INVALID_ROW_DATA")
        key = row["key_hmac"]
        require(key not in fingerprint_map, "DUPLICATE_PRIMARY_KEY_FINGERPRINT")
        fingerprint_map[key] = row["payload_hmac"]
    return fingerprint_map


def compare(source, target):
    s = validated(source, "source")
    t = validated(target, "target")
    require(all(source[k] == target[k] for k in (
        "database", "table", "pk_columns", "capture_window", "hmac_key_id")),
        "UNPAIRED_CAPTURE_OR_KEY_DOMAIN")

    report = {
        "format": "d1-keyed-comparison-offline-v1",
        "database": source["database"],
        "table": source["table"],
        "schema_identical": source["schema_sha256"] == target["schema_sha256"],
        "source_receipt_rows": len(s),
        "target_receipt_rows": len(t),
        "capture_complete_claimed": source["capture_complete"] and target["capture_complete"],
        "source_only": None,
        "target_only_unresolved": None,
        "payload_different": None,
        "matching": None,
        "source_deleted_proven": False,
        "no_tombstone_or_authoritative_lineage_proof": True,
        "row_parity_verified": False,
        "deletion_parity_verified": False,
        "cutover_ready": False,
        "r2_requests": 0,
        "remote_queries": 0,
        "status": "HOLD",
    }
    if not report["capture_complete_claimed"]:
        report["status"] = "INCOMPLETE_CAPTURE_HOLD"
        return report
    if not report["schema_identical"]:
        report["status"] = "SCHEMA_MISMATCH_HOLD"
        return report

    source_keys, target_keys = set(s), set(t)
    shared = source_keys & target_keys
    report.update(
        source_only=len(source_keys - target_keys),
        target_only_unresolved=len(target_keys - source_keys),
        payload_different=sum(s[k] != t[k] for k in shared),
        matching=sum(s[k] == t[k] for k in shared),
    )
    if report["source_only"] or report["target_only_unresolved"] or report["payload_different"]:
        report["status"] = "DATA_DIFFERENCES_HOLD"
    else:
        report["status"] = "DIGESTS_MATCH_NOT_CUTOVER_PROOF"
    return report


def load_json(path):
    file = pathlib.Path(path)
    require(file.is_file() and file.stat().st_size <= MAX_BYTES, "RECEIPT_FILE_UNAVAILABLE_OR_OVERSIZED")
    try:
        return json.loads(file.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise Blocked("RECEIPT_JSON_INVALID") from exc


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=pathlib.Path)
    parser.add_argument("--target", required=True, type=pathlib.Path)
    parser.add_argument("--out", required=True, type=pathlib.Path)
    args = parser.parse_args(argv)
    try:
        report = compare(load_json(args.source), load_json(args.target))
        require(args.out != args.source and args.out != args.target, "OUTPUT_WOULD_OVERWRITE_INPUT")
        args.out.write_text(json.dumps(report, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    except (OSError, Blocked) as exc:
        print("D1_KEYED_OFFLINE_BLOCKED", str(exc) if isinstance(exc, Blocked) else "IO_FAILURE")
        return 3
    print("D1_KEYED_OFFLINE", report["status"])
    # Always fail closed as a release gate: diagnostic equality is not parity.
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
