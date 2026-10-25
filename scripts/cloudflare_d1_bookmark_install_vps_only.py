#!/usr/bin/env python3
"""VPS-only: decrypt an encrypted bookmark in memory, set a GitHub Actions Secret.

Run only on the trusted VPS holding the private courier key. The secret is never
passed on argv, stored plaintext on disk, printed, or included in telemetry.
This is NOT row rollback approval or permission to execute D1 INSERT.
"""
import argparse
import base64
import datetime as dt
import json
import pathlib
import subprocess

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from cloudflare_d1_bookmark_encrypted_escrow import (
    AAD, ACCOUNT, DATABASE_ID, BOOKMARK_RE, Blocked, require
)

REPO = "louisalviss/runner-3"
SECRET_NAME = "CLOUDFLARE_TARGET_PREAPPLY_BOOKMARK"
PRIVATE_KEY = pathlib.Path("/var/lib/cloudflare-migration/2026-10-08/ephemeral-courier/key.pem")
MAX_CIPHERTEXT_FILE = 8192
MAX_AGE_SECONDS = 900

def reveal(envelope, private_pem, now=None):
    require(isinstance(envelope, dict) and
            envelope.get("format") == "runner3-d1-bookmark-encrypted-escrow-v1" and
            envelope.get("account_id") == ACCOUNT and
            envelope.get("database_id") == DATABASE_ID and
            envelope.get("plaintext_exposed") is False and
            envelope.get("d1_write_count") == 0 and
            envelope.get("r2_requests") == 0, "WRONG_OR_TAMPERED_ESCROW")
    captured = envelope.get("captured_at_utc")
    require(type(captured) is str and len(captured) < 64, "INVALID_ESCROW_TIME")
    try:
        t = dt.datetime.fromisoformat(captured)
    except ValueError:
        raise Blocked("INVALID_ESCROW_TIME") from None
    require(t.tzinfo is not None, "ESCROW_TIME_UNZONED")
    now = now or dt.datetime.now(dt.timezone.utc)
    age = (now - t).total_seconds()
    require(-30 <= age <= MAX_AGE_SECONDS, "STALE_ESCROW_RECAPTURE_REQUIRED")
    def dec(field):
        s = envelope.get(field)
        require(type(s) is str and len(s) < 4096, "INVALID_CIPHERTEXT_FIELD")
        try:
            return base64.b64decode(s, validate=True)
        except (ValueError, Exception):
            raise Blocked("MALFORMED_CIPHERTEXT") from None
    try:
        private_key = serialization.load_pem_private_key(private_pem, password=None)
        aes_key = private_key.decrypt(dec("key_rsa_oaep_sha256_b64"), padding.OAEP(
            mgf=padding.MGF1(algorithm=hashes.SHA256()),
            algorithm=hashes.SHA256(), label=None))
        payload = AESGCM(aes_key).decrypt(
            dec("nonce_b64"), dec("ciphertext_aes256gcm_b64"), AAD)
        obj = json.loads(payload)
    except (ValueError, TypeError, KeyError, Exception):
        raise Blocked("ESCROW_DECRYPTION_FAILED") from None
    require(isinstance(obj, dict) and obj.get("account_id") == ACCOUNT and
            obj.get("database_id") == DATABASE_ID and
            obj.get("captured_at_utc") == captured, "ESCROW_IDENTITY_MISMATCH")
    bookmark = obj.get("bookmark")
    require(type(bookmark) is str and BOOKMARK_RE.fullmatch(bookmark) is not None,
            "INVALID_DECRYPTED_BOOKMARK")
    return bookmark

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--envelope", required=True)
    ap.add_argument("--install", action="store_true")
    args = ap.parse_args()
    try:
        require(args.install, "EXPLICIT_INSTALL_REQUIRED")
        path = pathlib.Path(args.envelope)
        require(path.is_file() and path.stat().st_size <= MAX_CIPHERTEXT_FILE,
                "ESCROW_FILE_INVALID")
        envelope = json.loads(path.read_text())
        bookmark = reveal(envelope, PRIVATE_KEY.read_bytes())
        # GitHub CLI performs local libsodium encryption. Bookmark travels through
        # subprocess stdin ONLY, never argv, logs, shell history or disk.
        p = subprocess.run(
            ["gh", "secret", "set", SECRET_NAME, "-R", REPO, "--app", "actions"],
            input=bookmark, text=True, capture_output=True, timeout=30)
        require(p.returncode == 0, "GITHUB_SECRET_INSTALL_FAILED")
        # Read only metadata, NOT value; no cloud or database writes.
        status = subprocess.run(
            ["gh", "api", "repos/" + REPO + "/actions/secrets/" + SECRET_NAME],
            capture_output=True, text=True, timeout=15)
        require(status.returncode == 0, "GITHUB_SECRET_VERIFY_FAILED")
        meta = json.loads(status.stdout)
        require(meta.get("name") == SECRET_NAME, "SECRET_METADATA_MISMATCH")
    except (Blocked, OSError, ValueError, TypeError, subprocess.TimeoutExpired):
        print("D1_PREAPPLY_BOOKMARK_SECRET_INSTALL_HOLD")
        return 3
    print("D1_PREAPPLY_BOOKMARK_SECRET_INSTALLED_AND_METADATA_VERIFIED")
    print("NO_D1_WRITES NO_RESTORE NO_R2 ROLLBACK_STILL_HOLD")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
