#!/usr/bin/env python3
"""Run reddit_deep_sweep with an authenticated Cloudflare Reddit-JSON fallback.

The canonical collector remains unchanged. It tries Reddit/old Reddit directly first;
only when that lane fails do we relay the exact allow-listed Reddit JSON URL through
the existing private Cloudflare bridge.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
from pathlib import Path
import time
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
COLLECTOR = Path(__file__).with_name("reddit_deep_sweep.py")
STATUS_PATH = ROOT / "ops/audio-library/chatgpt-bridge-status.json"
UA = "runner3-reddit-deep-sweep-cloudflare/1.0"


def load_collector():
    spec = importlib.util.spec_from_file_location("runner3_reddit_deep_sweep", COLLECTOR)
    if spec is None or spec.loader is None:
        raise RuntimeError("unable_to_load_reddit_collector")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def bridge_url() -> str:
    data = json.loads(STATUS_PATH.read_text(encoding="utf-8"))
    value = str(data.get("url") or data.get("worker_url") or "").rstrip("/")
    if not value.startswith("https://"):
        raise RuntimeError("cloudflare_reddit_bridge_url_missing")
    return value


def queue_token() -> str:
    token = os.environ.get("CLOUDFLARE_API_TOKEN", "")
    if not token:
        raise RuntimeError("CLOUDFLARE_API_TOKEN_missing")
    return hashlib.sha256(b"runner3-chatgpt-queue-v2\0" + token.encode()).hexdigest()


def reddit_url(path: str, query: dict[str, str | int] | None) -> str:
    suffix = path
    if query:
        suffix += ("&" if "?" in suffix else "?") + urllib.parse.urlencode(query)
    return "https://www.reddit.com" + suffix


def bridge_request_json(path: str, query: dict[str, str | int] | None = None):
    target = reddit_url(path, query)
    payload = json.dumps({"url": target}).encode("utf-8")
    errors: list[str] = []
    endpoint = bridge_url() + "/source/reddit-json"

    # A config commit can trigger the bridge deployment at the same time as a sweep.
    # Retry 404/5xx briefly so the sweep survives that rollout race.
    for attempt in range(1, 7):
        req = urllib.request.Request(
            endpoint,
            data=payload,
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
                "User-Agent": UA,
                "X-Runner-Token": queue_token(),
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=40) as resp:
                raw = resp.read()
                status = resp.status
            envelope = json.loads(raw.decode("utf-8"))
            if status != 200 or envelope.get("ok") is not True:
                raise RuntimeError(envelope.get("error") or f"bridge_http_{status}")
            data = envelope.get("data")
            if data is None:
                raise RuntimeError("bridge_missing_data")
            return data, {
                "url": target,
                "bytes": int(envelope.get("bytes") or len(raw)),
                "via": "cloudflare-reddit-json:" + str(envelope.get("via") or "unknown"),
            }
        except Exception as exc:
            errors.append(f"attempt={attempt}:{type(exc).__name__}:{exc}")
            if attempt < 6:
                time.sleep(min(2 * attempt, 8))
    raise RuntimeError("cloudflare_reddit_json_failed:" + " | ".join(errors[-6:]))


def main():
    collector = load_collector()
    direct_request_json = collector.request_json

    def request_json(path: str, query=None, tries: int = 3):
        try:
            return direct_request_json(path, query, tries)
        except Exception as direct_exc:
            try:
                return bridge_request_json(path, query)
            except Exception as bridge_exc:
                raise RuntimeError(
                    f"direct_reddit_failed:{direct_exc} | bridge_failed:{bridge_exc}"
                ) from bridge_exc

    collector.request_json = request_json
    collector.main()


if __name__ == "__main__":
    main()
