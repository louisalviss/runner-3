#!/usr/bin/env python3
"""Cloudflare Workers AI proxy compatibility runner for AutoContent.

The repository's existing Cloudflare API token can deploy/read Workers but does
not have direct Workers AI REST scope. This runner derives a narrow proxy key
from that existing secret and calls the secured Worker AI binding instead.
"""
import hashlib
import json
import os
import time

import autocontent_engine as engine

_real_post = engine.requests.post


class CompatResponse:
    def __init__(self, status_code, payload):
        self.status_code = int(status_code)
        self._payload = payload
        self.text = json.dumps(payload, ensure_ascii=False)
        self.ok = 200 <= self.status_code < 300

    def json(self):
        return self._payload


def proxy_post(url, *args, **kwargs):
    if "models.github.ai" not in str(url):
        return _real_post(url, *args, **kwargs)

    token = (
        os.environ.get("CLOUDFLARE_API_TOKEN", "").strip()
        or os.environ.get("AUTOMATION_KEY", "").strip()
    )
    endpoint = os.environ.get(
        "AUTOCONTENT_PROXY_URL",
        "https://runner3-autocontent-ai.ducduy2411.workers.dev",
    ).strip()
    if not token or not endpoint:
        return CompatResponse(
            500,
            {
                "error": {
                    "code": "autocontent_proxy_config_missing",
                    "message": "Cloudflare token and AutoContent proxy URL are required",
                }
            },
        )

    proxy_key = hashlib.sha256(
        (token + "|runner3-autocontent-ai-v1").encode("utf-8")
    ).hexdigest()

    incoming = kwargs.get("json") or {}
    model = str(
        incoming.get("model")
        or os.environ.get("AUTOCONTENT_MODEL")
        or "@cf/openai/gpt-oss-120b"
    )
    if not model.startswith("@cf/"):
        model = "@cf/openai/gpt-oss-120b"

    payload = {
        "model": model,
        "messages": incoming.get("messages") or [],
        "temperature": incoming.get("temperature", 0.2),
        "max_tokens": incoming.get("max_tokens", 5000),
    }

    # gpt-oss-120b can occasionally exceed the base engine's historical 120s
    # timeout on large grounded prompts. Keep the caller fail-closed, but allow
    # one transport retry instead of losing the entire editorial run to a
    # transient read timeout.
    requested_timeout = kwargs.get("timeout", 180)
    try:
        requested_timeout = float(requested_timeout)
    except Exception:
        requested_timeout = 180.0
    timeout = max(240.0, requested_timeout)

    response = None
    last_error = None
    for attempt in range(2):
        try:
            response = _real_post(
                endpoint,
                headers={
                    "Authorization": f"Bearer {proxy_key}",
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                },
                json=payload,
                timeout=timeout,
            )
            break
        except (engine.requests.exceptions.ReadTimeout, engine.requests.exceptions.ConnectionError) as exc:
            last_error = exc
            if attempt == 0:
                time.sleep(2)
                continue
            raise

    if response is None:
        raise last_error or RuntimeError("AutoContent proxy request failed without a response")

    if not response.ok:
        return response

    try:
        data = response.json()
    except Exception:
        return CompatResponse(
            502,
            {
                "error": {
                    "code": "autocontent_proxy_invalid_json",
                    "message": response.text[:1200],
                }
            },
        )

    if not data.get("success"):
        return CompatResponse(
            response.status_code if response.status_code >= 400 else 502,
            data,
        )

    result = data.get("result") or {}
    content = result.get("response") if isinstance(result, dict) else None
    if not content and isinstance(result, dict):
        choices = result.get("choices") or []
        if choices:
            content = ((choices[0] or {}).get("message") or {}).get("content")
    if not content and isinstance(result, str):
        content = result

    if not isinstance(content, str) or not content.strip():
        return CompatResponse(
            502,
            {
                "error": {
                    "code": "autocontent_proxy_empty_response",
                    "message": "Workers AI proxy returned no text response",
                    "result_keys": list(result.keys()) if isinstance(result, dict) else [],
                }
            },
        )

    return CompatResponse(
        200,
        {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": content,
                    }
                }
            ]
        },
    )


engine.requests.post = proxy_post


if __name__ == "__main__":
    engine.main()
