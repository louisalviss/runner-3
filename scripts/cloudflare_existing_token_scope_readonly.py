#!/usr/bin/env python3
"""Inspect only existing GitHub Actions secret *presence* and Cloudflare GET permissions.

No writes, no D1 SQL query endpoint, no R2, no tokens/policy documents in
logs or artifacts. Intended for trusted pushes to this repository's main only.
The operator's existing full-access credential may work for target D1, but
a successful read is NOT proof of D1 Write.
"""
import json
import os
import pathlib
import re
import urllib.error
import urllib.request

SOURCE_ACCOUNT = "7415a87f6bce7884e73ad7cfed5782df"
TARGET_ACCOUNT = "748a80810f77f447ee476543ef0e5014"
SOURCE_D1 = "9cbec4ec-c930-459d-9499-9c66166c9241"
TARGET_D1 = "82613659-8d08-455f-b6e7-f8f6e4312e22"
BASE = "https://api.cloudflare.com/client/v4"
OUT = pathlib.Path("migration-out/cloudflare-secret-scope-readonly.json")
TOKENS = (
    "CLOUDFLARE_API_TOKEN",
    "CLOUDFLARE_TARGET_AUDIT_TOKEN",
    "CLOUDFLARE_TARGET_D1_WRITE_TOKEN",
    "CLOUDFLARE_TARGET_MIGRATION_R2_TOKEN",
    "CLOUDFLARE_MIGRATION_TOKEN",
    "CLOUDFLARE_TARGET_WRITE_TOKEN",
    "CLOUDFLARE_TARGET_API_TOKEN",
    "CLOUDFLARE_ACCOUNT_MIGRATION_TOKEN",
)
URLS = {
    "source_metadata": BASE + f"/accounts/{SOURCE_ACCOUNT}/d1/database/{SOURCE_D1}",
    "target_metadata": BASE + f"/accounts/{TARGET_ACCOUNT}/d1/database/{TARGET_D1}",
    "user_verify": BASE + "/user/tokens/verify",
    "target_account_verify": BASE + f"/accounts/{TARGET_ACCOUNT}/tokens/verify",
}
MAX_BYTES = 90_000
TOKEN_ID = re.compile(r"[a-f0-9]{32}\Z")


def readonly_get(token, url, opener=urllib.request.urlopen):
    """Return (HTTP status, Cloudflare result); never echo credentials."""
    allowed = url in URLS.values()
    # Self-token details require API Tokens Read, and may be denied.
    user_prefix = BASE + "/user/tokens/"
    account_prefix = BASE + f"/accounts/{TARGET_ACCOUNT}/tokens/"
    if url.startswith(user_prefix) or url.startswith(account_prefix):
        candidate = url.rsplit("/", 1)[-1]
        allowed = bool(TOKEN_ID.fullmatch(candidate)) and (
            url == user_prefix + candidate or
            url == account_prefix + candidate)
    if not allowed or type(token) is not str or len(token) < 16:
        return 0, None
    req = urllib.request.Request(
        url,method="GET",headers={
            "Authorization": "Bearer " + token,
            "Accept": "application/json",
        })
    if req.get_method() != "GET" or req.data is not None:
        return 0,None
    try:
        with opener(req, timeout=15) as response:
            status = response.status
            raw = response.read(MAX_BYTES + 1)
    except urllib.error.HTTPError as error:
        return int(error.code),None
    except (urllib.error.URLError, TimeoutError, OSError):
        return 0,None
    if status != 200 or len(raw) > MAX_BYTES:
        return status,None
    try:
        value = json.loads(raw)
    except (ValueError,UnicodeError):
        return status,None
    if not isinstance(value,dict) or value.get("success") is not True:
        return status,None
    return status,value.get("result")


