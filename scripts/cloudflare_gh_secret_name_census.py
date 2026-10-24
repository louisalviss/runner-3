#!/usr/bin/env python3
"""One-time, trusted-main GitHub Actions Cloudflare SECRET NAME census.

The GitHub Actions secrets context is available at runtime, not via this
connector's repository API. GitHub injects it as JSON only into THIS STEP.
Parse it in memory. Export only Cloudflare-related secret NAMES and boolean
read-only target metadata checks, not raw values, hashes, policies, identities
or arbitrary other secrets. Strictly GET Cloudflare D1 metadata, never query
D1 rows, WRITE, RESTORE, R2, or perform credential-management actions.
"""
import json
import os
import pathlib
import re

from cloudflare_existing_token_scope_readonly import inspect_secret

REPO = "louisalviss/runner-3"
OUTPUT = pathlib.Path("migration-out/cloudflare-secret-name-census.json")
NAME = re.compile(r"^[A-Z][A-Z0-9_]{1,99}$")
MAX_CONTEXT_SIZE = 250_000
MAX_CANDIDATES = 40
MAX_BEARER_PROBES = 20


class Hold(ValueError):
    pass


def ensure(condition, reason):
    if not condition:
        raise Hold(reason)


def cloudflare_candidate(name):
    return (isinstance(name, str) and NAME.fullmatch(name) is not None and
            (name.startswith("CLOUDFLARE_") or name.startswith("CF_") or
             name in ("CF_API_TOKEN", "CF_TOKEN")))


def inspect_names(context_json, probe=inspect_secret):
    """Values of ALL secrets are kept in local process memory, NEVER output."""
    ensure(isinstance(context_json, str) and
           0 < len(context_json) <= MAX_CONTEXT_SIZE,
           "GITHUB_SECRETS_CONTEXT_MISSING_OR_OVERSIZED")
    try:
        secrets = json.loads(context_json)
    except (UnicodeError, ValueError):
        raise Hold("INVALID_GITHUB_SECRETS_CONTEXT") from None
    ensure(type(secrets) is dict, "GITHUB_SECRETS_CONTEXT_NOT_OBJECT")
    names = sorted(name for name in secrets if cloudflare_candidate(name))
    ensure(len(names) <= MAX_CANDIDATES,
           "CLOUDFLARE_SECRET_COUNT_BUDGET_EXCEEDED")
    bearer_names = [
        name for name in names
        if name.endswith("_TOKEN") or name == "CF_TOKEN"
    ]
    ensure(len(bearer_names) <= MAX_BEARER_PROBES,
           "CLOUDFLARE_BEARER_PROBE_BUDGET_EXCEEDED")

    summary = {}
    for name in names:
        value = secrets[name]
        entry = {
            "present_nonempty": isinstance(value, str) and bool(value),
            "tested_as_cloudflare_bearer_token": name in bearer_names,
            "target_d1_metadata_verified": None,
            "target_d1_http_status": None,
            "source_d1_metadata_verified": None,
            "d1_write_proven": False,
        }
        if name in bearer_names and isinstance(value, str) and len(value) >= 16:
            # GET-only helper, may read token policy metadata if permitted.
            # No Cloudflare D1 queries, mutations, R2, or restore paths.
            try:
                observed = probe(value)
            except (ValueError, TypeError, OSError, RuntimeError):
                # E.g. malformed authorization header / invalid bearer format.
                # Neither the secret nor exception is ever printed or exported.
                observed = {}
            entry["target_d1_metadata_verified"] = observed.get(
                "target_metadata_verified", False)
            entry["target_d1_http_status"] = observed.get(
                "target_metadata_http_status", 0)
            entry["source_d1_metadata_verified"] = observed.get(
                "source_metadata_verified", False)
            entry["token_self_policy_readable"] = observed.get(
                "self_policy_readable", False)
            entry["d1_write_permission_name_visible"] = observed.get(
                "d1_write_permission_named", None)
            entry["target_resource_named_in_policy"] = observed.get(
                "policy_target_resource_mentioned", None)
        summary[name] = entry

    # Do not expose values from secrets object in any local report object.
    return {
        "format": "cloudflare-github-secrets-name-census-v1",
        "repository": REPO,
        "cloudflare_matching_secret_names": names,
        "matching_secret_count": len(names),
        "cloudflare_secret_checks": summary,
        "unrelated_secret_names_exported": False,
        "any_secret_values_or_hashes_exported": False,
        "token_policy_raw_exported": False,
        "actual_target_d1_write_permission_proven": False,
        "cloudflare_d1_row_queries": 0,
        "cloudflare_d1_mutations": 0,
        "r2_requests": 0,
        "time_travel_restores": 0,
        "production_cutover_approved": False,
    }


def main():
    if not (os.getenv("GITHUB_REPOSITORY") == REPO and
            os.getenv("GITHUB_REF") == "refs/heads/main" and
            os.getenv("GITHUB_EVENT_NAME") == "push"):
        print("CLOUDFLARE_SECRET_CENSUS_HOLD UNTRUSTED_CONTEXT")
        return 3
    try:
        summary = inspect_names(os.getenv("GH_ALL_SECRETS_JSON", ""))
        OUTPUT.parent.mkdir(parents=True, exist_ok=True)
        OUTPUT.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n",
                          encoding="utf8")
    except Hold as exc:
        print("CLOUDFLARE_SECRET_CENSUS_HOLD", str(exc))
        return 3
    except (OSError, ValueError, TypeError, UnicodeError):
        print("CLOUDFLARE_SECRET_CENSUS_HOLD INTERNAL_OR_IO_ERROR")
        return 3
    # Summary only, never the secrets JSON, values or token policy raw text.
    print("CLOUDFLARE_SECRET_CENSUS_READONLY_PASS",
          "matching_names", summary["matching_secret_count"],
          "target_readable", sum(
              x["target_d1_metadata_verified"] is True
              for x in summary["cloudflare_secret_checks"].values()),
          "no_d1_mutations no_r2")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
