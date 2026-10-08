#!/usr/bin/env python3
"""Encrypted source-side R2 courier. Uses GitHub secret in runner memory only."""
import base64
import datetime
import hashlib
import gzip
import json
import os
import pathlib
import secrets
import urllib.error
import urllib.parse
import urllib.request

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

SOURCE = "7415a87f6bce7884e73ad7cfed5782df"
ALLOWED = {
    "runner3-artifacts", "runner3-wp-media", "runner3-rss-fastlane-artifacts",
    "ai-vps-common-access", "clm-copilot-data", "runner-vps-dr",
    "runner3-reddit-opportunity-raw", "runner3-telegram-bobvolman-raw",
    "runner3-telegram-raw"
}
MAX_BUNDLE_BYTES = 25_000_000
MAX_OBJECTS = 30
MAX_PAGES = 15

def request(url, token, accept_encoded=False):
    h = {"Authorization": "Bearer " + token, "Accept": "*/*"}
    if accept_encoded:
        h["Accept-Encoding"] = "gzip"
    req = urllib.request.Request(url, headers=h)
    with urllib.request.urlopen(req, timeout=50) as result:
        return result.status, dict(result.headers), result.read()

def main():
    account = os.environ.get("CF_ACCOUNT", "")
    token = os.environ.get("CF_TOKEN", "")
    bucket = os.environ.get("BUCKET", "")
    start = int(os.environ.get("START_INDEX", "0"))
    limit = int(os.environ.get("LIMIT_OBJECTS", "10"))
    if account != SOURCE or not token:
        raise SystemExit("SOURCE_AUTH_PRECONDITION_FAILED")
    if bucket not in ALLOWED or start < 0 or not (1 <= limit <= MAX_OBJECTS):
        raise SystemExit("BOUNDED_INPUT_PRECONDITION_FAILED")
    base = (
        "https://api.cloudflare.com/client/v4/accounts/"
        + SOURCE + "/r2/buckets/" + bucket + "/objects"
    )
    objects = []
    cursor = None
    for page in range(MAX_PAGES):
        query = "?per_page=1000"
        if cursor:
            query += "&cursor=" + urllib.parse.quote(cursor, safe="")
        code, _, raw = request(base + query, token)
        response = json.loads(raw)
        if code != 200 or not response.get("success"):
            raise SystemExit("SOURCE_LIST_FAILED")
        result = response.get("result") or []
        if isinstance(result, dict):
            result = result.get("objects") or []
        objects.extend(result)
        info = response.get("result_info") or {}
        cursor = info.get("cursor") if info.get("is_truncated") else None
        if not cursor:
            break
    if cursor:
        raise SystemExit("SOURCE_MANIFEST_INCOMPLETE")
    objects.sort(key=lambda x: x.get("key", ""))
    selected = objects[start:start+limit]
    if not selected:
        raise SystemExit("EMPTY_RANGE")
    expected_bytes = sum(int(x.get("size") or 0) for x in selected)
    if expected_bytes > MAX_BUNDLE_BYTES:
        raise SystemExit("BUNDLE_BUDGET_EXCEEDED_CHANGE_LIMIT")
    if any(int(x.get("size") or 0) > MAX_BUNDLE_BYTES for x in selected):
        raise SystemExit("OBJECT_TOO_LARGE")
    encrypted_items = []
    for x in selected:
        key = x.get("key")
        if not isinstance(key, str) or not key:
            raise SystemExit("SOURCE_OBJECT_MISSING_KEY")
        path = base + "/" + urllib.parse.quote(key, safe="/")
        code, headers, wire_bytes = request(path, token, accept_encoded=True)
        if code != 200:
            raise SystemExit("SOURCE_READ_HTTP_"+str(code))
        listed_size = int(x.get("size") or -1)
        hm = x.get("http_metadata") or {}
        storage_encoding = str(hm.get("contentEncoding") or "").lower()
        wire_encoding = str(next((v for k,v in headers.items() if k.lower() == "content-encoding"), "")).lower()
        if storage_encoding not in ("", "identity", "gzip"):
            raise SystemExit("UNSUPPORTED_STORED_ENCODING")
        if wire_encoding not in ("", "identity", "gzip"):
            raise SystemExit("UNSUPPORTED_WIRE_ENCODING")

        # Cloudflare's R2 object API can apply *HTTP transfer gzip* even to
        # an object without stored Content-Encoding=gzip. Select exact stored
        # bytes by comparing against LIST size; never confuse transfer gzip
        # with R2 object's Content-Encoding metadata.
        if len(wire_bytes) == listed_size:
            stored = wire_bytes
        else:
            # First try to undo transfer gzip. Certain API responses declare
            # gzip without returning a gzip-framed body; fall back to
            # Accept-Encoding: identity for exact stored bytes.
            stored = None
            if wire_encoding == "gzip" and wire_bytes.startswith(b"\\x1f\\x8b"):
                try:
                    decoded = gzip.decompress(wire_bytes)
                    if len(decoded) == listed_size:
                        stored = decoded
                except Exception:
                    pass
            if stored is None:
                code2, headers2, identity_bytes = request(
                    path, token, accept_encoded=False
                )
                if code2 != 200 or len(identity_bytes) != listed_size:
                    raise SystemExit(
                        "R2_SOURCE_SIZE_DRIFT_ABORT listed="+str(listed_size)+
                        " encoded_response="+str(len(wire_bytes))+
                        " identity_response="+str(len(identity_bytes))
                    )
                stored = identity_bytes

        if storage_encoding == "gzip":
            if not stored.startswith(b"\\x1f\\x8b"):
                raise SystemExit("STORED_GZIP_MAGIC_MISSING")
            try:
                logical = gzip.decompress(stored)
            except Exception:
                raise SystemExit("STORED_GZIP_INVALID")
        else:
            logical = stored
        logical_sha = hashlib.sha256(logical).hexdigest()
        if x.get("custom_metadata"):
            # Don't silently strip custom metadata during browser API uploads.
            raise SystemExit("OBJECT_CUSTOM_METADATA_REQUIRES_SPECIAL_PATH")
        encrypted_items.append({
            "key": key, "size": len(stored), "sha256": hashlib.sha256(stored).hexdigest(),
            "logical_sha256": logical_sha,
            "content_type": hm.get("contentType") or h.get("Content-Type") or "application/octet-stream",
            "http_metadata": hm,
            "payload_b64": base64.b64encode(stored).decode(),
        })
    actual_bytes=sum(int(x["size"]) for x in encrypted_items)
    if actual_bytes>MAX_BUNDLE_BYTES:
        raise SystemExit("BUNDLE_ACTUAL_SIZE_EXCEEDED")
    payload = {
        "version": 2, "account": SOURCE, "bucket": bucket,
        "start_index": start, "source_inventory": len(objects),
        "objects": encrypted_items,
        "read_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }
    pub = serialization.load_pem_public_key(
        pathlib.Path("ops/cloudflare-account-rehome/courier-public-20261008.pem").read_bytes()
    )
    aes = secrets.token_bytes(32)
    nonce = secrets.token_bytes(12)
    aad = b"cf-r2-rehome-bundle-v2"
    encrypted = AESGCM(aes).encrypt(
        nonce, json.dumps(payload, separators=(",", ":")).encode(), aad
    )
    wrapped = pub.encrypt(
        aes, padding.OAEP(
            mgf=padding.MGF1(algorithm=hashes.SHA256()),
            algorithm=hashes.SHA256(), label=None
        )
    )
    envelope = {
        "version": 2, "alg": "RSA-OAEP-SHA256+A256GCM",
        "nonce": base64.b64encode(nonce).decode(),
        "aad": base64.b64encode(aad).decode(),
        "wrapped_key": base64.b64encode(wrapped).decode(),
        "ciphertext": base64.b64encode(encrypted).decode(),
    }
    d = pathlib.Path("courier-out")
    d.mkdir(exist_ok=True)
    (d / "envelope.json").write_text(json.dumps(envelope, separators=(",", ":")) + "\n")
    print(json.dumps({
        "status": "ENCRYPTED_BUNDLE_READY", "object_count": len(selected),
        "source_total": len(objects), "start_index": start,
        "payload_bytes": expected_bytes, "encrypted_only": True,
    }))

if __name__ == "__main__":
    main()
