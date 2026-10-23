#!/usr/bin/env python3
"""Target-only Cloudflare D1/Workers metadata inventory. NO R2 operations.

Does not copy, deploy, delete, read any Worker source code or reveal secrets.
Requires an explicit scoped TARGET token; no fallback to the SOURCE token,
browser profiles, S3 credentials, or global account keys.
"""
import datetime as dt
import json
import os
import pathlib
import urllib.error
import urllib.parse
import urllib.request

TARGET = "748a80810f77f447ee476543ef0e5014"
SOURCE = "7415a87f6bce7884e73ad7cfed5782df"
BASE = "https://api.cloudflare.com/client/v4/accounts/" + TARGET
OUT = pathlib.Path("migration-out/target-d1-workers-inventory.json")
D1_CANONICAL = (
    "runner3-core", "runner3-opportunity-radar", "personal-library",
    "louis-task-context", "runner3-content-intelligence", "runner3-rss",
    "volamidle-rogue-data", "clm-copilot-v1",
)
D1_EXTRA_REVIEW = "clm-copilot-calibration"
HISTORIC_MAP = pathlib.Path("ops/cloudflare-account-rehome/d1-nine-store-source-target-matrix-2026-10-16.json")
WORKERS_PROTECT = (
    "balatro-clef-api", "clm-conversation-copilot-api", "ema-forward-monitor",
    "khotruyen-worker", "media-library", "rss-proxy",
    "runner3-audio-chatgpt-bridge", "runner3-audio-library",
    "runner3-autocontent-ai", "runner3-core", "runner3-rss-fastlane",
    "runner3-x-fast-direct", "runner5-restore-proxy", "vbth-free-editorial-ai",
    "volamidle-rogue", "wave-rider-scanner", "wordpress-edge-proxy",
    "wordpress-edge-proxy-v2",
)
MAX_DATABASES = 80
MAX_WORKERS = 200

class AuditBlocked(Exception):
    pass

