#!/usr/bin/env python3
"""Offline Runner3 Core Cloudflare target binding staging plan; NO deploy.

Produces a non-deployable JSON planning document. Only historical destination
UUID candidates are present. No credential, D1, R2, or Worker network calls.
"""
import argparse
import json
import pathlib
import re

SOURCE_ACCOUNT = "7415a87f6bce7884e73ad7cfed5782df"
TARGET_ACCOUNT = "748a80810f77f447ee476543ef0e5014"
UUID = re.compile(r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}\Z")
SOURCE = pathlib.Path("cloudflare/runner3-core/wrangler.jsonc")
DRAFT = pathlib.Path("ops/cloudflare-account-rehome/runner3-core-target-d1-binding-draft-2026-10-16.json")
OUT = pathlib.Path("ops/cloudflare-account-rehome/staging/runner3-core-target-stage-plan.json")
LIVE = pathlib.Path("ops/cloudflare-account-rehome/staging/target-d1-live-id-evidence-20261023.json")
HISTORY_MATRIX = pathlib.Path("ops/cloudflare-account-rehome/d1-nine-store-source-target-matrix-2026-10-16.json")
BINDINGS = frozenset((
    "DB", "OPPORTUNITY_DB", "LIBRARY_DB", "BUSINESS_OPPORTUNITY_DB",
    "TASK_CONTEXT_DB", "CONTEXT_INDEX_DB", "CONTENT_DB", "RSS_DB",
))


class Blocked(Exception):
    pass


def require(condition, code):
    if not condition:
        raise Blocked(code)


