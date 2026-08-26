#!/usr/bin/env python3
from __future__ import annotations
import argparse, json, shutil, subprocess, tarfile, tempfile
from pathlib import Path
import private_backtest_worker_v2 as core
import private_backtest_crypto_expanded as base
PROJECT="private-backtest"

def wj(p,x): p.parent.mkdir(parents=True,exist_ok=True); p.write_text(json.dumps(x,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
def load(path): return json.loads(Path(path).read_text(encoding="utf-8"))

def stage(a):
    c=load(a.config); v=c["venues"][a.venue]; src=c["source_scope"]; scope=v["scope"]; work=Path(tempfile.mkdtemp(prefix=f"crypto60-stage-{a.venue}-")); smp=work/"src.json"
    core.download_artifact(PROJECT,src,"manifest.json",smp); sm=json.loads(smp.read_text()); files={}
    for key in ("engine","evaluator","profile"):
        s=sm["files"][key]; p=work/Path(s["name"]).name; core.download_artifact(PROJECT,src,s["name"],p)
        if core.sha256_file(p).lower()!=str(s["sha256"]).lower(): raise RuntimeError(f"source hash mismatch {key}")
        if key=="profile":
            pr=json.loads(p.read_text()); pr.update({"name":v["profile_name"],"status":"PREREGISTERED_CRYPTO_60M_TIMEFRAME_PROBE","asset_class":v["asset_class"],"timeframe_minutes":int(c["timeframe_minutes"]),"source_minutes":int(c["source_minutes"]),"universe":list(v["symbols"]),"primary_exclude":[]}); pr["session"]={"timezone":"UTC","open_minute":0,"close_minute":1440,"allow_final_partial_bar":False}; pr["dates"]={"warmup":c["warmup"],"report_start":c["report_start"],"end":c["end"]}; pr["pre_cutoff_year"]=2024; pr["recent_years"]=[2024,2025,2026]; pr["gates"]={"coverage_min":len(v["symbols"]),"trades_min":1,"actual_pf_min":0.0,"actual_mean_bps_min":-99999.0,"mid_pf_min":0.0,"positive_symbol_fraction_min":0.0,"median_symbol_pf_min":0.0,"pre2026_actual_pf_min":0.0,"recent_year_pf_threshold":0.0,"recent_years_min":0}; pr["lineage"]={"source_scope":src,"venue":a.venue,"holdout_start":c["holdout_start"],"parameter_changes":"TIMEFRAME_ONLY_TO_60M","direction":"LONG_ONLY","execution_note":"Binance archive klines + same preregistered synthetic bid/ask and fees as 30m screen"}; wj(p,pr)
        target=f"package/{key}.py" if key in ("engine","evaluator") else "package/profile.json"; core.upload_artifact(PROJECT,scope,target,p,"text/x-python; charset=utf-8" if key in ("engine","evaluator") else "application/json; charset=utf-8"); files[key]={"name":target,"sha256":core.sha256_file(p)}
    hp=work/"exp.py"; text=base.helper_text(a.venue,float(v["half_spread_slippage_bps"]),v["symbols"])
    if a.venue=="perp": text=text.replace("def resolve_symbol(symbol):\n    s=str(symbol).strip().upper()\n    return s if s in ALLOWED else None\n","VENUE_ALIASES={'SHIBUSDT':'1000SHIBUSDT'}\n\ndef resolve_symbol(symbol):\n    s=str(symbol).strip().upper()\n    if s not in ALLOWED: return None\n    return VENUE_ALIASES.get(s,s)\n",1)
    hp.write_text(text,encoding="utf-8"); core.upload_artifact(PROJECT,scope,"package/exp.py",hp,"text/x-python; charset=utf-8"); files["helper"]={"name":"package/exp.py","sha256":core.sha256_file(hp)}
    m={"schema":1,"type":"super-rsi-crypto-60m-probe","venue":a.venue,"scope":scope,"source_scope":src,"created_at":core.now_iso(),"files":files,"shards":c["shards"],"retries":c["retries"],"symbol_timeout_seconds":c["symbol_timeout_seconds"],"holdout_start":c["holdout_start"],"fee_bps_per_side":v["fee_bps_per_side"],"half_spread_slippage_bps":v["half_spread_slippage_bps"],"symbol_gates":c["symbol_gates"],"stress_extra_rt_bps":c["stress_extra_rt_bps"],"promotion_blocker":v["promotion_blocker"],"data_transport":"Binance Public Data archive data.binance.vision daily/monthly"}
    mp=work/"manifest.json"; wj(mp,m); core.upload_artifact(PROJECT,scope,"manifest.json",mp,"application/json; charset=utf-8"); core.put_json(f"/checkpoints/super-rsi/crypto-60m-{a.venue}-v1",{"source":core.SOURCE,"status":"running","position":{"phase":"staged","scope":scope,"symbols":len(v["symbols"])},"dropbox_path":None,"last_error":None}); print(json.dumps({"stage":"ready","venue":a.venue,"scope":scope,"symbols":len(v["symbols"])})); return 0

def shard(a): return base.shard(a)

def evaluate(a):
    c=load(a.config); v=c["venues"][a.venue]; scope=v["scope"]; work=Path(tempfile.mkdtemp(prefix=f"crypto60-eval-{a.venue}-")); pkg=work/"pkg"; symbols=work/"symbols"; final=work/"final"; pkg.mkdir(); symbols.mkdir(); final.mkdir(); m,l=base.fetch_package(scope,pkg); failed=[]; missing=[]
    for sid in range(int(m["shards"])):
        ar=work/f"shard-{sid:02d}.tar.gz"; sp=work/f"shard-{sid:02d}.json"
        try: core.download_artifact(PROJECT,scope,f"shards/shard-{sid:02d}.tar.gz",ar); core.download_artifact(PROJECT,scope,f"shards/shard-{sid:02d}.json",sp)
        except Exception: missing.append(sid); continue
        failed+=json.loads(sp.read_text()).get("failed_symbols",[])
        with tarfile.open(ar,"r:gz") as tf: tf.extractall(work)
    if missing or failed: raise RuntimeError(f"incomplete venue={a.venue} missing={missing} failed={sorted(set(failed))}")
    ev=subprocess.run(["python",str(l["evaluator"]),"--profile",str(l["profile"]),"--input",str(symbols),"--out",str(final)],capture_output=True,text=True,timeout=1800)
    if ev.returncode: raise RuntimeError(ev.stderr[-4000:])
    rows=[json.loads(x) for x in (final/"trades.jsonl").read_text().splitlines() if x.strip()]; fee=float(m["fee_bps_per_side"])/10000.0; rt=float(m["stress_extra_rt_bps"]); sg=m["symbol_gates"]; hs=m["holdout_start"]
    def net(r): return (((1+float(r["actual_return"]))*(1-fee)*(1-fee))-1)*10000
    detail={}; eligible=[]
    for sym in v["symbols"]:
        rr=[r for r in rows if str(r.get("symbol","")).upper()==sym.upper()]; av=[net(r) for r in rr]; pv=[net(r) for r in rr if str(r.get("entry_time",""))<hs]; hv=[net(r) for r in rr if str(r.get("entry_time",""))>=hs]; sv=[x-rt for x in av]; bm,pm,hm,sm=base.met(av),base.met(pv),base.met(hv),base.met(sv); flags={"trades":bm["n"]>=sg["trades_min"],"pre_trades":pm["n"]>=sg["pre_trades_min"],"holdout_trades":hm["n"]>=sg["holdout_trades_min"],"base_pf":bm["pf"] is not None and bm["pf"]>=sg["actual_pf_min"],"base_mean":bm["mean_bps"] is not None and bm["mean_bps"]>=sg["actual_mean_bps_min"],"pre_pf":pm["pf"] is not None and pm["pf"]>=sg["pre_holdout_pf_min"],"holdout_pf":hm["pf"] is not None and hm["pf"]>=sg["holdout_pf_min"],"holdout_mean":hm["mean_bps"] is not None and hm["mean_bps"]>0,"stress_pf":sm["pf"] is not None and sm["pf"]>=sg["stress_pf_min"],"stress_mean":sm["mean_bps"] is not None and sm["mean_bps"]>0}; passed=all(flags.values()); detail[sym]={"pass":passed,"base_fee_adjusted":bm,"pre_holdout_fee_adjusted":pm,"holdout_fee_adjusted":hm,"stress":sm,"flags":flags}; eligible += [sym] if passed else []
    allv=[net(r) for r in rows]; allh=[net(r) for r in rows if str(r.get("entry_time",""))>=hs]; result={"schema":1,"venue":a.venue,"timeframe_minutes":60,"scope":scope,"eligible_count":len(eligible),"eligible_symbols":eligible,"aggregate_fee_adjusted":base.met(allv),"aggregate_holdout_fee_adjusted":base.met(allh),"fee_bps_per_side":m["fee_bps_per_side"],"synthetic_half_spread_slippage_bps":m["half_spread_slippage_bps"],"stress_extra_rt_bps":rt,"promotion_blocker":m["promotion_blocker"],"symbols_detail":detail}
    rp=work/"crypto-60m-probe.json"; wj(rp,result); core.upload_artifact(PROJECT,scope,"research/crypto-60m-probe.json",rp,"application/json; charset=utf-8"); core.put_json(f"/checkpoints/super-rsi/crypto-60m-{a.venue}-v1",{"source":core.SOURCE,"status":"complete","position":{"phase":"evaluated","scope":scope,"eligible_symbols":eligible,"artifact_name":"research/crypto-60m-probe.json"},"dropbox_path":None,"last_error":None}); print(json.dumps({"venue":a.venue,"eligible_count":len(eligible),"eligible_symbols":eligible,"aggregate":result["aggregate_fee_adjusted"],"holdout":result["aggregate_holdout_fee_adjusted"]},indent=2)); return 0

def main():
    ap=argparse.ArgumentParser(); sub=ap.add_subparsers(dest="cmd",required=True)
    for cmd in ("stage","shard","evaluate"):
        p=sub.add_parser(cmd); p.add_argument("--config",required=True); p.add_argument("--venue",choices=["spot","perp"],required=True)
        if cmd=="shard": p.add_argument("--shard",type=int,required=True)
    a=ap.parse_args(); return globals()[a.cmd](a)
if __name__=="__main__": raise SystemExit(main())