def get(token, path):
    if not path.startswith("/") or "://" in path or "//" in path:
        raise AuditBlocked("UNSAFE_ENDPOINT")
    request = urllib.request.Request(BASE + path, headers={
        "Authorization": "Bearer " + token, "Accept": "application/json"
    }, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            if response.status != 200:
                raise AuditBlocked("HTTP_NON_200")
            raw = response.read(2_000_001)
            if len(raw) > 2_000_000:
                raise AuditBlocked("RESPONSE_TOO_LARGE")
            data = json.loads(raw)
    except urllib.error.HTTPError as exc:
        raise AuditBlocked("HTTP_" + str(exc.code)) from None
    except (urllib.error.URLError, TimeoutError):
        raise AuditBlocked("TARGET_NETWORK_ERROR") from None
    if data.get("success") is not True:
        raise AuditBlocked("TARGET_API_NOT_SUCCESS")
    return data

def limited_unique(items, key, limit, label):
    if not isinstance(items, list) or len(items) > limit:
        raise AuditBlocked(label + "_INVALID_COUNT")
    seen = set()
    for item in items:
        val = item.get(key) if isinstance(item, dict) else None
        if not isinstance(val, str) or not val or val in seen:
            raise AuditBlocked(label + "_INVALID_ID")
        seen.add(val)
    return sorted(items, key=lambda a: a[key])

def summarize_bindings(rows):
    if not isinstance(rows, list):
        raise AuditBlocked("WORKER_BINDINGS_INVALID")
    result = []
    for b in rows:
        if not isinstance(b, dict):
            raise AuditBlocked("WORKER_BINDING_INVALID")
        typ = str(b.get("type", ""))[:80]
        name = str(b.get("name", ""))[:128]
        if not typ or not name:
            raise AuditBlocked("WORKER_BINDING_ID_INVALID")
        item = {"type": typ, "binding": name}
        if typ == "service":
            item["service"] = str(b.get("service", ""))[:128]
        # Never emit secret values, raw bindings, database UUIDs, KV IDs,
        # DO namespace IDs, environment variable contents or API responses.
        result.append(item)
    return sorted(result, key=lambda b: (b["type"], b["binding"]))

def read_inventory(token):
    # Require a target-only secret and guard account identity before calling API.
    if not token or len(token) < 16:
        raise AuditBlocked("TARGET_AUDIT_TOKEN_ABSENT")
    if TARGET == SOURCE:
        raise AuditBlocked("SOURCE_TARGET_NOT_DISTINCT")
    data = get(token, "/d1/database?per_page=100&page=1")
    # D1 List is paginated. API result_info.total_count is the documented
    # completeness signal; total_pages is OPTIONAL and must not be assumed 1.
    # Never silently accept a truncated first page as a full account inventory.
    d1 = limited_unique(data.get("result"), "name", MAX_DATABASES, "D1")
    paging = data.get("result_info")
    if not isinstance(paging, dict):
        raise AuditBlocked("D1_PAGINATION_UNKNOWN")
    expected = paging.get("total_count")
    page = paging.get("page")
    count = paging.get("count")
    if type(expected) is not int or type(page) is not int or type(count) is not int:
        raise AuditBlocked("D1_PAGINATION_INVALID")
    if page != 1 or expected != len(d1) or count != len(d1):
        raise AuditBlocked("D1_INVENTORY_INCOMPLETE")
    total_pages = paging.get("total_pages")
    if total_pages is not None and (type(total_pages) is not int or total_pages != 1):
        raise AuditBlocked("D1_PAGINATION_INCOMPLETE")
    d1_names = [x["name"] for x in d1]
    # Confirm configured historical destination UUIDs without publishing raw UUIDs.
    try:
        history = json.loads(HISTORIC_MAP.read_text(encoding="utf-8"))
        if history.get("target_account_id") != TARGET or not isinstance(history.get("stores"), list):
            raise AuditBlocked("TARGET_HISTORY_INVALID")
        prior = {x["name"]: x.get("target_historical_uuid")
                 for x in history["stores"] if isinstance(x, dict) and isinstance(x.get("name"), str)}
        historical_uuid_matches = {
            x["name"]: bool(isinstance(prior.get(x["name"]), str) and
                            x.get("uuid") == prior[x["name"]])
            for x in d1
        }
    except (OSError, ValueError, TypeError) as exc:
        raise AuditBlocked("TARGET_HISTORY_UNAVAILABLE_OR_INVALID") from None
    scripts_data = get(token, "/workers/scripts")
    worker_list = limited_unique(scripts_data.get("result"), "id", MAX_WORKERS, "WORKER")
    scripts_page = scripts_data.get("result_info")
    scripts_page_complete = True
    if scripts_page is not None:
        scripts_page_complete = bool(isinstance(scripts_page, dict) and
                                     scripts_page.get("page") == 1 and
                                     scripts_page.get("count") == len(worker_list) and
                                     scripts_page.get("total_count") == len(worker_list))
    # Cloudflare documents this separate endpoint as "List all Workers".
    # It may fail if token scope does not allow it; never invent a 0 result.
    alt_worker_names, alt_status = None, "UNAVAILABLE"
    try:
        alt_data = get(token, "/workers/workers?per_page=100&page=1")
        alt_items = limited_unique(alt_data.get("result"), "name", MAX_WORKERS, "WORKER_V2")
        alt_page = alt_data.get("result_info")
        if (not isinstance(alt_page, dict) or
            alt_page.get("page") != 1 or
            alt_page.get("count") != len(alt_items) or
            alt_page.get("total_count") != len(alt_items)):
            alt_status = "INCOMPLETE_PAGE"
        else:
            alt_worker_names = [x["name"] for x in alt_items]
            alt_status = "COMPLETE"
    except AuditBlocked:
        alt_status = "UNAVAILABLE"
    workers = []
    for obj in worker_list:
        name = obj["id"]
        escaped = urllib.parse.quote(name, safe="")
        entry = {"name": name, "cron_count": None,
                 "bindings": None, "settings_verified": False,
                 "cron_verified": False}
        try:
            settings = get(token, "/workers/scripts/" + escaped + "/settings")
            payload = settings.get("result") or {}
            entry["bindings"] = summarize_bindings(payload.get("bindings") or [])
            entry["settings_verified"] = True
        except AuditBlocked:
            pass
        try:
            cron = get(token, "/workers/scripts/" + escaped + "/schedules")
            schedules = (cron.get("result") or {}).get("schedules")
            if not isinstance(schedules, list):
                raise AuditBlocked("CRON_RESPONSE_INVALID")
            entry["cron_count"] = len(schedules)
            entry["cron_verified"] = True
        except AuditBlocked:
            pass
        workers.append(entry)
    names = {w["name"] for w in workers}
    census_agrees = bool(scripts_page_complete and alt_status == "COMPLETE" and
                         names == set(alt_worker_names) and len(names) > 0)
    if not scripts_page_complete:
        census_state = "LEGACY_SCRIPTS_LIST_TRUNCATED"
    elif alt_status != "COMPLETE":
        census_state = "ALTERNATE_WORKERS_LIST_" + alt_status
    elif names != set(alt_worker_names):
        census_state = "WORKER_LISTS_DISAGREE"
    elif not names:
        census_state = "BOTH_LISTS_EMPTY_HISTORIC_DISCREPANCY"
    else:
        census_state = "BOTH_LISTS_MATCH"
    return {
        "status": "TARGET_INVENTORY_READ_ONLY_PARTIAL_PARITY",
        "account_scope": "Louisalviss3 target only",
        "account_id": TARGET,
        "checked_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "database_count": len(d1), "database_names": d1_names,
        "historical_target_d1_uuid_matches_live": historical_uuid_matches,
        "historical_target_d1_uuid_all_match": all(historical_uuid_matches.values()),
        "canonical_d1_present": {name: name in d1_names for name in D1_CANONICAL},
        "calibration_d1_present": D1_EXTRA_REVIEW in d1_names,
        "calibration_retention_unresolved": True,
        "worker_count": len(workers), "workers": workers,
        "alternative_worker_count": len(alt_worker_names) if alt_worker_names is not None else None,
        "alternative_worker_names": alt_worker_names,
        "alternative_worker_list_status": alt_status,
        "worker_census_state": census_state,
        "worker_census_consistent": census_agrees,
        "target_workers_zero_verified": False,
        "source_protected_worker_names_present": {
            name: name in names for name in WORKERS_PROTECT
        },
        "all_worker_settings_verified": census_agrees and all(w["settings_verified"] for w in workers),
        "all_worker_cron_verified": census_agrees and all(w["cron_verified"] for w in workers),
        "d1_schema_row_parity_verified": False,
        "worker_code_deployment_parity_verified": False,
        "worker_binding_secret_values_checked": False,
        "r2_operations": 0,
        "cutover_ready": False,
        "source_deleted": False,
    }

def main():
    result = None
    try:
        token = os.environ.get("CLOUDFLARE_TARGET_AUDIT_TOKEN", "")
        result = read_inventory(token)
    except AuditBlocked as e:
        result = {"status": "BLOCKED", "reason": str(e),
                  "r2_operations": 0, "cutover_ready": False,
                  "source_deleted": False}
    except Exception as e:
        result = {"status": "BLOCKED",
                  "reason": "UNEXPECTED_" + type(e).__name__,
                  "r2_operations": 0, "cutover_ready": False,
                  "source_deleted": False}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    print("TARGET_D1_WORKER_AUDIT", result["status"],
          "d1=" + str(result.get("database_count", "unknown")),
          "workers=" + str(result.get("worker_count", "unknown")))
    if result["status"] == "BLOCKED":
        raise SystemExit(3)

if __name__ == "__main__":
    main()
