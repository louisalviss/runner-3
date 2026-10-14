#!/usr/bin/env python3
"""Read-only, bounded Worker inventory for Ducduy2411.

Uses the existing source account-scoped Actions secret on the GitHub runner.
Never exposes secret text, Worker source bodies, credentials or auth headers.
No Worker mutation/deletion; absence of cron is NOT absence of traffic.
"""
from __future__ import annotations

import datetime as dt
import json
import os
from pathlib import Path
import re
import urllib.error
import urllib.parse
import urllib.request

ACCOUNT = "7415a87f6bce7884e73ad7cfed5782df"
ROOT = "https://api.cloudflare.com/client/v4/accounts/" + ACCOUNT
MAX_WORKERS = 250
SAFE_NAME = re.compile(r"^[A-Za-z0-9_-]{1,128}$")
OUT = Path("migration-out/workers-source-audit.json")


class AuditBlocked(RuntimeError):
    pass


def get_json(path, token):
    request = urllib.request.Request(
        ROOT + path,
        headers={"Authorization": "Bearer " + token, "Accept": "application/json"},
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as res:
            status, raw = res.status, res.read(2_000_001)
    except urllib.error.HTTPError as exc:
        return exc.code, None
    except Exception:
        return 0, None
    if len(raw) > 2_000_000:
        return 0, None
    try:
        obj = json.loads(raw)
    except (ValueError, TypeError):
        return 0, None
    if not isinstance(obj, dict) or not obj.get("success"):
        return status, None
    return status, obj


def get_result(reader, path):
    code, data = reader(path)
    if code != 200 or not isinstance(data, dict):
        return None, "DENIED" if code in (401, 403) else "UNAVAILABLE"
    if data.get("success") is not True:
        return None, "UNAVAILABLE"
    return data.get("result"), "OK"


def inventory(reader):
    scripts, status = get_result(reader, "/workers/scripts")
    if status != "OK" or not isinstance(scripts, list):
        raise AuditBlocked("SOURCE_WORKERS_LIST_" + status)
    if len(scripts) > MAX_WORKERS:
        raise AuditBlocked("WORKER_COUNT_BOUND")
    items, seen = [], set()
    for script in scripts:
        if not isinstance(script, dict):
            raise AuditBlocked("WORKER_ENTRY_INVALID")
        name = script.get("id")
        if not isinstance(name, str) or not SAFE_NAME.fullmatch(name) or name in seen:
            raise AuditBlocked("WORKER_ID_INVALID_OR_DUPLICATE")
        seen.add(name)
        p = "/workers/scripts/" + urllib.parse.quote(name, safe="")
        settings, ss = get_result(reader, p + "/settings")
        schedules, cs = get_result(reader, p + "/schedules")
        subdomain, ds = get_result(reader, p + "/subdomain")
        deployments, vs = get_result(reader, p + "/deployments")

        bindings = []
        if ss == "OK" and isinstance(settings, dict) and isinstance(settings.get("bindings"), list):
            for binding in settings["bindings"]:
                if not isinstance(binding, dict):
                    raise AuditBlocked("BINDING_SHAPE_INVALID")
                # Deliberately omit all binding values, ids, text and secrets.
                kind = binding.get("type")
                label = binding.get("name")
                if not isinstance(kind, str) or not isinstance(label, str):
                    raise AuditBlocked("BINDING_NAME_INVALID")
                bindings.append({"type": kind[:60], "name": label[:100]})
        elif ss == "OK":
            ss = "INCOMPLETE"

        cron_count = None
        if cs == "OK" and isinstance(schedules, dict) and isinstance(schedules.get("schedules"), list):
            cron_count = len(schedules["schedules"])
        elif cs == "OK":
            cs = "INCOMPLETE"

        publicly_enabled = None
        if ds == "OK" and isinstance(subdomain, dict) and isinstance(subdomain.get("enabled"), bool):
            publicly_enabled = subdomain["enabled"]
        elif ds == "OK":
            ds = "INCOMPLETE"

        deployments_count = None
        if vs == "OK" and isinstance(deployments, dict) and isinstance(deployments.get("deployments"), list):
            deployments_count = len(deployments["deployments"])
        elif vs == "OK":
            vs = "INCOMPLETE"

        statuses = {"settings": ss, "cron": cs, "subdomain": ds, "deployments": vs}
        items.append({
            "name": name,
            "created_on": script.get("created_on") if isinstance(script.get("created_on"), str) else None,
            "modified_on": script.get("modified_on") if isinstance(script.get("modified_on"), str) else None,
            "checks": statuses,
            "binding_names_and_types_only": bindings,
            "cron_count": cron_count,
            "workers_dev_enabled": publicly_enabled,
            "deployment_count": deployments_count,
            "traffic_30d": "UNKNOWN",
            "routes_and_external_callers": "UNKNOWN",
            "restorable_backup": "UNKNOWN",
            "cleanup_classification": "HOLD_NOT_DELETE",
        })
    items.sort(key=lambda x: x["name"])
    all_ok = all(all(status == "OK" for status in x["checks"].values()) for x in items)
    return {
        "schema": "cf-worker-source-readonly-audit-v1",
        "source_account_id": ACCOUNT,
        "captured_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "status": "READ_ONLY_INVENTORY_COMPLETE" if all_ok else "PARTIAL_UNKNOWN",
        "worker_count": len(items),
        "safe_to_delete_count": 0,
        "traffic_and_dependency_parity_verified": False,
        "source_mutated": False,
        "secrets_exposed": False,
        "workers": items,
    }


def main():
    if os.environ.get("CLOUDFLARE_ACCOUNT_ID") != ACCOUNT:
        raise SystemExit("SOURCE_ACCOUNT_MISMATCH")
    token = os.environ.get("CLOUDFLARE_API_TOKEN")
    if not token:
        raise SystemExit("SOURCE_CREDENTIAL_UNAVAILABLE")
    try:
        result = inventory(lambda path: get_json(path, token))
    except AuditBlocked as exc:
        print("WORKERS_READONLY_BLOCKED", str(exc))
        raise SystemExit(3) from None
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print("WORKERS_READONLY_RESULT", json.dumps({
        "status": result["status"], "worker_count": result["worker_count"],
        "safe_to_delete_count": 0, "source_mutated": False,
    }, sort_keys=True))
    if result["status"] != "READ_ONLY_INVENTORY_COMPLETE":
        raise SystemExit(2)


if __name__ == "__main__":
    main()
