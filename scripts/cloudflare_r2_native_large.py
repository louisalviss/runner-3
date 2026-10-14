#!/usr/bin/env python3
"""Single-object disk-streamed R2 REST -> S3 PUT with conditional no-overwrite.

Only WordPress media objects strictly >20 MB and <=256 MB. Uses the existing
GitHub Actions credentials, never copies source cookies/tokens into artifacts,
and never deletes or overwrites. Not suitable for encrypted/encoded data if
the Cloudflare REST GET returns a byte stream differing from the LIST size.
"""
from __future__ import annotations

import base64
import hashlib
import os
import tempfile
import urllib.error
import urllib.parse
import urllib.request

from botocore.exceptions import ClientError
from cloudflare_r2_native_canary import (
    SOURCE_ACCOUNT, GateError, head_or_none, source_properties, verify_properties,
)

BUCKET = "runner3-wp-media"
MIN_BYTES_EXCLUSIVE = 20_000_000
MAX_BYTES = 256_000_000
CHUNK_BYTES = 1024 * 1024


def check_object(obj):
    key = obj.get("key")
    size = obj.get("size")
    if not isinstance(key, str) or not key or not isinstance(size, int):
        raise GateError("LARGE_OBJECT_SHAPE")
    if not MIN_BYTES_EXCLUSIVE < size <= MAX_BYTES:
        raise GateError("LARGE_OBJECT_SIZE_GATE")
    return key, size


def stream_source(token, obj, out):
    """Read the exact source stored size through the documented account REST GET.

    Fail closed rather than guess when HTTP transfer encoding changes the
    number of returned bytes. No Range dependency, no buffering a 256 MB object.
    """
    key, expected = check_object(obj)
    path = "/r2/buckets/" + BUCKET + "/objects/" + urllib.parse.quote(key, safe="/")
    req = urllib.request.Request(
        "https://api.cloudflare.com/client/v4/accounts/" + SOURCE_ACCOUNT + path,
        headers={
            "Authorization": "Bearer " + token,
            "Accept": "application/octet-stream",
            "Accept-Encoding": "identity",
        },
        method="GET",
    )
    try:
        res = urllib.request.urlopen(req, timeout=180)
    except Exception:
        raise GateError("LARGE_SOURCE_GET_FAILED") from None
    sha = hashlib.sha256()
    md5 = hashlib.md5()
    size = 0
    try:
        with res:
            if res.status != 200:
                raise GateError("LARGE_SOURCE_HTTP")
            while True:
                chunk = res.read(CHUNK_BYTES)
                if not chunk:
                    break
                size += len(chunk)
                if size > expected or size > MAX_BYTES:
                    raise GateError("LARGE_SOURCE_STREAM_OVERFLOW")
                out.write(chunk)
                sha.update(chunk)
                md5.update(chunk)
    except GateError:
        raise
    except Exception:
        raise GateError("LARGE_SOURCE_STREAM_FAILED") from None
    if size != expected:
        # Do not assume gzip decoding equals stored bytes, or re-encode.
        raise GateError("LARGE_SOURCE_TRANSFER_SIZE_DRIFT")
    out.seek(0)
    return sha.hexdigest(), base64.b64encode(md5.digest()).decode()


def verify_s3_read_only(client, obj, expected_sha, source_put):
    """Read target HEAD+full GET in constant memory; never writes."""
    key, expected_size = check_object(obj)
    try:
        head = client.head_object(Bucket=BUCKET, Key=key)
        if head.get("ContentLength") != expected_size:
            raise GateError("LARGE_TARGET_SIZE_DRIFT")
        verify_properties(source_put, head)
        response = client.get_object(Bucket=BUCKET, Key=key)
    except GateError:
        raise
    except Exception:
        raise GateError("LARGE_TARGET_READ_FAILED") from None
    total = 0
    sha = hashlib.sha256()
    try:
        body = response["Body"]
        try:
            while True:
                chunk = body.read(CHUNK_BYTES)
                if not chunk:
                    break
                total += len(chunk)
                if total > expected_size:
                    raise GateError("LARGE_TARGET_STREAM_OVERFLOW")
                sha.update(chunk)
        finally:
            if hasattr(body, "close"):
                body.close()
    except GateError:
        raise
    except Exception:
        raise GateError("LARGE_TARGET_STREAM_FAILED") from None
    if total != expected_size or sha.hexdigest() != expected_sha:
        raise GateError("LARGE_TARGET_SHA256_MISMATCH")
    return total


def copy_one_large(client, token, obj):
    key, expected_size = check_object(obj)
    properties = source_properties(obj)
    if not token or os.environ.get("CLOUDFLARE_ACCOUNT_ID") != SOURCE_ACCOUNT:
        raise GateError("LARGE_SOURCE_CREDENTIAL_GATE")
    with tempfile.TemporaryFile(mode="w+b") as tmp:
        expected_sha, b64_md5 = stream_source(token, obj, tmp)
        old = head_or_none(client, BUCKET, key)
        uploaded = False
        if old is None:
            def require_new_key(request, **kwargs):
                request.headers["If-None-Match"] = "*"

            event = "before-sign.s3.PutObject"
            client.meta.events.register(event, require_new_key)
            try:
                args = {
                    "Bucket": BUCKET, "Key": key, "Body": tmp,
                    "ContentLength": expected_size, "ContentMD5": b64_md5,
                    **properties,
                }
                client.put_object(**args)
                uploaded = True
            except ClientError as e:
                status = (e.response.get("ResponseMetadata") or {}).get("HTTPStatusCode", 0)
                if status in (409, 412):
                    raise GateError("LARGE_CONDITIONAL_PUT_CONFLICT") from None
                raise GateError("LARGE_CONDITIONAL_PUT_FAILED") from None
            except GateError:
                raise
            except Exception:
                raise GateError("LARGE_CONDITIONAL_PUT_FAILED") from None
            finally:
                client.meta.events.unregister(event, require_new_key)
        else:
            if old.get("ContentLength") != expected_size:
                raise GateError("LARGE_EXISTING_TARGET_SIZE_DRIFT")
        verified_bytes = verify_s3_read_only(client, obj, expected_sha, properties)
        return {
            "key_sha256": hashlib.sha256(key.encode()).hexdigest(),
            "object_sha256": expected_sha,
            "object_bytes": verified_bytes,
            "uploaded": uploaded,
            "verified": True,
            "source_deleted": False,
            "overwritten": False,
        }
