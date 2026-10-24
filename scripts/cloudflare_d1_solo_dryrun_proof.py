#!/usr/bin/env python3
"""Read-only GitHub proof of a fresh user-triggered D1 additive Dry-Run.

For one-person operation: user manually triggers the read-only Dry-Run first,
then enters THAT run's GitHub Actions ID into a separate, explicitly gated
target-INSERT workflow. This module verifies the prior successful manual run
belongs to the same initiating account, workflow, branch, and exact commit,
is recent, and has not been rerun. No GitHub write, Cloudflare API or R2 calls.

This proof is necessary but *not* sufficient for D1 writes: production apply
still requires distinct target-write token, exact fresh preserved D1 bookmark,
writer-quiescence acknowledgement, row-safe recovery, and live re-diff.
"""
import datetime as dt
import json
import os
import re
import urllib.error
import urllib.request

REPOSITORY = "louisalviss/runner-3"
DRYRUN_WORKFLOW_PATH = (
    ".github/workflows/cloudflare-d1-recommendation-runs-additive-dryrun.yml"
)
API_PREFIX = "https://api.github.com/repos/" + REPOSITORY + "/actions/runs/"
MAX_AGE_SECONDS = 1800
MAX_RESPONSE_BYTES = 96_000
RUN_ID = re.compile(r"[1-9][0-9]{5,19}\Z")
SHA = re.compile(r"[0-9a-f]{40}\Z")


class Hold(ValueError):
    pass


def require(value, error):
    if not value:
        raise Hold(error)


def read_workflow_run(token, run_id, opener=urllib.request.urlopen):
    require(type(token) is str and len(token) >= 16,
            "SOLO_GITHUB_READ_TOKEN_MISSING")
    require(type(run_id) is str and RUN_ID.fullmatch(run_id) is not None,
            "SOLO_PREPARE_RUN_ID_INVALID")
    req = urllib.request.Request(
        API_PREFIX + run_id, method="GET",
        headers={"Authorization": "Bearer " + token,
                 "Accept": "application/vnd.github+json",
                 "X-GitHub-Api-Version": "2022-11-28"})
    require(req.get_method() == "GET" and req.data is None,
            "SOLO_PROOF_MUTATING_GITHUB_REQUEST_BLOCKED")
    try:
        with opener(req, timeout=15) as response:
            require(response.status == 200, "SOLO_PROOF_HTTP_NOT_200")
            raw = response.read(MAX_RESPONSE_BYTES + 1)
    except urllib.error.HTTPError as err:
        raise Hold("SOLO_PROOF_HTTP_" + str(err.code)) from None
    except (urllib.error.URLError, OSError, TimeoutError):
        raise Hold("SOLO_PROOF_API_UNAVAILABLE") from None
    require(len(raw) <= MAX_RESPONSE_BYTES,
            "SOLO_PROOF_OVERSIZED_GITHUB_RESPONSE")
    try:
        result = json.loads(raw)
    except (ValueError, UnicodeError):
        raise Hold("SOLO_PROOF_INVALID_GITHUB_JSON") from None
    require(type(result) is dict, "SOLO_PROOF_BAD_GITHUB_RESULT")
    return result


def parse_utc(value):
    require(type(value) is str and value.endswith("Z"),
            "SOLO_PROOF_INVALID_TIMESTAMP")
    try:
        d = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise Hold("SOLO_PROOF_INVALID_TIMESTAMP") from None
    require(d.tzinfo is not None, "SOLO_PROOF_INVALID_TIMESTAMP")
    return d


def verify(run_id, token, repository, event, ref, sha, actor,
           getter=read_workflow_run, now=None):
    """One fresh run ID, strict no-secret output; no D1 access."""
    require(repository == REPOSITORY and event == "workflow_dispatch" and
            ref == "refs/heads/main" and type(sha) is str and
            SHA.fullmatch(sha) is not None and type(actor) is str and
            len(actor) > 0, "SOLO_PROOF_CURRENT_CONTEXT_NOT_MANUAL_MAIN")
    require(type(run_id) is str and RUN_ID.fullmatch(run_id) is not None,
            "SOLO_PREPARE_RUN_ID_INVALID")
    require(type(token) is str and len(token) >= 16,
            "SOLO_GITHUB_READ_TOKEN_MISSING")
    result = getter(token, run_id)
    require(result.get("id") == int(run_id) and
            result.get("name") ==
                "Cloudflare D1 Recommendation Runs Additive Dry-Run (Read Only)" and
            result.get("path") == DRYRUN_WORKFLOW_PATH and
            result.get("event") == "workflow_dispatch" and
            result.get("head_branch") == "main" and
            result.get("head_sha") == sha and
            result.get("status") == "completed" and
            result.get("conclusion") == "success" and
            result.get("run_attempt") == 1 and
            type(result.get("actor")) is dict and
            result["actor"].get("login") == actor and
            type(result.get("triggering_actor")) is dict and
            result["triggering_actor"].get("login") == actor,
            "SOLO_PROOF_NOT_SAME_USER_SUCCESSFUL_DRYRUN")
    start = parse_utc(result.get("created_at"))
    end = parse_utc(result.get("updated_at"))
    current = now if now is not None else dt.datetime.now(dt.timezone.utc)
    require(type(current) is dt.datetime and current.tzinfo is not None,
            "SOLO_PROOF_CLOCK_INVALID")
    require(start <= end <= current and
            (current - start).total_seconds() <= MAX_AGE_SECONDS and
            (current - end).total_seconds() <= MAX_AGE_SECONDS,
            "SOLO_PROOF_STALE_OR_CLOCK_INVALID")
    return {
        "proof": "FRESH_SOLO_MANUAL_READONLY_DRYRUN_VERIFIED",
        "run_id": int(run_id),
        "same_commit": True,
        "same_initiating_actor": True,
        "max_age_seconds": MAX_AGE_SECONDS,
        "target_d1_write_authorized": False,
        "cloudflare_queries": 0,
        "r2_requests": 0,
    }


def from_environment():
    return verify(
        os.environ.get("D1_SOLO_DRYRUN_RUN_ID", ""),
        os.environ.get("GITHUB_TOKEN", ""),
        os.environ.get("GITHUB_REPOSITORY", ""),
        os.environ.get("GITHUB_EVENT_NAME", ""),
        os.environ.get("GITHUB_REF", ""),
        os.environ.get("GITHUB_SHA", ""),
        os.environ.get("GITHUB_ACTOR", ""),
    )


def main():
    try:
        result = from_environment()
    except Hold as err:
        print("D1_SOLO_PREPARE_HOLD", str(err))
        return 3
    except (OSError, TypeError, ValueError):
        print("D1_SOLO_PREPARE_HOLD INTERNAL_FAILURE")
        return 3
    print("D1_SOLO_PREPARE_PASS manual_dryrun", result["run_id"],
          "same_actor true recent true same_sha true",
          "target_writes=0 cutover=false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
