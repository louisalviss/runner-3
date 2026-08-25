#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
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
        "User-Agent": "runner-3-private-backtest/1",
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
        artifact_url(project, scope, name),
        data=data,
        headers=headers(content_type=content_type),
        method="PUT",
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r).get("artifact")


def put_json(path: str, payload: dict, timeout=30):
    data = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    req = urllib.request.Request(
        CORE_URL + path,
        data=data,
        headers=headers(content_type="application/json"),
        method="PUT",
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def load_request(path: Path) -> dict:
    req = json.loads(path.read_text(encoding="utf-8"))
    for key in ("project", "scope", "shards"):
        if key not in req:
            raise ValueError(f"request missing {key}")
    if int(req["shards"]) != 8:
        raise ValueError("this workflow is frozen to 8 shards")
    return req


def fetch_package(req: dict, root: Path):
    project, scope = req["project"], req["scope"]
    manifest_path = root / "manifest.json"
    download_artifact(project, scope, "manifest.json", manifest_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("compute_scope") != scope:
        raise ValueError("manifest scope mismatch")
    files = manifest["files"]
    local = {}
    for key, spec in files.items():
        p = root / spec["name"]
        download_artifact(project, scope, spec["name"], p)
        got = sha256_file(p)
        if got.lower() != str(spec["sha256"]).lower():
            raise ValueError(f"sha256 mismatch for {key}")
        local[key] = p
    return manifest, local


def run_symbol(py: str, engine: Path, profile: Path, helper_dir: Path, symbol: str, out_root: Path, timeout_s: int):
    sym_out = out_root / symbol
    sym_out.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env["SUPER_RSI_HELPER_DIR"] = str(helper_dir)
    cmd = [py, str(engine), "--profile", str(profile), "--symbol", symbol, "--out", str(sym_out)]
    p = subprocess.run(cmd, text=True, capture_output=True, env=env, timeout=timeout_s)
    return {
        "symbol": symbol,
        "returncode": p.returncode,
        "stdout": p.stdout[-4000:],
        "stderr": p.stderr[-8000:],
    }


def parity_check(report: dict, spec: dict):
    primary = report["primary"]
    actual = primary["actual"]
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
    req = load_request(Path(args.request))
    shard_id = int(args.shard)
    shard_count = int(req["shards"])
    work = Path(tempfile.mkdtemp(prefix=f"private-bt-{shard_id}-"))
    pkg = work / "pkg"
    symbols_root = work / "symbols"
    helper_dir = work / "helper"
    pkg.mkdir(); symbols_root.mkdir(); helper_dir.mkdir()
    manifest, local = fetch_package(req, pkg)
    shutil.copy2(local["helper"], helper_dir / "exp.py")
    profile_data = json.loads(local["profile"].read_text(encoding="utf-8"))
    universe = [str(s).upper() for s in profile_data["universe"]]
    assigned = [s for i, s in enumerate(universe) if i % shard_count == shard_id]
    timeout_s = int(manifest.get("symbol_timeout_seconds", 5400))
    retries = int(manifest.get("retries", 1))
    attempts = {}
    failed = []
    started = time.time()
    for symbol in assigned:
        ok = False
        last = None
        for attempt in range(retries + 1):
            attempts[symbol] = attempt + 1
            try:
                last = run_symbol("python", local["engine"], local["profile"], helper_dir, symbol, symbols_root, timeout_s)
            except Exception as exc:
                last = {"symbol": symbol, "returncode": 99, "stdout": "", "stderr": repr(exc)}
            summary_path = symbols_root / symbol / f"summary-{symbol}.json"
            if last["returncode"] == 0 and summary_path.exists():
                ok = True
                break
        if not ok:
            failed.append(symbol)
            (symbols_root / symbol / "runner-error.json").write_text(json.dumps(last, ensure_ascii=False, indent=2), encoding="utf-8")

    archive = work / f"shard-{shard_id:02d}.tar.gz"
    with tarfile.open(archive, "w:gz") as tf:
        tf.add(symbols_root, arcname="symbols")
    status = {
        "shard": shard_id,
        "assigned_count": len(assigned),
        "failed_count": len(failed),
        "failed_symbols": failed,
        "attempts": attempts,
        "elapsed_seconds": round(time.time() - started, 3),
        "completed_at": now_iso(),
    }
    status_path = work / f"shard-{shard_id:02d}.json"
    status_path.write_text(json.dumps(status, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    upload_artifact(req["project"], req["scope"], f"shards/shard-{shard_id:02d}.tar.gz", archive, "application/gzip")
    upload_artifact(req["project"], req["scope"], f"shards/shard-{shard_id:02d}.json", status_path, "application/json; charset=utf-8")
    print(json.dumps({"shard": shard_id, "assigned": len(assigned), "failed": len(failed)}))
    return 0


def evaluate(args) -> int:
    req = load_request(Path(args.request))
    work = Path(tempfile.mkdtemp(prefix="private-bt-eval-"))
    pkg = work / "pkg"; symbols_root = work / "symbols"; final_dir = work / "final"
    pkg.mkdir(); symbols_root.mkdir(); final_dir.mkdir()
    manifest, local = fetch_package(req, pkg)
    shard_statuses = []
    missing = []
    for shard_id in range(int(req["shards"])):
        archive = work / f"shard-{shard_id:02d}.tar.gz"
        status_path = work / f"shard-{shard_id:02d}.json"
        try:
            download_artifact(req["project"], req["scope"], f"shards/shard-{shard_id:02d}.tar.gz", archive)
            download_artifact(req["project"], req["scope"], f"shards/shard-{shard_id:02d}.json", status_path)
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                missing.append(shard_id)
                continue
            raise
        with tarfile.open(archive, "r:gz") as tf:
            tf.extractall(work)
        shard_statuses.append(json.loads(status_path.read_text(encoding="utf-8")))

    failed_symbols = sorted({s for row in shard_statuses for s in row.get("failed_symbols", [])})
    result = {
        "request_id": manifest.get("request_id"),
        "compute_scope": req["scope"],
        "type": manifest.get("type"),
        "completed_at": now_iso(),
        "infrastructure_ok": False,
        "execution_exit_code": 70,
        "result": {"missing_shards": missing, "failed_symbols": failed_symbols},
    }
    exit_code = 1
    if not missing:
        eval_run = subprocess.run(
            ["python", str(local["evaluator"]), "--profile", str(local["profile"]), "--input", str(symbols_root), "--out", str(final_dir)],
            text=True, capture_output=True, timeout=1800,
        )
        if eval_run.returncode != 0:
            result["error"] = "evaluator failed"
            result["log_tail"] = eval_run.stderr[-8000:]
        else:
            report = json.loads((final_dir / "report.json").read_text(encoding="utf-8"))
            parity = parity_check(report, manifest["parity_target"])
            primary = report.get("primary", {})
            result = {
                "request_id": manifest.get("request_id"),
                "compute_scope": req["scope"],
                "type": manifest.get("type"),
                "completed_at": now_iso(),
                "infrastructure_ok": True,
                "execution_exit_code": 0,
                "result": {
                    "failed_symbols": failed_symbols,
                    "primary_ok": primary.get("ok_symbols"),
                    "primary_expected": primary.get("expected_symbols"),
                    "primary_trades": primary.get("actual", {}).get("n"),
                    "actual_pf": primary.get("actual", {}).get("PF"),
                    "actual_mean_bps": primary.get("actual", {}).get("mean_bps"),
                    "positive_symbols": primary.get("positive_symbols"),
                    "median_symbol_pf": primary.get("median_symbol_PF_ge5"),
                    "PASS_PROFILE_GATES": report.get("PASS_PROFILE_GATES"),
                    "parity": parity,
                },
            }
            for name, ctype in [
                ("report.json", "application/json; charset=utf-8"),
                ("SUMMARY.md", "text/markdown; charset=utf-8"),
                ("symbol_summary.csv", "text/csv; charset=utf-8"),
                ("yearly_summary.csv", "text/csv; charset=utf-8"),
                ("trades.jsonl", "application/x-ndjson; charset=utf-8"),
            ]:
                p = final_dir / name
                if p.exists():
                    upload_artifact(req["project"], req["scope"], f"final/{name}", p, ctype)
            exit_code = 0 if not failed_symbols and parity["PASS_CANONICAL_PARITY"] else 2

    result_path = work / "result.json"
    result_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    upload_artifact(req["project"], req["scope"], "result.json", result_path, "application/json; charset=utf-8")

    cp_project = manifest.get("checkpoint_project")
    cp_scope = manifest.get("checkpoint_scope")
    if cp_project and cp_scope:
        parity = result.get("result", {}).get("parity") or {}
        status = "success" if exit_code == 0 else "failed"
        put_json(
            f"/checkpoints/{q(cp_project)}/{q(cp_scope)}",
            {
                "source": SOURCE,
                "status": status,
                "position": {
                    "phase": "complete" if status == "success" else "parity_mismatch",
                    "request_id": manifest.get("request_id"),
                    "compute_scope": req["scope"],
                    "completed_at": result.get("completed_at"),
                    "PASS_CANONICAL_PARITY": parity.get("PASS_CANONICAL_PARITY"),
                    "artifact_project": req["project"],
                    "artifact_scope": req["scope"],
                    "artifact_name": "result.json",
                },
                "dropbox_path": None,
                "last_error": None if status == "success" else json.dumps(result.get("result", {}), ensure_ascii=False)[-1800:],
            },
        )
    print(json.dumps({"compute_scope": req["scope"], "exit_code": exit_code, "parity": result.get("result", {}).get("parity", {}).get("PASS_CANONICAL_PARITY")}))
    return exit_code


def main() -> int:
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("shard"); s.add_argument("--request", required=True); s.add_argument("--shard", required=True, type=int)
    e = sub.add_parser("evaluate"); e.add_argument("--request", required=True)
    args = p.parse_args()
    if args.cmd == "shard":
        return shard(args)
    return evaluate(args)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception:
        traceback.print_exc()
        raise SystemExit(70)
