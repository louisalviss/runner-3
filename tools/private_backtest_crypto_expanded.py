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


def wj(path: Path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def load_cfg(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def pf(vals):
    gp = sum(v for v in vals if v > 0)
    gl = -sum(v for v in vals if v < 0)
    return gp / gl if gl > 0 else (999.0 if gp > 0 else None)


def met(vals):
    return {
        "n": len(vals),
        "pf": pf(vals),
        "mean_bps": statistics.fmean(vals) if vals else None,
        "median_bps": statistics.median(vals) if vals else None,
        "win_rate_pct": 100.0 * sum(v > 0 for v in vals) / len(vals) if vals else None,
    }


def helper_text(venue: str, half_spread_bps: float, symbols: list[str]) -> str:
    root = "spot" if venue == "spot" else "futures/um"
    allowed = repr(tuple(str(s).upper() for s in symbols))
    return f'''from __future__ import annotations
import csv, io, urllib.error, urllib.request, zipfile
import pandas as pd
BID=0; ASK=1; ROOT={root!r}; HALF={float(half_spread_bps)!r}; BASE="https://data.binance.vision/data/"+ROOT; ALLOWED=set({allowed}); CACHE={{}}

def resolve_symbol(symbol):
    s=str(symbol).strip().upper()
    return s if s in ALLOWED else None

def pick_const(names):
    for n in names:
        if "BID" in n: return BID
        if "ASK" in n or "OFFER" in n: return ASK
    raise AttributeError(names)

def month_chunks(start,end):
    cur=pd.Timestamp(start); stop=pd.Timestamp(end)
    cur=cur.tz_localize("UTC") if cur.tzinfo is None else cur.tz_convert("UTC")
    stop=stop.tz_localize("UTC") if stop.tzinfo is None else stop.tz_convert("UTC")
    while cur<stop:
        if cur.month==12: nxt=pd.Timestamp(year=cur.year+1,month=1,day=1,tz="UTC")
        else: nxt=pd.Timestamp(year=cur.year,month=cur.month+1,day=1,tz="UTC")
        yield cur,min(nxt,stop); cur=nxt

def _get_zip(url):
    req=urllib.request.Request(url,headers={{"User-Agent":"runner3-super-rsi-public-archive/2"}})
    with urllib.request.urlopen(req,timeout=90) as r: raw=r.read()
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        names=[n for n in z.namelist() if n.lower().endswith('.csv')]
        if not names: raise ValueError("archive has no csv")
        return z.read(names[0]).decode('utf-8')

def _rows_from_csv(text):
    out=[]
    for row in csv.reader(io.StringIO(text)):
        if not row or not str(row[0]).lstrip('-').isdigit(): continue
        try: out.append((int(row[0]),float(row[1]),float(row[2]),float(row[3]),float(row[4])))
        except Exception: continue
    return out

def _monthly_url(symbol,interval,t):
    ym=t.strftime('%Y-%m'); name=f"{{symbol}}-{{interval}}-{{ym}}.zip"
    return f"{{BASE}}/monthly/klines/{{symbol}}/{{interval}}/{{name}}"

def _daily_url(symbol,interval,t):
    ymd=t.strftime('%Y-%m-%d'); name=f"{{symbol}}-{{interval}}-{{ymd}}.zip"
    return f"{{BASE}}/daily/klines/{{symbol}}/{{interval}}/{{name}}"

def _load_rows(symbol,interval,start,end):
    key=(symbol,interval,str(start),str(end))
    if key in CACHE: return CACHE[key]
    try:
        rows=_rows_from_csv(_get_zip(_monthly_url(symbol,interval,start))); CACHE[key]=rows; return rows
    except urllib.error.HTTPError as e:
        if e.code not in (404,403): raise
    rows=[]; d=start.normalize(); stop=end.normalize()
    if end>stop: stop=stop+pd.Timedelta(days=1)
    while d<stop:
        try: rows.extend(_rows_from_csv(_get_zip(_daily_url(symbol,interval,d))))
        except urllib.error.HTTPError as e:
            if e.code!=404: raise
        d+=pd.Timedelta(days=1)
    CACHE[key]=rows; return rows

def _ts(v):
    unit='us' if abs(int(v))>=100_000_000_000_000 else 'ms'
    return pd.to_datetime(int(v),unit=unit,utc=True)

def fetch_side(instrument,offer_side,start,end,source_minutes):
    start=pd.Timestamp(start); end=pd.Timestamp(end)
    start=start.tz_localize('UTC') if start.tzinfo is None else start.tz_convert('UTC')
    end=end.tz_localize('UTC') if end.tzinfo is None else end.tz_convert('UTC')
    interval=f"{{int(source_minutes)}}m"; raw=_load_rows(instrument,interval,start,end)
    rows=[]
    for ts,o,h,l,c in raw:
        t=_ts(ts)
        if start<=t<end: rows.append((t,o,h,l,c))
    if not rows: return pd.DataFrame(columns=['open','high','low','close'])
    idx=pd.DatetimeIndex([x[0] for x in rows])
    out=pd.DataFrame({{'open':[x[1] for x in rows],'high':[x[2] for x in rows],'low':[x[3] for x in rows],'close':[x[4] for x in rows]}},index=idx)
    mult=1.0+(HALF/10000.0 if offer_side==ASK else -HALF/10000.0)
    out=out*mult
    return out[~out.index.duplicated(keep='last')].sort_index()
'''


def fetch_package(scope: str, root: Path):
    mp = root / "manifest.json"
    core.download_artifact(PROJECT, scope, "manifest.json", mp)
    m = json.loads(mp.read_text(encoding="utf-8"))
    local = {}
    for key, spec in m["files"].items():
        p = root / spec["name"]
        core.download_artifact(PROJECT, scope, spec["name"], p)
        if core.sha256_file(p).lower() != str(spec["sha256"]).lower():
            raise RuntimeError(f"package hash mismatch {key}")
        local[key] = p
    return m, local


def stage(args):
    cfg = load_cfg(args.config); v = cfg["venues"][args.venue]
    source_scope = cfg["source_scope"]; scope = v["scope"]
    work = Path(tempfile.mkdtemp(prefix=f"crypto-exp-stage-{args.venue}-"))
    smp = work / "source-manifest.json"
    core.download_artifact(PROJECT, source_scope, "manifest.json", smp)
    sm = json.loads(smp.read_text(encoding="utf-8"))
    files = {}
    for key in ("engine", "evaluator", "profile"):
        spec = sm["files"][key]
        p = work / Path(spec["name"]).name
        core.download_artifact(PROJECT, source_scope, spec["name"], p)
        if core.sha256_file(p).lower() != str(spec["sha256"]).lower():
            raise RuntimeError(f"source hash mismatch {key}")
        if key == "profile":
            pr = json.loads(p.read_text(encoding="utf-8"))
            pr.update({
                "name": v["profile_name"], "status": "PREREGISTERED_CRYPTO_EXPANDED_30M_SCREEN",
                "asset_class": v["asset_class"], "timeframe_minutes": 30, "source_minutes": 30,
                "universe": list(v["symbols"]), "primary_exclude": []
            })
            pr["session"] = {"timezone":"UTC","open_minute":0,"close_minute":1440,"allow_final_partial_bar":False}
            pr["dates"] = {"warmup":cfg["warmup"],"report_start":cfg["report_start"],"end":cfg["end"]}
            pr["pre_cutoff_year"] = 2024; pr["recent_years"] = [2024, 2025, 2026]
            pr["gates"] = {
                "coverage_min": len(v["symbols"]), "trades_min": 1, "actual_pf_min": 0.0, "actual_mean_bps_min": -99999.0,
                "mid_pf_min": 0.0, "positive_symbol_fraction_min": 0.0, "median_symbol_pf_min": 0.0,
                "pre2026_actual_pf_min": 0.0, "recent_year_pf_threshold": 0.0, "recent_years_min": 0
            }
            pr["lineage"] = {
                "source_scope": source_scope, "venue": args.venue, "pair_quote": "USDT", "holdout_start": cfg["holdout_start"],
                "parameter_changes": "NONE", "direction": "LONG_ONLY",
                "execution_note": "Binance archive trade-price klines + preregistered synthetic bid/ask + fixed fee; research screen only"
            }
            wj(p, pr)
        target = f"package/{key}.py" if key in ("engine","evaluator") else "package/profile.json"
        core.upload_artifact(PROJECT, scope, target, p, "text/x-python; charset=utf-8" if key in ("engine","evaluator") else "application/json; charset=utf-8")
        files[key] = {"name": target, "sha256": core.sha256_file(p)}
    hp = work / "exp.py"
    hp.write_text(helper_text(args.venue, v["half_spread_slippage_bps"], v["symbols"]), encoding="utf-8")
    core.upload_artifact(PROJECT, scope, "package/exp.py", hp, "text/x-python; charset=utf-8")
    files["helper"] = {"name":"package/exp.py","sha256":core.sha256_file(hp)}
    manifest = {
        "schema":1,"type":"super-rsi-crypto-expanded-30m","venue":args.venue,"scope":scope,"source_scope":source_scope,
        "created_at":core.now_iso(),"files":files,"shards":int(cfg.get("shards",4)),"retries":int(cfg.get("retries",1)),
        "symbol_timeout_seconds":int(cfg.get("symbol_timeout_seconds",5400)),"holdout_start":cfg["holdout_start"],
        "fee_bps_per_side":float(v["fee_bps_per_side"]),"half_spread_slippage_bps":float(v["half_spread_slippage_bps"]),
        "symbol_gates":cfg["symbol_gates"],"stress_extra_rt_bps":float(cfg["stress_extra_rt_bps"]),
        "promotion_blocker":v["promotion_blocker"],"data_transport":"Binance Public Data archive data.binance.vision daily/monthly"
    }
    mp = work / "manifest.json"; wj(mp, manifest); core.upload_artifact(PROJECT, scope, "manifest.json", mp, "application/json; charset=utf-8")
    core.put_json(f"/checkpoints/super-rsi/crypto-expanded-30m-{args.venue}-v1", {"source":core.SOURCE,"status":"running","position":{"phase":"staged","scope":scope,"venue":args.venue,"symbols":len(v["symbols"])},"dropbox_path":None,"last_error":None})
    print(json.dumps({"stage":"ready","venue":args.venue,"scope":scope,"symbols":len(v["symbols"])})); return 0


def shard(args):
    cfg = load_cfg(args.config); v = cfg["venues"][args.venue]; scope = v["scope"]; sid = int(args.shard)
    work = Path(tempfile.mkdtemp(prefix=f"crypto-exp-{args.venue}-{sid}-")); pkg=work/"pkg"; out=work/"symbols"; helper=work/"helper"
    pkg.mkdir(); out.mkdir(); helper.mkdir(); m,l = fetch_package(scope,pkg); shutil.copy2(l["helper"], helper/"exp.py")
    pr = json.loads(l["profile"].read_text(encoding="utf-8")); assigned=[s for i,s in enumerate(pr["universe"]) if i % int(m["shards"]) == sid]
    failed=[]; started=time.time()
    for sym in assigned:
        ok=False; last=None
        for _ in range(int(m["retries"])+1):
            last=core.run_symbol(l["engine"],l["profile"],helper,sym,out,int(m["symbol_timeout_seconds"]))
            sp=out/sym/f"summary-{sym}.json"
            if last["returncode"]==0 and sp.exists() and json.loads(sp.read_text(encoding="utf-8")).get("status")=="OK": ok=True; break
        if not ok:
            failed.append(sym); wj(out/sym/"runner-error.json",last or {"symbol":sym})
    ar=work/f"shard-{sid:02d}.tar.gz"
    with tarfile.open(ar,"w:gz") as tf: tf.add(out,arcname="symbols")
    sp=work/f"shard-{sid:02d}.json"; wj(sp,{"shard":sid,"assigned":assigned,"failed_symbols":failed,"elapsed_seconds":round(time.time()-started,3)})
    core.upload_artifact(PROJECT,scope,f"shards/shard-{sid:02d}.tar.gz",ar,"application/gzip"); core.upload_artifact(PROJECT,scope,f"shards/shard-{sid:02d}.json",sp,"application/json; charset=utf-8")
    print(json.dumps({"venue":args.venue,"shard":sid,"assigned":len(assigned),"failed":failed})); return 0 if not failed else 2


def evaluate(args):
    cfg=load_cfg(args.config); v=cfg["venues"][args.venue]; scope=v["scope"]
    work=Path(tempfile.mkdtemp(prefix=f"crypto-exp-eval-{args.venue}-")); pkg=work/"pkg"; symbols=work/"symbols"; final=work/"final"
    pkg.mkdir(); symbols.mkdir(); final.mkdir(); m,l=fetch_package(scope,pkg); failed=[]; missing=[]
    for sid in range(int(m["shards"])):
        ar=work/f"shard-{sid:02d}.tar.gz"; sp=work/f"shard-{sid:02d}.json"
        try: core.download_artifact(PROJECT,scope,f"shards/shard-{sid:02d}.tar.gz",ar); core.download_artifact(PROJECT,scope,f"shards/shard-{sid:02d}.json",sp)
        except Exception: missing.append(sid); continue
        failed.extend(json.loads(sp.read_text(encoding="utf-8")).get("failed_symbols",[]))
        with tarfile.open(ar,"r:gz") as tf: tf.extractall(work)
    if missing or failed: raise RuntimeError(f"incomplete venue={args.venue} missing={missing} failed={sorted(set(failed))}")
    ev=subprocess.run(["python",str(l["evaluator"]),"--profile",str(l["profile"]),"--input",str(symbols),"--out",str(final)],capture_output=True,text=True,timeout=1800)
    if ev.returncode: raise RuntimeError(ev.stderr[-4000:])
    rows=[json.loads(x) for x in (final/"trades.jsonl").read_text(encoding="utf-8").splitlines() if x.strip()]
    fee=float(m["fee_bps_per_side"])/10000.0; stress_rt=float(m["stress_extra_rt_bps"]); sg=m["symbol_gates"]; holdout_start=m["holdout_start"]
    def netbps(r): return (((1.0+float(r["actual_return"]))*(1-fee)*(1-fee))-1.0)*10000.0
    symbol_results={}; eligible=[]
    for sym in v["symbols"]:
        rr=[r for r in rows if str(r.get("symbol","")).upper()==sym.upper()]
        vals=[netbps(r) for r in rr]; pre=[netbps(r) for r in rr if str(r.get("entry_time",""))<holdout_start]; ho=[netbps(r) for r in rr if str(r.get("entry_time",""))>=holdout_start]; stress=[x-stress_rt for x in vals]
        bm,pm,hm,sm=met(vals),met(pre),met(ho),met(stress)
        flags={
            "trades":bm["n"]>=int(sg["trades_min"]),"pre_trades":pm["n"]>=int(sg["pre_trades_min"]),"holdout_trades":hm["n"]>=int(sg["holdout_trades_min"]),
            "base_pf":bm["pf"] is not None and bm["pf"]>=float(sg["actual_pf_min"]),"base_mean":bm["mean_bps"] is not None and bm["mean_bps"]>=float(sg["actual_mean_bps_min"]),
            "pre_pf":pm["pf"] is not None and pm["pf"]>=float(sg["pre_holdout_pf_min"]),"holdout_pf":hm["pf"] is not None and hm["pf"]>=float(sg["holdout_pf_min"]),"holdout_mean":hm["mean_bps"] is not None and hm["mean_bps"]>0,
            "stress_pf":sm["pf"] is not None and sm["pf"]>=float(sg["stress_pf_min"]),"stress_mean":sm["mean_bps"] is not None and sm["mean_bps"]>0}
        ok=all(flags.values()); eligible += [sym] if ok else []
        symbol_results[sym]={"base_fee_adjusted":bm,"pre_holdout_fee_adjusted":pm,"holdout_fee_adjusted":hm,"stress":sm,"flags":flags,"lower_tf_research_eligible":ok}
    allvals=[netbps(r) for r in rows]; allho=[netbps(r) for r in rows if str(r.get("entry_time",""))>=holdout_start]
    result={"schema":1,"venue":args.venue,"scope":scope,"symbols":len(v["symbols"]),"eligible_count":len(eligible),"eligible_symbols":eligible,
            "aggregate_fee_adjusted":met(allvals),"aggregate_holdout_fee_adjusted":met(allho),"fee_bps_per_side":m["fee_bps_per_side"],"synthetic_half_spread_slippage_bps":m["half_spread_slippage_bps"],
            "stress_extra_rt_bps":stress_rt,"symbol_gates":sg,"promotion_blocker":m["promotion_blocker"],"symbols_detail":symbol_results,
            "limitations":["historical top-of-book not used","funding not modeled" if args.venue=="perp" else "spot fee fixed preregistered assumption"]}
    rp=work/"crypto-expanded-30m-v1.json"; wj(rp,result); core.upload_artifact(PROJECT,scope,"research/crypto-expanded-30m-v1.json",rp,"application/json; charset=utf-8")
    for name,ctype in [("report.json","application/json; charset=utf-8"),("SUMMARY.md","text/markdown; charset=utf-8"),("symbol_summary.csv","text/csv; charset=utf-8"),("yearly_summary.csv","text/csv; charset=utf-8"),("trades.jsonl","application/x-ndjson; charset=utf-8")]:
        p=final/name
        if p.exists(): core.upload_artifact(PROJECT,scope,f"final/{name}",p,ctype)
    core.put_json(f"/checkpoints/super-rsi/crypto-expanded-30m-{args.venue}-v1", {"source":core.SOURCE,"status":"complete","position":{"phase":"evaluated","scope":scope,"eligible_symbols":eligible,"artifact_project":PROJECT,"artifact_scope":scope,"artifact_name":"research/crypto-expanded-30m-v1.json"},"dropbox_path":None,"last_error":None})
    print(json.dumps({"venue":args.venue,"eligible_count":len(eligible),"eligible_symbols":eligible,"aggregate":result["aggregate_fee_adjusted"],"holdout":result["aggregate_holdout_fee_adjusted"]},indent=2)); return 0


def main():
    ap=argparse.ArgumentParser(); sub=ap.add_subparsers(dest="cmd",required=True)
    for cmd in ("stage","shard","evaluate"):
        p=sub.add_parser(cmd); p.add_argument("--config",required=True); p.add_argument("--venue",choices=["spot","perp"],required=True)
        if cmd=="shard": p.add_argument("--shard",type=int,required=True)
    a=ap.parse_args(); return globals()[a.cmd](a)


if __name__=="__main__":
    raise SystemExit(main())
