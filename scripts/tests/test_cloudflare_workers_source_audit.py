#!/usr/bin/env python3
"""Synthetic-only Worker inventory tests: no network and no credentials."""
import importlib.util
import json

spec = importlib.util.spec_from_file_location("audit", "scripts/cloudflare_workers_source_audit.py")
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


def reader_factory(*, deny=None, duplicate=False):
    scripts = [{"id": "runner3-core"}, {"id": "old-reader-v33-preview"}]
    if duplicate:
        scripts[1]["id"] = scripts[0]["id"]

    def reader(path):
        if path == "/workers/scripts":
            return 200, {"success": True, "result": scripts}
        if deny and deny in path:
            return 403, None
        if path.endswith("/script-settings"):
            return 200, {"success": True, "result": {"tail_consumers": []}}
        if path.endswith("/settings"):
            return 200, {"success": True, "result": {
                "bindings": [{"type": "secret_text", "name": "SECRET_TOKEN",
                              "text": "DO_NOT_EXPOSE_THIS_TEST_SECRET"}]}}
        if path.endswith("/schedules"):
            return 200, {"success": True, "result": {"schedules": []}}
        if path.endswith("/subdomain"):
            return 200, {"success": True, "result": {"enabled": False}}
        if path.endswith("/deployments"):
            return 200, {"success": True, "result": {"deployments": []}}
        return 404, None

    return reader


result = audit.inventory(reader_factory())
assert result["status"] == "READ_ONLY_INVENTORY_COMPLETE"
assert result["worker_count"] == 2 and result["safe_to_delete_count"] == 0
assert all(x["cleanup_classification"] == "HOLD_NOT_DELETE" for x in result["workers"])
assert "DO_NOT_EXPOSE_THIS_TEST_SECRET" not in json.dumps(result)
assert result["workers"][0]["checks"] == {
    "settings": "OK", "cron": "OK", "subdomain": "OK",
    "deployments": "OK", "tail_consumers": "OK"}
print("PASS read-only full inventory and secret value redaction")

result = audit.inventory(reader_factory(deny="/schedules"))
assert result["status"] == "PARTIAL_UNKNOWN"
assert all(x["checks"]["cron"] == "DENIED" for x in result["workers"])
assert result["safe_to_delete_count"] == 0
print("PASS partial permissions fail closed, no delete eligibility")

try:
    audit.inventory(reader_factory(duplicate=True))
    raise AssertionError("duplicate should not pass")
except audit.AuditBlocked as err:
    assert str(err) == "WORKER_ID_INVALID_OR_DUPLICATE"
print("PASS duplicate inventory fails closed")

def no_permission(path):
    return 403, None

try:
    audit.inventory(no_permission)
    raise AssertionError("source list denial should fail closed")
except audit.AuditBlocked as err:
    assert str(err) == "SOURCE_WORKERS_LIST_DENIED"
print("PASS source inventory denied fail closed")


# A source Worker with a service binding protects its target even if the
# target receives no independent HTTP requests. Never emit credential values.
def graph_reader(path):
    if path == "/workers/scripts":
        return 200, {"success": True, "result": [
            {"id": "caller"}, {"id": "callee"}, {"id": "irrelevant"}]}
    if path == "/workers/scripts/caller/settings":
        return 200, {"success": True, "result": {"bindings": [
            {"name": "WORKER_API", "type": "service", "service": "callee"},
            {"name": "PRIVATE", "type": "secret_text", "text": "HIDDEN_SECRET_VALUE"},
        ]}}
    if path.endswith("/script-settings"):
        return 200, {"success": True, "result": {"tail_consumers": []}}
    if path.endswith("/settings"):
        return 200, {"success": True, "result": {"bindings": []}}
    if path.endswith("/schedules"):
        return 200, {"success": True, "result": {"schedules": []}}
    if path.endswith("/subdomain"):
        return 200, {"success": True, "result": {"enabled": False}}
    if path.endswith("/deployments"):
        return 200, {"success": True, "result": {"deployments": []}}
    return 404, None

graph = audit.inventory(graph_reader)
by_name = {w["name"]: w for w in graph["workers"]}
assert by_name["caller"]["outbound_worker_refs"] == ["callee"]
assert by_name["callee"]["inbound_worker_refs"] == ["caller"]
assert by_name["callee"]["cleanup_classification"] == "REFERENCED_DO_NOT_DELETE"
assert by_name["irrelevant"]["cleanup_classification"] == "HOLD_NOT_DELETE"
assert "HIDDEN_SECRET_VALUE" not in json.dumps(graph)
assert graph["safe_to_delete_count"] == 0
print("PASS service binding graph prevents deleting reachable Worker; secret redacted")

graph_partial = audit.inventory(lambda p: (403, None) if p.endswith("/script-settings") else graph_reader(p))
assert graph_partial["status"] == "PARTIAL_UNKNOWN"
assert all(x["checks"]["tail_consumers"] == "DENIED" for x in graph_partial["workers"])
assert graph_partial["safe_to_delete_count"] == 0
print("PASS tail-consumer read denial stays UNKNOWN and cannot authorize deletion")
