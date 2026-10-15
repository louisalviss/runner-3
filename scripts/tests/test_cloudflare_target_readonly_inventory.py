#!/usr/bin/env python3
"""Synthetic-only API contract; never contacts Cloudflare."""
from unittest.mock import patch
import cloudflare_target_readonly_inventory as m

calls=[]
def fake_get(token, path):
    calls.append(path)
    assert token == "fake-only-target-read-scope-token"
    if path.startswith("/d1/database?"):
        return {"success":True,"result":[{"name":"runner3-core","uuid":"hidden1"},
                                          {"name":"clm-copilot-calibration","uuid":"hidden2"}],
                "result_info":{"page":1,"count":2,"per_page":100,"total_count":2}}
    if path == "/workers/scripts":
        return {"success":True,"result":[{"id":"runner3-core"},{"id":"runner3-rss-fastlane"}]}
    if path.endswith("/settings"):
        return {"success":True,"result":{"bindings":[
            {"type":"service","name":"FASTLANE","service":"runner3-rss-fastlane"},
            {"type":"secret_text","name":"PRIVATE_KEY","text":"NEVER_LOG_THIS_SECRET"},
            {"type":"d1","name":"DB","id":"DO_NOT_SERIALIZE_DB_ID"},
            {"type":"r2_bucket","name":"ARTIFACTS","bucket_name":"runner3-artifacts"}
        ]}}
    if path.endswith("/schedules"):
        return {"success":True,"result":{"schedules":[{"cron":"*/5 * * * *"}]}}
    assert False,path

try:
    m.read_inventory("")
    raise AssertionError("Absent target token must abort before any network call")
except m.AuditBlocked as e:
    assert str(e) == "TARGET_AUDIT_TOKEN_ABSENT"
assert calls == []
print("PASS no target token => no requests")

with patch.object(m,"get",side_effect=fake_get):
    x=m.read_inventory("fake-only-target-read-scope-token")
assert x["database_count"]==2 and x["worker_count"]==2
assert x["calibration_d1_present"] is True
assert x["d1_schema_row_parity_verified"] is False
assert x["worker_code_deployment_parity_verified"] is False
assert x["cutover_ready"] is False and x["r2_operations"] == 0
assert x["all_worker_settings_verified"] and x["all_worker_cron_verified"]
flat=str(x)
assert "NEVER_LOG_THIS_SECRET" not in flat
assert "DO_NOT_SERIALIZE_DB_ID" not in flat
assert "runner3-artifacts" not in flat
assert "PRIVATE_KEY" in flat
assert "runner3-rss-fastlane" in flat
assert not any("r2" in p for p in calls)
print("PASS target read-only metadata, secret redaction and conservative parity flags")

# Cloudflare D1 API reports total_count even when total_pages is absent.
# The first page must NEVER be accepted as the whole account if truncated.
def partial_list(token, path):
    if path.startswith("/d1/database?"):
        value=fake_get(token,path)
        value["result_info"]={"page":1,"count":2,"per_page":2,"total_count":9}
        return value
    return fake_get(token,path)

with patch.object(m,"get",side_effect=partial_list):
    try:
        m.read_inventory("fake-only-target-read-scope-token")
        raise AssertionError("Incomplete D1 page must fail closed")
    except m.AuditBlocked as e:
        assert str(e) == "D1_INVENTORY_INCOMPLETE"

def missing_page_info(token,path):
    value=fake_get(token,path)
    if path.startswith("/d1/database?"):
        value.pop("result_info")
    return value

with patch.object(m,"get",side_effect=missing_page_info):
    try:
        m.read_inventory("fake-only-target-read-scope-token")
        raise AssertionError("Missing D1 result_info must fail closed")
    except m.AuditBlocked as e:
        assert str(e) == "D1_PAGINATION_UNKNOWN"

print("PASS incomplete or unknown D1 API pagination fails closed")


bad=[{"type":"secret_text","name":"","text":"bad"}]
try:
    m.summarize_bindings(bad)
    raise AssertionError("Invalid binding must abort")
except m.AuditBlocked:
    pass
print("PASS invalid binding fails closed")
