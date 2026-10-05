#!/opt/chatgpt-bridge/venv/bin/python
from __future__ import annotations

import json
import os
import pathlib
import subprocess
from typing import Any

HEALTHCHECK = pathlib.Path(os.environ.get("SEMRUSH_HEALTHCHECK_BIN", "/usr/local/bin/semrush-healthcheck"))


def _run_healthcheck(*, deep: bool) -> dict[str, Any]:
    cmd = [str(HEALTHCHECK)]
    if deep:
        cmd.append("--deep")
    timeout = 180 if deep else 20
    try:
        proc = subprocess.run(cmd, text=True, capture_output=True, timeout=timeout, check=False)
    except FileNotFoundError as exc:
        return {"ok": False, "mode": "deep" if deep else "shallow", "reason": "HEALTHCHECK_NOT_FOUND"}
    except subprocess.TimeoutExpired as exc:
        return {"ok": False, "mode": "deep" if deep else "shallow", "reason": "HEALTHCHECK_TIMEOUT"}
    stdout = (proc.stdout or "").strip()
    try:
        payload = json.loads(stdout) if stdout else {}
    except Exception:
        payload = {}
    ok = proc.returncode == 0 and isinstance(payload, dict) and payload.get("status") == "PASS"
    return {
        "ok": ok,
        "mode": "deep" if deep else "shallow",
        "returncode": proc.returncode,
        "payload": payload if isinstance(payload, dict) else {},
        "stderr": (proc.stderr or "")[:500],
        "reason": None if ok else (
            str(payload.get("reason") or "")[:500] if isinstance(payload, dict) else ""
        ) or "HEALTHCHECK_FAILED",
    }


def require_semrush_preflight() -> dict[str, Any]:
    shallow = _run_healthcheck(deep=False)
    if shallow.get("ok"):
        return {"ok": True, "shallow": shallow, "deep": None}
    deep = _run_healthcheck(deep=True)
    detail = {
        "shallow": {
            "reason": shallow.get("reason"),
            "returncode": shallow.get("returncode"),
            "payload": shallow.get("payload"),
        },
        "deep": {
            "reason": deep.get("reason"),
            "returncode": deep.get("returncode"),
            "payload": deep.get("payload"),
        },
    }
    raise RuntimeError("SEMRUSH_RUNTIME_PREFLIGHT_FAILED:" + json.dumps(detail, ensure_ascii=False, separators=(",", ":"))[:1600])
