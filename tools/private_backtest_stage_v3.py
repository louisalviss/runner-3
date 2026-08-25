#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import gzip
import hashlib
import json
import os
import tempfile
from pathlib import Path

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey, X25519PublicKey
from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

import private_backtest_worker_v2 as core

CRYPTO_SEED_PREFIX = b"runner3-audio-library-chatgpt-bridge-v1\0"
CRYPTO_INFO = b"runner3-private-backtest-v1"
DROPBOX_BLOCK_SIZE = 4 * 1024 * 1024


def decrypt_compressed(env: dict) -> dict:
    token = os.environ.get("CLOUDFLARE_API_TOKEN", "").strip()
    if not token:
        raise RuntimeError("CLOUDFLARE_API_TOKEN is required")
    seed = hashlib.sha256(CRYPTO_SEED_PREFIX + token.encode()).digest()
    private = X25519PrivateKey.from_private_bytes(seed)
    ephemeral = X25519PublicKey.from_public_bytes(base64.b64decode(env["ephemeralPublicKey"]))
    shared = private.exchange(ephemeral)
    key = HKDF(algorithm=hashes.SHA256(), length=32, salt=None, info=CRYPTO_INFO).derive(shared)
    compressed = ChaCha20Poly1305(key).decrypt(
        base64.b64decode(env["nonce"]),
        base64.b64decode(env["ciphertext"]),
        str(env["id"]).encode(),
    )
    payload = json.loads(gzip.decompress(compressed))
    if str(payload.get("id")) != str(env["id"]):
        raise ValueError("encrypted payload id mismatch")
    if str(payload.get("compute_scope")) != str(env["scope"]):
        raise ValueError("encrypted payload scope mismatch")
    return payload


def dropbox_content_hash(path: Path) -> str:
    overall = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            block = f.read(DROPBOX_BLOCK_SIZE)
            if not block:
                break
            overall.update(hashlib.sha256(block).digest())
    return overall.hexdigest()


def stage(request_path: Path) -> int:
    env = core.load_envelope(request_path)
    payload = decrypt_compressed(env)
    work = Path(tempfile.mkdtemp(prefix="private-bt-stage-v3-"))
    local = {
        "engine": work / "engine.py",
        "evaluator": work / "evaluator.py",
        "profile": work / "profile.json",
        "helper": work / "exp.py",
    }

    hashes_out = {}
    source_content_hashes = {}
    for key in ("engine", "evaluator", "profile"):
        spec = payload["sources"][key]
        hashes_out[key] = core.download_private_source(spec["url"], local[key], "")
        expected = str(spec.get("dropbox_content_hash") or spec.get("sha256") or "").lower()
        got_content = dropbox_content_hash(local[key])
        source_content_hashes[key] = got_content
        if expected and got_content.lower() != expected:
            raise ValueError(f"Dropbox content hash mismatch for {local[key].name}")

    local["helper"].write_bytes(base64.b64decode(payload["helper_b64"]))
    hashes_out["helper"] = core.sha256_file(local["helper"])
    if hashes_out["helper"].lower() != str(payload["helper_sha256"]).lower():
        raise ValueError("SHA256 mismatch for helper")

    files = {
        "engine": {"name": "package/engine.py", "sha256": hashes_out["engine"]},
        "evaluator": {"name": "package/evaluator.py", "sha256": hashes_out["evaluator"]},
        "profile": {"name": "package/profile.json", "sha256": hashes_out["profile"]},
        "helper": {"name": "package/exp.py", "sha256": hashes_out["helper"]},
    }
    ctypes = {
        "engine": "text/x-python; charset=utf-8",
        "evaluator": "text/x-python; charset=utf-8",
        "profile": "application/json; charset=utf-8",
        "helper": "text/x-python; charset=utf-8",
    }
    for key, spec in files.items():
        core.upload_artifact(env["project"], env["scope"], spec["name"], local[key], ctypes[key])

    manifest = {
        "schema": 3,
        "request_id": payload["request_id"],
        "type": payload["type"],
        "compute_scope": env["scope"],
        "created_at": core.now_iso(),
        "files": files,
        "source_dropbox_content_hash": source_content_hashes,
        "symbol_timeout_seconds": int(payload.get("symbol_timeout_seconds", 5400)),
        "retries": int(payload.get("retries", 1)),
        "parity_target": payload["parity_target"],
        "checkpoint_project": payload.get("checkpoint_project", "super-rsi"),
        "checkpoint_scope": payload["checkpoint_scope"],
    }
    manifest_path = work / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    core.upload_artifact(env["project"], env["scope"], "manifest.json", manifest_path, "application/json; charset=utf-8")
    core.put_json(
        f"/checkpoints/{core.q(manifest['checkpoint_project'])}/{core.q(manifest['checkpoint_scope'])}",
        {
            "source": core.SOURCE,
            "status": "staged",
            "position": {
                "phase": "staged_for_runner3_matrix",
                "request_id": payload["request_id"],
                "compute_scope": env["scope"],
                "created_at": manifest["created_at"],
                "artifact_project": env["project"],
                "artifact_scope": env["scope"],
                "artifact_name": "manifest.json",
                "source_sha256": hashes_out,
                "source_dropbox_content_hash": source_content_hashes,
            },
            "dropbox_path": None,
            "last_error": None,
        },
    )
    print(json.dumps({"stage": "ready", "scope": env["scope"], "shards": env["shards"]}))
    return 0


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--request", required=True)
    args = p.parse_args()
    return stage(Path(args.request))


if __name__ == "__main__":
    raise SystemExit(main())
