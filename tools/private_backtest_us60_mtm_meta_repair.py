#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import gzip
import json
import tempfile
from collections import defaultdict
from pathlib import Path
from types import SimpleNamespace

import private_backtest_worker_v2 as core
import private_backtest_us60_mtm_replay as mtm

PROJECT = "private-backtest"
META = "META"
LEGACY = "FB.US/USD"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    args = ap.parse_args()

    work = Path(tempfile.mkdtemp(prefix="us60-mtm-meta-repair-"))
    manifest, local = mtm.download_package(work)
    profile = json.loads(local["profile"].read_text(encoding="utf-8"))
    accepted = [json.loads(x) for x in local["accepted"].read_text(encoding="utf-8").splitlines() if x.strip()]
    meta_trades = [r for r in accepted if str(r.get("symbol", "")).upper() == META]
    if not meta_trades:
        raise RuntimeError("META has no accepted 40-slot trades")

    target_sid = None
    target_status = None
    for sid in range(int(manifest["shards"])):
        stp = work / f"status-{sid}.json"
        core.download_artifact(PROJECT, mtm.MTM_SCOPE, f"mtm/shard-{sid:02d}.json", stp)
        st = json.loads(stp.read_text(encoding="utf-8"))
        if META in st.get("assigned", []):
            target_sid = sid
            target_status = st
            break
    if target_sid is None or target_status is None:
        raise RuntimeError("cannot find META shard")

    engine = mtm.load_engine(local["engine"], local["helper"], work / "helper")
    original_resolve = engine.exp.resolve_symbol
    engine.exp.resolve_symbol = lambda s: LEGACY if str(s).upper() == META else original_resolve(s)
    points, meta_info = mtm.symbol_points(META, meta_trades, engine, profile)

    old_csv = work / f"old-{target_sid}.csv.gz"
    core.download_artifact(PROJECT, mtm.MTM_SCOPE, f"mtm/shard-{target_sid:02d}.csv.gz", old_csv)
    new_csv = work / f"mtm-shard-{target_sid:02d}.csv.gz"
    with gzip.open(old_csv, "rt", encoding="utf-8", newline="") as src, gzip.open(new_csv, "wt", encoding="utf-8", newline="") as dst:
        reader = csv.DictReader(src)
        writer = csv.writer(dst)
        writer.writerow(["symbol", "time", "open_return_bps"])
        for row in reader:
            if str(row.get("symbol", "")).upper() != META:
                writer.writerow([row["symbol"], row["time"], row["open_return_bps"]])
        for row in points:
            writer.writerow(row)

    target_status.setdefault("failed", {}).pop(META, None)
    if META not in target_status.setdefault("successful", []):
        target_status["successful"].append(META)
        target_status["successful"].sort()
    target_status.setdefault("symbol_meta", {})[META] = {**meta_info, "repair_alias": LEGACY}
    new_status = work / f"mtm-shard-{target_sid:02d}.json"
    new_status.write_text(json.dumps(target_status, indent=2) + "\n", encoding="utf-8")

    core.upload_artifact(PROJECT, mtm.MTM_SCOPE, f"mtm/shard-{target_sid:02d}.csv.gz", new_csv, "application/gzip")
    core.upload_artifact(PROJECT, mtm.MTM_SCOPE, f"mtm/shard-{target_sid:02d}.json", new_status, "application/json; charset=utf-8")
    print(json.dumps({"repair": "META_OK", "shard": target_sid, "points": len(points), "instrument": LEGACY}, indent=2))

    return mtm.evaluate(SimpleNamespace(config=args.config))


if __name__ == "__main__":
    raise SystemExit(main())
