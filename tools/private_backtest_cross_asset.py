#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shutil
import statistics
import subprocess
import tarfile
import tempfile
import time
from pathlib import Path

import private_backtest_worker_v2 as core

PROJECT = "private-backtest"


def write_json(path: Path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def load_cfg(path):
    cfg = json.loads(Path(path).read_text(encoding="utf-8"))
    if not cfg.get("source_scope") or not cfg.get("families"):
        raise ValueError("config requires source_scope and families")
    return cfg


def family_cfg(cfg, family):
    if family not in cfg["families"]:
        raise ValueError(f"unknown family {family}")
    return cfg["families"][family]


def pf_bps(vals):
    gp = sum(v for v in vals if v > 0)
    gl = -sum(v for v in vals if v < 0)
    return gp / gl if gl > 0 else (999.0 if gp > 0 else None)


def metrics_bps(vals):
    return {
        "n": len(vals),
        "pf": pf_bps(vals),
        "mean_bps": statistics.fmean(vals) if vals else None,
        "median_bps": statistics.median(vals) if vals else None,
        "win_rate_pct": 100.0 * sum(v > 0 for v in vals) / len(vals) if vals else None,
    }


def helper_text(mapping):
    mapping_literal = repr({str(k).upper(): str(v) for k, v in mapping.items()})
    return f'''from __future__ import annotations
import pandas as pd
import dukascopy_python as duka
INSTRUMENTS = {mapping_literal}

def resolve_symbol(symbol):
    return INSTRUMENTS.get(str(symbol).strip().upper())

def pick_const(names):
    for name in names:
        if hasattr(duka, name):
            return getattr(duka, name)
    raise AttributeError(f"missing Dukascopy constant: {{tuple(names)}}")

def month_chunks(start, end):
    cur = pd.Timestamp(start)
    stop = pd.Timestamp(end)
    cur = cur.tz_localize("UTC") if cur.tzinfo is None else cur.tz_convert("UTC")
    stop = stop.tz_localize("UTC") if stop.tzinfo is None else stop.tz_convert("UTC")
    while cur < stop:
        if cur.month == 12:
            nxt = pd.Timestamp(year=cur.year+1, month=1, day=1, tz="UTC")
        else:
            nxt = pd.Timestamp(year=cur.year, month=cur.month+1, day=1, tz="UTC")
        yield cur, min(nxt, stop)
        cur = nxt

def _naive_utc(v):
    t = pd.Timestamp(v)
    t = t.tz_localize("UTC") if t.tzinfo is None else t.tz_convert("UTC")
    return t.to_pydatetime().replace(tzinfo=None)

def fetch_side(instrument, offer_side, start, end, source_minutes):
    interval_name = f"INTERVAL_MIN_{{int(source_minutes)}}"
    if not hasattr(duka, interval_name):
        raise ValueError(f"unsupported interval {{interval_name}}")
    df = duka.fetch(instrument=instrument, interval=getattr(duka, interval_name), offer_side=offer_side,
                    start=_naive_utc(start), end=_naive_utc(end), max_retries=5)
    if df is None or len(df) == 0:
        return pd.DataFrame(columns=["open","high","low","close"])
    out = df.copy(); out.columns = [str(c).lower() for c in out.columns]
    need = ["open","high","low","close"]
    miss = [c for c in need if c not in out.columns]
    if miss: raise ValueError(f"missing OHLC {{miss}}")
    out.index = pd.to_datetime(out.index, utc=True)
    return out.sort_index()[~out.sort_index().index.duplicated(keep="last")][need].astype(float)
'''


def stage(args):
    cfg = load_cfg(args.config); fam = family_cfg(cfg, args.family)
    source_scope = cfg["source_scope"]; scope = fam["scope"]
    work = Path(tempfile.mkdtemp(prefix=f"xa-stage-{args.family}-"))
    smp = work / "source-manifest.json"
    core.download_artifact(PROJECT, source_scope, "manifest.json", smp)
    source_manifest = json.loads(smp.read_text(encoding="utf-8"))

    files = {}
    for key in ("engine", "evaluator", "profile"):
        spec = source_manifest["files"][key]
        p = work / Path(spec["name"]).name
        core.download_artifact(PROJECT, source_scope, spec["name"], p)
        if core.sha256_file(p).lower() != str(spec["sha256"]).lower():
            raise RuntimeError(f"source hash mismatch {key}")
        if key == "profile":
            profile = json.loads(p.read_text(encoding="utf-8"))
            profile["name"] = fam["profile_name"]
            profile["status"] = "PREREGISTERED_CROSS_ASSET_SCREEN"
            profile["asset_class"] = fam["asset_class"]
            profile["timeframe_minutes"] = int(cfg.get("timeframe_minutes", 30))
            profile["source_minutes"] = int(cfg.get("source_minutes", 5))
            profile["universe"] = list(fam["instruments"].keys())
            profile["primary_exclude"] = []
            profile["session"] = {"timezone":"UTC","open_minute":0,"close_minute":1440,"allow_final_partial_bar":False}
            profile["dates"] = {
                "warmup": cfg["warmup"], "report_start": cfg["report_start"], "end": cfg["end"]
            }
            profile["pre_cutoff_year"] = 2024
            profile["recent_years"] = [2024, 2025, 2026]
            profile["gates"] = {
                "coverage_min": len(profile["universe"]),
                "trades_min": int(cfg["gates"]["trades_min"]),
                "actual_pf_min": float(cfg["gates"]["actual_pf_min"]),
                "actual_mean_bps_min": float(cfg["gates"]["actual_mean_bps_min"]),
                "mid_pf_min": float(cfg["gates"].get("mid_pf_min", 1.20)),
                "positive_symbol_fraction_min": float(cfg["gates"]["positive_symbol_fraction_min"]),
                "median_symbol_pf_min": float(cfg["gates"]["median_symbol_pf_min"]),
                "pre2026_actual_pf_min": float(cfg["gates"].get("pre_holdout_pf_min", 1.05)),
                "recent_year_pf_threshold": float(cfg["gates"].get("recent_year_pf_threshold", 1.0)),
                "recent_years_min": int(cfg["gates"].get("recent_years_min", 2)),
            }
            profile["lineage"] = {
                "source_scope": source_scope,
                "research_branch": "cross-asset-lower-timeframe",
                "family": args.family,
                "holdout_start": cfg["holdout_start"],
                "parameter_changes": "NONE",
                "direction": "LONG_ONLY",
            }
            write_json(p, profile)
        target = f"package/{key}.py" if key in ("engine", "evaluator") else "package/profile.json"
        ctype = "text/x-python; charset=utf-8" if key in ("engine", "evaluator") else "application/json; charset=utf-8"
        core.upload_artifact(PROJECT, scope, target, p, ctype)
        files[key] = {"name": target, "sha256": core.sha256_file(p)}

    hp = work / "exp.py"; hp.write_text(helper_text(fam["instruments"]), encoding="utf-8")
    core.upload_artifact(PROJECT, scope, "package/exp.py", hp, "text/x-python; charset=utf-8")
    files["helper"] = {"name":"package/exp.py","sha256":core.sha256_file(hp)}

    manifest = {
        "schema":1,"type":"super-rsi-cross-asset-30m","family":args.family,"source_scope":source_scope,
        "compute_scope":scope,"created_at":core.now_iso(),"files":files,
        "shards":int(cfg.get("shards",4)),"retries":int(cfg.get("retries",1)),
        "symbol_timeout_seconds":int(cfg.get("symbol_timeout_seconds",5400)),
        "holdout_start":cfg["holdout_start"],"gates":cfg["gates"],
        "carry_model":fam.get("carry_model","none"),"instrument_type":fam.get("instrument_type"),
        "data_source":"Dukascopy paired M5 BID/ASK"
    }
    mp = work / "manifest.json"; write_json(mp, manifest)
    core.upload_artifact(PROJECT, scope, "manifest.json", mp, "application/json; charset=utf-8")
    core.put_json(f"/checkpoints/super-rsi/cross-asset-30m-{args.family}-v1", {
        "source":core.SOURCE,"status":"running","position":{"phase":"staged","scope":scope,"family":args.family,
        "artifact_project":PROJECT,"artifact_scope":scope,"artifact_name":"manifest.json"},"dropbox_path":None,"last_error":None})
    print(json.dumps({"stage":"ready","family":args.family,"scope":scope,"symbols":len(fam["instruments"])}))
    return 0


def fetch_package(scope, root):
    mp = root / "manifest.json"; core.download_artifact(PROJECT, scope, "manifest.json", mp)
    m = json.loads(mp.read_text(encoding="utf-8")); local={}
    for key,spec in m["files"].items():
        p = root / spec["name"]; core.download_artifact(PROJECT, scope, spec["name"], p)
        if core.sha256_file(p).lower() != str(spec["sha256"]).lower(): raise RuntimeError(f"package hash mismatch {key}")
        local[key]=p
    return m, local


def summary_ok(p):
    try: return p.exists() and json.loads(p.read_text(encoding="utf-8")).get("status") == "OK"
    except Exception: return False


def shard(args):
    cfg=load_cfg(args.config); fam=family_cfg(cfg,args.family); scope=fam["scope"]; sid=int(args.shard)
    work=Path(tempfile.mkdtemp(prefix=f"xa-{args.family}-{sid}-")); pkg=work/"pkg"; out=work/"symbols"; helper=work/"helper"
    pkg.mkdir(); out.mkdir(); helper.mkdir(); manifest,local=fetch_package(scope,pkg)
    shutil.copy2(local["helper"],helper/"exp.py")
    profile=json.loads(local["profile"].read_text(encoding="utf-8")); universe=[str(s).upper() for s in profile["universe"]]
    assigned=[s for i,s in enumerate(universe) if i % int(manifest["shards"]) == sid]
    failed=[]; started=time.time()
    for symbol in assigned:
        ok=False; last=None
        for _ in range(int(manifest["retries"])+1):
            last=core.run_symbol(local["engine"],local["profile"],helper,symbol,out,int(manifest["symbol_timeout_seconds"]))
            if last["returncode"]==0 and summary_ok(out/symbol/f"summary-{symbol}.json"):
                ok=True; break
        if not ok:
            failed.append(symbol); write_json(out/symbol/"runner-error.json",last or {"symbol":symbol})
    ar=work/f"shard-{sid:02d}.tar.gz"
    with tarfile.open(ar,"w:gz") as tf: tf.add(out,arcname="symbols")
    sp=work/f"shard-{sid:02d}.json"; write_json(sp,{"shard":sid,"assigned":assigned,"failed_symbols":failed,"elapsed_seconds":round(time.time()-started,3)})
    core.upload_artifact(PROJECT,scope,f"shards/shard-{sid:02d}.tar.gz",ar,"application/gzip")
    core.upload_artifact(PROJECT,scope,f"shards/shard-{sid:02d}.json",sp,"application/json; charset=utf-8")
    print(json.dumps({"family":args.family,"shard":sid,"assigned":len(assigned),"failed":failed}))
    return 0 if not failed else 2


def evaluate(args):
    cfg=load_cfg(args.config); fam=family_cfg(cfg,args.family); scope=fam["scope"]
    work=Path(tempfile.mkdtemp(prefix=f"xa-eval-{args.family}-")); pkg=work/"pkg"; symbols=work/"symbols"; final=work/"final"
    pkg.mkdir(); symbols.mkdir(); final.mkdir(); manifest,local=fetch_package(scope,pkg)
    failed=[]; missing=[]
    for sid in range(int(manifest["shards"])):
        ar=work/f"shard-{sid:02d}.tar.gz"; sp=work/f"shard-{sid:02d}.json"
        try:
            core.download_artifact(PROJECT,scope,f"shards/shard-{sid:02d}.tar.gz",ar); core.download_artifact(PROJECT,scope,f"shards/shard-{sid:02d}.json",sp)
        except Exception:
            missing.append(sid); continue
        failed.extend(json.loads(sp.read_text(encoding="utf-8")).get("failed_symbols",[]))
        with tarfile.open(ar,"r:gz") as tf: tf.extractall(work)
    if missing or failed: raise RuntimeError(f"incomplete family={args.family} missing={missing} failed={sorted(set(failed))}")
    ev=subprocess.run(["python",str(local["evaluator"]),"--profile",str(local["profile"]),"--input",str(symbols),"--out",str(final)],text=True,capture_output=True,timeout=1800)
    if ev.returncode!=0: raise RuntimeError("evaluator failed: "+ev.stderr[-4000:])
    report=json.loads((final/"report.json").read_text(encoding="utf-8"))
    rows=[json.loads(x) for x in (final/"trades.jsonl").read_text(encoding="utf-8").splitlines() if x.strip()]
    holdout_start=cfg["holdout_start"]
    vals=[float(r["actual_return_bps"]) for r in rows]
    hold=[float(r["actual_return_bps"]) for r in rows if str(r.get("entry_time","")) >= holdout_start]
    stressed=[v-float(cfg["gates"]["stress_extra_rt_bps"]) for v in vals]
    base=metrics_bps(vals); ho=metrics_bps(hold); stress=metrics_bps(stressed)
    p=report["primary"]
    gates={
        "coverage_all": int(p["ok_symbols"])==int(p["expected_symbols"]),
        "trades": base["n"]>=int(cfg["gates"]["trades_min"]),
        "actual_pf": base["pf"] is not None and base["pf"]>=float(cfg["gates"]["actual_pf_min"]),
        "actual_mean": base["mean_bps"] is not None and base["mean_bps"]>=float(cfg["gates"]["actual_mean_bps_min"]),
        "holdout_pf": ho["pf"] is not None and ho["pf"]>=float(cfg["gates"]["holdout_pf_min"]),
        "holdout_mean_positive": ho["mean_bps"] is not None and ho["mean_bps"]>0,
        "positive_symbol_fraction": float(p["positive_symbol_fraction"])>=float(cfg["gates"]["positive_symbol_fraction_min"]),
        "median_symbol_pf": p["median_symbol_PF_ge5"] is not None and float(p["median_symbol_PF_ge5"])>=float(cfg["gates"]["median_symbol_pf_min"]),
        "stress_pf": stress["pf"] is not None and stress["pf"]>=float(cfg["gates"]["stress_pf_min"]),
        "stress_mean_positive": stress["mean_bps"] is not None and stress["mean_bps"]>0,
    }
    technical_pass=all(gates.values())
    carry_required=str(manifest.get("carry_model","none"))!="none"
    state="TECHNICAL_PASS_CARRY_PENDING" if technical_pass and carry_required else ("PASS" if technical_pass else "FAIL")
    result={"schema":1,"family":args.family,"scope":scope,"profile":report["profile"],"data_source":manifest["data_source"],
            "instrument_type":manifest.get("instrument_type"),"carry_model":manifest.get("carry_model"),"base":base,"holdout":ho,
            "stress_extra_rt_bps":float(cfg["gates"]["stress_extra_rt_bps"]),"stress":stress,
            "positive_symbol_fraction":p["positive_symbol_fraction"],"median_symbol_pf":p["median_symbol_PF_ge5"],
            "gate_flags":gates,"technical_pass":technical_pass,"promotion_state":state,
            "discipline":{"parameter_changes":"NONE","direction":"LONG_ONLY","holdout_start":holdout_start}}
    rp=work/"transferability-30m-v1.json"; write_json(rp,result)
    core.upload_artifact(PROJECT,scope,"research/transferability-30m-v1.json",rp,"application/json; charset=utf-8")
    for name,ctype in [("report.json","application/json; charset=utf-8"),("SUMMARY.md","text/markdown; charset=utf-8"),("symbol_summary.csv","text/csv; charset=utf-8"),("yearly_summary.csv","text/csv; charset=utf-8"),("trades.jsonl","application/x-ndjson; charset=utf-8")]:
        pth=final/name
        if pth.exists(): core.upload_artifact(PROJECT,scope,f"final/{name}",pth,ctype)
    core.put_json(f"/checkpoints/super-rsi/cross-asset-30m-{args.family}-v1", {"source":core.SOURCE,"status":"complete","position":{"phase":"evaluated","scope":scope,"promotion_state":state,"technical_pass":technical_pass,"artifact_project":PROJECT,"artifact_scope":scope,"artifact_name":"research/transferability-30m-v1.json"},"dropbox_path":None,"last_error":None})
    print(json.dumps(result,indent=2))
    return 0


def main():
    ap=argparse.ArgumentParser(); sub=ap.add_subparsers(dest="cmd",required=True)
    for cmd in ("stage","shard","evaluate"):
        p=sub.add_parser(cmd); p.add_argument("--config",required=True); p.add_argument("--family",required=True)
        if cmd=="shard": p.add_argument("--shard",required=True,type=int)
    a=ap.parse_args(); return globals()[a.cmd](a)

if __name__=="__main__":
    raise SystemExit(main())
