#!/usr/bin/env python3
"""Encrypted source-side R2 courier. Uses GitHub secret in runner memory only."""
import base64
import datetime
import hashlib
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

def request(url, token):
    req = urllib.request.Request(
        url, headers={"Authorization": "Bearer " + token, "Accept": "*/*"}
    )
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
        code, h, blob = request(path, token)
        if code != 200:
            raise SystemExit("SOURCE_READ_HTTP_"+str(code))
        if len(blob) != int(x.get("size") or -1):
            # R2 object may have changed after listing, or HTTP metadata may
            # describe encoded length; require two stable independent GETs.
            code2, h2, blob2 = request(path, token)
            if code2 != 200 or hashlib.sha256(blob2).digest() != hashlib.sha256(blob).digest():
                raise SystemExit("SOURCE_UNSTABLE_CONTENT_ABORT")
            print("SOURCE_LIST_SIZE_DRIFT_VERIFIED_INDEX",len(encrypted_items),
                  "listed_bytes",int(x.get("size") or -1),"stable_read_bytes",len(blob))
        hm = x.get("http_metadata") or {}
        if x.get("custom_metadata"):
            # Don't silently strip custom metadata during browser API uploads.
            raise SystemExit("OBJECT_CUSTOM_METADATA_REQUIRES_SPECIAL_PATH")
        encrypted_items.append({
            "key": key, "size": len(blob), "sha256": hashlib.sha256(blob).hexdigest(),
            "content_type": hm.get("contentType") or h.get("Content-Type") or "application/octet-stream",
            "http_metadata": hm,
            "payload_b64": base64.b64encode(blob).decode(),
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
