#!/usr/bin/env python3
from __future__ import annotations

import argparse
import ast
import csv
import io
import json
import shutil
import statistics
import tarfile
import tempfile
import time
import urllib.request
from datetime import date, datetime
from pathlib import Path

import private_backtest_worker_v2 as core

PROJECT = "private-backtest"


def load_json(path: str | Path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(path: Path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def pf(vals):
    gp = sum(x for x in vals if x > 0)
    gl = -sum(x for x in vals if x < 0)
    if gl > 0:
        return gp / gl
    return 999.0 if gp > 0 else None


def metrics(vals):
    return {
        "n": len(vals),
        "pf": pf(vals),
        "mean_bps": statistics.fmean(vals) if vals else None,
        "median_bps": statistics.median(vals) if vals else None,
        "win_rate_pct": (100.0 * sum(x > 0 for x in vals) / len(vals)) if vals else None,
        "sum_bps": sum(vals),
    }


def norm_symbol(s: str, aliases: dict[str, str]) -> str:
    x = str(s).strip().upper().replace(".", "-")
    return aliases.get(x, x)


def parse_date(s: str) -> date:
    x = str(s).strip()
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%Y/%m/%d", "%m-%d-%Y"):
        try:
            return datetime.strptime(x, fmt).date()
        except ValueError:
            pass
    return datetime.fromisoformat(x.replace("Z", "+00:00")).date()


def parse_ticker_cell(raw: str, aliases: dict[str, str]) -> set[str]:
    s = str(raw or "").strip()
    if not s:
        return set()
    vals = None
    if s.startswith("[") and s.endswith("]"):
        try:
            obj = ast.literal_eval(s)
            if isinstance(obj, (list, tuple, set)):
                vals = list(obj)
        except Exception:
            vals = None
    if vals is None:
        vals = [x for x in s.replace(";", ",").split(",") if x.strip()]
    return {norm_symbol(x, aliases) for x in vals if str(x).strip() and str(x).strip().lower() != "nan"}


def fetch_history(cfg: dict):
    url = cfg["historical_index_proxy"]["raw_url"]
    req = urllib.request.Request(url, headers={"User-Agent": "runner3-us60-survivorship-audit/1"})
    with urllib.request.urlopen(req, timeout=120) as r:
        text = r.read().decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        raise RuntimeError("historical constituent CSV has no header")
    fields = [str(x) for x in reader.fieldnames]
    date_key = next((x for x in fields if "date" in x.lower()), fields[0])
    ticker_key = next((x for x in fields if any(k in x.lower() for k in ("ticker", "component", "constituent", "symbol")) and x != date_key), None)
    if ticker_key is None:
        others = [x for x in fields if x != date_key]
        if not others:
            raise RuntimeError(f"cannot identify ticker column from {fields}")
        ticker_key = others[0]
    aliases = {norm_symbol(k, {}): norm_symbol(v, {}) for k, v in cfg.get("ticker_aliases", {}).items()}
    rows = []
    for row in reader:
        try:
            d = parse_date(row.get(date_key, ""))
        except Exception:
            continue
        ticks = parse_ticker_cell(row.get(ticker_key, ""), aliases)
        if ticks:
            rows.append((d, ticks))
    if not rows:
        raise RuntimeError(f"no historical membership rows parsed; fields={fields}")
    rows.sort(key=lambda x: x[0])
    return rows, {"date_key": date_key, "ticker_key": ticker_key, "rows": len(rows), "first": rows[0][0].isoformat(), "last": rows[-1][0].isoformat()}


def snapshot(rows, target: str):
    td = parse_date(target)
    eligible = [x for x in rows if x[0] <= td]
    if not eligible:
        raise RuntimeError(f"no snapshot on/before {target}")
    return eligible[-1]


def provenance_paths(obj, prefix=""):
    needles = ("asof", "as_of", "point_in_time", "point-in-time", "selection", "universe_source", "constituent", "membership", "snapshot")
    out = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            p = f"{prefix}.{k}" if prefix else str(k)
            lk = str(k).lower()
            if any(n in lk for n in needles):
                out.append(p)
            out.extend(provenance_paths(v, p))
    elif isinstance(obj, list):
        for i, v in enumerate(obj[:20]):
            out.extend(provenance_paths(v, f"{prefix}[{i}]"))
    return sorted(set(out))


def fetch_source_package(scope: str, root: Path):
    mp = root / "source-manifest.json"
    core.download_artifact(PROJECT, scope, "manifest.json", mp)
    m = json.loads(mp.read_text(encoding="utf-8"))
    local = {}
    for key in ("engine", "profile", "helper"):
        spec = m["files"][key]
        p = root / Path(spec["name"]).name
        core.download_artifact(PROJECT, scope, spec["name"], p)
        if core.sha256_file(p).lower() != str(spec["sha256"]).lower():
            raise RuntimeError(f"source hash mismatch: {key}")
        local[key] = p
    return m, local


def stage(args):
    c = load_json(args.config)
    work = Path(tempfile.mkdtemp(prefix="us60-surv-stage-"))
    _, src = fetch_source_package(c["source_scope"], work)
    profile = json.loads(src["profile"].read_text(encoding="utf-8"))
    aliases = {norm_symbol(k, {}): norm_symbol(v, {}) for k, v in c.get("ticker_aliases", {}).items()}
    excluded = {norm_symbol(x, aliases) for x in profile.get("primary_exclude", [])}
    canonical = [norm_symbol(x, aliases) for x in profile["universe"] if norm_symbol(x, aliases) not in excluded]
    canonical = sorted(set(canonical))
    if len(canonical) != 63:
        raise RuntimeError(f"canonical primary count mismatch: {len(canonical)} != 63")

    rows, hist_meta = fetch_history(c)
    sd, start_set = snapshot(rows, c["snapshot_start"])
    ed, end_set = snapshot(rows, c["snapshot_end"])
    removed = sorted(start_set - end_set)
    controls = sorted(set(removed) - set(canonical))
    future_membership = sorted((set(canonical) & end_set) - start_set)
    current_overlap = sorted(set(canonical) & end_set)
    start_overlap = sorted(set(canonical) & start_set)

    prov = provenance_paths(profile)
    audit = {
        "schema": 1,
        "scope": c["scope"],
        "source_scope": c["source_scope"],
        "canonical_primary_symbols": canonical,
        "canonical_primary_count": len(canonical),
        "profile_provenance_paths": prov,
        "profile_has_explicit_pit_or_selection_provenance": bool(prov),
        "historical_proxy": c["historical_index_proxy"],
        "history_parse": hist_meta,
        "requested_start": c["snapshot_start"],
        "actual_start_snapshot": sd.isoformat(),
        "requested_end": c["snapshot_end"],
        "actual_end_snapshot": ed.isoformat(),
        "start_members": len(start_set),
        "end_members": len(end_set),
        "canonical_overlap_start": start_overlap,
        "canonical_overlap_start_count": len(start_overlap),
        "canonical_overlap_end": current_overlap,
        "canonical_overlap_end_count": len(current_overlap),
        "canonical_current_sp500_overlap_fraction": len(current_overlap) / len(canonical),
        "canonical_sp500_future_additions_vs_start": future_membership,
        "canonical_sp500_future_additions_count": len(future_membership),
        "removed_from_start_snapshot_by_end": removed,
        "removed_count": len(removed),
        "control_symbols_preregistered": controls,
        "control_count": len(controls),
        "control_definition": c["control_definition"],
        "proxy_note": "S&P500 historical membership is a survivorship stress proxy; it is not asserted to be the original universe selection rule.",
    }
    ap = work / "audit-stage.json"
    write_json(ap, audit)
    core.upload_artifact(PROJECT, c["scope"], "research/survivorship-audit-stage.json", ap, "application/json; charset=utf-8")

    pr = profile
    pr["name"] = "super-rsi-us60-survivorship-control-v1"
    pr["status"] = "PREREGISTERED_SURVIVORSHIP_CONTROL"
    pr["timeframe_minutes"] = int(c["timeframe_minutes"])
    pr["source_minutes"] = int(c["source_minutes"])
    pr["universe"] = controls
    pr["primary_exclude"] = []
    pr["dates"] = {"warmup": c["warmup"], "report_start": c["report_start"], "end": c["end"]}
    pr["lineage"] = {
        "source_scope": c["source_scope"],
        "experiment": "US60_SURVIVORSHIP_INDEX_REMOVAL_CONTROL",
        "parameter_changes": "UNIVERSE_ONLY_TO_PREREGISTERED_HISTORICAL_REMOVAL_CONTROL",
        "strategy_changes": "NONE",
        "direction": "LONG_ONLY",
        "historical_proxy_commit": c["historical_index_proxy"]["commit"],
    }
    pp = work / "profile.json"
    write_json(pp, pr)
    files = {}
    for key, source_path, target, ct in (
        ("engine", src["engine"], "package/engine.py", "text/x-python; charset=utf-8"),
        ("profile", pp, "package/profile.json", "application/json; charset=utf-8"),
        ("helper", src["helper"], "package/exp.py", "text/x-python; charset=utf-8"),
    ):
        core.upload_artifact(PROJECT, c["scope"], target, source_path, ct)
        files[key] = {"name": target, "sha256": core.sha256_file(source_path)}
    manifest = {
        "schema": 1,
        "type": "super-rsi-us60-survivorship-audit",
        "scope": c["scope"],
        "source_scope": c["source_scope"],
        "files": files,
        "shards": int(c["shards"]),
        "retries": int(c["retries"]),
        "symbol_timeout_seconds": int(c["symbol_timeout_seconds"]),
        "control_count": len(controls),
    }
    mp = work / "manifest.json"
    write_json(mp, manifest)
    core.upload_artifact(PROJECT, c["scope"], "manifest.json", mp, "application/json; charset=utf-8")
    core.put_json("/checkpoints/super-rsi/us60-survivorship-audit-v1", {
        "source": core.SOURCE,
        "status": "running",
        "position": {"phase": "staged", "scope": c["scope"], "control_count": len(controls), "profile_provenance_paths": prov},
        "dropbox_path": None,
        "last_error": None,
    })
    print(json.dumps({
        "stage": "ready",
        "scope": c["scope"],
        "canonical": len(canonical),
        "profile_provenance_paths": prov,
        "sp500_overlap_start": len(start_overlap),
        "sp500_overlap_end": len(current_overlap),
        "future_additions": future_membership,
        "control_count": len(controls),
        "control_symbols": controls,
    }, indent=2))
    return 0


def fetch_audit_package(c: dict, root: Path):
    mp = root / "manifest.json"
    core.download_artifact(PROJECT, c["scope"], "manifest.json", mp)
    m = json.loads(mp.read_text(encoding="utf-8"))
    local = {}
    for key, spec in m["files"].items():
        p = root / spec["name"]
        core.download_artifact(PROJECT, c["scope"], spec["name"], p)
        if core.sha256_file(p).lower() != str(spec["sha256"]).lower():
            raise RuntimeError(f"audit package hash mismatch: {key}")
        local[key] = p
    return m, local


def shard(args):
    c = load_json(args.config)
    sid = int(args.shard)
    work = Path(tempfile.mkdtemp(prefix=f"us60-surv-{sid}-"))
    pkg, out, helper = work / "pkg", work / "symbols", work / "helper"
    pkg.mkdir(); out.mkdir(); helper.mkdir()
    m, local = fetch_audit_package(c, pkg)
    shutil.copy2(local["helper"], helper / "exp.py")
    pr = json.loads(local["profile"].read_text(encoding="utf-8"))
    uni = [str(x).upper() for x in pr["universe"]]
    assigned = [s for i, s in enumerate(uni) if i % int(m["shards"]) == sid]
    failed = []
    attempts = {}
    started = time.time()
    for sym in assigned:
        good = False
        last = None
        ntry = 0
        for attempt in range(int(m["retries"]) + 1):
            ntry = attempt + 1
            last = core.run_symbol(local["engine"], local["profile"], helper, sym, out, int(m["symbol_timeout_seconds"]))
            sp = out / sym / f"summary-{sym}.json"
            if last["returncode"] == 0 and sp.exists():
                try:
                    if json.loads(sp.read_text(encoding="utf-8")).get("status") == "OK":
                        good = True
                        break
                except Exception:
                    pass
        attempts[sym] = ntry
        if not good:
            failed.append(sym)
            write_json(out / sym / "runner-error.json", last or {"symbol": sym, "error": "no result"})
    archive = work / f"shard-{sid:02d}.tar.gz"
    status = work / f"shard-{sid:02d}.json"
    with tarfile.open(archive, "w:gz") as tf:
        tf.add(out, arcname="symbols")
    write_json(status, {
        "shard": sid,
        "assigned": assigned,
        "failed_symbols": failed,
        "attempts": attempts,
        "elapsed_seconds": round(time.time() - started, 3),
    })
    core.upload_artifact(PROJECT, c["scope"], f"shards/shard-{sid:02d}.tar.gz", archive, "application/gzip")
    core.upload_artifact(PROJECT, c["scope"], f"shards/shard-{sid:02d}.json", status, "application/json; charset=utf-8")
    print(json.dumps({"shard": sid, "assigned": len(assigned), "failed_count": len(failed), "failed": failed}))
    # Transport/data failures are part of the audit outcome; do not block evaluator.
    return 0


def read_trade_rows(symbol_dir: Path):
    rows = []
    for p in symbol_dir.rglob("*.jsonl"):
        for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
            if not line.strip():
                continue
            try:
                r = json.loads(line)
            except Exception:
                continue
            if r.get("actual_return_bps") is not None:
                rows.append(r)
    return rows


def evaluate(args):
    c = load_json(args.config)
    work = Path(tempfile.mkdtemp(prefix="us60-surv-eval-"))
    symbols_root = work / "symbols"
    symbols_root.mkdir()
    stage_path = work / "stage.json"
    core.download_artifact(PROJECT, c["scope"], "research/survivorship-audit-stage.json", stage_path)
    stage_info = json.loads(stage_path.read_text(encoding="utf-8"))
    controls = stage_info["control_symbols_preregistered"]

    failed = []
    missing_shards = []
    for sid in range(int(c["shards"])):
        ar = work / f"shard-{sid:02d}.tar.gz"
        st = work / f"shard-{sid:02d}.json"
        try:
            core.download_artifact(PROJECT, c["scope"], f"shards/shard-{sid:02d}.tar.gz", ar)
            core.download_artifact(PROJECT, c["scope"], f"shards/shard-{sid:02d}.json", st)
        except Exception:
            missing_shards.append(sid)
            continue
        failed.extend(json.loads(st.read_text(encoding="utf-8")).get("failed_symbols", []))
        with tarfile.open(ar, "r:gz") as tf:
            tf.extractall(work)

    successful = []
    by_symbol = {}
    all_control_vals = []
    for sym in controls:
        sd = symbols_root / sym
        sp = sd / f"summary-{sym}.json"
        if not sp.exists():
            continue
        try:
            sm = json.loads(sp.read_text(encoding="utf-8"))
        except Exception:
            continue
        if sm.get("status") != "OK":
            continue
        trades = read_trade_rows(sd)
        vals = [float(r["actual_return_bps"]) for r in trades if r.get("actual_return_bps") is not None]
        successful.append(sym)
        by_symbol[sym] = {"trades": len(vals), "metrics": metrics(vals)}
        all_control_vals.extend(vals)

    canon_report_p = work / "canonical-report.json"
    canon_trades_p = work / "canonical-trades.jsonl"
    core.download_artifact(PROJECT, c["source_scope"], "final/report.json", canon_report_p)
    core.download_artifact(PROJECT, c["source_scope"], "final/trades.jsonl", canon_trades_p)
    canon_report = json.loads(canon_report_p.read_text(encoding="utf-8"))
    primary_symbols = {str(x).upper() for x in canon_report.get("primary_symbols", [])}
    canon_vals = []
    for line in canon_trades_p.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        if str(r.get("symbol", "")).upper() in primary_symbols and r.get("actual_return_bps") is not None:
            canon_vals.append(float(r["actual_return_bps"]))
    if len(canon_vals) != 4023:
        raise RuntimeError(f"canonical trade mismatch in audit: {len(canon_vals)} != 4023")

    control_m = metrics(all_control_vals)
    canon_m = metrics(canon_vals)
    combined_m = metrics(canon_vals + all_control_vals)
    coverage = len(successful) / len(controls) if controls else 0.0
    pf_drop = (canon_m["pf"] - combined_m["pf"]) if canon_m["pf"] is not None and combined_m["pf"] is not None else None
    th = c["diagnostic_thresholds"]

    if missing_shards:
        risk = "UNRESOLVED_MISSING_SHARDS"
    elif coverage < float(th["control_data_coverage_min_fraction"]):
        risk = "UNRESOLVED_DATA_SOURCE_SURVIVORSHIP"
    elif control_m["pf"] is not None and control_m["pf"] <= float(th["high_risk_control_pf_max"]) and pf_drop is not None and pf_drop >= float(th["high_risk_combined_pf_drop_min"]):
        risk = "HIGH_PROXY_SURVIVORSHIP_RISK"
    elif (control_m["pf"] is not None and control_m["pf"] <= float(th["moderate_risk_control_pf_max"])) or (combined_m["pf"] is not None and combined_m["pf"] < float(th["moderate_risk_combined_pf_min"])):
        risk = "MODERATE_PROXY_SURVIVORSHIP_RISK"
    else:
        risk = "LOWER_PROXY_RISK_RESIDUAL_TRUE_DELISTED_RISK_REMAINS"

    profile_provenance = bool(stage_info.get("profile_has_explicit_pit_or_selection_provenance"))
    overlap_fraction = float(stage_info.get("canonical_current_sp500_overlap_fraction", 0.0))
    result = {
        "schema": 1,
        "scope": c["scope"],
        "source_scope": c["source_scope"],
        "verdict": risk,
        "canonical_profile_has_explicit_pit_or_selection_provenance": profile_provenance,
        "profile_provenance_paths": stage_info.get("profile_provenance_paths", []),
        "sp500_proxy_applicability": {
            "canonical_current_overlap_fraction": overlap_fraction,
            "threshold": th["sp500_proxy_applicability_min_current_overlap_fraction"],
            "strong_enough_for_proxy": overlap_fraction >= float(th["sp500_proxy_applicability_min_current_overlap_fraction"]),
        },
        "membership_lookahead": {
            "canonical_sp500_future_additions_vs_start": stage_info.get("canonical_sp500_future_additions_vs_start", []),
            "count": stage_info.get("canonical_sp500_future_additions_count", 0),
        },
        "control": {
            "definition": c["control_definition"],
            "symbols_preregistered": controls,
            "count": len(controls),
            "successful_symbols": sorted(successful),
            "successful_count": len(successful),
            "failed_or_unavailable_symbols": sorted(set(controls) - set(successful)),
            "coverage_fraction": coverage,
            "metrics_conditioned_on_data_availability": control_m,
            "by_symbol": by_symbol,
        },
        "canonical": canon_m,
        "combined_canonical_plus_available_control": combined_m,
        "canonical_to_combined_pf_drop": pf_drop,
        "missing_shards": missing_shards,
        "transport_failed_symbols_reported_by_shards": sorted(set(failed)),
        "interpretation": {
            "sp500_is_proxy_only": True,
            "transport_failures_are_not_strategy_losses": True,
            "available_control_metrics_are_conditioned_on_data_availability": True,
            "true_delisted_names_without_historical_market_data_leave_residual_risk": True,
            "no_strategy_or_gate_changes": True,
        },
    }
    rp = work / "survivorship-audit-v1.json"
    write_json(rp, result)
    core.upload_artifact(PROJECT, c["scope"], "research/survivorship-audit-v1.json", rp, "application/json; charset=utf-8")
    core.put_json("/checkpoints/super-rsi/us60-survivorship-audit-v1", {
        "source": core.SOURCE,
        "status": "complete",
        "position": {
            "phase": "evaluated",
            "scope": c["scope"],
            "verdict": risk,
            "control_count": len(controls),
            "successful_control_count": len(successful),
            "control_coverage_fraction": coverage,
            "canonical_pf": canon_m["pf"],
            "control_pf_conditioned_on_data": control_m["pf"],
            "combined_pf": combined_m["pf"],
        },
        "dropbox_path": None,
        "last_error": None,
    })
    print(json.dumps({
        "scope": c["scope"],
        "verdict": risk,
        "profile_has_pit_provenance": profile_provenance,
        "sp500_proxy_overlap_fraction": overlap_fraction,
        "future_additions": stage_info.get("canonical_sp500_future_additions_vs_start", []),
        "control_count": len(controls),
        "successful_control_count": len(successful),
        "coverage_fraction": coverage,
        "failed_or_unavailable": sorted(set(controls) - set(successful)),
        "canonical": canon_m,
        "control_available": control_m,
        "combined": combined_m,
        "canonical_to_combined_pf_drop": pf_drop,
    }, indent=2))
    return 0


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
