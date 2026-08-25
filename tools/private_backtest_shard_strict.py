#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shutil
import tarfile
import tempfile
import time
from pathlib import Path

import private_backtest_worker_v2 as core


def run(request_path: str, shard_id: int) -> int:
    req = core.load_envelope(Path(request_path))
    shard_count = int(req["shards"])
    if shard_id < 0 or shard_id >= shard_count:
        raise ValueError(f"invalid shard id: {shard_id}")

    work = Path(tempfile.mkdtemp(prefix=f"private-bt-strict-{shard_id}-"))
    pkg = work / "pkg"
    symbols_root = work / "symbols"
    helper_dir = work / "helper"
    pkg.mkdir(); symbols_root.mkdir(); helper_dir.mkdir()

    manifest, local = core.fetch_package(req, pkg)
    shutil.copy2(local["helper"], helper_dir / "exp.py")
    profile_data = json.loads(local["profile"].read_text(encoding="utf-8"))
    universe = [str(s).upper() for s in profile_data["universe"]]
    assigned = [s for i, s in enumerate(universe) if i % shard_count == shard_id]
    timeout_s = int(manifest.get("symbol_timeout_seconds", 5400))
    retries = int(manifest.get("retries", 1))

    attempts: dict[str, int] = {}
    failed: list[str] = []
    failure_details: dict[str, dict] = {}
    started = time.time()

    for symbol in assigned:
        ok = False
        last: dict | None = None
        for attempt in range(retries + 1):
            attempts[symbol] = attempt + 1
            try:
                last = core.run_symbol(
                    local["engine"], local["profile"], helper_dir,
                    symbol, symbols_root, timeout_s,
                )
            except Exception as exc:
                last = {"symbol": symbol, "returncode": 99, "stdout": "", "stderr": repr(exc)}

            summary_path = symbols_root / symbol / f"summary-{symbol}.json"
            summary = None
            if last.get("returncode") == 0 and summary_path.exists():
                try:
                    summary = json.loads(summary_path.read_text(encoding="utf-8"))
                except Exception as exc:
                    last["stderr"] = (last.get("stderr", "") + f"\nsummary parse error: {exc!r}")[-8000:]

            if summary is not None and str(summary.get("status", "")).upper() == "OK":
                ok = True
                break

            if summary is not None:
                last["summary_status"] = summary.get("status")

        if not ok:
            failed.append(symbol)
            failure_details[symbol] = {
                "returncode": None if last is None else last.get("returncode"),
                "summary_status": None if last is None else last.get("summary_status"),
                "stderr_tail": "" if last is None else str(last.get("stderr", ""))[-2000:],
                "stdout_tail": "" if last is None else str(last.get("stdout", ""))[-1000:],
            }
            err_dir = symbols_root / symbol
            err_dir.mkdir(parents=True, exist_ok=True)
            (err_dir / "runner-error.json").write_text(
                json.dumps(failure_details[symbol], ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )

    archive = work / f"shard-{shard_id:02d}.tar.gz"
    with tarfile.open(archive, "w:gz") as tf:
        tf.add(symbols_root, arcname="symbols")

    status = {
        "shard": shard_id,
        "assigned_count": len(assigned),
        "failed_count": len(failed),
        "failed_symbols": failed,
        "failure_details": failure_details,
        "attempts": attempts,
        "strict_summary_status": True,
        "elapsed_seconds": round(time.time() - started, 3),
        "completed_at": core.now_iso(),
    }
    status_path = work / f"shard-{shard_id:02d}.json"
    status_path.write_text(json.dumps(status, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    core.upload_artifact(req["project"], req["scope"], f"shards/shard-{shard_id:02d}.tar.gz", archive, "application/gzip")
    core.upload_artifact(req["project"], req["scope"], f"shards/shard-{shard_id:02d}.json", status_path, "application/json; charset=utf-8")

    print(json.dumps({
        "shard": shard_id,
        "assigned": len(assigned),
        "failed": len(failed),
        "failed_symbols": failed,
        "strict_summary_status": True,
    }))
    return 2 if failed else 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--request", required=True)
    ap.add_argument("--shard", required=True, type=int)
    args = ap.parse_args()
    return run(args.request, args.shard)


if __name__ == "__main__":
    raise SystemExit(main())
