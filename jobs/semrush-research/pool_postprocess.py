#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import time
from typing import Any

VPS_CONTROL_ROOT = pathlib.Path(os.environ.get("VPS_CONTROL_ROOT", "/var/lib/github-ops-guard/vps-control-main"))
RUNNER3_ENV = pathlib.Path(os.environ.get("RUNNER3_CORE_ENV", "/etc/vps-control/runner3-core.env"))
SWARM = pathlib.Path(os.environ.get("VPS_ACTIONS_SWARM", "/usr/local/bin/vps-actions-swarm"))
ROUTER_JOBS = pathlib.Path(os.environ.get("VPS_ACTIONS_ROUTER_JOBS", "/var/lib/vps-actions-router/jobs"))
PROJECT = "semrush-research"
SCOPE = "pool-input"
FLOW = "data-pipeline-stateless"
TASK = "niche-research-postprocess"

DEFAULT_CONFIG: dict[str, Any] = {
    "max_kd": 29.0,
    "min_keyword_volume": 20,
    "min_total_volume": 10000,
    "min_low_kd_volume": 2000,
    "min_keyword_count": 20,
    "min_longtail_count": 10,
    "longtail_tokens": 4,
    "max_median_kd": 30.0,
    "max_head_share": 0.60,
    "cluster_min_tokens": 3,
}


