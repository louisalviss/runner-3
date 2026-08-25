#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import re
import shutil
import subprocess
import tarfile
import tempfile
import time
import traceback
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

CORE_URL = os.environ.get("RUNNER3_CORE_URL", "https://runner3-core.ducduy2411.workers.dev").rstrip("/")
TOKEN = os.environ.get("RUNNER3_CORE_TOKEN", "").strip()
SOURCE = os.environ.get("RUNNER3_SOURCE", "runner-3-github-hosted")
DROPBOX_HOST_SUFFIX = ".dropboxusercontent.com"
CRYPTO_SEED_PREFIX = b"runner3-audio-library-chatgpt-bridge-v1\0"
CRYPTO_INFO = b"runner3-private-backtest-v1"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def q(value: str) -> str:
    return urllib.parse.quote(str(value), safe="")


def headers(*, accept="application/json", content_type=None):
    if not TOKEN:
        raise RuntimeError("RUNNER3_CORE_TOKEN is required")
    out = {
        "Authorization": f"Bearer {TOKEN}",
        "Accept": accept,
        "User-Agent": "runner-3-private-backtest/2",
        "Cache-Control": "no-cache",
        "X-Runner3-Source": SOURCE,
    }
    if content_type:
        out["Content-Type"] = content_type
    return out


def artifact_url(project: str, scope: str, name: str) -> str:
    parts = ["artifacts", project, scope] + str(name).split("/")
    return CORE_URL + "/" + "/".join(q(x) for x in parts)


def download_artifact(project: str, scope: str, name: str, dest: Path, timeout=300):
    dest.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(artifact_url(project, scope, name), headers=headers(accept="*/*"), method="GET")
    with urllib.request.urlopen(req, timeout=timeout) as r, dest.open("wb") as f:
        shutil.copyfileobj(r, f, length=1024 * 1024)


def upload_artifact(project: str, scope: str, name: str, path: Path, content_type="application/octet-stream", timeout=300):
    data = path.read_bytes()
    req = urllib.request.Request(
        artifact_url(project, scope, name), data=data, headers=headers(content_type=content_type), method="PUT"
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r).get("artifact")


def put_json(path: str, payload: dict, timeout=30):
    data = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    req = urllib.request.Request(CORE_URL + path, data=data, headers=headers(content_type="application/json"), method="PUT")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def load_envelope(path: Path) -> dict:
    req = json.loads(path.read_text(encoding="utf-8"))
    for key in ("v", "id", "project", "scope", "shards", "ephemeralPublicKey", "nonce", "ciphertext"):
        if key not in req:
            raise ValueError(f"request missing {key}")
    if int(req["v"]) != 1:
        raise ValueError("unsupported encrypted request version")
    if int(req["shards"]) != 8:
        raise ValueError("this workflow is frozen to 8 shards")
    if req["project"] != "private-backtest":
        raise ValueError("unsupported artifact project")
    return req


def decrypt_payload(env: dict) -> dict:
    token = os.environ.get("CLOUDFLARE_API_TOKEN", "").strip()
    if not token:
        raise RuntimeError("CLOUDFLARE_API_TOKEN is required for staging")
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey, X25519PublicKey
    from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305
    from cryptography.hazmat.primitives.kdf.hkdf import HKDF

    seed = hashlib.sha256(CRYPTO_SEED_PREFIX + token.encode()).digest()
    private = X25519PrivateKey.from_private_bytes(seed)
    ephemeral = X25519PublicKey.from_public_bytes(base64.b64decode(env["ephemeralPublicKey"]))
    shared = private.exchange(ephemeral)
    key = HKDF(algorithm=hashes.SHA256(), length=32, salt=None, info=CRYPTO_INFO).derive(shared)
    plain = ChaCha20Poly1305(key).decrypt(
        base64.b64decode(env["nonce"]), base64.b64decode(env["ciphertext"]), str(env["id"]).encode()
    )
    payload = json.loads(plain)
    if str(payload.get("id")) != str(env["id"]):
        raise ValueError("encrypted payload id mismatch")
    if str(payload.get("compute_scope")) != str(env["scope"]):
        raise ValueError("encrypted payload scope mismatch")
    return payload


def download_private_source(url: str, dest: Path, expected_sha256: str):
    parsed = urllib.parse.urlparse(url)
    host = (parsed.hostname or "").lower()
    if parsed.scheme != "https" or not host.endswith(DROPBOX_HOST_SUFFIX):
        raise ValueError("unsupported private source host")
    req = urllib.request.Request(url, headers={"User-Agent": "runner-3-private-backtest-stage/1"})
    with urllib.request.urlopen(req, timeout=180) as r, dest.open("wb") as f:
        shutil.copyfileobj(r, f, length=1024 * 1024)
    got = sha256_file(dest)
    if expected_sha256 and got.lower() != str(expected_sha256).lower():
        raise ValueError(f"SHA256 mismatch for {dest.name}")
    return got


