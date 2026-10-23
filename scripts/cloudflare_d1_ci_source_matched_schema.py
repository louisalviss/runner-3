#!/usr/bin/env python3
"""Offline-only, source-fingerprint-pinned D1 Content Intelligence staging SQL.

Never touches Cloudflare, credentials, real D1, R2, or Worker deployments.
Emits a CREATE-only candidate *for review*, not an executable migration job.
"""
import argparse
import hashlib
import json
import pathlib
import re
import sqlite3

CI = pathlib.Path("cloudflare/runner3-core/content-intelligence-schema.sql")
CORE = pathlib.Path("cloudflare/runner3-core/migrations/0002_state_checkpoints.sql")
STAGE = pathlib.Path("cloudflare/runner3-core/migrations/0015_personal_score_stage.sql")
IDEMPOTENCY = pathlib.Path("cloudflare/runner3-core/migrations/0017_user_content_event_idempotency.sql")
TRIGGER = pathlib.Path("cloudflare/runner3-core/migrations/0009_content_event_dedupe.sql")
OUT = pathlib.Path("ops/cloudflare-account-rehome/staging/content-intelligence-additive-proven-15.sql")

# (type, name) -> verified *source* metadata SHA-256, run 39826582807,
# artifact 12447225966; only entries confirmed absent in TARGET digest
# artifact 12447330783. Object identity hashes are recomputed and checked
# against the separately recorded source-only digest map below.
SOURCE = {
    ("table", "workflow_state"): "5cf69ed645ab73991bb961e949fdc96e5b45b56dccb54dce9d4f68ba64bb263b",
    ("table", "checkpoints"): "28f7bf55be4d5330ce68fddc074b146ab81576c9576fc999238e908434881d6d",
    ("index", "idx_content_items_source_type"): "23128b597609116b42c335db5d26e2a0b187a2933483347c66f7b5fea55f6786",
    ("index", "idx_content_items_source_key"): "1c4e7377f387c3e41434018ae39c2e68ab392259648f17b8af93ed4cd4e3fb4e",
    ("index", "idx_content_items_published_at"): "448102c62913f1201cf50c2ba20ffb34dc7eb909ea5c6ae6cdccf7aefb89d632",
    ("index", "idx_content_features_lookup"): "1511fb9518337d11bed8a08fc8058db45b2615a4b4d5d36f435a686b496d815f",
    ("index", "idx_user_content_events_item"): "7f1d8022fbb896f2b9ecefa88e0d2a14d212917fcf5345b96d186659ce5a08c5",
    ("index", "idx_user_content_events_type"): "813275953286404936c74434dfa679d6d7f2b5912a3a0e114a7c09608beeb268",
    ("index", "idx_user_content_events_at"): "32168ea31cc3f302669b45ba48d50f898b963bcdeb130db975386a87da31bf4f",
    ("index", "idx_user_content_events_render"): "d117708de63a503165a35bc17e749daf24225c7377f10d1073a3bf17fdfc7c67",
    ("index", "idx_content_scores_type_score"): "1d2fe281351f9003735bd53f030f9de97b550889e807d4c9b6ea8a455ff3b2a9",
    ("index", "idx_checkpoints_source"): "ff434e988db833ef4579696383f51c5f4eda1e313223c0b37d0fdc08be33f9",
    ("index", "idx_personal_score_stage_model_base"): "b22a04c2794b3760d79138466388b6868225d822e61369ee8c599e0736089d4f",
    ("index", "idx_user_content_events_identity"): "292952310b702615647bedbd3d41092312fd2e484d7eb74214732a0d53ffcd26",
    ("trigger", "trg_user_content_events_render_dedupe"): "77ca47e8631ae76f68394bd2cc87592147b3017357675fb69a931d93043bfbce",
}
# Allow exactly this approved source-only identity census, never new names.
SOURCE_ONLY_IDS = frozenset((
    "52f32320738bbfdb0a6f30febd6c47de2cd843c16dac0c5b6e53b722b0f9e560",
    "e3a7c3607c37447eeb535ffd45f2c55404effa491c2d679df70fa97d98b5506e",
    "9be1dd062857f0cd47476105b85debccb3433f4d1bd7b5dfd17b5f477d899403",
    "14042512ba6de2ff94332b103b09a5688505e6009f1973c8dbb24a39a6f65508",
    "48998a240bf2d4750fd3ccb28c718090a6a0b7a1049b6640a15ac527babc6909",
    "9f18622a73d26865d1756abe3684898b1b6a82a461725f99c4d191e01f2ae9e6",
    "bdcdefecc31e4ea872f05e73fd19f0b2a0541bdb6172c647682f03c3074f8df6",
    "03697b05e823a890c8f91ae391912553769bae66ca4d6760f67c4c558737071e",
    "2105b6cc0dc8caa74a2f80095c4a8d1d881c93e19a514dd6cfcf2c4196660f00",
    "26911221e958b9ed3b790e77e2dcc9c0eeb90b71dab7a7e7ded55bd4f82971c5",
    "ad023bead807cbf97b93ee6b57bd359c2c7b13954bf1ff1c6e192124d71632ae",
    "e4df1ffc4fbbabc6ab714ad92bda8d79746ccca8d4268fd5d52d8261d69fbc28",
    "465c2cf28f6133208ba773b75998b2c0ddc396a8bcd7860a20993c360f5cc017",
    "57127a9e4223ef318c7debacc2655eff7ca4136bacbb72a6f45fef66077254f8",
    "7898815483bba20397fa313a061d52b99f14216c37aed803367b1f4d9151324a",
))


