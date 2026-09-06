#!/usr/bin/env python3
from __future__ import annotations

import base64
import csv
import datetime as dt
import hashlib
import io
import json
import os
import pathlib
import re
import secrets
import subprocess
import tempfile
import time
import urllib.request

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

CORE = "https://runner3-core.ducduy2411.workers.dev"
MAILBOX_SOURCE = "https://raw.githubusercontent.com/louisalviss/runner-3/main/cloudflare/runner3-core/mailbox-fast-entry.js"
TOKEN = os.environ.get("RUNNER3_CORE_TOKEN", "").strip()


def request(method: str, path: str, data: bytes | None = None, *, auth: bool = False):
    auth_path: str | None = None
    try:
        cmd = [
            "curl", "--silent", "--show-error", "--max-time", "30",
            "--request", method,
            "--header", "Accept: application/json,*/*",
            "--header", "Cache-Control: no-store",
            "--user-agent", "runner3-public-hosted-vps-recovery",
        ]
        if auth:
            fd, auth_path = tempfile.mkstemp(prefix="runner3-auth-", text=True)
            try:
                os.write(fd, f"Authorization: Bearer {TOKEN}\n".encode("utf-8"))
            finally:
                os.close(fd)
            os.chmod(auth_path, 0o600)
            cmd += ["--header", f"@{auth_path}"]
        if data is not None:
            cmd += ["--header", "Content-Type: application/json", "--data-binary", "@-"]
        cmd += ["--write-out", "\n%{http_code}\n%{content_type}", CORE + path]
        completed = subprocess.run(
            cmd, input=data, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            check=False, timeout=40,
        )
        if completed.returncode != 0:
            raise RuntimeError(f"curl_transport_failed_{completed.returncode}")
        try:
            raw, status_raw, content_type_raw = completed.stdout.rsplit(b"\n", 2)
            status = int(status_raw.decode("ascii"))
            content_type = content_type_raw.decode("utf-8", "replace").strip()[:160]
        except Exception as exc:
            raise RuntimeError("curl_status_parse_failed") from exc
        return status, raw, content_type
    finally:
        if auth_path:
            try:
                os.unlink(auth_path)
            except FileNotFoundError:
                pass


def classify_http_body(raw: bytes, content_type: str) -> dict[str, object]:
    out: dict[str, object] = {
        "submit_content_type": content_type or "unknown",
        "submit_body_bytes": len(raw),
        "submit_body_sha256": hashlib.sha256(raw).hexdigest(),
    }
    text = raw[:16_384].decode("utf-8", "replace")
    lowered = text.lower()
    if "cloudflare" in lowered or "cf-ray" in lowered:
        out["submit_body_class"] = "cloudflare_edge"
    elif "application/json" in content_type.lower():
        out["submit_body_class"] = "json"
    elif "text/html" in content_type.lower() or "<html" in lowered or "<!doctype" in lowered:
        out["submit_body_class"] = "html"
    elif not raw:
        out["submit_body_class"] = "empty"
    else:
        out["submit_body_class"] = "other"

    code_match = re.search(r'"error_code"\s*:\s*([0-9]{3,5})', text)
    if not code_match:
        code_match = re.search(r'error[-_ ]?([0-9]{3,5})', lowered)
    if code_match:
        out["submit_cloudflare_error_code"] = int(code_match.group(1))

    try:
        parsed = json.loads(raw.decode("utf-8"))
    except Exception:
        parsed = None
    if isinstance(parsed, dict):
        error = parsed.get("error")
        if isinstance(error, str) and re.fullmatch(r"[A-Z0-9_:-]{1,100}", error):
            out["submit_error"] = error
        error_name = parsed.get("error_name")
        if isinstance(error_name, str) and re.fullmatch(r"[a-z0-9_-]{1,100}", error_name):
            out["submit_cloudflare_error_name"] = error_name
    return out


def mailbox_public_key() -> rsa.RSAPublicKey:
    req = urllib.request.Request(MAILBOX_SOURCE, headers={"User-Agent": "runner3-public-hosted-vps-recovery"})
    with urllib.request.urlopen(req, timeout=30) as response:
        source = response.read().decode("utf-8")
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