def make_plan(source, history, live=None):
    if live is None:
        live = json.loads(LIVE.read_text(encoding="utf-8"))
    require(type(source) is dict and type(history) is dict and type(live) is dict,
            "INVALID_INPUT")
    require(live.get("format") == "target-d1-identity-live-v1" and
            live.get("source_account_id") == SOURCE_ACCOUNT and
            live.get("target_account_id") == TARGET_ACCOUNT and
            live.get("target_database_count") == 9 and
            live.get("workflow_run_id") == 39893435140 and
            live.get("artifact_id") == 12475319253 and
            live.get("artifact_zip_sha256") ==
            "8ad3426e515adac48875e43a00a5a717f3d5daa4c94e706132e1542b8d240010" and
            live.get("cutover_ready") is False and
            live.get("row_key_content_parity_verified") is False and
            live.get("deletion_parity_verified") is False and
            live.get("target_workers_zero_verified") is False and
            live.get("worker_census_consistent") is False and
            live.get("d1_writes") == 0 and
            live.get("worker_deploys") == 0 and
            live.get("r2_requests") == 0,
            "LIVE_TARGET_EVIDENCE_INVALID")
    matched = live.get("historical_target_uuid_matches_live")
    historic_matrix = json.loads(HISTORY_MATRIX.read_text(encoding="utf-8"))
    require(historic_matrix.get("target_account_id") == TARGET_ACCOUNT and
            isinstance(historic_matrix.get("stores"), list),
            "LIVE_TARGET_HISTORY_MATRIX_INVALID")
    historical_expected = {x.get("name") for x in historic_matrix["stores"]
                           if isinstance(x, dict) and x.get("target_historical_uuid")}
    require(type(matched) is dict and set(matched) == historical_expected and
            len(matched) == 9 and all(v is True for v in matched.values()),
            "LIVE_TARGET_UUID_NOT_PROVEN")
    require(source.get("name") == "runner3-core" and
            source.get("main") == "rss-reader-read-fast-entry.js",
            "WORKER_SCOPE_DRIFT")
    require(history.get("source_account_id") == SOURCE_ACCOUNT and
            history.get("target_account_id") == TARGET_ACCOUNT and
            history.get("status") == "HISTORICAL_DRAFT_READ_ONLY_NO_DEPLOY",
            "HISTORY_SCOPE_DRIFT")
    source_bindings = source.get("d1_databases")
    target_candidates = history.get("bindings")
    require(type(source_bindings) is list and len(source_bindings) == 8 and
            type(target_candidates) is list and len(target_candidates) == 8,
            "D1_BINDING_COUNT_DRIFT")
    smap = {x.get("binding"): x for x in source_bindings if type(x) is dict}
    tmap = {x.get("binding"): x for x in target_candidates if type(x) is dict}
    require(set(smap) == set(tmap) == BINDINGS, "D1_BINDING_IDENTITY_DRIFT")
    require(len(set(smap)) == len(source_bindings) and
            len(set(tmap)) == len(target_candidates), "DUPLICATE_BINDING")
    mappings = []
    source_ids, target_ids = set(), set()
    db_seen = {}
    for name in sorted(BINDINGS):
        item, old = smap[name], tmap[name]
        src_id, dst_id = item.get("database_id"), old.get("historical_target_database_id")
        db = item.get("database_name")
        require(type(src_id) is str and UUID.fullmatch(src_id) and
                type(dst_id) is str and UUID.fullmatch(dst_id) and src_id != dst_id and
                old.get("source_database_id") == src_id and
                old.get("database_name") == db and
                old.get("current_target_parity_verified") is False,
                "D1_IDENTITY_OR_PARITY_DRIFT")
        if db in db_seen:
            require(db_seen[db] == dst_id, "TARGET_ALIAS_DIVERGENCE")
        db_seen[db] = dst_id
        source_ids.add(src_id)
        target_ids.add(dst_id)
        mappings.append({"binding": name, "database_name": db,
                         "target_id_candidate_historical": dst_id,
                         "target_id_verified_live": True,
                         "schema_and_row_parity_verified": False})
    require(set(db_seen) <= set(matched), "LIVE_TARGET_DATABASE_MISSING")
    require(len(db_seen) == 6 and len(source_ids) == len(target_ids) == 6 and
            not source_ids.intersection(target_ids),
            "D1_DATABASE_SET_DRIFT")
    require(source.get("triggers", {}).get("crons") == ["17 * * * *"],
            "CRON_EXPECTATION_DRIFT")
    r2 = source.get("r2_buckets")
    services = source.get("services")
    require(type(r2) is list and len(r2) == 2 and
            {v.get("binding") for v in r2} == {"ARTIFACTS", "AUDIO_MEDIA"} and
            type(services) is list and len(services) == 1 and
            services[0].get("binding") == "RSS_FASTLANE" and
            services[0].get("service") == "runner3-rss-fastlane",
            "SERVICE_OR_R2_EXPECTATION_DRIFT")
    var = source.get("vars")
    require(type(var) is dict and
            var.get("RSS_READER_PUBLIC_ORIGIN") ==
            "https://runner3-core.ducduy2411.workers.dev",
            "SOURCE_ORIGIN_DRIFT")

    return {
        "format": "runner3-core-target-stage-plan-v1",
        "status": "OFFLINE_REVIEW_ONLY_NOT_DEPLOYABLE",
        "source_account_id": SOURCE_ACCOUNT,
        "target_account_id": TARGET_ACCOUNT,
        "worker_name_candidate": "runner3-core-migration-preview",
        "target_worker_exists_verified": False,
        "source_code_entrypoint": source["main"],
        "d1_bindings": mappings,
        "d1_unique_target_candidates": len(db_seen),
        "target_binding_ids_freshly_verified": True,
        "target_d1_id_evidence_run": live["workflow_run_id"],
        "target_d1_id_evidence_artifact": live["artifact_id"],
        "target_workers_census": "UNVERIFIED_TOKEN_OR_ENDPOINT_SCOPE",
        "r2_bindings_inhibited": sorted(v["binding"] for v in r2),
        "r2_buckets_unmodified": True,
        "service_bindings_inhibited": ["RSS_FASTLANE"],
        "cron_disabled_in_stage": True,
        "source_cron_for_future_cutover_only": source["triggers"]["crons"],
        "source_origin_reference_blocked": True,
        "runtime_secrets_not_copied": True,
        "no_routes_no_public_deployment": True,
        "migration_sql_executed": False,
        "source_d1_writes": 0,
        "target_d1_writes": 0,
        "r2_requests": 0,
        "worker_deploys": 0,
        "live_row_parity_verified": False,
        "rollback_tested": False,
        "cutover_ready": False,
        "gate": [
            "target D1 UUIDs 9/9 verified by read-only workflow #39893435140",
            "verify source/target applied DDL, primary keys and all schema objects",
            "stage missing schemas using reviewed non-destructive DDL only",
            "reconcile keys/content and deletions under final source writer quiescence",
            "verify target R2 and service bindings independently; release R2 COST_HOLD",
            "stage Worker smoke tests with no public route, source writers, or cron",
            "approve reversible production cutover and demonstrate rollback",
        ],
    }


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--check", action="store_true", help="compare with committed plan, no file writes")
    args = p.parse_args(argv)
    try:
        source = json.loads(SOURCE.read_text(encoding="utf-8"))
        history = json.loads(DRAFT.read_text(encoding="utf-8"))
        expected = make_plan(source, history)
        result = json.dumps(expected, indent=2, sort_keys=True) + "\n"
        if args.check:
            require(OUT.is_file() and OUT.read_text(encoding="utf-8") == result,
                    "STAGING_PLAN_NOT_CURRENT_OR_NOT_REVIEWED")
        else:
            OUT.parent.mkdir(parents=True, exist_ok=True)
            OUT.write_text(result, encoding="utf-8")
    except (OSError, ValueError, Blocked) as exc:
        print("D1_STAGING_PLAN_BLOCKED", str(exc) if isinstance(exc, Blocked) else "INPUT_OR_IO_INVALID")
        return 3
    print("D1_STAGING_PLAN_OFFLINE_PASS no_deploy no_r2 no_d1_writes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