def canonical(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def sha256_file(path: pathlib.Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def atomic_json(path: pathlib.Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_bytes(canonical(payload))
    tmp.replace(path)


def load_runner3_env() -> None:
    if os.environ.get("RUNNER3_CORE_TOKEN") or os.environ.get("RUNNER3_CORE_TOKEN_B64"):
        return
    if not RUNNER3_ENV.is_file():
        raise RuntimeError("RUNNER3_CORE_ENV_MISSING")
    for raw in RUNNER3_ENV.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if key not in {"RUNNER3_CORE_URL", "RUNNER3_CORE_TOKEN", "RUNNER3_CORE_TOKEN_B64", "RUNNER3_CORE_USER_AGENT"}:
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        os.environ.setdefault(key, value)
    if not (os.environ.get("RUNNER3_CORE_TOKEN") or os.environ.get("RUNNER3_CORE_TOKEN_B64")):
        raise RuntimeError("RUNNER3_CORE_CREDENTIAL_MISSING")


def source_identity() -> tuple[str, str]:
    commit = subprocess.run(
        ["git", "-C", str(VPS_CONTROL_ROOT), "rev-parse", "HEAD"],
        text=True, capture_output=True, check=True, timeout=20,
    ).stdout.strip()
    if not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise RuntimeError("VPS_CONTROL_COMMIT_INVALID")
    helper = VPS_CONTROL_ROOT / "scripts/vps_actions_pool_source_sha.py"
    proc = subprocess.run(
        [sys.executable, str(helper), FLOW, "--root", str(VPS_CONTROL_ROOT)],
        text=True, capture_output=True, check=True, timeout=60,
    )
    source_sha = proc.stdout.strip()
    if not re.fullmatch(r"[0-9a-f]{64}", source_sha):
        raise RuntimeError("POOL_SOURCE_SHA_INVALID")
    return commit, source_sha


def runner3_module():
    sys.path.insert(0, str(VPS_CONTROL_ROOT / "stack"))
    import runner3_core  # type: ignore
    return runner3_core


def ensure_artifact(src: pathlib.Path, source_sha: str) -> dict[str, Any]:
    load_runner3_env()
    core = runner3_module()
    name = f"universe-{source_sha[:16]}.json"
    existing = core.get_artifact_bytes(PROJECT, SCOPE, name, timeout=120)
    if existing is not None:
        actual = hashlib.sha256(existing).hexdigest()
        if actual != source_sha:
            raise RuntimeError("POOL_INPUT_ARTIFACT_HASH_COLLISION")
        return {"project": PROJECT, "scope": SCOPE, "name": name, "sha256": source_sha, "reused": True, "bytes": len(existing)}
    meta = core.put_artifact_file(PROJECT, SCOPE, name, src, content_type="application/json", timeout=300)
    readback = core.get_artifact_bytes(PROJECT, SCOPE, name, timeout=120)
    if readback is None or hashlib.sha256(readback).hexdigest() != source_sha:
        raise RuntimeError("POOL_INPUT_ARTIFACT_READBACK_MISMATCH")
    return {"project": PROJECT, "scope": SCOPE, "name": name, "sha256": source_sha, "reused": False, "bytes": len(readback), "meta": meta}


def build_payload(artifact: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema": "vps-control-pool-task-v1",
        "flow": FLOW,
        "task": TASK,
        "source_artifact": {k: artifact[k] for k in ("project", "scope", "name", "sha256")},
        "config": config,
    }


def build_manifest(source_commit: str, flow_sha: str, payload: dict[str, Any], swarm_id: str) -> dict[str, Any]:
    return {
        "schema": "vps-actions-swarm-v1",
        "swarm_id": swarm_id,
        "max_parallel": 2,
        "tasks": [{
            "id": "demand",
            "flow": FLOW,
            "payload_ref": f"vps-control@{source_commit}",
            "source_sha": flow_sha,
            "estimate_minutes": 2,
            "timeout": 900,
            "job_payload": payload,
        }],
    }


def materialize(job_id: str, output_dir: pathlib.Path, expected_input_sha: str) -> dict[str, Any]:
    job_dir = ROUTER_JOBS / job_id
    state_path = job_dir / "state.json"
    if not state_path.is_file():
        raise RuntimeError("POOL_JOB_STATE_MISSING")
    job_state = json.loads(state_path.read_text(encoding="utf-8"))
    if job_state.get("state") != "completed" or (job_state.get("proof") or {}).get("ok") is not True:
        raise RuntimeError("POOL_JOB_NOT_VERIFIED_COMPLETE")
    src = job_dir / "artifact/niche-research"
    if not src.is_dir():
        raise RuntimeError("POOL_JOB_OUTPUT_MISSING")
    state = json.loads((src / "state.json").read_text(encoding="utf-8"))
    if state.get("stage") != "SERP_DD_PENDING" or state.get("source_sha256") != expected_input_sha:
        raise RuntimeError("POOL_JOB_OUTPUT_IDENTITY_MISMATCH")
    output_dir.mkdir(parents=True, exist_ok=True)
    for item in src.iterdir():
        target = output_dir / item.name
        if item.is_file():
            target.write_bytes(item.read_bytes())
    return {"job_state": job_state, "demand_state": state}


def main() -> int:
    ap = argparse.ArgumentParser(description="Offload Semrush niche demand/clustering post-processing to the GitHub hosted pool.")
    ap.add_argument("--input", required=True, help="Existing VPS universe.json. This helper never calls Semrush.")
    ap.add_argument("--output-dir", required=True)
    ap.add_argument("--config-json", help="Optional JSON object overriding demand_first numeric defaults.")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    src = pathlib.Path(args.input).resolve()
    out = pathlib.Path(args.output_dir).resolve()
    if not src.is_file() or src.suffix.lower() != ".json":
        raise RuntimeError("POOL_INPUT_JSON_REQUIRED")
    if src.stat().st_size > 64 * 1024 * 1024:
        raise RuntimeError("POOL_INPUT_TOO_LARGE")
    input_sha = sha256_file(src)

    config = dict(DEFAULT_CONFIG)
    if args.config_json:
        override = json.loads(args.config_json)
        if not isinstance(override, dict) or set(override) - set(DEFAULT_CONFIG):
            raise RuntimeError("POOL_CONFIG_INVALID")
        config.update(override)
    config_sha = hashlib.sha256(canonical(config)).hexdigest()

    current_state = out / "state.json"
    if current_state.is_file() and not args.force:
        state = json.loads(current_state.read_text(encoding="utf-8"))
        proof_path = out / "pool-proof.json"
        proof = json.loads(proof_path.read_text(encoding="utf-8")) if proof_path.is_file() else {}
        if state.get("stage") == "SERP_DD_PENDING" and state.get("source_sha256") == input_sha and proof.get("config_sha256") == config_sha:
            print(json.dumps({"status": "RESUME_NO_BACKTRACK", "stage": "SERP_DD_PENDING", "source_sha256": input_sha, "output_dir": str(out)}, ensure_ascii=False))
            return 0

    commit, flow_sha = source_identity()
    dispatch_path = out / "pool-dispatch.json"
    if dispatch_path.is_file() and not args.force:
        prior = json.loads(dispatch_path.read_text(encoding="utf-8"))
        if prior.get("input_sha256") == input_sha and prior.get("config_sha256") == config_sha:
            job_id = str(prior.get("job_id") or "")
            if job_id and (ROUTER_JOBS / job_id / "state.json").is_file():
                info = materialize(job_id, out, input_sha)
                proof = {"ok": True, "recovered": True, "input_sha256": input_sha, "config_sha256": config_sha,
                         "vps_control_commit": prior.get("vps_control_commit"), "flow_source_sha256": prior.get("flow_source_sha256"),
                         "artifact": prior.get("artifact"), "job_id": job_id, "router_proof": (info["job_state"].get("proof") or {})}
                atomic_json(out / "pool-proof.json", proof)
                print(json.dumps({"status": "RECOVERED", "stage": "SERP_DD_PENDING", "job_id": job_id, "output_dir": str(out)}, ensure_ascii=False))
                return 0
            raise RuntimeError("POOL_PREVIOUS_DISPATCH_NOT_TERMINAL")

    if args.dry_run:
        artifact = {"project": PROJECT, "scope": SCOPE, "name": f"universe-{input_sha[:16]}.json", "sha256": input_sha}
    else:
        artifact = ensure_artifact(src, input_sha)
    payload = build_payload(artifact, config)
    swarm_id = f"niche-{input_sha[:12]}-{int(time.time())}"
    manifest = build_manifest(commit, flow_sha, payload, swarm_id)
    manifest_path = out / "pool-swarm.json"
    out.mkdir(parents=True, exist_ok=True)
    atomic_json(manifest_path, manifest)

    if args.dry_run:
        proc = subprocess.run([str(SWARM), "--dry-run", str(manifest_path)], text=True, capture_output=True, timeout=60)
        if proc.returncode:
            raise RuntimeError("POOL_SWARM_DRY_RUN_FAILED:" + (proc.stderr or proc.stdout)[-800:])
        print(json.dumps({"status": "DRY_RUN_PASS", "input_sha256": input_sha, "vps_control_commit": commit,
                          "flow_source_sha256": flow_sha, "plan": json.loads(proc.stdout), "manifest": str(manifest_path)}, ensure_ascii=False))
        return 0

    job_id = f"{swarm_id}.demand"
    dispatch = {"schema": "semrush-niche-pool-dispatch-v1", "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "input": str(src), "input_sha256": input_sha, "config": config, "config_sha256": config_sha,
                "vps_control_commit": commit, "flow_source_sha256": flow_sha, "artifact": artifact,
                "swarm_id": swarm_id, "job_id": job_id, "manifest": str(manifest_path)}
    atomic_json(dispatch_path, dispatch)
    proc = subprocess.run([str(SWARM), str(manifest_path)], text=True, capture_output=True, timeout=1100)
    if proc.returncode:
        raise RuntimeError("POOL_SWARM_FAILED:" + (proc.stderr or proc.stdout)[-1600:])
    swarm_result = json.loads(proc.stdout)
    if swarm_result.get("ok") is not True:
        raise RuntimeError("POOL_SWARM_RESULT_NOT_OK")
    info = materialize(job_id, out, input_sha)
    proof = {"ok": True, "input_sha256": input_sha, "config_sha256": config_sha, "vps_control_commit": commit,
             "flow_source_sha256": flow_sha, "artifact": artifact, "job_id": job_id,
             "swarm_result": swarm_result, "router_proof": (info["job_state"].get("proof") or {})}
    atomic_json(out / "pool-proof.json", proof)
    print(json.dumps({"status": "PASS", "stage": "SERP_DD_PENDING", "job_id": job_id,
                      "passed_projects": info["demand_state"].get("passed_projects") or [],
                      "queue_count": int(info["demand_state"].get("queue_count") or 0), "output_dir": str(out)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
