#!/usr/bin/env python3
import argparse
import datetime as dt
import json
import os
import sys
import urllib.request
from pathlib import Path

DEFAULT_EVENT_URL = "https://runner3-core.ducduy2411.workers.dev/events"
DEFAULT_LATEST_URL = "https://runner3-core.ducduy2411.workers.dev/events/latest"


def utc_now():
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def write_checkpoint(path, data):
    if not path:
        return
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def request_json(url, *, method="GET", payload=None, timeout=10):
    headers = {
        "Accept": "application/json",
        "User-Agent": "Mozilla/5.0 Runner3Telemetry/1.0",
    }
    body = None
    if payload is not None:
        headers["Content-Type"] = "application/json"
        body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=timeout) as response:
        raw = response.read().decode("utf-8")
        print(method, response.status, raw)
        return json.loads(raw) if raw else None


def event_list(value):
    if isinstance(value, list):
        return value
    if isinstance(value, dict):
        for key in ("events", "data", "items"):
            if isinstance(value.get(key), list):
                return value[key]
    return []


def decode_payload(value):
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            decoded = json.loads(value)
            return decoded if isinstance(decoded, dict) else {}
        except Exception:
            return {}
    return {}


def main():
    parser = argparse.ArgumentParser(description="Post non-blocking workflow telemetry to Runner3 Core and verify D1 readback.")
    parser.add_argument("--source", required=True)
    parser.add_argument("--status", required=True)
    parser.add_argument("--workflow", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--run-attempt", required=True)
    parser.add_argument("--sha", required=True)
    parser.add_argument("--ref", required=True)
    parser.add_argument("--checkpoint")
    parser.add_argument("--event-url", default=os.environ.get("RUNNER3_EVENT_URL", DEFAULT_EVENT_URL))
    parser.add_argument("--latest-url", default=os.environ.get("RUNNER3_LATEST_URL", DEFAULT_LATEST_URL))
    args = parser.parse_args()

    base = {
        "source": args.source,
        "event_type": "workflow_status",
        "workflow": args.workflow,
        "run_id": str(args.run_id),
        "run_attempt": str(args.run_attempt),
        "job_status_at_tail": args.status,
        "sha": args.sha,
        "ref": args.ref,
        "checked_at": utc_now(),
    }

    try:
        payload = {
            "source": args.source,
            "event_type": "workflow_status",
            "payload": {
                "workflow": args.workflow,
                "run_id": str(args.run_id),
                "run_attempt": str(args.run_attempt),
                "status": args.status,
                "sha": args.sha,
                "ref": args.ref,
            },
        }
        request_json(args.event_url, method="POST", payload=payload)
        latest = request_json(args.latest_url)

        match = None
        match_body = None
        for event in event_list(latest):
            if event.get("source") != args.source or event.get("event_type") != "workflow_status":
                continue
            body = decode_payload(event.get("payload"))
            if str(body.get("run_id")) == str(args.run_id) and str(body.get("run_attempt")) == str(args.run_attempt):
                match = event
                match_body = body
                break

        print("D1_READBACK", json.dumps(match, ensure_ascii=False))
        if not match:
            raise RuntimeError("workflow_status_not_visible_in_d1")
        if str(match_body.get("status")) != str(args.status):
            raise RuntimeError(
                f"workflow_status_mismatch expected={args.status!r} actual={match_body.get('status')!r}"
            )

        checkpoint = {
            "ok": True,
            "telemetry_outcome": "success",
            **base,
            "d1_readback": match,
        }
        write_checkpoint(args.checkpoint, checkpoint)
        print(json.dumps(checkpoint, ensure_ascii=False, indent=2))
        return 0
    except Exception as exc:
        checkpoint = {
            "ok": False,
            "telemetry_outcome": "failure",
            **base,
            "error": f"{type(exc).__name__}: {exc}",
        }
        write_checkpoint(args.checkpoint, checkpoint)
        print(json.dumps(checkpoint, ensure_ascii=False, indent=2), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