def stage(args) -> int:
    env = load_envelope(Path(args.request))
    payload = decrypt_payload(env)
    work = Path(tempfile.mkdtemp(prefix="private-bt-stage-"))
    local = {
        "engine": work / "engine.py", "evaluator": work / "evaluator.py",
        "profile": work / "profile.json", "helper": work / "exp.py",
    }
    hashes = {}
    for key in ("engine", "evaluator", "profile"):
        spec = payload["sources"][key]
        hashes[key] = download_private_source(spec["url"], local[key], spec["sha256"])
    local["helper"].write_bytes(base64.b64decode(payload["helper_b64"]))
    hashes["helper"] = sha256_file(local["helper"])
    if hashes["helper"].lower() != str(payload["helper_sha256"]).lower():
        raise ValueError("SHA256 mismatch for helper")

    files = {
        "engine": {"name": "package/engine.py", "sha256": hashes["engine"]},
        "evaluator": {"name": "package/evaluator.py", "sha256": hashes["evaluator"]},
        "profile": {"name": "package/profile.json", "sha256": hashes["profile"]},
        "helper": {"name": "package/exp.py", "sha256": hashes["helper"]},
    }
    ctypes = {
        "engine": "text/x-python; charset=utf-8", "evaluator": "text/x-python; charset=utf-8",
        "profile": "application/json; charset=utf-8", "helper": "text/x-python; charset=utf-8",
    }
    for key, spec in files.items():
        upload_artifact(env["project"], env["scope"], spec["name"], local[key], ctypes[key])

    manifest = {
        "schema": 2, "request_id": payload["request_id"], "type": payload["type"],
        "compute_scope": env["scope"], "created_at": now_iso(), "files": files,
        "symbol_timeout_seconds": int(payload.get("symbol_timeout_seconds", 5400)),
        "retries": int(payload.get("retries", 1)), "parity_target": payload["parity_target"],
        "checkpoint_project": payload.get("checkpoint_project", "super-rsi"),
        "checkpoint_scope": payload["checkpoint_scope"],
    }
    manifest_path = work / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    upload_artifact(env["project"], env["scope"], "manifest.json", manifest_path, "application/json; charset=utf-8")
    put_json(
        f"/checkpoints/{q(manifest['checkpoint_project'])}/{q(manifest['checkpoint_scope'])}",
        {
            "source": SOURCE, "status": "staged",
            "position": {
                "phase": "staged_for_runner3_matrix", "request_id": payload["request_id"],
                "compute_scope": env["scope"], "created_at": manifest["created_at"],
                "artifact_project": env["project"], "artifact_scope": env["scope"],
                "artifact_name": "manifest.json", "source_sha256": hashes,
            },
            "dropbox_path": None, "last_error": None,
        },
    )
    print(json.dumps({"stage": "ready", "scope": env["scope"], "shards": env["shards"]}))
    return 0


