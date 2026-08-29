#!/usr/bin/env python3
from __future__ import annotations

import json
import mimetypes
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any


class CloudflareR2RestClient:
    """Small boto3-compatible subset for R2 object operations via Cloudflare REST API."""

    def __init__(self, account_id: str, api_token: str, timeout: int = 120):
        self.account_id = account_id.strip()
        self.api_token = api_token.strip()
        self.timeout = timeout
        if not self.account_id or not self.api_token:
            raise ValueError("Cloudflare account id and API token are required")

    def _bucket_base(self, bucket: str) -> str:
        account = urllib.parse.quote(self.account_id, safe="")
        bucket_q = urllib.parse.quote(bucket, safe="")
        return f"https://api.cloudflare.com/client/v4/accounts/{account}/r2/buckets/{bucket_q}/objects"

    def _request(self, method: str, url: str, *, data: bytes | None = None, headers: dict[str, str] | None = None) -> tuple[bytes, Any]:
        h = {
            "Authorization": f"Bearer {self.api_token}",
            "Accept": "application/json",
        }
        if headers:
            h.update(headers)
        req = urllib.request.Request(url, data=data, method=method, headers=h)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return resp.read(), resp.headers
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")[:1600]
            raise RuntimeError(f"Cloudflare R2 REST HTTP {exc.code}: {body}") from exc
        except Exception as exc:
            raise RuntimeError(f"Cloudflare R2 REST {method} failed: {type(exc).__name__}: {exc}") from exc

    @staticmethod
    def _json(raw: bytes) -> dict[str, Any]:
        try:
            payload = json.loads(raw.decode("utf-8"))
        except Exception as exc:
            raise RuntimeError(f"Cloudflare R2 REST invalid JSON: {exc}") from exc
        if payload.get("success") is not True:
            errs = payload.get("errors") or []
            safe = [
                {"code": e.get("code"), "message": e.get("message")}
                for e in errs[:5]
                if isinstance(e, dict)
            ]
            raise RuntimeError("Cloudflare R2 REST API error: " + json.dumps(safe, ensure_ascii=False))
        return payload

    def list_objects_v2(self, *, Bucket: str, Prefix: str = "", MaxKeys: int = 1000, ContinuationToken: str | None = None, **_: Any) -> dict[str, Any]:
        params: dict[str, str] = {"per_page": str(min(max(int(MaxKeys), 1), 1000))}
        if Prefix:
            params["prefix"] = Prefix
        if ContinuationToken:
            params["cursor"] = ContinuationToken
        url = self._bucket_base(Bucket) + "?" + urllib.parse.urlencode(params)
        raw, _headers = self._request("GET", url)
        payload = self._json(raw)
        result = payload.get("result") or []
        info = payload.get("result_info") or {}
        contents = []
        for obj in result:
            if not isinstance(obj, dict) or not obj.get("key"):
                continue
            contents.append({
                "Key": obj.get("key"),
                "Size": int(obj.get("size") or 0),
                "LastModified": obj.get("uploaded") or obj.get("last_modified") or "",
                "ETag": obj.get("etag") or "",
            })
        truncated = bool(info.get("is_truncated"))
        return {
            "Contents": contents,
            "IsTruncated": truncated,
            "NextContinuationToken": info.get("cursor") if truncated else None,
        }

    def download_file(self, bucket: str, key: str, filename: str) -> None:
        key_q = urllib.parse.quote(key, safe="/")
        url = self._bucket_base(bucket) + "/" + key_q
        raw, _headers = self._request("GET", url, headers={"Accept": "application/octet-stream"})
        path = Path(filename)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)

    def upload_file(self, filename: str, bucket: str, key: str, ExtraArgs: dict[str, Any] | None = None) -> None:
        path = Path(filename)
        raw = path.read_bytes()
        key_q = urllib.parse.quote(key, safe="/")
        url = self._bucket_base(bucket) + "/" + key_q
        content_type = None
        if ExtraArgs:
            content_type = ExtraArgs.get("ContentType")
        if not content_type:
            content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        body, _headers = self._request(
            "PUT",
            url,
            data=raw,
            headers={"Content-Type": content_type, "Accept": "application/json"},
        )
        self._json(body)
