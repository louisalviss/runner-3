#!/usr/bin/env python3
"""Manual, target-only D1 Time Travel read-only eligibility check.

Two allowlisted GETs only: D1 database metadata and Time Travel bookmark.
No D1 query/row access, restore, writing, R2, source account, deployment or
raw bookmark in stdout/artifacts. A current bookmark is NOT a pre-apply backup:
fresh bookmark and target-writer quiescence remain required immediately before
separately approved writes.
"""
import datetime as dt
import hashlib
import json
import os
import pathlib
import re
import urllib.error
import urllib.request

TARGET_ACCOUNT = "748a80810f77f447ee476543ef0e5014"
TARGET_UUID = "82613659-8d08-455f-b6e7-f8f6e4312e22"
DATABASE = "runner3-content-intelligence"
API = ("https://api.cloudflare.com/client/v4/accounts/" +
       TARGET_ACCOUNT + "/d1/database/" + TARGET_UUID)
PATHS = (API, API + "/time_travel/bookmark")
OUT = pathlib.Path("migration-out/d1-target-time-travel-readonly-gate.json")
MAX_BYTES = 32_000
# Bookmarks are opaque; restrict printable bounded ASCII without relying on
# undocumented stable length or structure beyond well-formed API response.
PRINTABLE = re.compile(r"[\x21-\x7e]{12,256}\Z")


class Hold(ValueError):
    pass


def require(ok, message):
    if not ok:
        raise Hold(message)


def get_json(token, url, opener=urllib.request.urlopen):
    require(url in PATHS, "URL_NOT_ALLOWLISTED")
    require(isinstance(token, str) and len(token) >= 16,
            "TARGET_AUDIT_TOKEN_MISSING")
    request = urllib.request.Request(
        url, method="GET", headers={
            "Authorization": "Bearer " + token,
            "Accept": "application/json",
        })
    require(request.get_method() == "GET" and request.data is None,
            "NON_GET_REQUEST_BLOCKED")
    try:
        with opener(request, timeout=25) as response:
            require(response.status == 200, "HTTP_NON_200")
            raw = response.read(MAX_BYTES + 1)
    except urllib.error.HTTPError as ex:
        raise Hold("TARGET_HTTP_" + str(ex.code)) from None
    except (urllib.error.URLError, OSError, TimeoutError):
        raise Hold("TARGET_ENDPOINT_UNAVAILABLE") from None
    require(len(raw) <= MAX_BYTES, "RESPONSE_OVERSIZED")
    try:
        data = json.loads(raw)
    except (ValueError, UnicodeError):
        raise Hold("INVALID_TARGET_API_RESPONSE") from None
    require(isinstance(data, dict) and data.get("success") is True and
            isinstance(data.get("result"), dict),
            "TARGET_API_NOT_SUCCESS")
    return data["result"]


def inspect(token, request=get_json):
    details = request(token, PATHS[0])
    require(details.get("name") == DATABASE and
            details.get("uuid") == TARGET_UUID,
            "WRONG_TARGET_D1_IDENTITY")
    require(details.get("version") == "production",
            "TIME_TRAVEL_BACKEND_NOT_PRODUCTION")
    bookmark = request(token, PATHS[1]).get("bookmark")
    require(type(bookmark) is str and PRINTABLE.fullmatch(bookmark) is not None,
            "TIME_TRAVEL_BOOKMARK_UNAVAILABLE")
    # Hash proves an internally observed value without publishing the raw
    # bookmark; does not claim the bookmark is preserved for restoration.
    bookmark_hash = hashlib.sha256(bookmark.encode("utf8")).hexdigest()
    return {
        "format": "d1-target-time-travel-readonly-preflight-v1",
        "captured_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "target_account_id": TARGET_ACCOUNT,
        "database": DATABASE,
        "target_identity_verified": True,
        "target_production_backend": True,
        "bookmark_api_read_success": True,
        "observed_bookmark_sha256": bookmark_hash,
        "raw_bookmark_exported": False,
        "bookmark_preserved_for_actual_restore": False,
        "pre_apply_fresh_bookmark_verified": False,
        "target_writers_quiesced": False,
        "whole_database_restore_is_destructive": True,
        "safe_restore_approved": False,
        "target_d1_writes": 0,
        "target_d1_queries": 0,
        "source_d1_queries": 0,
        "r2_requests": 0,
        "cutover_ready": False,
        "status": "TIME_TRAVEL_ELIGIBLE_NOT_ROLLBACK_READY",
    }


def main():
    try:
        require(not os.environ.get("CLOUDFLARE_TARGET_D1_WRITE_TOKEN") and
                not os.environ.get("CLOUDFLARE_TARGET_WRITE_TOKEN"),
                "WRITE_TOKEN_PRESENT_IN_READONLY_WORKFLOW")
        result = inspect(os.environ.get("CLOUDFLARE_TARGET_AUDIT_TOKEN", ""))
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(json.dumps(result, sort_keys=True, indent=2) + "\n",
                       encoding="utf8")
    except Hold as ex:
        print("D1_TIME_TRAVEL_READONLY_HOLD", str(ex))
        return 3
    except (OSError, UnicodeError, ValueError, TypeError):
        print("D1_TIME_TRAVEL_READONLY_HOLD INTERNAL_FAILURE")
        return 3
    print("D1_TIME_TRAVEL_READONLY_PASS target_production_backend true",
          "bookmark_api_works true rollback_not_authorized no_writes no_r2")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
