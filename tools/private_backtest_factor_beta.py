#!/usr/bin/env python3
from __future__ import annotations

import argparse
import calendar
import csv
import io
import json
import math
import statistics
import tempfile
import urllib.request
import zipfile
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

import private_backtest_worker_v2 as core

ENTRY_KEYS = ["entry_time", "entry_ts", "entry_at", "entry_datetime", "entry_dt", "entry_timestamp", "entry_time_utc", "entry"]
EXIT_KEYS = ["exit_time", "exit_ts", "exit_at", "exit_datetime", "exit_dt", "exit_timestamp", "exit_time_utc", "exit"]
SYMBOL_KEYS = ["symbol", "ticker", "instrument"]
PRIMARY_SLOTS = 40
SENSITIVITY_SLOTS = [50, 56]
FF5_URL = "https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/F-F_Research_Data_5_Factors_2x3_CSV.zip"
MOM_URL = "https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/F-F_Momentum_Factor_CSV.zip"
IND10_URL = "https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/10_Industry_Portfolios_CSV.zip"


def parse_dt(v):
    s = str(v).strip()
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def pick_key(row, candidates):
    for k in candidates:
        if k in row and row[k] not in (None, ""):
            return k
    return None


def pf(vals):
    pos = sum(x for x in vals if x > 0)
    neg = -sum(x for x in vals if x < 0)
    return pos / neg if neg > 0 else None