def fetch_package(req: dict, root: Path):
    project, scope = req["project"], req["scope"]
    manifest_path = root / "manifest.json"
    download_artifact(project, scope, "manifest.json", manifest_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("compute_scope") != scope:
        raise ValueError("manifest scope mismatch")
    local = {}
    for key, spec in manifest["files"].items():
        p = root / spec["name"]
        download_artifact(project, scope, spec["name"], p)
        if sha256_file(p).lower() != str(spec["sha256"]).lower():
            raise ValueError(f"sha256 mismatch for {key}")
        local[key] = p
    return manifest, local


def run_symbol(engine: Path, profile: Path, helper_dir: Path, symbol: str, out_root: Path, timeout_s: int):
    sym_out = out_root / symbol
    sym_out.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy(); env["SUPER_RSI_HELPER_DIR"] = str(helper_dir)
    p = subprocess.run(
        ["python", str(engine), "--profile", str(profile), "--symbol", symbol, "--out", str(sym_out)],
        text=True, capture_output=True, env=env, timeout=timeout_s,
    )
    return {"symbol": symbol, "returncode": p.returncode, "stdout": p.stdout[-4000:], "stderr": p.stderr[-8000:]}


def parity_check(report: dict, spec: dict):
    primary = report["primary"]; actual = primary["actual"]
    checks = {
        "coverage_exact": int(primary["ok_symbols"]) == int(spec["primary_symbols"]) and int(primary["expected_symbols"]) == int(spec["primary_symbols"]),
        "trades_exact": int(actual["n"]) == int(spec["trades"]),
        "positive_symbols_exact": int(primary["positive_symbols"]) == int(spec["positive_symbols"]),
    }
    numeric = {
        "actual_pf": (float(actual["PF"]), float(spec["actual_pf"]), float(spec.get("actual_pf_tol", 0.0005))),
        "actual_mean_bps": (float(actual["mean_bps"]), float(spec["actual_mean_bps"]), float(spec.get("actual_mean_bps_tol", 0.10))),
        "median_symbol_pf": (float(primary["median_symbol_PF_ge5"]), float(spec["median_symbol_pf"]), float(spec.get("median_symbol_pf_tol", 0.001))),
    }
    deltas = {}
    for name, (got, target, tol) in numeric.items():
        deltas[name] = {"actual": got, "target": target, "delta": got - target, "tolerance": tol}
        checks[f"{name}_within_tolerance"] = abs(got - target) <= tol
    return {"PASS_CANONICAL_PARITY": all(checks.values()), "checks": checks, "deltas": deltas}


def shard(args) -> int:
    req = load_envelope(Path(args.request)); shard_id = int(args.shard); shard_count = int(req["shards"])
    work = Path(tempfile.mkdtemp(prefix=f"private-bt-{shard_id}-"))
    pkg, symbols_root, helper_dir = work / "pkg", work / "symbols", work / "helper"
    pkg.mkdir(); symbols_root.mkdir(); helper_dir.mkdir()
    manifest, local = fetch_package(req, pkg); shutil.copy2(local["helper"], helper_dir / "exp.py")
    profile_data = json.loads(local["profile"].read_text(encoding="utf-8"))
    universe = [str(s).upper() for s in profile_data["universe"]]
    assigned = [s for i, s in enumerate(universe) if i % shard_count == shard_id]
    timeout_s, retries = int(manifest.get("symbol_timeout_seconds", 5400)), int(manifest.get("retries", 1))
    attempts, failed = {}, []; started = time.time()
    for symbol in assigned:
        ok, last = False, None
        for attempt in range(retries + 1):
            attempts[symbol] = attempt + 1
            try:
                last = run_symbol(local["engine"], local["profile"], helper_dir, symbol, symbols_root, timeout_s)
            except Exception as exc:
                last = {"symbol": symbol, "returncode": 99, "stdout": "", "stderr": repr(exc)}
            if last["returncode"] == 0 and (symbols_root / symbol / f"summary-{symbol}.json").exists():
                ok = True; break
        if not ok:
            failed.append(symbol)
            (symbols_root / symbol / "runner-error.json").write_text(json.dumps(last, ensure_ascii=False, indent=2), encoding="utf-8")
    archive = work / f"shard-{shard_id:02d}.tar.gz"
    with tarfile.open(archive, "w:gz") as tf:
        tf.add(symbols_root, arcname="symbols")
    status = {
        "shard": shard_id, "assigned_count": len(assigned), "failed_count": len(failed),
        "failed_symbols": failed, "attempts": attempts, "elapsed_seconds": round(time.time() - started, 3),
        "completed_at": now_iso(),
    }
    status_path = work / f"shard-{shard_id:02d}.json"
    status_path.write_text(json.dumps(status, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    upload_artifact(req["project"], req["scope"], f"shards/shard-{shard_id:02d}.tar.gz", archive, "application/gzip")
    upload_artifact(req["project"], req["scope"], f"shards/shard-{shard_id:02d}.json", status_path, "application/json; charset=utf-8")
    print(json.dumps({"shard": shard_id, "assigned": len(assigned), "failed": len(failed)}))
    return 0


def evaluate(args) -> int:
    req = load_envelope(Path(args.request)); work = Path(tempfile.mkdtemp(prefix="private-bt-eval-"))
    pkg, symbols_root, final_dir = work / "pkg", work / "symbols", work / "final"
    pkg.mkdir(); symbols_root.mkdir(); final_dir.mkdir(); manifest, local = fetch_package(req, pkg)
    shard_statuses, missing = [], []
    for shard_id in range(int(req["shards"])):
        archive, status_path = work / f"shard-{shard_id:02d}.tar.gz", work / f"shard-{shard_id:02d}.json"
        try:
            download_artifact(req["project"], req["scope"], f"shards/shard-{shard_id:02d}.tar.gz", archive)
            download_artifact(req["project"], req["scope"], f"shards/shard-{shard_id:02d}.json", status_path)
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                missing.append(shard_id); continue
            raise
        with tarfile.open(archive, "r:gz") as tf:
            tf.extractall(work)
        shard_statuses.append(json.loads(status_path.read_text(encoding="utf-8")))
    failed_symbols = sorted({s for row in shard_statuses for s in row.get("failed_symbols", [])})
    result = {
        "request_id": manifest.get("request_id"), "compute_scope": req["scope"], "type": manifest.get("type"),
        "completed_at": now_iso(), "infrastructure_ok": False, "execution_exit_code": 70,
        "result": {"missing_shards": missing, "failed_symbols": failed_symbols},
    }
    exit_code = 1
    if not missing:
        ev = subprocess.run(
            ["python", str(local["evaluator"]), "--profile", str(local["profile"]), "--input", str(symbols_root), "--out", str(final_dir)],
            text=True, capture_output=True, timeout=1800,
        )
        if ev.returncode != 0:
            result["error"] = "evaluator failed"; result["log_tail"] = ev.stderr[-8000:]
        else:
            report = json.loads((final_dir / "report.json").read_text(encoding="utf-8")); parity = parity_check(report, manifest["parity_target"])
            primary = report.get("primary", {})
            result = {
                "request_id": manifest.get("request_id"), "compute_scope": req["scope"], "type": manifest.get("type"),
                "completed_at": now_iso(), "infrastructure_ok": True, "execution_exit_code": 0,
                "result": {
                    "failed_symbols": failed_symbols, "primary_ok": primary.get("ok_symbols"),
                    "primary_expected": primary.get("expected_symbols"), "primary_trades": primary.get("actual", {}).get("n"),
                    "actual_pf": primary.get("actual", {}).get("PF"), "actual_mean_bps": primary.get("actual", {}).get("mean_bps"),
                    "positive_symbols": primary.get("positive_symbols"), "median_symbol_pf": primary.get("median_symbol_PF_ge5"),
                    "PASS_PROFILE_GATES": report.get("PASS_PROFILE_GATES"), "parity": parity,
                },
            }
            for name, ctype in [
                ("report.json", "application/json; charset=utf-8"), ("SUMMARY.md", "text/markdown; charset=utf-8"),
                ("symbol_summary.csv", "text/csv; charset=utf-8"), ("yearly_summary.csv", "text/csv; charset=utf-8"),
                ("trades.jsonl", "application/x-ndjson; charset=utf-8"),
            ]:
                p = final_dir / name
                if p.exists():
                    upload_artifact(req["project"], req["scope"], f"final/{name}", p, ctype)
            exit_code = 0 if not failed_symbols and parity["PASS_CANONICAL_PARITY"] else 2
    result_path = work / "result.json"
    result_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    upload_artifact(req["project"], req["scope"], "result.json", result_path, "application/json; charset=utf-8")
    cp_project, cp_scope = manifest.get("checkpoint_project"), manifest.get("checkpoint_scope")
    if cp_project and cp_scope:
        parity = result.get("result", {}).get("parity") or {}; status = "success" if exit_code == 0 else "failed"
        put_json(
            f"/checkpoints/{q(cp_project)}/{q(cp_scope)}",
            {
                "source": SOURCE, "status": status,
                "position": {
                    "phase": "complete" if status == "success" else "parity_mismatch",
                    "request_id": manifest.get("request_id"), "compute_scope": req["scope"],
                    "completed_at": result.get("completed_at"), "PASS_CANONICAL_PARITY": parity.get("PASS_CANONICAL_PARITY"),
                    "artifact_project": req["project"], "artifact_scope": req["scope"], "artifact_name": "result.json",
                },
                "dropbox_path": None,
                "last_error": None if status == "success" else json.dumps(result.get("result", {}), ensure_ascii=False)[-1800:],
            },
        )
    print(json.dumps({
        "scope": req["scope"], "exit_code": exit_code,
        "coverage": [result.get("result", {}).get("primary_ok"), result.get("result", {}).get("primary_expected")],
        "trades": result.get("result", {}).get("primary_trades"),
        "parity": result.get("result", {}).get("parity", {}).get("PASS_CANONICAL_PARITY"),
    }))
    return exit_code


def redact_error(text: str) -> str:
    text = re.sub(r"https?://\S+", "[url-redacted]", text)
    text = re.sub(r"(?i)(authorization|token|secret|key)\s*[=:]\s*\S+", r"\1=[redacted]", text)
    return text[-12000:]


def main() -> int:
    p = argparse.ArgumentParser(); sub = p.add_subparsers(dest="cmd", required=True)
    st = sub.add_parser("stage"); st.add_argument("--request", required=True)
    s = sub.add_parser("shard"); s.add_argument("--request", required=True); s.add_argument("--shard", required=True, type=int)
    e = sub.add_parser("evaluate"); e.add_argument("--request", required=True)
    args = p.parse_args()
    if args.cmd == "stage": return stage(args)
    if args.cmd == "shard": return shard(args)
    return evaluate(args)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    except Exception:
        print(redact_error(traceback.format_exc()))
        raise SystemExit(70)
