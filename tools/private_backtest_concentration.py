#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import statistics
import tempfile
import urllib.request
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

import private_backtest_worker_v2 as core

ENTRY_KEYS = ["entry_time", "entry_ts", "entry_at", "entry_datetime", "entry_dt", "entry_timestamp", "entry_time_utc", "entry"]
EXIT_KEYS = ["exit_time", "exit_ts", "exit_at", "exit_datetime", "exit_dt", "exit_timestamp", "exit_time_utc", "exit"]
SYMBOL_KEYS = ["symbol", "ticker", "instrument"]


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
    return (pos / neg) if neg > 0 else None


def pearson(a, b):
    if len(a) != len(b) or len(a) < 2:
        return None
    ma = statistics.fmean(a); mb = statistics.fmean(b)
    da = [x-ma for x in a]; db = [x-mb for x in b]
    va = sum(x*x for x in da); vb = sum(x*x for x in db)
    if va <= 0 or vb <= 0:
        return None
    return sum(x*y for x,y in zip(da, db)) / math.sqrt(va*vb)


def quantile(vals, q):
    if not vals:
        return None
    xs = sorted(vals)
    if len(xs) == 1:
        return xs[0]
    p = (len(xs)-1)*q
    lo = int(math.floor(p)); hi = int(math.ceil(p))
    if lo == hi:
        return xs[lo]
    w = p-lo
    return xs[lo]*(1-w) + xs[hi]*w


def normalize_symbol(s):
    return str(s).strip().upper().replace("/", ".").replace("-", ".")


def fetch_sector_map(expected):
    url = "https://api.nasdaq.com/api/screener/stocks?tableonly=true&limit=10000&offset=0&download=true"
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0",
        "Accept": "application/json,text/plain,*/*",
        "Referer": "https://www.nasdaq.com/market-activity/stocks/screener",
    })
    with urllib.request.urlopen(req, timeout=45) as r:
        payload = json.load(r)
    rows = (((payload or {}).get("data") or {}).get("rows") or [])
    out = {}
    for row in rows:
        sym = normalize_symbol(row.get("symbol", ""))
        if not sym:
            continue
        sector = str(row.get("sector") or "").strip()
        industry = str(row.get("industry") or "").strip()
        if sector:
            out[sym] = {"sector": sector, "industry": industry}
    # Known ticker aliases / punctuation normalization only; not sector guesses.
    aliases = {"BRK.B": ["BRK.B", "BRK/B", "BRK-B"], "BF.B": ["BF.B", "BF/B", "BF-B"]}
    for canon, variants in aliases.items():
        if canon in expected and canon not in out:
            for v in variants:
                nv = normalize_symbol(v)
                if nv in out:
                    out[canon] = out[nv]
                    break
    missing = sorted(s for s in expected if normalize_symbol(s) not in out)
    if missing:
        raise RuntimeError(f"sector mapping incomplete: {len(missing)}/{len(expected)} missing={missing}")
    return {s: out[normalize_symbol(s)] for s in expected}


