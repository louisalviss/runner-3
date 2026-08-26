#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import private_backtest_shadow as base

PROJECT = "private-backtest"
NY = ZoneInfo("America/New_York")


def load_cfg(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(path: Path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def previous_weekday(d):
    d = d - timedelta(days=1)
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d


def latest_completed_15m_boundary(now_utc=None):
    now_utc = now_utc or datetime.now(timezone.utc)
    local = now_utc.astimezone(NY)
    d = local.date()
    if d.weekday() >= 5:
        while d.weekday() >= 5:
            d -= timedelta(days=1)
        return datetime(d.year, d.month, d.day, 16, 0, tzinfo=NY).astimezone(timezone.utc)
    open_local = datetime(d.year, d.month, d.day, 9, 30, tzinfo=NY)
    close_local = datetime(d.year, d.month, d.day, 16, 0, tzinfo=NY)
    if local >= close_local:
        return close_local.astimezone(timezone.utc)
    if local < open_local + timedelta(minutes=15):
        p = previous_weekday(d)
        return datetime(p.year, p.month, p.day, 16, 0, tzinfo=NY).astimezone(timezone.utc)
    elapsed = int((local - open_local).total_seconds() // 60)
    completed = (elapsed // 15) * 15
    boundary = open_local + timedelta(minutes=completed)
    return min(boundary, close_local).astimezone(timezone.utc)


def prepare_source(c):
    source_scope = c["source_scope"]
    prepared_scope = c["prepared_source_scope"]
    wanted = [str(x).upper() for x in c["symbols"]]
    work = Path(tempfile.mkdtemp(prefix="us15-shadow-source-"))
    mp = work / "manifest.json"
    base.core.download_artifact(PROJECT, source_scope, "manifest.json", mp)
    manifest = json.loads(mp.read_text(encoding="utf-8"))
    files = {}
    ctypes = {
        "engine": "text/x-python; charset=utf-8",
        "evaluator": "text/x-python; charset=utf-8",
        "profile": "application/json; charset=utf-8",
        "helper": "text/x-python; charset=utf-8",
    }
    for key, spec in manifest["files"].items():
        local = work / Path(spec["name"]).name
        base.core.download_artifact(PROJECT, source_scope, spec["name"], local)
        if base.core.sha256_file(local).lower() != str(spec["sha256"]).lower():
            raise RuntimeError(f"source hash mismatch: {key}")
        if key == "profile":
            profile = json.loads(local.read_text(encoding="utf-8"))
            available = {str(x).upper() for x in profile.get("universe", [])}
            missing = [x for x in wanted if x not in available]
            if missing:
                raise RuntimeError(f"shadow symbols not in 15m promotion source: {missing}")
            if int(profile.get("timeframe_minutes", 0)) != 15:
                raise RuntimeError(f"source timeframe is not 15m: {profile.get('timeframe_minutes')}")
            profile["universe"] = wanted
            profile["primary_exclude"] = []
            profile["status"] = "FROZEN_15M_SHADOW_SOURCE"
            profile["shadow_selection"] = {
                "rule": c["selection_lineage"],
                "symbols": wanted,
                "count": len(wanted),
                "strategy_parameter_changes": "NONE",
                "posthoc_additions": "NONE",
            }
            write_json(local, profile)
        base.core.upload_artifact(PROJECT, prepared_scope, spec["name"], local, ctypes[key])
        files[key] = {"name": spec["name"], "sha256": base.core.sha256_file(local)}
    out_manifest = dict(manifest)
    out_manifest["scope"] = prepared_scope
    out_manifest["source_scope"] = source_scope
    out_manifest["files"] = files
    out_manifest["selection"] = {
        "lineage": c["selection_lineage"],
        "symbols": wanted,
        "timeframe_minutes": 15,
        "strategy_changes": "NONE",
    }
    write_json(mp, out_manifest)
    base.core.upload_artifact(PROJECT, prepared_scope, "manifest.json", mp, "application/json; charset=utf-8")
    return prepared_scope


def redirect_checkpoint(c, fn, args):
    original = base.core.put_json
    target = c["checkpoint_path"]
    def redirected(path, payload):
        return original(target, payload)
    base.core.put_json = redirected
    try:
        return fn(args)
    finally:
        base.core.put_json = original


def configure_base(c):
    if int(c["timeframe_minutes"]) != 15:
        raise RuntimeError("this runner is locked to 15m")
    if int(c["shards"]) != 2:
        raise RuntimeError("this runner is locked to 2 shards")
    if [str(x).upper() for x in c["symbols"]] != ["AMAT", "MU"]:
        raise RuntimeError("this runner is locked to AMAT,MU")
    base.SHARDS = 2
    base.latest_completed_60m_boundary = latest_completed_15m_boundary


def stage(args):
    c = load_cfg(args.config)
    configure_base(c)
    prepared = prepare_source(c)
    temp = Path(tempfile.mkdtemp(prefix="us15-shadow-cfg-")) / "config.json"
    cc = dict(c)
    cc["source_scope"] = prepared
    write_json(temp, cc)
    aa = argparse.Namespace(config=str(temp))
    rc = redirect_checkpoint(c, base.stage, aa)
    if rc == 0:
        base.core.put_json(c["checkpoint_path"], {
            "source": base.core.SOURCE,
            "status": "running",
            "position": {
                "phase": "shadow_staged",
                "original_source_scope": c["source_scope"],
                "prepared_source_scope": prepared,
                "shadow_scope": c["shadow_scope"],
                "cutoff": c["cutoff"],
                "timeframe_minutes": 15,
                "symbols": c["symbols"],
                "maturity_gate": {
                    "min_calendar_days": c["min_calendar_days"],
                    "min_closed_primary_trades": c["min_closed_primary_trades"],
                    "actual_pf_min": c["actual_pf_min"],
                    "actual_mean_bps_min": c["actual_mean_bps_min"],
                },
            },
            "dropbox_path": None,
            "last_error": None,
        })
    return rc


def shard(args):
    c = load_cfg(args.config)
    configure_base(c)
    return redirect_checkpoint(c, base.shard, args)


def evaluate(args):
    c = load_cfg(args.config)
    configure_base(c)
    return redirect_checkpoint(c, base.evaluate, args)


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    for cmd in ("stage", "shard", "evaluate"):
        p = sub.add_parser(cmd)
        p.add_argument("--config", required=True)
        if cmd == "shard":
            p.add_argument("--shard", required=True, type=int)
    args = ap.parse_args()
    return globals()[args.cmd](args)


if __name__ == "__main__":
    raise SystemExit(main())