def inspect_secret(token, requester=readonly_get):
    if not isinstance(token,str) or len(token) < 16:
        return {"present": False}
    outcome = {"present":True}
    kind = None
    token_id = None
    for kindname, urlkey in (
        ("user","user_verify"),
        ("account","target_account_verify"),
    ):
        status, result = requester(token, URLS[urlkey])
        if isinstance(result,dict) and result.get("status") == "active":
            kind=kindname
            tid=result.get("id")
            if type(tid) is str and TOKEN_ID.fullmatch(tid):
                token_id=tid
            break
    outcome["active_token_verified"]=kind is not None
    for label, account, uuid in (
        ("source_metadata",SOURCE_ACCOUNT,SOURCE_D1),
        ("target_metadata",TARGET_ACCOUNT,TARGET_D1),
    ):
        status,result=requester(token,URLS[label])
        outcome[label+"_http_status"]=status
        outcome[label+"_verified"]=(
            status==200 and isinstance(result,dict) and
            result.get("uuid")==uuid and
            result.get("name")=="runner3-content-intelligence")
    # Policy introspection is conditional: without API Tokens Read,
    # it can return 403 despite a valid D1 Write token.
    outcome["self_policy_readable"]=False
    outcome["d1_write_permission_named"]=None
    outcome["policy_target_resource_mentioned"]=None
    if kind and token_id:
        details_url=(BASE + "/user/tokens/" + token_id if kind=="user" else
                     BASE + f"/accounts/{TARGET_ACCOUNT}/tokens/" + token_id)
        status,data=requester(token,details_url)
        if status==200 and isinstance(data,dict) and isinstance(data.get("policies"),list):
            outcome["self_policy_readable"]=True
            allows=[p for p in data["policies"]
                    if isinstance(p,dict) and p.get("effect")=="allow"]
            group_names=[
                str(g.get("name","")).lower()
                for p in allows
                for g in p.get("permission_groups",[])
                if isinstance(g,dict)
            ]
            outcome["d1_write_permission_named"]=any(
                "d1" in g and any(x in g for x in ("write","edit","admin"))
                for g in group_names)
            # A mention is evidence for manual review only, NOT complete
            # proof of policy resource coverage or effective privileges.
            outcome["policy_target_resource_mentioned"]=any(
                TARGET_ACCOUNT in json.dumps(p.get("resources",{}))
                for p in allows)
    outcome["actual_target_d1_write_test_performed"]=False
    return outcome


def main():
    # This audit never runs on a PR or on a fork.
    if (os.environ.get("GITHUB_REPOSITORY")!="louisalviss/runner-3" or
        os.environ.get("GITHUB_REF")!="refs/heads/main" or
        os.environ.get("GITHUB_EVENT_NAME")!="push"):
        print("CLOUDFLARE_TOKEN_SCOPE_HOLD UNTRUSTED_ACTION_CONTEXT")
        return 3
    report={
        "format":"cloudflare-existing-gh-secrets-readonly-scope-v1",
        "source_account_id":SOURCE_ACCOUNT,
        "target_account_id":TARGET_ACCOUNT,
        "secret_checks":{},
        "cloudflare_http_methods":["GET"],
        "d1_sql_requests":0,
        "d1_writes":0,"r2_requests":0,
        "actual_d1_write_authorized":False,
    }
    for name in TOKENS:
        report["secret_checks"][name]=inspect_secret(os.environ.get(name,""))
    OUT.parent.mkdir(exist_ok=True,parents=True)
    OUT.write_text(json.dumps(report,indent=2,sort_keys=True)+"\n")
    # Print only presence and read-only scopes. Never print tokens, IDs,
    # policy documents, scopes list, response body, or exception strings.
    print("CLOUDFLARE_TOKEN_SCOPE_READONLY_CHECK_COMPLETE")
    print("candidate_secret_names_checked",len(TOKENS),
          "present",sum(bool(v.get("present")) for v in report["secret_checks"].values()))
    print("no D1 writes, no SQL, no R2, no real Write permission test")
    return 0


if __name__=="__main__":
    raise SystemExit(main())
