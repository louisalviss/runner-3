#!/usr/bin/env python3
from __future__ import annotations

import argparse
import copy
import csv
import gzip
import importlib.util
import json
import os
import shutil
import tempfile
import time
from collections import defaultdict
from datetime import timedelta
from pathlib import Path

import private_backtest_worker_v2 as core
import private_backtest_us60_survivorship_audit as surv
import private_backtest_us60_pit_portfolio as pit

PROJECT = "private-backtest"
MTM_SCOPE = "bt-super-rsi-us60-pit-proxy-mtm-v1"
SLOTS = 40


def write_json(path: Path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def select_slots(rows, slots: int):
    candidates = sorted(rows, key=lambda r: (pit.ts(r["entry_time"]), str(r.get("symbol", ""))))
    active = []
    accepted = []
    skipped = []
    for r in candidates:
        et = pit.ts(r["entry_time"])
        active = [x for x in active if x[0] > et]
        active.sort(key=lambda x: (x[0], x[1]))
        if len(active) < slots:
            accepted.append(r)
            active.append((pit.ts(r["exit_time"]), str(r.get("symbol", ""))))
        else:
            skipped.append(r)
    return accepted, skipped


def fetch_source_package(c: dict, root: Path):
    return surv.fetch_source_package(c["source_scope"], root)


def stage(args):
    c = surv.load_json(args.config)
    work = Path(tempfile.mkdtemp(prefix="us60-mtm-stage-"))

    _, canonical, controls, successful_controls, missing_shards = pit.load_available_trade_rows(c, work)
    if missing_shards:
        raise RuntimeError(f"cannot stage MTM replay with missing survivorship shards: {missing_shards}")

    hist_rows, hist_meta = surv.fetch_history(c)
    aliases = {surv.norm_symbol(k, {}): surv.norm_symbol(v, {}) for k, v in c.get("ticker_aliases", {}).items()}
    pit_rows, excluded_rows, exclusion_reasons = pit.filter_pit_proxy(canonical + controls, hist_rows, aliases)
    accepted, skipped = select_slots(pit_rows, SLOTS)

    if len(accepted) != 4713:
        raise RuntimeError(f"40-slot accepted trade mismatch: {len(accepted)} != 4713")

    source_root = work / "source"
    source_root.mkdir()
    _, src = fetch_source_package(c, source_root)

    package_root = work / "package"
    package_root.mkdir()
    package_files = {}
    for key in ("engine", "profile", "helper"):
        target = package_root / f"{key}{src[key].suffix}"
        shutil.copy2(src[key], target)
        remote = f"package/{target.name}"
        ct = "application/json; charset=utf-8" if target.suffix == ".json" else "text/x-python; charset=utf-8"
        core.upload_artifact(PROJECT, MTM_SCOPE, remote, target, ct)
        package_files[key] = {"name": remote, "sha256": core.sha256_file(target)}

    accepted_path = package_root / "accepted-40.jsonl"
    with accepted_path.open("w", encoding="utf-8") as f:
        for r in accepted:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    core.upload_artifact(PROJECT, MTM_SCOPE, "package/accepted-40.jsonl", accepted_path, "application/x-ndjson; charset=utf-8")
    package_files["accepted"] = {"name": "package/accepted-40.jsonl", "sha256": core.sha256_file(accepted_path)}

    symbols = sorted({str(r["symbol"]).upper() for r in accepted})
    manifest = {
        "schema": 1,
        "scope": MTM_SCOPE,
        "source_survivorship_scope": c["scope"],
        "source_canonical_scope": c["source_scope"],
        "slots": SLOTS,
        "shards": int(c["shards"]),
        "accepted_trades": len(accepted),
        "skipped_due_to_capacity": len(skipped),
        "pit_proxy_candidates": len(pit_rows),
        "symbols": symbols,
        "symbol_count": len(symbols),
        "successful_control_symbols": len(successful_controls),
        "history_parse": hist_meta,
        "pit_excluded_rows": len(excluded_rows),
        "pit_exclusion_reasons": exclusion_reasons,
        "files": package_files,
        "method": "40_SLOT_PIT_PROXY_BOOK_REPLAY_US_REGULAR_SESSION_BID_M5_OPEN_PLUS_SESSION_CLOSE",
    }
    mp = work / "manifest.json"
    write_json(mp, manifest)
    core.upload_artifact(PROJECT, MTM_SCOPE, "manifest.json", mp, "application/json; charset=utf-8")
    core.put_json("/checkpoints/super-rsi/us60-pit-proxy-mtm-v1", {
        "source": core.SOURCE,
        "status": "running",
        "position": {"phase": "staged", "scope": MTM_SCOPE, "accepted_trades": len(accepted), "symbol_count": len(symbols)},
        "dropbox_path": None,
        "last_error": None,
    })
    print(json.dumps({"stage": "ready", "scope": MTM_SCOPE, "accepted_trades": len(accepted), "symbols": len(symbols)}, indent=2))
    return 0


def download_package(work: Path):
    mp = work / "manifest.json"
    core.download_artifact(PROJECT, MTM_SCOPE, "manifest.json", mp)
    m = json.loads(mp.read_text(encoding="utf-8"))
    local = {}
    for key, spec in m["files"].items():
        p = work / Path(spec["name"]).name
        core.download_artifact(PROJECT, MTM_SCOPE, spec["name"], p)
        if core.sha256_file(p).lower() != str(spec["sha256"]).lower():
            raise RuntimeError(f"MTM package hash mismatch: {key}")
        local[key] = p
    return m, local


def load_engine(engine_path: Path, helper_path: Path, helper_dir: Path):
    helper_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(helper_path, helper_dir / "exp.py")
    os.environ["SUPER_RSI_HELPER_DIR"] = str(helper_dir)
    spec = importlib.util.spec_from_file_location("private_mtm_engine", engine_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot import private engine")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def regular_session_bid(bid, profile):
    import numpy as np
    sess = profile["session"]
    local = bid.index.tz_convert(sess["timezone"])
    mins = local.hour * 60 + local.minute
    mask = (mins >= int(sess["open_minute"])) & (mins < int(sess["close_minute"]))
    return bid.loc[bid.index[np.asarray(mask)]]


def symbol_points(sym: str, trades: list[dict], engine, profile: dict):
    import pandas as pd

    trades = sorted(trades, key=lambda r: pit.ts(r["entry_time"]))
    start = pd.Timestamp(min(pit.ts(r["entry_time"]) for r in trades)) - pd.Timedelta(days=1)
    end = pd.Timestamp(max(pit.ts(r["exit_time"]) for r in trades)) + pd.Timedelta(days=1)
    p = copy.deepcopy(profile)
    p["dates"] = dict(p.get("dates", {}))
    p["dates"]["warmup"] = start.isoformat()
    p["dates"]["end"] = end.isoformat()

    bid, ask, manifest, instrument = engine.load_quotes(sym, p)
    if bid is None or len(bid) == 0:
        raise RuntimeError(f"no BID path for {sym}; instrument={instrument}")
    bid = regular_session_bid(bid, p)
    if len(bid) == 0:
        raise RuntimeError(f"no regular-session BID path for {sym}")

    src_minutes = int(p["source_minutes"])
    sess_close = int(p["session"]["close_minute"])
    local = bid.index.tz_convert(p["session"]["timezone"])
    local_min = local.hour * 60 + local.minute

    rows = []
    missing_entry_marks = 0
    for r in trades:
        entry = pd.Timestamp(pit.ts(r["entry_time"]))
        exit_t = pd.Timestamp(pit.ts(r["exit_time"]))
        entry_price = float(r["actual_entry"])

        seg = bid[(bid.index >= entry) & (bid.index < exit_t)]
        if len(seg) == 0:
            raise RuntimeError(f"empty holding path for {sym} {entry} -> {exit_t}")

        # Synchronized 5m BID-open marks. Entry mark immediately reflects executable BID/ASK spread.
        for t, px in seg["open"].items():
            rows.append((sym, t.isoformat(), (float(px) / entry_price - 1.0) * 10000.0))

        # Add the 16:00 regular-session close when the position remains open overnight.
        seg_local = seg.index.tz_convert(p["session"]["timezone"])
        seg_min = seg_local.hour * 60 + seg_local.minute
        final_mask = seg_min == (sess_close - src_minutes)
        finals = seg.loc[seg.index[final_mask]]
        for t, px in finals["close"].items():
            mark_t = t + pd.Timedelta(minutes=src_minutes)
            if mark_t < exit_t:
                rows.append((sym, mark_t.isoformat(), (float(px) / entry_price - 1.0) * 10000.0))

        # At exit the open-position contribution becomes zero; realized P&L is handled by evaluator.
        rows.append((sym, exit_t.isoformat(), 0.0))

        if entry not in seg.index:
            missing_entry_marks += 1

    rows.sort(key=lambda x: x[1])
    # Last value wins for duplicate symbol/timestamp points.
    dedup = []
    for row in rows:
        if dedup and dedup[-1][1] == row[1]:
            dedup[-1] = row
        else:
            dedup.append(row)
    return dedup, {"instrument": instrument, "points": len(dedup), "missing_entry_marks": missing_entry_marks, "source_manifest_months": len(manifest)}


def shard(args):
    sid = int(args.shard)
    work = Path(tempfile.mkdtemp(prefix=f"us60-mtm-{sid}-"))
    m, local = download_package(work)
    profile = json.loads(local["profile"].read_text(encoding="utf-8"))

    accepted = []
    for line in local["accepted"].read_text(encoding="utf-8").splitlines():
        if line.strip():
            accepted.append(json.loads(line))
    grouped = defaultdict(list)
    for r in accepted:
        grouped[str(r["symbol"]).upper()].append(r)

    symbols = list(m["symbols"])
    assigned = [s for i, s in enumerate(symbols) if i % int(m["shards"]) == sid]
    engine = load_engine(local["engine"], local["helper"], work / "helper")

    out = work / f"mtm-shard-{sid:02d}.csv.gz"
    status = {"shard": sid, "assigned": assigned, "successful": [], "failed": {}, "symbol_meta": {}}
    started = time.time()
    with gzip.open(out, "wt", encoding="utf-8", newline="") as gz:
        w = csv.writer(gz)
        w.writerow(["symbol", "time", "open_return_bps"])
        for sym in assigned:
            last_error = None
            points = None
            meta = None
            for attempt in range(2):
                try:
                    points, meta = symbol_points(sym, grouped[sym], engine, profile)
                    break
                except Exception as e:
                    last_error = repr(e)
                    time.sleep(1.0)
            if points is None:
                status["failed"][sym] = last_error or "unknown"
                continue
            for row in points:
                w.writerow(row)
            status["successful"].append(sym)
            status["symbol_meta"][sym] = meta

    status["elapsed_seconds"] = round(time.time() - started, 3)
    sp = work / f"mtm-shard-{sid:02d}.json"
    write_json(sp, status)
    core.upload_artifact(PROJECT, MTM_SCOPE, f"mtm/shard-{sid:02d}.csv.gz", out, "application/gzip")
    core.upload_artifact(PROJECT, MTM_SCOPE, f"mtm/shard-{sid:02d}.json", sp, "application/json; charset=utf-8")
    print(json.dumps({"shard": sid, "assigned": len(assigned), "successful": len(status["successful"]), "failed": status["failed"], "elapsed_seconds": status["elapsed_seconds"]}, indent=2))
    return 0


def evaluate(args):
    import numpy as np
    import pandas as pd

    work = Path(tempfile.mkdtemp(prefix="us60-mtm-eval-"))
    m, local = download_package(work)
    accepted = [json.loads(x) for x in local["accepted"].read_text(encoding="utf-8").splitlines() if x.strip()]

    frames = []
    failed = {}
    missing_shards = []
    for sid in range(int(m["shards"])):
        csvp = work / f"mtm-shard-{sid:02d}.csv.gz"
        stp = work / f"mtm-shard-{sid:02d}.json"
        try:
            core.download_artifact(PROJECT, MTM_SCOPE, f"mtm/shard-{sid:02d}.csv.gz", csvp)
            core.download_artifact(PROJECT, MTM_SCOPE, f"mtm/shard-{sid:02d}.json", stp)
        except Exception:
            missing_shards.append(sid)
            continue
        st = json.loads(stp.read_text(encoding="utf-8"))
        failed.update(st.get("failed", {}))
        df = pd.read_csv(csvp)
        if len(df):
            df["time"] = pd.to_datetime(df["time"], utc=True)
            frames.append(df)

    if missing_shards or failed:
        result = {
            "schema": 1,
            "scope": MTM_SCOPE,
            "status": "INCOMPLETE_MISSING_PRICE_PATHS",
            "missing_shards": missing_shards,
            "failed_symbols": failed,
        }
        rp = work / "us60-pit-proxy-mtm-v1.json"
        write_json(rp, result)
        core.upload_artifact(PROJECT, MTM_SCOPE, "research/us60-pit-proxy-mtm-v1.json", rp, "application/json; charset=utf-8")
        print(json.dumps(result, indent=2))
        return 2

    df = pd.concat(frames, ignore_index=True)
    # Include every entry/exit event in the grid even if no quote row lands exactly there.
    event_times = pd.to_datetime([r["entry_time"] for r in accepted] + [r["exit_time"] for r in accepted], utc=True)
    grid = pd.DatetimeIndex(sorted(set(df["time"].tolist()) | set(event_times.tolist())))

    open_sum_bps = np.zeros(len(grid), dtype=float)
    for sym, g in df.groupby("symbol", sort=True):
        s = g.sort_values("time").drop_duplicates("time", keep="last").set_index("time")["open_return_bps"].astype(float)
        vals = s.reindex(grid).ffill().fillna(0.0).to_numpy(dtype=float)
        open_sum_bps += vals

    realized_steps = np.zeros(len(grid), dtype=float)
    grid_pos = {t: i for i, t in enumerate(grid)}
    for r in accepted:
        t = pd.Timestamp(r["exit_time"])
        if t.tzinfo is None:
            t = t.tz_localize("UTC")
        else:
            t = t.tz_convert("UTC")
        realized_steps[grid_pos[t]] += (float(r["actual_return_bps"]) / 10000.0) / SLOTS
    realized_cum = np.cumsum(realized_steps)
    open_equity_contrib = (open_sum_bps / 10000.0) / SLOTS
    equity = 1.0 + realized_cum + open_equity_contrib

    running_peak = np.maximum.accumulate(equity)
    dd = equity / running_peak - 1.0
    trough_i = int(np.argmin(dd))
    peak_i = int(np.argmax(equity[:trough_i + 1]))
    recovery_i = None
    for i in range(trough_i + 1, len(equity)):
        if equity[i] >= equity[peak_i]:
            recovery_i = i
            break

    start = pit.ts(surv.load_json(args.config)["report_start"])
    end = pit.ts(surv.load_json(args.config)["end"])
    years = (end - start).total_seconds() / (365.2425 * 24 * 3600)
    final_equity = float(equity[-1])
    cagr = final_equity ** (1.0 / years) - 1.0 if final_equity > 0 and years > 0 else None

    prevp = work / "prior-portfolio.json"
    prior = None
    try:
        core.download_artifact(PROJECT, m["source_survivorship_scope"], "research/us60-pit-proxy-portfolio-v1.json", prevp)
        prior = json.loads(prevp.read_text(encoding="utf-8"))
    except Exception:
        prior = None

    result = {
        "schema": 1,
        "scope": MTM_SCOPE,
        "status": "COMPLETE",
        "source_portfolio_scope": "bt-super-rsi-us60-pit-proxy-portfolio-v1",
        "method": "40-slot fixed-initial-notional PIT proxy portfolio; synchronized regular-session BID M5 opens plus 16:00 session closes; actual ASK entry and BID exit retained",
        "accepted_trades": len(accepted),
        "symbols": int(df["symbol"].nunique()),
        "mtm_points": len(grid),
        "final_realized_equity_multiple": final_equity,
        "simple_return_pct_fixed_initial_notional": (final_equity - 1.0) * 100.0,
        "cagr_equivalent_pct": cagr * 100.0 if cagr is not None else None,
        "mtm_max_drawdown_pct": float(dd[trough_i] * 100.0),
        "drawdown_peak_time": grid[peak_i].isoformat(),
        "drawdown_trough_time": grid[trough_i].isoformat(),
        "drawdown_recovery_time": grid[recovery_i].isoformat() if recovery_i is not None else None,
        "drawdown_duration_peak_to_trough_days": float((grid[trough_i] - grid[peak_i]).total_seconds() / 86400.0),
        "recovery_days_from_trough": float((grid[recovery_i] - grid[trough_i]).total_seconds() / 86400.0) if recovery_i is not None else None,
        "minimum_mtm_equity_multiple": float(np.min(equity)),
        "maximum_mtm_equity_multiple": float(np.max(equity)),
        "calmar_like_cagr_over_abs_mtm_dd": (cagr / abs(float(dd[trough_i]))) if cagr is not None and dd[trough_i] < 0 else None,
        "prior_realized_exit_dd_pct": prior.get("portfolio", {}).get("40", {}).get("realized_exit_equity_max_drawdown_pct") if prior else None,
        "prior_cagr_equivalent_pct": prior.get("portfolio", {}).get("40", {}).get("cagr_equivalent_from_final_realized_equity_pct") if prior else None,
        "limitations": [
            "This remains an S&P500 point-in-time membership proxy, not proof of the original US60 historical selection rule.",
            "24/84 historical-removal controls were unavailable in the survivorship audit, so residual survivorship risk remains.",
            "MTM is sampled at synchronized 5-minute BID opens during the regular US session plus the 16:00 session close; it is not tick-level intrabar MTM.",
            "Fixed slot notional is a fraction of initial capital with no compounding, matching the preregistered capacity model.",
        ],
    }

    rp = work / "us60-pit-proxy-mtm-v1.json"
    write_json(rp, result)
    core.upload_artifact(PROJECT, MTM_SCOPE, "research/us60-pit-proxy-mtm-v1.json", rp, "application/json; charset=utf-8")

    curve = work / "us60-pit-proxy-mtm-equity.csv.gz"
    with gzip.open(curve, "wt", encoding="utf-8", newline="") as gz:
        w = csv.writer(gz)
        w.writerow(["time", "equity", "drawdown_pct", "realized_equity_component", "open_mtm_component"])
        for i, t in enumerate(grid):
            w.writerow([t.isoformat(), float(equity[i]), float(dd[i] * 100.0), float(realized_cum[i]), float(open_equity_contrib[i])])
    core.upload_artifact(PROJECT, MTM_SCOPE, "research/us60-pit-proxy-mtm-equity.csv.gz", curve, "application/gzip")

    core.put_json("/checkpoints/super-rsi/us60-pit-proxy-mtm-v1", {
        "source": core.SOURCE,
        "status": "complete",
        "position": {
            "phase": "evaluated",
            "scope": MTM_SCOPE,
            "accepted_trades": len(accepted),
            "cagr_equivalent_pct": result["cagr_equivalent_pct"],
            "mtm_max_drawdown_pct": result["mtm_max_drawdown_pct"],
            "calmar_like": result["calmar_like_cagr_over_abs_mtm_dd"],
        },
        "dropbox_path": None,
        "last_error": None,
    })
    print(json.dumps(result, indent=2))
    return 0


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("stage")
    p.add_argument("--config", required=True)
    p = sub.add_parser("shard")
    p.add_argument("--config", required=True)
    p.add_argument("--shard", required=True, type=int)
    p = sub.add_parser("evaluate")
    p.add_argument("--config", required=True)
    args = ap.parse_args()
    return globals()[args.cmd](args)


if __name__ == "__main__":
    raise SystemExit(main())
