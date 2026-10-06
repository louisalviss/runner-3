from __future__ import annotations

import json
import os
import pathlib
import subprocess

RECOVERY_BIN = pathlib.Path(os.environ.get(
    "SEMRUSH_RECOVERY_BIN",
    "/usr/local/bin/semrush-noxtools-login",
))
RECOVERABLE_CODES = {"SEMRUSH_LIVE_AUTH_UNAVAILABLE"}


def response_code(response):
    if not isinstance(response, dict):
        return "BROKER_INVALID_RESPONSE"
    return str(
        response.get("error_code")
        or response.get("state")
        or ("PASS" if response.get("ok") is True else "BROKER_UNAVAILABLE")
    )


def _run_recovery(timeout=180):
    try:
        proc = subprocess.run(
            [str(RECOVERY_BIN)],
            text=True,
            capture_output=True,
            timeout=timeout,
            check=False,
        )
    except FileNotFoundError:
        return {
            "ok": False,
            "state": "RECOVERY_BIN_NOT_FOUND",
            "returncode": 127,
        }
    except subprocess.TimeoutExpired:
        return {
            "ok": False,
            "state": "RECOVERY_TIMEOUT",
            "returncode": 124,
        }

    stdout = (proc.stdout or "").strip()
    try:
        payload = json.loads(stdout) if stdout else {}
    except Exception:
        payload = {}

    ok = (
        proc.returncode == 0
        and isinstance(payload, dict)
        and payload.get("ok") is True
    )
    return {
        "ok": ok,
        "state": (
            str(payload.get("state") or "RECOVERY_PASS")
            if ok
            else str(payload.get("state") or "RECOVERY_FAILED")
        ),
        "server": payload.get("server") if isinstance(payload, dict) else None,
        "returncode": proc.returncode,
        "detail": (
            str(payload.get("detail") or "")[:300]
            if isinstance(payload, dict)
            else ""
        ),
    }


def ensure_with_one_shot_recovery(broker_call, timeout=180):
    first = broker_call({"action": "ensure"}, timeout=timeout)
    first_code = response_code(first)
    evidence = {
        "attempted": False,
        "trigger": first_code,
        "recovery": None,
        "retry_code": None,
        "success": bool(isinstance(first, dict) and first.get("ok") is True),
    }
    if evidence["success"] or first_code not in RECOVERABLE_CODES:
        return first, evidence

    evidence["attempted"] = True
    recovery = _run_recovery(timeout=timeout)
    evidence["recovery"] = recovery
    if not recovery.get("ok"):
        failed = {
            "ok": False,
            "state": "SEMRUSH_ONE_SHOT_RECOVERY_FAILED",
            "error_code": "SEMRUSH_ONE_SHOT_RECOVERY_FAILED",
            "detail": str(recovery.get("state") or "RECOVERY_FAILED")[:300],
        }
        evidence["retry_code"] = "NOT_ATTEMPTED"
        return failed, evidence

    retry = broker_call({"action": "ensure"}, timeout=timeout)
    retry_code = response_code(retry)
    evidence["retry_code"] = retry_code
    evidence["success"] = bool(isinstance(retry, dict) and retry.get("ok") is True)
    return retry, evidence
