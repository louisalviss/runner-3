#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path

import private_backtest_us_timeframe_probe as base

PROJECT = "private-backtest"


def wj(path: Path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def cfg(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _redirect_checkpoint(c, fn, a):
    original = base.core.put_json
    checkpoint_path = c["checkpoint_path"]

    def redirected(path, payload):
        return original(checkpoint_path, payload)

    base.core.put_json = redirected
    try:
        return fn(a)
    finally:
        base.core.put_json = original


def _prepare_source(c):
    src = c["source_scope"]
    prepared = c["prepared_source_scope"]
    universe = [str(x).upper() for x in c["universe_override"]]
    work = Path(tempfile.mkdtemp(prefix="us5-source-"))
    mp = work / "manifest.json"
    base.core.download_artifact(PROJECT, src, "manifest.json", mp)
    manifest = json.loads(mp.read_text(encoding="utf-8"))

    copied = {}
    for key, spec in manifest["files"].items():
        local = work / Path(spec["name"]).name
        base.core.download_artifact(PROJECT, src, spec["name"], local)
        if base.core.sha256_file(local).lower() != str(spec["sha256"]).lower():
            raise RuntimeError(f"source hash mismatch {key}")
        if key == "profile":
            profile = json.loads(local.read_text(encoding="utf-8"))
            available = {str(x).upper() for x in profile.get("universe", [])}
            missing = [x for x in universe if x not in available]
            if missing:
                raise RuntimeError(f"5m universe not subset of 15m source: {missing}")
            profile["universe"] = universe
            profile["primary_exclude"] = []
            profile["status"] = "PREREGISTERED_5M_PROMOTION_SOURCE"
            profile["selection"] = {
                "source": "15m preregistered symbol-gate survivors",
                "eligible_symbols": universe,
                "posthoc_additions": "NONE"
            }
            wj(local, profile)
        base.core.upload_artifact(
            PROJECT,
            prepared,
            spec["name"],
            local,
            "application/json; charset=utf-8" if key == "profile" else "text/x-python; charset=utf-8",
        )
        copied[key] = {"name": spec["name"], "sha256": base.core.sha256_file(local)}

    out_manifest = dict(manifest)
    out_manifest["scope"] = prepared
    out_manifest["source_scope"] = src
    out_manifest["files"] = copied
    out_manifest["selection"] = {
        "rule": "EXACT_15M_SYMBOL_GATE_SURVIVORS_ONLY",
        "symbols": universe,
        "count": len(universe),
        "gates_changed": False,
        "strategy_parameters_changed": False,
    }
    wj(mp, out_manifest)
    base.core.upload_artifact(PROJECT, prepared, "manifest.json", mp, "application/json; charset=utf-8")
    return prepared


def _patch_staged_lineage(c):
    scope = c["scope"]
    work = Path(tempfile.mkdtemp(prefix="us5-lineage-"))
    mp = work / "manifest.json"
    base.core.download_artifact(PROJECT, scope, "manifest.json", mp)
    manifest = json.loads(mp.read_text(encoding="utf-8"))
    spec = manifest["files"]["profile"]
    pp = work / "profile.json"
    base.core.download_artifact(PROJECT, scope, spec["name"], pp)
    profile = json.loads(pp.read_text(encoding="utf-8"))
    profile["lineage"] = {
        "source_scope": c["source_scope"],
        "promotion_source_scope": c["prepared_source_scope"],
        "experiment": "US_EQUITIES_5M_PROMOTION_FROM_15M_SURVIVORS",
        "holdout_start": c["holdout_start"],
        "parameter_changes": "TIMEFRAME_ONLY_15M_TO_5M",
        "direction": "LONG_ONLY",
        "session": "PRESERVED_FROM_CANONICAL",
        "universe_rule": "EXACT_2_PREREGISTERED_15M_SURVIVORS",
        "gates": "UNCHANGED_FROM_15M_SYMBOL_PROMOTION_GATES",
    }
    profile["status"] = "PREREGISTERED_5M_PROMOTION_TEST"
    wj(pp, profile)
    base.core.upload_artifact(PROJECT, scope, spec["name"], pp, "application/json; charset=utf-8")
    manifest["files"]["profile"]["sha256"] = base.core.sha256_file(pp)
    manifest["discipline"] = {
        "universe": c["universe_override"],
        "signal_parameters": "UNCHANGED",
        "symbol_gates": c["symbol_gates"],
        "friction_stress_extra_rt_bps": c["stress_extra_rt_bps"],
        "posthoc_changes": "FORBIDDEN",
        "terminal_rule": "5M_IS_FINAL_TIMEFRAME_IN_CURRENT_LONG_ONLY_PROMOTION_LADDER",
    }
    wj(mp, manifest)
    base.core.upload_artifact(PROJECT, scope, "manifest.json", mp, "application/json; charset=utf-8")


def stage(a):
    c = cfg(a.config)
    prepared = _prepare_source(c)
    temp = Path(tempfile.mkdtemp(prefix="us5-config-")) / "config.json"
    cc = dict(c)
    cc["source_scope"] = prepared
    wj(temp, cc)
    aa = argparse.Namespace(config=str(temp))
    rc = _redirect_checkpoint(c, base.stage, aa)
    if rc == 0:
        _patch_staged_lineage(c)
        base.core.put_json(c["checkpoint_path"], {
            "source": base.core.SOURCE,
            "status": "running",
            "position": {
                "phase": "staged",
                "scope": c["scope"],
                "timeframe_minutes": 5,
                "symbols": c["universe_override"],
                "gates": "UNCHANGED_FROM_15M",
            },
            "dropbox_path": c.get("dropbox_checkpoint_path"),
            "last_error": None,
        })
    return rc


def shard(a):
    c = cfg(a.config)
    return _redirect_checkpoint(c, base.shard, a)


def evaluate(a):
    c = cfg(a.config)
    return _redirect_checkpoint(c, base.evaluate, a)


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    for cmd in ("stage", "shard", "evaluate"):
        p = sub.add_parser(cmd)
        p.add_argument("--config", required=True)
        if cmd == "shard":
            p.add_argument("--shard", required=True, type=int)
    a = ap.parse_args()
    return globals()[a.cmd](a)


if __name__ == "__main__":
    raise SystemExit(main())
