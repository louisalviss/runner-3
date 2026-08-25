#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import shutil
import statistics
import subprocess
import tarfile
import tempfile
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import private_backtest_worker_v2 as core

PROJECT = "private-backtest"
SHARDS = 8
NY = ZoneInfo("America/New_York")
ENTRY_KEYS = ["entry_time", "entry_ts", "entry_at", "entry_datetime", "entry_dt", "entry_timestamp", "entry_time_utc", "entry"]
SYMBOL_KEYS = ["symbol", "ticker", "instrument"]


def parse_dt(v):
    s = str(v).strip()
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def iso_z(dt):
    return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def previous_weekday(d):
    d = d - timedelta(days=1)
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d


def latest_completed_60m_boundary(now_utc=None):
    now_utc = now_utc or datetime.now(timezone.utc)
    local = now_utc.astimezone(NY)
    d = local.date()
    if d.weekday() >= 5:
        d = previous_weekday(d + timedelta(days=1))
        end_local = datetime(d.year, d.month, d.day, 16, 0, tzinfo=NY)
        return end_local.astimezone(timezone.utc)
    open_local = datetime(d.year, d.month, d.day, 9, 30, tzinfo=NY)
    close_local = datetime(d.year, d.month, d.day, 16, 0, tzinfo=NY)
    if local >= close_local:
        return close_local.astimezone(timezone.utc)
    if local < open_local + timedelta(hours=1):
        p = previous_weekday(d)
        return datetime(p.year, p.month, p.day, 16, 0, tzinfo=NY).astimezone(timezone.utc)
    elapsed = int((local - open_local).total_seconds() // 60)
    completed = (elapsed // 60) * 60
    boundary = open_local + timedelta(minutes=completed)
    return min(boundary, close_local).astimezone(timezone.utc)


def load_cfg(path):
    cfg = json.loads(Path(path).read_text(encoding="utf-8"))
    required = ["source_scope", "shadow_scope", "cutoff"]
    for k in required:
        if not cfg.get(k):
            raise ValueError(f"missing config field {k}")
    return cfg


def write_json(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def stage(args):
    cfg = load_cfg(args.config)
    source_scope = cfg["source_scope"]
    shadow_scope = cfg["shadow_scope"]
    cutoff = parse_dt(cfg["cutoff"])
    resolved_end = latest_completed_60m_boundary()
    if resolved_end <= cutoff:
        resolved_end = cutoff

    work = Path(tempfile.mkdtemp(prefix="shadow-stage-"))
    source_manifest_p = work / "source-manifest.json"
    core.download_artifact(PROJECT, source_scope, "manifest.json", source_manifest_p)
    source_manifest = json.loads(source_manifest_p.read_text(encoding="utf-8"))

    files = {}
    ctypes = {
        "engine": "text/x-python; charset=utf-8",
        "evaluator": "text/x-python; charset=utf-8",
        "profile": "application/json; charset=utf-8",
        "helper": "text/x-python; charset=utf-8",
    }
    for key, spec in source_manifest["files"].items():
        local = work / Path(spec["name"]).name
        core.download_artifact(PROJECT, source_scope, spec["name"], local)
        if core.sha256_file(local).lower() != str(spec["sha256"]).lower():
            raise RuntimeError(f"source package hash mismatch: {key}")
        if key == "profile":
            profile = json.loads(local.read_text(encoding="utf-8"))
            frozen_end = parse_dt(profile["dates"]["end"])
            if frozen_end != cutoff:
                raise RuntimeError(f"cutoff mismatch profile_end={iso_z(frozen_end)} configured={iso_z(cutoff)}")
            profile["status"] = "FROZEN_SHADOW_CONTINUATION"
            profile["dates"]["end"] = iso_z(resolved_end)
            profile.setdefault("shadow", {})
            profile["shadow"].update({
                "canonical_cutoff": iso_z(cutoff),
                "resolved_end": iso_z(resolved_end),
                "rule_changes": "NONE",
            })
            write_json(local, profile)
        shadow_name = spec["name"]
        core.upload_artifact(PROJECT, shadow_scope, shadow_name, local, ctypes[key])
        files[key] = {"name": shadow_name, "sha256": core.sha256_file(local)}

    manifest = {
        "schema": 1,
        "type": "frozen-shadow-validation",
        "source_scope": source_scope,
        "compute_scope": shadow_scope,
        "canonical_cutoff": iso_z(cutoff),
        "resolved_end": iso_z(resolved_end),
        "created_at": core.now_iso(),
        "files": files,
        "symbol_timeout_seconds": int(cfg.get("symbol_timeout_seconds", source_manifest.get("symbol_timeout_seconds", 5400))),
        "retries": int(cfg.get("retries", 1)),
        "maturity_gate": {
            "min_calendar_days": int(cfg.get("min_calendar_days", 90)),
            "min_closed_primary_trades": int(cfg.get("min_closed_primary_trades", 300)),
            "actual_pf_min": float(cfg.get("actual_pf_min", 1.2)),
            "actual_mean_bps_min": float(cfg.get("actual_mean_bps_min", 10.0)),
        },
    }
    mp = work / "manifest.json"
    write_json(mp, manifest)
    core.upload_artifact(PROJECT, shadow_scope, "manifest.json", mp, "application/json; charset=utf-8")
    core.put_json("/checkpoints/super-rsi/shadow-validation-v1", {
        "source": core.SOURCE,
        "status": "running",
        "position": {
            "phase": "shadow_staged",
            "source_scope": source_scope,
            "compute_scope": shadow_scope,
            "canonical_cutoff": iso_z(cutoff),
            "resolved_end": iso_z(resolved_end),
            "artifact_project": PROJECT,
            "artifact_scope": shadow_scope,
            "artifact_name": "manifest.json",
        },
        "dropbox_path": None,
        "last_error": None,
    })
    print(json.dumps({"stage": "shadow_ready", "scope": shadow_scope, "cutoff": iso_z(cutoff), "end": iso_z(resolved_end)}))
    return 0


def fetch_shadow_package(scope, root):
    mp = root / "manifest.json"
    core.download_artifact(PROJECT, scope, "manifest.json", mp)
    manifest = json.loads(mp.read_text(encoding="utf-8"))
    local = {}
    for key, spec in manifest["files"].items():
        p = root / spec["name"]
        core.download_artifact(PROJECT, scope, spec["name"], p)
        if core.sha256_file(p).lower() != str(spec["sha256"]).lower():
            raise RuntimeError(f"shadow package hash mismatch: {key}")
        local[key] = p
    return manifest, local


def summary_ok(path):
    if not path.exists():
        return False
    try:
        row = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return False
    return str(row.get("status", "")).upper() == "OK"


def shard(args):
    cfg = load_cfg(args.config)
    scope = cfg["shadow_scope"]
    shard_id = int(args.shard)
    work = Path(tempfile.mkdtemp(prefix=f"shadow-{shard_id}-"))
    pkg = work / "pkg"; symbols_root = work / "symbols"; helper = work / "helper"
    pkg.mkdir(); symbols_root.mkdir(); helper.mkdir()
    manifest, local = fetch_shadow_package(scope, pkg)
    shutil.copy2(local["helper"], helper / "exp.py")
    profile = json.loads(local["profile"].read_text(encoding="utf-8"))
    universe = [str(s).upper() for s in profile["universe"]]
    assigned = [s for i,s in enumerate(universe) if i % SHARDS == shard_id]
    timeout_s = int(manifest.get("symbol_timeout_seconds", 5400)); retries = int(manifest.get("retries", 1))
    failed=[]; attempts={}; started=time.time()
    for symbol in assigned:
        last=None; ok=False
        for attempt in range(retries+1):
            attempts[symbol]=attempt+1
            try:
                last = core.run_symbol(local["engine"], local["profile"], helper, symbol, symbols_root, timeout_s)
            except Exception as exc:
                last = {"symbol":symbol,"returncode":99,"stdout":"","stderr":repr(exc)}
            sp = symbols_root / symbol / f"summary-{symbol}.json"
            if last["returncode"] == 0 and summary_ok(sp):
                ok=True; break
        if not ok:
            failed.append(symbol)
            write_json(symbols_root / symbol / "runner-error.json", last or {"symbol":symbol,"stderr":"unknown"})
    archive=work/f"shard-{shard_id:02d}.tar.gz"
    with tarfile.open(archive,"w:gz") as tf:
        tf.add(symbols_root,arcname="symbols")
    status={"shard":shard_id,"assigned_count":len(assigned),"failed_count":len(failed),"failed_symbols":failed,"attempts":attempts,"elapsed_seconds":round(time.time()-started,3),"completed_at":core.now_iso()}
    status_p=work/f"shard-{shard_id:02d}.json"; write_json(status_p,status)
    core.upload_artifact(PROJECT,scope,f"shards/shard-{shard_id:02d}.tar.gz",archive,"application/gzip")
    core.upload_artifact(PROJECT,scope,f"shards/shard-{shard_id:02d}.json",status_p,"application/json; charset=utf-8")
    print(json.dumps({"shard":shard_id,"assigned":len(assigned),"failed":len(failed)}))
    return 0 if not failed else 2


def pf(vals):
    pos=sum(x for x in vals if x>0); neg=-sum(x for x in vals if x<0)
    return pos/neg if neg>0 else None


def pick_key(row, keys):
    for k in keys:
        if k in row and row[k] not in (None,""):
            return k
    return None


def evaluate(args):
    cfg=load_cfg(args.config); scope=cfg["shadow_scope"]
    work=Path(tempfile.mkdtemp(prefix="shadow-eval-")); pkg=work/"pkg"; symbols_root=work/"symbols"; final=work/"final"
    pkg.mkdir(); symbols_root.mkdir(); final.mkdir()
    manifest,local=fetch_shadow_package(scope,pkg)
    failed=[]; missing=[]
    for sid in range(SHARDS):
        ar=work/f"shard-{sid:02d}.tar.gz"; sp=work/f"shard-{sid:02d}.json"
        try:
            core.download_artifact(PROJECT,scope,f"shards/shard-{sid:02d}.tar.gz",ar)
            core.download_artifact(PROJECT,scope,f"shards/shard-{sid:02d}.json",sp)
        except Exception:
            missing.append(sid); continue
        status=json.loads(sp.read_text(encoding="utf-8")); failed.extend(status.get("failed_symbols",[]))
        with tarfile.open(ar,"r:gz") as tf: tf.extractall(work)
    if missing or failed:
        raise RuntimeError(f"shadow infrastructure incomplete missing_shards={missing} failed_symbols={sorted(set(failed))}")
    ev=subprocess.run(["python",str(local["evaluator"]),"--profile",str(local["profile"]),"--input",str(symbols_root),"--out",str(final)],text=True,capture_output=True,timeout=1800)
    if ev.returncode!=0:
        raise RuntimeError("shadow evaluator failed: "+ev.stderr[-4000:])
    for name,ctype in [("report.json","application/json; charset=utf-8"),("SUMMARY.md","text/markdown; charset=utf-8"),("symbol_summary.csv","text/csv; charset=utf-8"),("yearly_summary.csv","text/csv; charset=utf-8"),("trades.jsonl","application/x-ndjson; charset=utf-8")]:
        p=final/name
        if p.exists(): core.upload_artifact(PROJECT,scope,f"final/{name}",p,ctype)

    profile=json.loads(local["profile"].read_text(encoding="utf-8")); primary=set(str(s).upper() for s in profile["universe"])-set(str(s).upper() for s in profile.get("primary_exclude",[]))
    cutoff=parse_dt(manifest["canonical_cutoff"]); end=parse_dt(manifest["resolved_end"])
    rows=[json.loads(x) for x in (final/"trades.jsonl").read_text(encoding="utf-8").splitlines() if x.strip()]
    if not rows: raise RuntimeError("evaluator produced no trades")
    ek=pick_key(rows[0],ENTRY_KEYS); sk=pick_key(rows[0],SYMBOL_KEYS)
    rk="actual_return_bps" if "actual_return_bps" in rows[0] else None
    if not ek or not sk or not rk: raise RuntimeError(f"required trade fields unavailable keys={sorted(rows[0])}")
    fwd=[]
    for r in rows:
        sym=str(r.get(sk,"")).upper()
        if sym not in primary: continue
        entry=parse_dt(r[ek])
        if entry >= cutoff:
            fwd.append((sym,entry,float(r[rk])))
    vals=[x[2] for x in fwd]; bysym=defaultdict(list)
    for sym,_,v in fwd: bysym[sym].append(v)
    positive=sum(1 for v in bysym.values() if sum(v)>0)
    days=max(0.0,(end-cutoff).total_seconds()/86400.0)
    gate=manifest["maturity_gate"]
    mature=days>=gate["min_calendar_days"] and len(vals)>=gate["min_closed_primary_trades"]
    metrics={
        "closed_primary_trades":len(vals),
        "symbols_with_closed_trades":len(bysym),
        "positive_symbols":positive,
        "pf":pf(vals) if vals else None,
        "mean_bps":statistics.fmean(vals) if vals else None,
        "median_bps":statistics.median(vals) if vals else None,
        "win_rate_pct":100.0*sum(v>0 for v in vals)/len(vals) if vals else None,
        "calendar_days":days,
    }
    if mature:
        gate_pass=(metrics["pf"] is not None and metrics["pf"]>=gate["actual_pf_min"] and metrics["mean_bps"]>=gate["actual_mean_bps_min"])
        state="PASS" if gate_pass else "FAIL"
    else:
        gate_pass=None; state="PENDING_SAMPLE"
    result={
        "schema":1,"scope":scope,"source_scope":manifest["source_scope"],"canonical_cutoff":manifest["canonical_cutoff"],"resolved_end":manifest["resolved_end"],
        "discipline":{"rule_changes":"NONE","parameter_tuning":False,"universe_changes":False,"decision_before_maturity":False},
        "maturity_gate":gate,"metrics":metrics,"mature":mature,"forward_gate_pass":gate_pass,"state":state,
    }
    out=work/"shadow-forward-v1.json"; write_json(out,result)
    core.upload_artifact(PROJECT,scope,"research/shadow-forward-v1.json",out,"application/json; charset=utf-8")
    core.put_json("/checkpoints/super-rsi/shadow-validation-v1",{
        "source":core.SOURCE,"status":"success","position":{"phase":"shadow_observation","state":state,"compute_scope":scope,"canonical_cutoff":manifest["canonical_cutoff"],"resolved_end":manifest["resolved_end"],"closed_primary_trades":len(vals),"calendar_days":days,"artifact_project":PROJECT,"artifact_scope":scope,"artifact_name":"research/shadow-forward-v1.json"},"dropbox_path":None,"last_error":None})
    print(json.dumps({"scope":scope,"cutoff":manifest["canonical_cutoff"],"end":manifest["resolved_end"],"state":state,"mature":mature,"metrics":metrics},ensure_ascii=False))
    return 0


def main():
    p=argparse.ArgumentParser(); sub=p.add_subparsers(dest="cmd",required=True)
    a=sub.add_parser("stage"); a.add_argument("--config",required=True)
    a=sub.add_parser("shard"); a.add_argument("--config",required=True); a.add_argument("--shard",required=True,type=int)
    a=sub.add_parser("evaluate"); a.add_argument("--config",required=True)
    args=p.parse_args()
    if args.cmd=="stage": return stage(args)
    if args.cmd=="shard": return shard(args)
    return evaluate(args)

if __name__=="__main__":
    raise SystemExit(main())
