#!/usr/bin/env python3
"""Encrypt one target-only D1 Time Travel bookmark. Never print/export plaintext.

Manual trusted GitHub Actions job only; GET-only Cloudflare access. Ciphertext
artifact is insufficient to authorize writes, restores, or source cutover.
"""
import base64
import datetime as dt
import hashlib
import json
import os
import pathlib
import re
import urllib.error
import urllib.request

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

REPO = "louisalviss/runner-3"
ACCOUNT = "748a80810f77f447ee476543ef0e5014"
DATABASE_ID = "82613659-8d08-455f-b6e7-f8f6e4312e22"
DATABASE_NAME = "runner3-content-intelligence"
PUBLIC = pathlib.Path("ops/cloudflare-account-rehome/courier-public-20261008.pem")
PUBLIC_SHA256 = "dc3605eb399082488b6a90396721f29c64c7c9b140949ba7ee982de774e687c1"
OUT = pathlib.Path("migration-out/d1-target-bookmark-encrypted-escrow.json")
BASE = ("https://api.cloudflare.com/client/v4/accounts/" + ACCOUNT +
        "/d1/database/" + DATABASE_ID)
ALLOWED = (BASE, BASE + "/time_travel/bookmark")
BOOKMARK_RE = re.compile(r"[\x21-\x7e]{12,256}\Z")
MAX_RESULT_BYTES = 32_000
AAD = ("runner3-d1-bookmark-v1:" + ACCOUNT + ":" + DATABASE_ID).encode()

class Blocked(Exception):
    pass

def require(ok, code):
    if not ok:
        raise Blocked(code)

def get(token, url, opener=urllib.request.urlopen):
    require(url in ALLOWED, "DISALLOWED_ENDPOINT")
    require(type(token) is str and len(token) >= 16, "MISSING_TARGET_AUDIT_TOKEN")
    req = urllib.request.Request(url, method="GET", headers={
        "Authorization": "Bearer " + token,
        "Accept": "application/json"
    })
    require(req.get_method() == "GET" and req.data is None, "GET_ONLY")
    try:
        with opener(req, timeout=20) as response:
            require(response.status == 200, "CLOUDFLARE_NOT_HTTP_200")
            raw = response.read(MAX_RESULT_BYTES + 1)
    except (urllib.error.HTTPError, urllib.error.URLError, OSError, TimeoutError):
        raise Blocked("CLOUDFLARE_READ_FAILED") from None
    require(len(raw) <= MAX_RESULT_BYTES, "CLOUDFLARE_RESULT_TOO_LARGE")
    try:
        d = json.loads(raw)
    except (ValueError, UnicodeError):
        raise Blocked("CLOUDFLARE_INVALID_JSON") from None
    require(isinstance(d, dict) and d.get("success") is True and
            isinstance(d.get("result"), dict), "CLOUDFLARE_INVALID_RESULT")
    return d["result"]

def seal(bookmark, public_key, captured_at):
    require(type(bookmark) is str and BOOKMARK_RE.fullmatch(bookmark) is not None,
            "INVALID_BOOKMARK")
    require(isinstance(captured_at, str) and len(captured_at) <= 64,
            "INVALID_TIME")
    aes_key = AESGCM.generate_key(bit_length=256)
    nonce = os.urandom(12)
    # D1 identity + timestamp authenticated by AES-GCM AAD/payload.
    payload = json.dumps({
        "bookmark": bookmark, "captured_at_utc": captured_at,
        "account_id": ACCOUNT, "database_id": DATABASE_ID,
    }, separators=(",", ":"), sort_keys=True).encode()
    sealed = AESGCM(aes_key).encrypt(nonce, payload, AAD)
    wrapped = public_key.encrypt(aes_key, padding.OAEP(
        mgf=padding.MGF1(algorithm=hashes.SHA256()),
        algorithm=hashes.SHA256(), label=None))
    b64 = lambda blob: base64.b64encode(blob).decode("ascii")
    return {
        "format": "runner3-d1-bookmark-encrypted-escrow-v1",
        "account_id": ACCOUNT, "database_id": DATABASE_ID,
        "captured_at_utc": captured_at,
        "key_rsa_oaep_sha256_b64": b64(wrapped),
        "nonce_b64": b64(nonce), "ciphertext_aes256gcm_b64": b64(sealed),
        "plaintext_exposed": False, "d1_write_count": 0,
        "r2_requests": 0, "restore_authorized": False,
        "migration_authorized": False,
    }

def main():
    try:
        require(os.environ.get("GITHUB_REPOSITORY") == REPO and
                os.environ.get("GITHUB_REF") == "refs/heads/main" and
                os.environ.get("GITHUB_EVENT_NAME") == "workflow_dispatch",
                "UNTRUSTED_JOB_CONTEXT")
        require(not os.environ.get("CLOUDFLARE_TARGET_D1_WRITE_TOKEN"),
                "WRITE_CREDENTIAL_NOT_ALLOWED")
        token = os.environ.get("CLOUDFLARE_TARGET_AUDIT_TOKEN", "")
        pub = PUBLIC.read_bytes()
        require(hashlib.sha256(pub).hexdigest() == PUBLIC_SHA256,
                "COURIER_PUBLIC_KEY_CHANGED")
        public_key = serialization.load_pem_public_key(pub)
        require(public_key.key_size >= 3072, "COURIER_KEY_TOO_SMALL")
        meta = get(token, BASE)
        require(meta.get("name") == DATABASE_NAME and
                meta.get("uuid") == DATABASE_ID and
                meta.get("version") == "production",
                "TARGET_D1_IDENTITY_MISMATCH")
        bookmark = get(token, ALLOWED[1]).get("bookmark")
        moment = dt.datetime.now(dt.timezone.utc).isoformat()
        envelope = seal(bookmark, public_key, moment)
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(json.dumps(envelope, indent=2, sort_keys=True) + "\n")
        OUT.chmod(0o600)
    except (Blocked, OSError, ValueError, TypeError):
        print("D1_BOOKMARK_ESCROW_HOLD_SAFE_NO_CLOUD_WRITES")
        return 3
    print("D1_BOOKMARK_ENCRYPTED_ESCROW_PASS CIPHERTEXT_ONLY no_cloud_writes no_r2 not_rollback_ready")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
