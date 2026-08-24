"""Small best-effort D1 checkpoint client for the story/VBTH pipeline.

The pipeline remains runnable without D1. When D1_CHECKPOINT_URL is configured,
state transitions are mirrored to the central checkpoint service so interrupted
batches can be inspected/resumed without treating GitHub artifacts as the lock.
"""
from __future__ import annotations

import json
import os
import urllib.request
from typing import Any


def publish(flow: str, unit: str, status: str, **meta: Any) -> bool:
    url = os.getenv("D1_CHECKPOINT_URL", "").strip()
    if not url:
        return False
    token = os.getenv("D1_CHECKPOINT_TOKEN", "").strip()
    body = json.dumps({"flow": flow, "unit": unit, "status": status, "meta": meta}).encode()
    req = urllib.request.Request(url, data=body, method="POST")
    req.add_header("content-type", "application/json")
    if token:
        req.add_header("authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return 200 <= resp.status < 300
    except Exception:
        # Checkpointing must never corrupt or abort the editorial batch itself.
        return False