def main() -> int:
    proof: dict[str, object] = {
        "observed_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "hosted_producer": True,
        "source_repo": "louisalviss/runner-3",
        "purpose": "recover-offline-self-hosted-runner-through-persistent-vps-mailbox",
        "opaque_submit_ok": False,
        "encrypted_result_roundtrip_ok": False,
        "runner_recover_ok": False,
        "transport_ok": False,
    }
    try:
        if not TOKEN:
            raise RuntimeError("token_missing")
        request_id = "m_" + secrets.token_hex(16)
        vps_pub = mailbox_public_key()
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
            "kind": "router", "timeout_seconds": 180,
            "task": {"flow": "runner-recover"},
        }
        plaintext = json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode()
        aes_key = os.urandom(32)
        nonce = os.urandom(12)
        envelope = {
            "version": 1, "alg": "RSA-OAEP-SHA256+A256GCM", "request_id": request_id,
            "encrypted_key": base64.b64encode(vps_pub.encrypt(
                aes_key,
                padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None),
            )).decode(),
            "nonce": base64.b64encode(nonce).decode(),
            "ciphertext": base64.b64encode(AESGCM(aes_key).encrypt(nonce, plaintext, request_id.encode())).decode(),
            "reply_public_key_der": base64.b64encode(reply_der).decode(),
        }
        status, raw, content_type = request(
            "PUT", f"/mailbox/requests/{request_id}",
            json.dumps(envelope, separators=(",", ":")).encode(), auth=True,
        )
        proof["submit_status"] = int(status)
        proof.update(classify_http_body(raw, content_type))
        try:
            accepted = json.loads(raw.decode())
        except Exception:
            accepted = {}
        proof["opaque_submit_ok"] = status in (200, 202) and accepted.get("ok") is True and accepted.get("accepted") is True
        if proof["opaque_submit_ok"] is not True:
            raise RuntimeError("mailbox_submit_rejected")

        deadline = time.time() + 210
        while time.time() < deadline:
            csv_status, csv_raw, _ = request("GET", f"/mailbox/results/{request_id}.csv")
            if csv_status != 200:
                time.sleep(3)
                continue
            rows = list(csv.reader(io.StringIO(csv_raw.decode())))
            if len(rows) < 2 or len(rows[1]) < 2 or rows[1][0] == "pending" or not rows[1][1]:
                time.sleep(3)
                continue
            detail = json.loads(base64.b64decode(rows[1][1]).decode())
            result_key = reply_priv.decrypt(
                base64.b64decode(detail["encrypted_key"]),
                padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None),
            )
            result_plain = AESGCM(result_key).decrypt(
                base64.b64decode(detail["nonce"]), base64.b64decode(detail["ciphertext"]), request_id.encode(),
            )
            result = json.loads(result_plain.decode())
            transport = result.get("result") if isinstance(result.get("result"), dict) else {}
            worker = transport.get("result") if isinstance(transport.get("result"), dict) else {}
            proof["encrypted_result_roundtrip_ok"] = (
                result.get("request_id") == request_id and transport.get("kind") == "router"
                and transport.get("flow") == "runner-recover"
            )
            proof["transport_ok"] = transport.get("ok") is True and transport.get("exit_code") in (None, 0)
            proof["runner_recover_ok"] = proof["transport_ok"] is True and worker.get("ok") is True and worker.get("flow") == "runner-recover"
            for src, dst in (
                ("action", "recovery_action"), ("recovered", "recovered"),
                ("active_after", "active_after"), ("listener_after", "listener_after"),
                ("blocker", "blocker"),
            ):
                if src in worker and worker.get(src) is not None:
                    proof[dst] = worker.get(src)
            break
        else:
            raise TimeoutError("mailbox runner recovery result timeout")
    except Exception as exc:
        proof["error_class"] = type(exc).__name__

    out = pathlib.Path("results/vps-mailbox-runner-recovery-public-hosted.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(proof, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(proof, ensure_ascii=False, separators=(",", ":")))
    return 0 if proof.get("encrypted_result_roundtrip_ok") is True and proof.get("runner_recover_ok") is True else 1


if __name__ == "__main__":
    raise SystemExit(main())
