#!/usr/bin/env python3
"""Small dependency-free client for Runner3 Core durable state/checkpoints."""

import json
import os
import urllib.parse
import urllib.request

DEFAULT_CORE_URL = "https://runner3-core.ducduy2411.workers.dev"
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36"
)


def _core_url(core_url=None):
    return (core_url or os.environ.get("RUNNER3_CORE_URL") or DEFAULT_CORE_URL).rstrip("/")


def _quote(value):
    return urllib.parse.quote(str(value), safe="")


def _request_json(method, path, payload=None, *, core_url=None, timeout=15):
    data = None
    headers = {
        "Accept": "application/json",
        "User-Agent": os.environ.get("RUNNER3_CORE_USER_AGENT", DEFAULT_USER_AGENT),
        "Cache-Control": "no-cache",
    }
    token = os.environ.get("RUNNER3_CORE_TOKEN", "").strip()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if payload is not None:
        data = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        headers["Content-Type"] = "application/json"

    request = urllib.request.Request(
        f"{_core_url(core_url)}{path}",
        data=data,
        headers=headers,
        method=method,
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.load(response)


def get_state(source, *, core_url=None, timeout=15):
    result = _request_json(
        "GET",
        f"/state/{_quote(source)}",
        core_url=core_url,
        timeout=timeout,
    )
    return result.get("state")


def save_state(source, *, status=None, run_id=None, detail=None, core_url=None, timeout=15):
    result = _request_json(
        "PUT",
        f"/state/{_quote(source)}",
        payload={"status": status, "run_id": run_id, "detail": detail},
        core_url=core_url,
        timeout=timeout,
    )
    return result.get("state")


def report_status(source, status, *, run_id=None, detail=None, core_url=None, timeout=15):
    return save_state(
        source,
        status=status,
        run_id=run_id,
        detail=detail,
        core_url=core_url,
        timeout=timeout,
    )


def get_checkpoint(project, scope="default", *, core_url=None, timeout=15):
    result = _request_json(
        "GET",
        f"/checkpoints/{_quote(project)}/{_quote(scope)}",
        core_url=core_url,
        timeout=timeout,
    )
    return result.get("checkpoint")


def save_checkpoint(
    project,
    source,
    *,
    scope="default",
    status=None,
    position=None,
    dropbox_path=None,
    last_error=None,
    core_url=None,
    timeout=15,
):
    result = _request_json(
        "PUT",
        f"/checkpoints/{_quote(project)}/{_quote(scope)}",
        payload={
            "source": source,
            "status": status,
            "position": position,
            "dropbox_path": dropbox_path,
            "last_error": last_error,
        },
        core_url=core_url,
        timeout=timeout,
    )
    return result.get("checkpoint")
