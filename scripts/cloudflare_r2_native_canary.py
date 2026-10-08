#!/usr/bin/env python3
"""Bounded source REST -> destination native R2 S3 migration canary.

Secrets are consumed inside the GitHub runner only. Never log credentials,
browser state or raw object data. No source mutations and no overwrite.
"""
import argparse
import base64
import datetime as dt
import gzip
import hashlib
import json
import os
from pathlib import Path
import urllib.error
import urllib.parse
import urllib.request

import boto3
from botocore.client import Config
from botocore.exceptions import ClientError

SOURCE_ACCOUNT = "7415a87f6bce7884e73ad7cfed5782df"
TARGET_ACCOUNT = "748a80810f77f447ee476543ef0e5014"
ALLOWED = {"runner3-telegram-bobvolman-raw"}
GZIP_MAGIC = bytes((0x1f, 0x8b))
MAX_BYTES = 20_000_000
MAX_PAGES = 32


class GateError(RuntimeError):
    pass


def source_api(token, path, *, accept_encoding="identity"):
    url = "https://api.cloudflare.com/client/v4/accounts/" + SOURCE_ACCOUNT + path
    request = urllib.request.Request(
        url, headers={
            "Authorization": "Bearer " + token,
            "Accept": "*/*",
            "Accept-Encoding": accept_encoding,
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=75) as res:
            return res.status, dict(res.headers), res.read()
    except Exception as exc:
        raise GateError("SOURCE_API_" + type(exc).__name__.upper()) from None


def source_list(token, bucket):
    root = "/r2/buckets/" + bucket + "/objects"
    seen_keys, seen_cursors, objects = set(), set(), []
    cursor = None
    for _ in range(MAX_PAGES):
        path = root + "?per_page=1000"
        if cursor:
            path += "&cursor=" + urllib.parse.quote(cursor, safe="")
        status, _, data = source_api(token, path)
        try:
            payload = json.loads(data)
        except (TypeError, ValueError):
            raise GateError("SOURCE_LIST_JSON_INVALID") from None
        if status != 200 or payload.get("success") is not True:
            raise GateError("SOURCE_LIST_FAILED")
        rows = payload.get("result") or []
        if isinstance(rows, dict):
            rows = rows.get("objects") or []
        if not isinstance(rows, list):
            raise GateError("SOURCE_LIST_SHAPE_INVALID")
        for obj in rows:
            if not isinstance(obj, dict) or not isinstance(obj.get("key"), str) or not obj["key"]:
                raise GateError("SOURCE_OBJECT_KEY_INVALID")
            if obj["key"] in seen_keys:
                raise GateError("SOURCE_OBJECT_KEY_DUPLICATE")
            seen_keys.add(obj["key"])
            objects.append(obj)
        info = payload.get("result_info") or {}
        if not info.get("is_truncated"):
            return sorted(objects, key=lambda obj: obj["key"])
        new_cursor = info.get("cursor")
        if not isinstance(new_cursor, str) or not new_cursor or new_cursor in seen_cursors:
            raise GateError("SOURCE_LIST_CURSOR_INVALID")
        seen_cursors.add(new_cursor)
        cursor = new_cursor
    raise GateError("SOURCE_LIST_PAGE_LIMIT")


def source_bytes(token, bucket, obj):
    key = obj["key"]
    size = obj.get("size")
    if not isinstance(size, int) or not 0 <= size <= MAX_BYTES:
        raise GateError("SOURCE_SIZE_GATE")
    path = "/r2/buckets/" + bucket + "/objects/" + urllib.parse.quote(key, safe="/")
    for accept_encoding in ("identity", "gzip"):
        status, headers, body = source_api(token, path, accept_encoding=accept_encoding)
        if status != 200:
            raise GateError("SOURCE_GET_HTTP")
        if len(body) == size:
            return body
        transfer_encoding = str(next(
            (v for k, v in headers.items() if k.lower() == "content-encoding"), ""
        )).lower()
        if transfer_encoding == "gzip" and body.startswith(GZIP_MAGIC):
            try:
                candidate = gzip.decompress(body)
                if len(candidate) == size:
                    return candidate
            except (OSError, EOFError):
                pass
    raise GateError("SOURCE_STORED_SIZE_MISMATCH")


def normalize_custom(meta):
    if not isinstance(meta, dict):
        raise GateError("CUSTOM_META_INVALID")
    normalized = {}
    for key, value in meta.items():
        if not isinstance(key, str) or not isinstance(value, str):
            raise GateError("CUSTOM_META_INVALID")
        if not key.isascii() or not value.isascii():
            # S3 headers cannot safely preserve arbitrary Unicode metadata keys.
            raise GateError("CUSTOM_META_UNICODE_REQUIRES_WORKER")
        folded = key.lower()
        if folded in normalized:
            raise GateError("CUSTOM_META_CASE_COLLISION")
        normalized[folded] = value
    return normalized


def source_properties(obj):
    if obj.get("ssec"):
        raise GateError("SSEC_REQUIRES_SEPARATE_FLOW")
    meta = normalize_custom(obj.get("custom_metadata") or {})
    http = obj.get("http_metadata") or {}
    if not isinstance(http, dict):
        raise GateError("HTTP_META_INVALID")
    put = {"Metadata": dict(meta)}
    for src_key, s3_key in (
        ("contentType", "ContentType"),
        ("contentEncoding", "ContentEncoding"),
        ("contentLanguage", "ContentLanguage"),
        ("contentDisposition", "ContentDisposition"),
        ("cacheControl", "CacheControl"),
    ):
        if http.get(src_key) is not None:
            put[s3_key] = str(http[src_key])
    if http.get("cacheExpiry"):
        try:
            expiration = dt.datetime.fromisoformat(str(http["cacheExpiry"]).replace("Z", "+00:00"))
            if expiration.tzinfo is None:
                raise ValueError("naive")
            put["Expires"] = expiration
        except (ValueError, TypeError):
            raise GateError("CACHE_EXPIRY_INVALID") from None
    storage = obj.get("storage_class") or "Standard"
    if storage not in ("Standard", "InfrequentAccess"):
        raise GateError("STORAGE_CLASS_UNSUPPORTED")
    put["StorageClass"] = "STANDARD_IA" if storage == "InfrequentAccess" else "STANDARD"
    return put


def verify_properties(source_put, head):
    actual_meta = normalize_custom(head.get("Metadata") or {})
    if actual_meta != source_put["Metadata"]:
        raise GateError("TARGET_CUSTOM_METADATA_MISMATCH")
    for name in ("ContentType", "ContentEncoding", "ContentLanguage", "ContentDisposition", "CacheControl"):
        if name in source_put and str(head.get(name) or "") != str(source_put[name]):
            raise GateError("TARGET_HTTP_METADATA_MISMATCH_" + name.upper())
    if "Expires" in source_put:
        actual = head.get("Expires")
        if not isinstance(actual, dt.datetime) or (
            int(actual.timestamp()) != int(source_put["Expires"].timestamp())
        ):
            raise GateError("TARGET_CACHE_EXPIRY_MISMATCH")
    actual_storage = head.get("StorageClass") or "STANDARD"
    if actual_storage != source_put["StorageClass"]:
        raise GateError("TARGET_STORAGE_CLASS_MISMATCH")


def head_or_none(client, bucket, key):
    try:
        return client.head_object(Bucket=bucket, Key=key)
    except ClientError as exc:
        code = str((exc.response.get("Error") or {}).get("Code") or "")
        if code in ("404", "NoSuchKey", "NotFound"):
            return None
        raise GateError("TARGET_HEAD_FAILED") from None
    except Exception:
        raise GateError("TARGET_HEAD_FAILED") from None


def run(mode, bucket):
    if bucket not in ALLOWED or mode not in ("probe", "canary"):
        raise GateError("INPUT_NOT_ALLOWED")
    src_token = os.environ.get("CLOUDFLARE_API_TOKEN", "")
    expected = os.environ.get("CLOUDFLARE_ACCOUNT_ID", "")
    access = os.environ.get("CLOUDFLARE_TARGET_R2_ACCESS_KEY_ID", "")
    secret = os.environ.get("CLOUDFLARE_TARGET_R2_SECRET_ACCESS_KEY", "")
    if not src_token or expected != SOURCE_ACCOUNT:
        raise GateError("SOURCE_CREDENTIAL_NOT_READY")
    if not access or not secret:
        raise GateError("TARGET_S3_CREDENTIAL_NOT_READY")

    client = boto3.client(
        "s3",
        endpoint_url="https://" + TARGET_ACCOUNT + ".r2.cloudflarestorage.com",
        region_name="auto",
        aws_access_key_id=access,
        aws_secret_access_key=secret,
        config=Config(signature_version="s3v4", s3={"addressing_style": "path"},
                      retries={"mode": "standard", "max_attempts": 2},
                      connect_timeout=15, read_timeout=75),
    )
    try:
        client.list_objects_v2(Bucket=bucket, MaxKeys=1)
    except Exception:
        raise GateError("TARGET_S3_PROBE_FAILED") from None
    src = source_list(src_token, bucket)
    if not src:
        raise GateError("SOURCE_BUCKET_EMPTY")

    receipt = {
        "status": "PASS", "mode": mode, "bucket": bucket,
        "source_inventory_count": len(src),
        "source_deleted": False, "overwritten": False,
        "cutover_ready": False, "full_bucket_parity_verified": False,
        "credential_values_exposed": False,
        "time_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
    }
    if mode == "probe":
        receipt["result"] = "CREDENTIALS_AND_SOURCE_LIST_OK"
        return receipt

    # Canary specifically exercises metadata-bearing objects.
    candidates = [obj for obj in src if obj.get("custom_metadata")]
    if not candidates:
        raise GateError("NO_CUSTOM_METADATA_CANARY")
    obj = min(candidates, key=lambda x: (int(x.get("size") or 0), x["key"]))
    raw = source_bytes(src_token, bucket, obj)
    properties = source_properties(obj)
    key = obj["key"]
    existing = head_or_none(client, bucket, key)
    sha = hashlib.sha256(raw).hexdigest()
    if existing is None:
        put_args = dict(Bucket=bucket, Key=key, Body=raw, IfNoneMatch="*",
                        ContentMD5=base64.b64encode(hashlib.md5(raw).digest()).decode())
        put_args.update(properties)
        try:
            client.put_object(**put_args)
        except Exception:
            raise GateError("TARGET_CANARY_PUT_FAILED") from None
        receipt["result"] = "COPIED_AND_VERIFIED"
    else:
        receipt["result"] = "EXISTING_VERIFIED_NO_OVERWRITE"
    try:
        head = client.head_object(Bucket=bucket, Key=key)
        data = client.get_object(Bucket=bucket, Key=key)["Body"].read(MAX_BYTES + 1)
    except Exception:
        raise GateError("TARGET_READBACK_FAILED") from None
    if len(data) != len(raw) or hashlib.sha256(data).hexdigest() != sha:
        raise GateError("TARGET_BYTES_SHA256_MISMATCH")
    if int(head.get("ContentLength") or -1) != len(raw):
        # Size zero is valid.
        if not (len(raw) == 0 and head.get("ContentLength") == 0):
            raise GateError("TARGET_HEAD_SIZE_MISMATCH")
    verify_properties(properties, head)
    receipt.update({
        "object_key_sha256": hashlib.sha256(key.encode()).hexdigest(),
        "object_bytes": len(raw),
        "object_sha256": sha,
        "custom_metadata_field_count": len(properties["Metadata"]),
        "object_verified": True,
    })
    return receipt


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("probe", "canary"), required=True)
    parser.add_argument("--bucket", choices=sorted(ALLOWED), required=True)
    args = parser.parse_args()
    try:
        result = run(args.mode, args.bucket)
        out = Path("migration-out")
        out.mkdir(exist_ok=True)
        (out / "receipt.json").write_text(json.dumps(result, indent=2) + "\n")
        print("R2_NATIVE_RESULT", json.dumps(result, sort_keys=True))
    except GateError as exc:
        print(json.dumps({"status": "BLOCKED", "reason": str(exc), "secret_exposed": False}))
        raise SystemExit(3)
    except Exception as exc:
        # Avoid logging SDK request headers, auth parameters or exception bodies.
        print(json.dumps({"status": "BLOCKED", "reason": "UNEXPECTED_" + type(exc).__name__,
                          "secret_exposed": False}))
        raise SystemExit(3)


if __name__ == "__main__":
    main()