class Hold(ValueError):
    pass


def h(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True,
        ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()


def safe_create_only(script):
    # Repository-sourced CI migration inputs must remain CREATE-only. Never
    # silently evaluate a future DELETE/UPDATE/DROP/INSERT in our scratch DB.
    parts = []
    for text in script.split(";"):
        cleaned = re.sub(r"(?m)^[ \t]*--[^\n]*(?:\n|$)", "", text).strip()
        if not cleaned:
            continue
        if not re.fullmatch(r"(?is)CREATE\s+(?:UNIQUE\s+)?(?:TABLE|INDEX)\s+IF\s+NOT\s+EXISTS\s+.+", cleaned):
            raise Hold("UNSAFE_SQL_INPUT")
        parts.append(cleaned)
    return parts


def read_trigger(text):
    marker = "CREATE TRIGGER IF NOT EXISTS trg_user_content_events_render_dedupe"
    if text.count(marker) != 1:
        raise Hold("TRIGGER_MARKER_DRIFT")
    tail = text.split(marker, 1)[1].strip()
    if not tail.endswith("END;") or tail.count("END;") != 1 or tail.count("SELECT RAISE(IGNORE);") != 1:
        raise Hold("TRIGGER_BODY_DRIFT")
    ddl = marker + "\n" + tail
    return ddl


def schema_metadata(conn, kind, name, ddl):
    fields = {"ddl_sha256": hashlib.sha256((ddl or "").strip().encode()).hexdigest()}
    if kind == "table":
        columns = [dict(row) for row in conn.execute(
            "PRAGMA table_xinfo(" + json.dumps(name) + ")")]
        if not columns:
            raise Hold("MISSING_COLUMNS")
        cols = ("cid", "name", "type", "notnull", "dflt_value", "pk", "hidden")
        fields.update(
            pk_columns=[c["name"] for c in sorted(columns,key=lambda c:c["pk"]) if c["pk"]],
            column_count=len(columns),
            columns_sha256=h([{k: c.get(k) for k in cols} for c in columns]),
        )
    return h(fields)


def build(root):
    if len(SOURCE) != 15 or len(SOURCE_ONLY_IDS) != 15 or {h([k, n]) for k, n in SOURCE} != SOURCE_ONLY_IDS:
        raise Hold("AUTHENTICATED_SOURCE_OBJECT_SET_DRIFT")
    ddl = [safe_create_only((root / p).read_text(encoding="utf-8"))
           for p in (CI, CORE, STAGE, IDEMPOTENCY)]
    trigger = read_trigger((root / TRIGGER).read_text(encoding="utf-8"))
    with sqlite3.connect(":memory:") as conn:
        conn.row_factory = sqlite3.Row
        for group in ddl:
            for stmt in group:
                conn.execute(stmt)
        conn.executescript(trigger)
        found = {}
        for kind, name, sql in conn.execute(
            "SELECT type, name, sql FROM sqlite_master "
            "WHERE type IN ('table','index','trigger') AND name NOT LIKE 'sqlite_%'"
        ):
            if (kind, name) in SOURCE:
                if schema_metadata(conn, kind, name, sql) != SOURCE[(kind,name)]:
                    raise Hold("SOURCE_DDL_METADATA_DRIFT_" + name)
                found[(kind, name)] = sql
        if set(found) != set(SOURCE):
            raise Hold("SOURCE_OBJECT_MISSING")
        if ("index","idx_content_items_last_seen_at") not in {
            (obj["type"],obj["name"])
            for obj in conn.execute("SELECT type, name FROM sqlite_master")
        }:
            # This repo-only index must never slip into target staging.
            raise Hold("EXPECTED_EXTRA_INDEX_IN_REPO_CHANGED")
    ordered = (
        sorted((kind, name) for kind, name in SOURCE if kind == "table") +
        sorted((kind, name) for kind, name in SOURCE if kind == "index") +
        sorted((kind, name) for kind, name in SOURCE if kind == "trigger")
    )
    script = (
        "-- REVIEW ONLY: DO NOT AUTO-APPLY TO D1. Exact source schema metadata, "
        "run #39826582807.\n"
        "-- 2 TABLE + 12 INDEX + 1 TRIGGER objects missing on target in historical "
        "source/target snapshot.\n"
        "-- Depends on nine shared source/target schema objects; re-check target "
        "DDL and existing data before any SQL.\n"
        "-- D1 rows transferred=0; worker deploys=0; R2 requests=0; cutover=false.\n\n"
    )
    return script + "\n\n".join(found[k].rstrip(";") + ";" for k in ordered) + "\n"


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=pathlib.Path, default=pathlib.Path("."))
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    try:
        output = build(args.root)
        file = args.root / OUT
        if args.check:
            if not file.is_file() or file.read_text(encoding="utf-8") != output:
                raise Hold("CI_REVIEW_SQL_NOT_SYNCHRONIZED")
        else:
            file.parent.mkdir(parents=True,exist_ok=True)
            file.write_text(output,encoding="utf-8")
    except (Hold,OSError,sqlite3.Error,ValueError) as e:
        print("CI_SOURCE_SCHEMA_HOLD",str(e) if isinstance(e,Hold) else "OFFLINE_INPUT_ERROR")
        return 3
    print("CI_SOURCE_SCHEMA_FINGERPRINT_PASS 15/15 offline target D1 writes=0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
