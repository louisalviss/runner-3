#!/usr/bin/env python3
from __future__ import annotations

import base64
import datetime as dt
import hashlib
import json
import os
import pathlib
import re
import secrets

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

MAILBOX_SOURCE = pathlib.Path(os.environ.get(
    "RUNNER_RECOVERY_MAILBOX_SOURCE",
    "cloudflare/runner3-core/mailbox-fast-entry.js",
))
REQUEST_PATH = pathlib.Path(os.environ.get(
    "RUNNER_RECOVERY_REQUEST_PATH",
    "ops/runner-recovery/request.json",
))
PROOF_PATH = pathlib.Path(os.environ.get(
    "RUNNER_RECOVERY_PROOF_PATH",
    "results/vps-mailbox-runner-recovery-public-hosted.json",
))
FLOW = "runner-recover"
ALG = "RSA-OAEP-SHA256+A256GCM"


def mailbox_public_key() -> rsa.RSAPublicKey:
    source = MAILBOX_SOURCE.read_text(encoding="utf-8")
    match = re.search(r'const VPS_MAILBOX_PUBLIC_KEY_DER_B64 = "([A-Za-z0-9+/=]+)";', source)
    if not match:
        raise RuntimeError("mailbox public key not found")
    der = base64.b64decode(match.group(1))
    key = serialization.load_der_public_key(der)
    if not isinstance(key, rsa.RSAPublicKey) or key.key_size < 3072:
        raise RuntimeError("invalid mailbox public key")
    if len(hashlib.sha256(der).digest()) != 32:
        raise RuntimeError("mailbox public key digest failed")
    return key


def build_envelope() -> bytes:
    request_id = "m_" + secrets.token_hex(16)
    vps_pub = mailbox_public_key()

    # decrypt_request requires a reply public key as part of the established
    # envelope contract. The corresponding private key is intentionally
    # ephemeral because this emergency lane uses the local receipt as proof.
    reply_priv = rsa.generate_private_key(public_exponent=65537, key_size=3072)
    reply_der = reply_priv.public_key().public_bytes(
        serialization.Encoding.DER,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    )

    now = dt.datetime.now(dt.timezone.utc)
    body = {
        "request_id": request_id,
        "issued_at": now.isoformat(),
        "expires_at": (now + dt.timedelta(minutes=10)).isoformat(),
        "kind": "router",
        "timeout_seconds": 180,
        "task": {"flow": FLOW},
    }
    plaintext = json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    aes_key = os.urandom(32)
    nonce = os.urandom(12)
    envelope = {
        "version": 1,
        "alg": ALG,
        "request_id": request_id,
        "encrypted_key": base64.b64encode(vps_pub.encrypt(
            aes_key,
            padding.OAEP(
                mgf=padding.MGF1(algorithm=hashes.SHA256()),
                algorithm=hashes.SHA256(),
                label=None,
            ),
        )).decode("ascii"),
        "nonce": base64.b64encode(nonce).decode("ascii"),
        "ciphertext": base64.b64encode(
            AESGCM(aes_key).encrypt(nonce, plaintext, request_id.encode("utf-8"))
        ).decode("ascii"),
        "reply_public_key_der": base64.b64encode(reply_der).decode("ascii"),
    }
    return (json.dumps(envelope, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")


def main() -> int:
    proof: dict[str, object] = {
        "observed_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "hosted_producer": True,
        "source_repo": "louisalviss/runner-3",
        "purpose": "quota-independent-fixed-purpose-self-hosted-runner-recovery",
        "transport": "github-public-encrypted-file",
        "fixed_flow": FLOW,
        "cloudflare_required": False,
        "d1_required": False,
        "request_published": False,
    }
    try:
        raw = build_envelope()
        REQUEST_PATH.parent.mkdir(parents=True, exist_ok=True)
        REQUEST_PATH.write_bytes(raw)
        proof.update({
            "request_published": True,
            "request_path": REQUEST_PATH.as_posix(),
            "envelope_sha256": hashlib.sha256(raw).hexdigest(),
            "envelope_bytes": len(raw),
            "expires_in_seconds": 600,
        })
    except Exception as exc:
        proof["error_class"] = type(exc).__name__

    PROOF_PATH.parent.mkdir(parents=True, exist_ok=True)
    PROOF_PATH.write_text(json.dumps(proof, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(proof, ensure_ascii=False, separators=(",", ":")))
    return 0 if proof.get("request_published") is True else 1


if __name__ == "__main__":
    raise SystemExit(main())
