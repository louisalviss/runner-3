#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import shutil
import tarfile
import tempfile
from pathlib import Path
from types import SimpleNamespace

import private_backtest_worker_v2 as core


def diagnose(req: dict, work: Path) -> dict:
    report_path = work / "report.json"
    csv_path = work / "symbol_summary.csv"
    core.download_artifact(req["project"], req["scope"], "final/report.json", report_path)
    core.download_artifact(req["project"], req["scope"], "final/symbol_summary.csv", csv_path)
    report = json.loads(report_path.read_text(encoding="utf-8"))
    rows = list(csv.DictReader(csv_path.open("r", encoding="utf-8", newline="")))
    row_by_symbol = {str(r.get("symbol", "")).upper(): r for r in rows if r.get("symbol")}
    expected = {str(s).upper() for s in report.get("primary_symbols", [])}
    ok = {s for s, r in row_by_symbol.items() if str(r.get("status", "")).upper() == "OK"}
    with_trades = {str(s).upper() for s in report.get("primary", {}).get("symbols", {}).keys()}
    missing_ok = sorted(expected - ok)
    missing_trades = sorted(expected - with_trades)
    details = {s: row_by_symbol.get(s) for s in sorted(set(missing_ok) | set(missing_trades))}
    return {
        "scope": req["scope"],
        "primary_expected": len(expected),
        "primary_ok": len(expected & ok),
        "missing_ok": missing_ok,
        "missing_trades": missing_trades,
        "details": details,
    }


def repair_one(req: dict, symbol: str, work: Path) -> dict:
    pkg_root = work / "pkg"
    helper_dir = work / "helper"
    pkg_root.mkdir(parents=True, exist_ok=True)
    helper_dir.mkdir(parents=True, exist_ok=True)
    manifest, local = core.fetch_package(req, pkg_root)
    shutil.copy2(local["helper"], helper_dir / "exp.py")

    profile = json.loads(local["profile"].read_text(encoding="utf-8"))
    universe = [str(s).upper() for s in profile["universe"]]
    symbol = symbol.upper()
    if symbol not in universe:
        raise ValueError(f"repair symbol not in universe: {symbol}")
    shard_id = universe.index(symbol) % int(req["shards"])

    archive = work / f"shard-{shard_id:02d}.tar.gz"
    status_path = work / f"shard-{shard_id:02d}.json"
    core.download_artifact(req["project"], req["scope"], f"shards/shard-{shard_id:02d}.tar.gz", archive)
    core.download_artifact(req["project"], req["scope"], f"shards/shard-{shard_id:02d}.json", status_path)

    shard_root = work / "shard-root"
    shard_root.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive, "r:gz") as tf:
        tf.extractall(shard_root)
    symbols_root = shard_root / "symbols"
    target = symbols_root / symbol
    if target.exists():
        shutil.rmtree(target)

    timeout_s = int(manifest.get("symbol_timeout_seconds", 5400))
    retries = int(manifest.get("retries", 1))
    last = None
    success = False
    for attempt in range(retries + 2):
        try:
            last = core.run_symbol(local["engine"], local["profile"], helper_dir, symbol, symbols_root, timeout_s)
        except Exception as exc:
            last = {"symbol": symbol, "returncode": 99, "stdout": "", "stderr": repr(exc)}
        summary_path = symbols_root / symbol / f"summary-{symbol}.json"
        if last["returncode"] == 0 and summary_path.exists():
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
            if str(summary.get("status", "")).upper() == "OK":
                success = True
                break
        if target.exists():
            shutil.rmtree(target)

    if not success:
        raise RuntimeError(json.dumps({
            "symbol": symbol,
            "returncode": None if last is None else last.get("returncode"),
            "stderr_tail": "" if last is None else str(last.get("stderr", ""))[-2000:],
            "stdout_tail": "" if last is None else str(last.get("stdout", ""))[-1000:],
        }, ensure_ascii=False))

    with tarfile.open(archive, "w:gz") as tf:
        tf.add(symbols_root, arcname="symbols")

    status = json.loads(status_path.read_text(encoding="utf-8"))
    status["failed_symbols"] = [s for s in status.get("failed_symbols", []) if str(s).upper() != symbol]
    status["failed_count"] = len(status["failed_symbols"])
    status.setdefault("repair", []).append({"symbol": symbol, "completed_at": core.now_iso()})
    status_path.write_text(json.dumps(status, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    core.upload_artifact(req["project"], req["scope"], f"shards/shard-{shard_id:02d}.tar.gz", archive, "application/gzip")
    core.upload_artifact(req["project"], req["scope"], f"shards/shard-{shard_id:02d}.json", status_path, "application/json; charset=utf-8")
    return {"symbol": symbol, "shard": shard_id, "status": "repaired"}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--request", required=True)
    ap.add_argument("--repair", required=True)
    args = ap.parse_args()

    req = core.load_envelope(Path(args.request))
    repair_spec = json.loads(Path(args.repair).read_text(encoding="utf-8"))
    if str(repair_spec.get("scope")) != str(req["scope"]):
        raise ValueError("repair scope does not match request scope")

    work = Path(tempfile.mkdtemp(prefix="private-bt-repair-"))
    before = diagnose(req, work / "diagnose-before")
    print(json.dumps({"diagnose_before": before}, ensure_ascii=False))

    candidates = sorted(set(before["missing_ok"]) | set(before["missing_trades"]))
    if len(candidates) != 1:
        raise RuntimeError(f"expected exactly one repair candidate, got {candidates}")

    repaired = repair_one(req, candidates[0], work / "repair")
    print(json.dumps({"repair": repaired}, ensure_ascii=False))

    exit_code = core.evaluate(SimpleNamespace(request=args.request))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