def summarize_corr(vals):
    vals = [v for v in vals if v is not None and math.isfinite(v)]
    return {
        "pairs": len(vals),
        "mean": statistics.fmean(vals) if vals else None,
        "median": statistics.median(vals) if vals else None,
        "p90": quantile(vals, .90),
        "p95": quantile(vals, .95),
        "max": max(vals) if vals else None,
        "min": min(vals) if vals else None,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", default="private-backtest")
    ap.add_argument("--scope", required=True)
    args = ap.parse_args()

    work = Path(tempfile.mkdtemp(prefix="bt-concentration-"))
    tp = work / "trades.jsonl"; rp = work / "report.json"
    core.download_artifact(args.project, args.scope, "final/trades.jsonl", tp)
    core.download_artifact(args.project, args.scope, "final/report.json", rp)
    report = json.loads(rp.read_text(encoding="utf-8"))
    primary_symbols = [str(s).upper() for s in report.get("primary_symbols", [])]
    if len(primary_symbols) != 63:
        raise RuntimeError(f"primary symbol count mismatch {len(primary_symbols)} != 63")
    primary_set = set(primary_symbols)
    target_pf = float(report["primary"]["actual"]["PF"])
    target_mean = float(report["primary"]["actual"]["mean_bps"])

    raw_all = [json.loads(x) for x in tp.read_text(encoding="utf-8").splitlines() if x.strip()]
    sample = raw_all[0]
    ek = pick_key(sample, ENTRY_KEYS); xk = pick_key(sample, EXIT_KEYS); sk = pick_key(sample, SYMBOL_KEYS)
    rk = "actual_return_bps" if "actual_return_bps" in sample else None
    if not all([ek, xk, sk, rk]):
        raise RuntimeError(f"required fields missing; keys={sorted(sample.keys())}")
    raw = [r for r in raw_all if str(r.get(sk, "")).upper() in primary_set]
    if len(raw) != 4023:
        raise RuntimeError(f"primary trade count mismatch {len(raw)} != 4023")

    trades = []
    for i,r in enumerate(raw):
        trades.append({
            "idx": i,
            "symbol": str(r[sk]).upper(),
            "entry": parse_dt(r[ek]),
            "exit": parse_dt(r[xk]),
            "bps": float(r[rk]),
        })
    vals = [t["bps"] for t in trades]
    baseline = {"trades": len(vals), "pf": pf(vals), "mean_bps": statistics.fmean(vals), "sum_bps": sum(vals)}
    if abs(baseline["pf"]-target_pf) > 1e-8 or abs(baseline["mean_bps"]-target_mean) > 1e-6:
        raise RuntimeError(f"canonical baseline mismatch: {baseline}")

    meta = fetch_sector_map(primary_symbols)
    for t in trades:
        t["sector"] = meta[t["symbol"]]["sector"]

    # Contribution concentration by symbol and sector.
    by_symbol = defaultdict(list); by_sector = defaultdict(list)
    for t in trades:
        by_symbol[t["symbol"]].append(t["bps"])
        by_sector[t["sector"]].append(t["bps"])
    symbol_rows = []
    for s in primary_symbols:
        v = by_symbol[s]
        symbol_rows.append({"symbol": s, "sector": meta[s]["sector"], "trades": len(v), "sum_bps": sum(v), "mean_bps": statistics.fmean(v), "pf": pf(v)})
    sector_rows = []
    for sec,v in by_sector.items():
        sector_rows.append({"sector": sec, "symbols": sum(1 for s in primary_symbols if meta[s]["sector"]==sec), "trades": len(v), "sum_bps": sum(v), "mean_bps": statistics.fmean(v), "pf": pf(v)})
    symbol_rows.sort(key=lambda x:x["sum_bps"], reverse=True)
    sector_rows.sort(key=lambda x:x["sum_bps"], reverse=True)
    total_net = sum(vals)
    abs_symbol = sum(abs(r["sum_bps"]) for r in symbol_rows)
    symbol_abs_hhi = sum((abs(r["sum_bps"])/abs_symbol)**2 for r in symbol_rows) if abs_symbol else None
    positive_net = sum(max(0.0,r["sum_bps"]) for r in symbol_rows)
    top_symbol_shares = {}
    for n in [1,3,5,10]:
        top_symbol_shares[str(n)] = 100.0*sum(max(0.0,r["sum_bps"]) for r in symbol_rows[:n])/positive_net if positive_net else None
    positive_sector_net = sum(max(0.0,r["sum_bps"]) for r in sector_rows)
    top_sector_shares = {}
    for n in [1,2,3]:
        top_sector_shares[str(n)] = 100.0*sum(max(0.0,r["sum_bps"]) for r in sector_rows[:n])/positive_sector_net if positive_sector_net else None

    # Monthly realized-P&L correlations, zero included for months with no exits.
    min_month = min(t["exit"] for t in trades).replace(day=1,hour=0,minute=0,second=0,microsecond=0)
    max_month = max(t["exit"] for t in trades).replace(day=1,hour=0,minute=0,second=0,microsecond=0)
    months=[]; cur=min_month
    while cur<=max_month:
        months.append(cur.strftime("%Y-%m"))
        cur = (cur.replace(day=28)+timedelta(days=4)).replace(day=1)
    monthly = {s:{m:0.0 for m in months} for s in primary_symbols}
    for t in trades:
        monthly[t["symbol"]][t["exit"].strftime("%Y-%m")] += t["bps"]
    pair_corr=[]; within_corr=[]; cross_corr=[]
    top_pairs=[]
    for i,a in enumerate(primary_symbols):
        av=[monthly[a][m] for m in months]
        for b in primary_symbols[i+1:]:
            bv=[monthly[b][m] for m in months]
            c=pearson(av,bv)
            if c is None: continue
            pair_corr.append(c)
            (within_corr if meta[a]["sector"]==meta[b]["sector"] else cross_corr).append(c)
            top_pairs.append({"a":a,"b":b,"sector_a":meta[a]["sector"],"sector_b":meta[b]["sector"],"corr":c})
    top_pairs.sort(key=lambda x:x["corr"], reverse=True)

    # Signal co-activity by calendar day: binary active-position state per symbol.
    all_days=[]
    d0=min(t["entry"].date() for t in trades); d1=max(t["exit"].date() for t in trades)
    d=d0
    while d<=d1:
        all_days.append(d); d += timedelta(days=1)
    active_days={s:set() for s in primary_symbols}
    for t in trades:
        d=t["entry"].date(); end=t["exit"].date()
        while d<=end:
            active_days[t["symbol"]].add(d); d += timedelta(days=1)
    activity_corr=[]; within_activity=[]; cross_activity=[]; jaccards=[]
    for i,a in enumerate(primary_symbols):
        av=[1.0 if d in active_days[a] else 0.0 for d in all_days]
        for b in primary_symbols[i+1:]:
            bv=[1.0 if d in active_days[b] else 0.0 for d in all_days]
            c=pearson(av,bv)
            if c is not None:
                activity_corr.append(c)
                (within_activity if meta[a]["sector"]==meta[b]["sector"] else cross_activity).append(c)
            u=active_days[a] | active_days[b]
            if u:
                jaccards.append(len(active_days[a]&active_days[b])/len(u))

    # Time-weighted sector concentration of the live book.
    events=defaultdict(lambda:{"entry":[],"exit":[]})
    for t in trades:
        events[t["entry"]]["entry"].append(t)
        events[t["exit"]]["exit"].append(t)
    active=defaultdict(int); prev=None
    weighted_top=0.0; weighted_hhi=0.0; weighted_hours=0.0; peak_top=0.0; peak_sector=None
    sector_peak_counts=defaultdict(int)
    for ts in sorted(events):
        if prev is not None:
            hours=(ts-prev).total_seconds()/3600.0
            total=sum(active.values())
            if total>0 and hours>0:
                shares=[n/total for n in active.values() if n>0]
                top=max(shares); hhi=sum(x*x for x in shares)
                weighted_top += top*hours; weighted_hhi += hhi*hours; weighted_hours += hours
                if top>peak_top:
                    peak_top=top
        # exits first at same timestamp
        for t in events[ts]["exit"]:
            active[t["sector"]]=max(0,active[t["sector"]]-1)
        for t in events[ts]["entry"]:
            active[t["sector"]]+=1
            sector_peak_counts[t["sector"]]=max(sector_peak_counts[t["sector"]],active[t["sector"]])
        prev=ts

    result={
        "schema":1,"scope":args.scope,"universe":"primary_63","baseline":baseline,
        "sector_mapping":{"source":"Nasdaq stock screener runtime fetch","coverage":f"{len(meta)}/63","sectors":sorted(set(x["sector"] for x in meta.values()))},
        "contribution":{
            "total_net_bps":total_net,
            "symbol_abs_contribution_hhi":symbol_abs_hhi,
            "effective_symbol_count_abs_contribution": (1.0/symbol_abs_hhi if symbol_abs_hhi else None),
            "top_positive_symbol_share_pct":top_symbol_shares,
            "top_positive_sector_share_pct":top_sector_shares,
            "top_symbols":symbol_rows[:10],
            "sectors":sector_rows,
        },
        "monthly_realized_pnl_correlation":{
            "months":len(months),"all_pairs":summarize_corr(pair_corr),"within_sector":summarize_corr(within_corr),"cross_sector":summarize_corr(cross_corr),"top_pairs":top_pairs[:10]},
        "signal_activity_daily":{
            "days":len(all_days),"binary_activity_corr_all_pairs":summarize_corr(activity_corr),"within_sector":summarize_corr(within_activity),"cross_sector":summarize_corr(cross_activity),"jaccard_all_pairs":summarize_corr(jaccards)},
        "live_book_sector_concentration":{
            "time_weighted_mean_top_sector_share_pct":100.0*weighted_top/weighted_hours if weighted_hours else None,
            "time_weighted_mean_sector_hhi":weighted_hhi/weighted_hours if weighted_hours else None,
            "effective_sector_count_time_weighted":weighted_hours/weighted_hhi if weighted_hhi else None,
            "max_observed_top_sector_share_pct":100.0*peak_top,
            "sector_peak_open_positions":dict(sorted(sector_peak_counts.items(), key=lambda kv:kv[1], reverse=True)),
        },
    }
    out=work/"sector-correlation-concentration-v1.json"
    out.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    core.upload_artifact(args.project,args.scope,"research/sector-correlation-concentration-v1.json",out,"application/json; charset=utf-8")
    core.put_json("/checkpoints/super-rsi/sector-correlation-concentration-v1",{
        "source":core.SOURCE,"status":"success","position":{"phase":"complete","scope":args.scope,"universe":"primary_63","artifact_project":args.project,"artifact_scope":args.scope,"artifact_name":"research/sector-correlation-concentration-v1.json"},"dropbox_path":None,"last_error":None})
    compact={
        "scope":args.scope,"baseline":baseline,"sector_coverage":f"{len(meta)}/63",
        "top_positive_symbol_share_pct":top_symbol_shares,"top_positive_sector_share_pct":top_sector_shares,
        "effective_symbol_count_abs_contribution":result["contribution"]["effective_symbol_count_abs_contribution"],
        "monthly_corr":result["monthly_realized_pnl_correlation"],
        "activity":result["signal_activity_daily"],
        "live_book":result["live_book_sector_concentration"],
        "top_symbols":symbol_rows[:10],"sectors":sector_rows,
    }
    print(json.dumps(compact,ensure_ascii=False))
    return 0

if __name__=="__main__":
    raise SystemExit(main())
