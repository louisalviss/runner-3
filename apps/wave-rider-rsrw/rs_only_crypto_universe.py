#!/usr/bin/env python3
from __future__ import annotations

import inspect
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import rsrw_crypto_universe as u


def patch_run_case_rs_only(base):
    original = base.run_case
    src = inspect.getsource(original)
    long_old = "nl=allowed and safe and z['sra_ok'] and b.c>b.o and lr and b.c>z['res'] and b.l<=z['res']"
    long_new = long_old + " and RS_GATE_LONG.get(b.ot,False)"
    if src.count(long_old) != 1:
        raise SystemExit("RS_ONLY_PATCH_ANCHOR_MISMATCH")
    src = src.replace(long_old, long_new, 1)
    ns = base.__dict__
    exec(compile(src, "<rs_only_universe_run_case>", "exec"), ns)
    patched = ns["run_case"]
    base.run_case = original
    return original, patched


def fix_shard_metadata():
    p = u.OUT / f"result-{u.SHARD}.json"
    if not p.exists():
        return
    x = json.loads(p.read_text())
    x["strategy"] = "WR canonical crypto 5m + RS-only/BTC full-universe confirmation"
    x["rule"] = "LONG: asset/BTC > EMA(asset/BTC) and EMA slope up; SHORT: canonical WR unchanged (no RW gate)"
    x["mode"] = "RS_ONLY_LONG"
    p.write_text(json.dumps(x, indent=2) + "\n")


def fix_merge_metadata():
    final = Path(__import__("os").getenv("WR_RSRW_FINAL_OUT", "/tmp/final"))
    p = final / "report.json"
    if not p.exists():
        return
    x = json.loads(p.read_text())
    x["strategy"] = "WR canonical crypto 5m + RS-only/BTC full-universe confirmation"
    x["rule"] = "LONG: asset/BTC > EMA(asset/BTC) and EMA slope up; SHORT: canonical WR unchanged (no RW gate)"
    x["mode"] = "RS_ONLY_LONG"
    p.write_text(json.dumps(x, indent=2) + "\n")


def main():
    u.patch_run_case = patch_run_case_rs_only
    mode = sys.argv[1] if len(sys.argv) > 1 else "shard"
    if mode == "shard":
        u.run_shard()
        fix_shard_metadata()
    elif mode == "merge":
        u.run_merge()
        fix_merge_metadata()
    else:
        raise SystemExit(f"unknown mode: {mode}")


if __name__ == "__main__":
    main()