def fetch_zip_text(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0", "Accept": "*/*"})
    with urllib.request.urlopen(req, timeout=60) as r:
        data = r.read()
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        names = [n for n in z.namelist() if n.lower().endswith((".csv", ".txt"))]
        if not names:
            names = z.namelist()
        raw = z.read(names[0])
    return raw.decode("utf-8", errors="replace")


def parse_monthly_table(text, required_cols):
    lines = [ln.strip("\ufeff\r\n") for ln in text.splitlines()]
    header_i = None
    header = None
    for i, ln in enumerate(lines):
        cells = [c.strip() for c in ln.split(",")]
        if all(any(req.lower() == c.lower() for c in cells) for req in required_cols):
            header_i = i
            header = cells
            break
    if header_i is None:
        raise RuntimeError(f"monthly table header not found for {required_cols}")
    colmap = {c.lower(): j for j, c in enumerate(header)}
    out = {}
    for ln in lines[header_i + 1:]:
        if not ln.strip():
            if out:
                break
            continue
        cells = [c.strip() for c in ln.split(",")]
        if not cells or not cells[0].isdigit() or len(cells[0]) != 6:
            if out:
                break
            continue
        ym = cells[0]
        row = {}
        good = True
        for req in required_cols:
            j = colmap.get(req.lower())
            if j is None or j >= len(cells):
                good = False
                break
            try:
                val = float(cells[j])
            except ValueError:
                good = False
                break
            if val <= -99.0:
                good = False
                break
            row[req] = val
        if good:
            out[ym] = row
    if len(out) < 12:
        raise RuntimeError(f"too few monthly rows parsed: {len(out)}")
    return out


def simulate(trades, slots):
    # Frozen capacity rule: exits free slots first, then simultaneous entries ticker A->Z.
    by_entry = defaultdict(list)
    for t in trades:
        by_entry[t["entry"]].append(t)
    active = []  # list of accepted live trades; small enough for deterministic scan
    accepted = []
    for ts in sorted(by_entry):
        active = [t for t in active if t["exit"] > ts]
        group = sorted(by_entry[ts], key=lambda x: (x["symbol"], x["idx"]))
        free = max(0, slots - len(active))
        take = group[:free]
        accepted.extend(take)
        active.extend(take)
    return accepted


def month_bounds(ym):
    y = int(ym[:4]); m = int(ym[4:])
    start = datetime(y, m, 1, tzinfo=timezone.utc)
    if m == 12:
        end = datetime(y + 1, 1, 1, tzinfo=timezone.utc)
    else:
        end = datetime(y, m + 1, 1, tzinfo=timezone.utc)
    return start, end


def portfolio_monthly(accepted, slots, months, rf_map):
    pnl = defaultdict(float)
    for t in accepted:
        ym = t["exit"].strftime("%Y%m")
        pnl[ym] += t["bps"] / (100.0 * slots)  # percentage points of initial capital

    exposure = {}
    for ym in months:
        ms, me = month_bounds(ym)
        month_sec = (me - ms).total_seconds()
        weighted = 0.0
        for t in accepted:
            a = max(t["entry"], ms); b = min(t["exit"], me)
            if b > a:
                weighted += (b - a).total_seconds() / slots
        exposure[ym] = weighted / month_sec if month_sec > 0 else 0.0
        if exposure[ym] > 1.0000001:
            raise RuntimeError(f"gross exposure >1 for {slots} slots {ym}: {exposure[ym]}")

    rows = {}
    for ym in months:
        rf = rf_map[ym]
        gross = pnl.get(ym, 0.0)
        # Idle cash earns RF; strategy excess return therefore subtracts RF only on invested capital.
        excess = gross - rf * exposure[ym]
        total = gross + rf * (1.0 - exposure[ym])
        rows[ym] = {
            "gross_trade_pnl_pct": gross,
            "avg_gross_exposure": exposure[ym],
            "rf_pct": rf,
            "total_return_with_idle_cash_rf_pct": total,
            "excess_return_pct": excess,
        }
    return rows


def nw_cov(X, residuals, lag=3):
    n, k = X.shape
    bread = np.linalg.inv(X.T @ X)
    S = np.zeros((k, k))
    for t in range(n):
        xt = X[t:t+1].T
        S += (residuals[t] ** 2) * (xt @ xt.T)
    for L in range(1, min(lag, n - 1) + 1):
        w = 1.0 - L / (lag + 1.0)
        G = np.zeros((k, k))
        for t in range(L, n):
            xt = X[t:t+1].T
            xl = X[t-L:t-L+1].T
            G += residuals[t] * residuals[t-L] * (xt @ xl.T)
        S += w * (G + G.T)
    return bread @ S @ bread


def regress(y, factor_names, factor_series, nw_lag=3):
    yv = np.asarray(y, dtype=float)
    Z = np.column_stack([np.asarray(factor_series[n], dtype=float) for n in factor_names]) if factor_names else np.empty((len(yv), 0))
    X = np.column_stack([np.ones(len(yv)), Z])
    beta = np.linalg.lstsq(X, yv, rcond=None)[0]
    fitted = X @ beta
    resid = yv - fitted
    sse = float(resid @ resid)
    sst = float(((yv - yv.mean()) ** 2).sum())
    r2 = 1.0 - sse / sst if sst > 0 else None
    cov = nw_cov(X, resid, nw_lag)
    se = np.sqrt(np.maximum(0.0, np.diag(cov)))
    tstats = [float(beta[i] / se[i]) if se[i] > 0 else None for i in range(len(beta))]
    names = ["alpha"] + factor_names
    coeffs = {names[i]: float(beta[i]) for i in range(len(names))}
    ts = {names[i]: tstats[i] for i in range(len(names))}
    return {
        "n_months": len(yv),
        "r2": r2,
        "alpha_monthly_pct": float(beta[0]),
        "alpha_annualized_simple_pct": float(beta[0] * 12.0),
        "alpha_nw_tstat": tstats[0],
        "coefficients": coeffs,
        "nw_tstats": ts,
        "residual_std_pct": float(np.std(resid, ddof=max(1, X.shape[1]))),
        "nw_lag": nw_lag,
    }


def residualize(target, factors):
    names = list(factors.keys())
    y = np.asarray(target, dtype=float)
    X = np.column_stack([np.ones(len(y))] + [np.asarray(factors[n], dtype=float) for n in names])
    b = np.linalg.lstsq(X, y, rcond=None)[0]
    return list(y - X @ b), {"alpha": float(b[0]), **{names[i]: float(b[i+1]) for i in range(len(names))}}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", default="private-backtest")
    ap.add_argument("--scope", required=True)
    args = ap.parse_args()

    work = Path(tempfile.mkdtemp(prefix="bt-factor-"))
    tp = work / "trades.jsonl"; rp = work / "report.json"; cp = work / "capacity.json"
    core.download_artifact(args.project, args.scope, "final/trades.jsonl", tp)
    core.download_artifact(args.project, args.scope, "final/report.json", rp)
    core.download_artifact(args.project, args.scope, "research/capital-capacity-v1.json", cp)
    report = json.loads(rp.read_text(encoding="utf-8"))
    capacity = json.loads(cp.read_text(encoding="utf-8"))
    primary = {str(s).upper() for s in report.get("primary_symbols", [])}
    if len(primary) != 63:
        raise RuntimeError(f"primary symbol count mismatch {len(primary)} != 63")

    raw_all = [json.loads(x) for x in tp.read_text(encoding="utf-8").splitlines() if x.strip()]
    sample = raw_all[0]
    ek = pick_key(sample, ENTRY_KEYS); xk = pick_key(sample, EXIT_KEYS); sk = pick_key(sample, SYMBOL_KEYS)
    rk = "actual_return_bps" if "actual_return_bps" in sample else None
    if not all([ek, xk, sk, rk]):
        raise RuntimeError(f"required trade fields missing: {sorted(sample.keys())}")
    raw = [r for r in raw_all if str(r.get(sk, "")).upper() in primary]
    if len(raw) != 4023:
        raise RuntimeError(f"primary trade count mismatch {len(raw)} != 4023")
    trades = []
    for i, r in enumerate(raw):
        trades.append({"idx": i, "symbol": str(r[sk]).upper(), "entry": parse_dt(r[ek]), "exit": parse_dt(r[xk]), "bps": float(r[rk])})
    vals = [t["bps"] for t in trades]
    target_pf = float(report["primary"]["actual"]["PF"]); target_mean = float(report["primary"]["actual"]["mean_bps"])
    baseline = {"trades": len(vals), "pf": pf(vals), "mean_bps": statistics.fmean(vals)}
    if abs(baseline["pf"] - target_pf) > 1e-8 or abs(baseline["mean_bps"] - target_mean) > 1e-6:
        raise RuntimeError(f"canonical baseline mismatch {baseline}")

    cap_by_slots = {int(r["slots"]): r for r in capacity.get("slot_results", [])}
    accepted_by_slots = {}
    for slots in [PRIMARY_SLOTS] + SENSITIVITY_SLOTS:
        accepted = simulate(trades, slots)
        accepted_by_slots[slots] = accepted
        expected = cap_by_slots.get(slots)
        if not expected:
            raise RuntimeError(f"capacity reference missing slots={slots}")
        av = [t["bps"] for t in accepted]
        got = {"accepted_trades": len(av), "pf": pf(av), "mean_bps": statistics.fmean(av)}
        if got["accepted_trades"] != int(expected["accepted_trades"]):
            raise RuntimeError(f"capacity accepted-count parity mismatch slots={slots}: {got} vs {expected}")
        if abs(got["pf"] - float(expected["accepted_pf"])) > 1e-9 or abs(got["mean_bps"] - float(expected["accepted_mean_bps"])) > 1e-8:
            raise RuntimeError(f"capacity return parity mismatch slots={slots}: {got} vs {expected}")

    ff5 = parse_monthly_table(fetch_zip_text(FF5_URL), ["Mkt-RF", "SMB", "HML", "RMW", "CMA", "RF"])
    mom = parse_monthly_table(fetch_zip_text(MOM_URL), ["Mom"])
    ind10 = parse_monthly_table(fetch_zip_text(IND10_URL), ["HiTec"])
    common = sorted(set(ff5) & set(mom) & set(ind10))
    # Frozen research window only; factors currently extend through the official library's latest month.
    common = [m for m in common if "202201" <= m <= "202608"]
    if len(common) < 48:
        raise RuntimeError(f"insufficient common factor months: {len(common)} {common[:2]}..{common[-2:] if common else []}")

    factors = {n: [ff5[m][n] for m in common] for n in ["Mkt-RF", "SMB", "HML", "RMW", "CMA"]}
    factors["Mom"] = [mom[m]["Mom"] for m in common]
    rf_map = {m: ff5[m]["RF"] for m in common}
    hitec_excess = [ind10[m]["HiTec"] - ff5[m]["RF"] for m in common]
    base_factor_names = ["Mkt-RF", "SMB", "HML", "RMW", "CMA", "Mom"]
    hitec_resid, hitec_resid_on = residualize(hitec_excess, {n: factors[n] for n in base_factor_names})
    factors["HiTecResidual"] = hitec_resid

    all_results = {}
    for slots in [PRIMARY_SLOTS] + SENSITIVITY_SLOTS:
        monthly = portfolio_monthly(accepted_by_slots[slots], slots, common, rf_map)
        y = [monthly[m]["excess_return_pct"] for m in common]
        model_capm = regress(y, ["Mkt-RF"], factors)
        model_ff5 = regress(y, ["Mkt-RF", "SMB", "HML", "RMW", "CMA"], factors)
        model_ff5mom = regress(y, base_factor_names, factors)
        model_tech = regress(y, base_factor_names + ["HiTecResidual"], factors)
        all_results[str(slots)] = {
            "accepted_trades": len(accepted_by_slots[slots]),
            "mean_monthly_excess_pct": statistics.fmean(y),
            "annualized_mean_excess_simple_pct": statistics.fmean(y) * 12.0,
            "mean_gross_exposure": statistics.fmean(monthly[m]["avg_gross_exposure"] for m in common),
            "months": {m: monthly[m] for m in common},
            "models": {"CAPM": model_capm, "FF5": model_ff5, "FF5+Mom": model_ff5mom, "FF5+Mom+HiTecResidual": model_tech},
        }

    primary_models = all_results[str(PRIMARY_SLOTS)]["models"]
    tech_model = primary_models["FF5+Mom+HiTecResidual"]
    ffm = primary_models["FF5+Mom"]
    interpretation = {
        "primary_slots": PRIMARY_SLOTS,
        "market_beta": ffm["coefficients"]["Mkt-RF"],
        "market_beta_nw_tstat": ffm["nw_tstats"]["Mkt-RF"],
        "growth_proxy_hml_beta": ffm["coefficients"]["HML"],
        "growth_proxy_note": "negative HML loading indicates growth tilt; positive indicates value tilt",
        "momentum_beta": ffm["coefficients"]["Mom"],
        "technology_specific_beta": tech_model["coefficients"]["HiTecResidual"],
        "technology_specific_nw_tstat": tech_model["nw_tstats"]["HiTecResidual"],
        "ff5mom_alpha_monthly_pct": ffm["alpha_monthly_pct"],
        "ff5mom_alpha_annualized_simple_pct": ffm["alpha_annualized_simple_pct"],
        "ff5mom_alpha_nw_tstat": ffm["alpha_nw_tstat"],
        "ff5mom_tech_alpha_monthly_pct": tech_model["alpha_monthly_pct"],
        "ff5mom_tech_alpha_annualized_simple_pct": tech_model["alpha_annualized_simple_pct"],
        "ff5mom_tech_alpha_nw_tstat": tech_model["alpha_nw_tstat"],
        "ff5mom_r2": ffm["r2"],
        "ff5mom_tech_r2": tech_model["r2"],
    }

    result = {
        "schema": 1,
        "scope": args.scope,
        "universe": "primary_63",
        "preregistered_primary_portfolio": {
            "slots": PRIMARY_SLOTS,
            "rule": "fixed 1/N initial capital; exits first; simultaneous entries ticker ascending A->Z",
            "selection_reason": "40-slot breakpoint was fixed before this factor regression from the completed capital-capacity phase",
            "secondary_diagnostics_only": SENSITIVITY_SLOTS,
        },
        "baseline": baseline,
        "factor_source": {
            "provider": "Kenneth R. French Data Library",
            "ff5_url": FF5_URL,
            "momentum_url": MOM_URL,
            "industry10_url": IND10_URL,
            "common_months": len(common),
            "first_month": common[0],
            "last_month": common[-1],
            "note": "Regression sample truncates automatically to months available simultaneously in FF5, Momentum and 10 Industry datasets.",
        },
        "return_construction": {
            "portfolio_pnl": "realized trade P&L by exit month with fixed 1/N initial-capital position size",
            "idle_cash": "uninvested capital assumed to earn monthly RF",
            "excess_return": "trade P&L minus RF times average gross invested fraction",
            "exposure": "calendar-time average capital tied in accepted positions",
            "limitation": "realized-exit monthly returns, not intratrade mark-to-market portfolio returns; diagnostic factor decomposition only",
        },
        "hitec_residualization": {
            "definition": "10-Industry HiTec excess return residualized on FF5+Mom over the common sample",
            "base_regression_coefficients": hitec_resid_on,
        },
        "portfolio_results": all_results,
        "primary_interpretation": interpretation,
    }
    out = work / "factor-beta-decomposition-v1.json"
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    core.upload_artifact(args.project, args.scope, "research/factor-beta-decomposition-v1.json", out, "application/json; charset=utf-8")
    core.put_json("/checkpoints/super-rsi/factor-beta-decomposition-v1", {
        "source": core.SOURCE,
        "status": "success",
        "position": {
            "phase": "complete", "scope": args.scope, "universe": "primary_63", "primary_slots": PRIMARY_SLOTS,
            "artifact_project": args.project, "artifact_scope": args.scope, "artifact_name": "research/factor-beta-decomposition-v1.json",
        },
        "dropbox_path": None,
        "last_error": None,
    })
    compact = {
        "scope": args.scope,
        "factor_months": {"n": len(common), "first": common[0], "last": common[-1]},
        "primary_40": {
            "accepted_trades": all_results["40"]["accepted_trades"],
            "mean_gross_exposure": all_results["40"]["mean_gross_exposure"],
            "mean_monthly_excess_pct": all_results["40"]["mean_monthly_excess_pct"],
            "models": primary_models,
            "interpretation": interpretation,
        },
        "sensitivity": {
            s: {
                "accepted_trades": all_results[s]["accepted_trades"],
                "mean_gross_exposure": all_results[s]["mean_gross_exposure"],
                "ff5mom_alpha_monthly_pct": all_results[s]["models"]["FF5+Mom"]["alpha_monthly_pct"],
                "ff5mom_alpha_t": all_results[s]["models"]["FF5+Mom"]["alpha_nw_tstat"],
                "market_beta": all_results[s]["models"]["FF5+Mom"]["coefficients"]["Mkt-RF"],
            } for s in ["50", "56"]
        },
    }
    print(json.dumps(compact, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
