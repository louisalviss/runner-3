#!/usr/bin/env python3
from __future__ import annotations
import argparse, json, shutil, statistics, subprocess, tarfile, tempfile, time
from pathlib import Path
import private_backtest_worker_v2 as core

PROJECT = "private-backtest"

def wj(p: Path, x):
    p.parent.mkdir(parents=True, exist_ok=True); p.write_text(json.dumps(x, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")

def cfg(path): return json.loads(Path(path).read_text(encoding="utf-8"))
def pf(v):
    gp=sum(x for x in v if x>0); gl=-sum(x for x in v if x<0)
    return gp/gl if gl>0 else (999.0 if gp>0 else None)
def met(v):
    return {"n":len(v),"pf":pf(v),"mean_bps":statistics.fmean(v) if v else None,"median_bps":statistics.median(v) if v else None,"win_rate_pct":100*sum(x>0 for x in v)/len(v) if v else None}
def ok(v, k, op="ge"):
    return v is not None and (v>=k if op=="ge" else v>k)

def fetch_scope(scope, root):
    mp=root/"manifest.json"; core.download_artifact(PROJECT,scope,"manifest.json",mp); m=json.loads(mp.read_text())
    loc={}
    for key,s in m["files"].items():
        p=root/s["name"]; core.download_artifact(PROJECT,scope,s["name"],p)
        if core.sha256_file(p).lower()!=str(s["sha256"]).lower(): raise RuntimeError(f"hash mismatch {key}")
        loc[key]=p
    return m,loc

def stage(a):
    c=cfg(a.config); src=c["source_scope"]; scope=c["scope"]; work=Path(tempfile.mkdtemp(prefix="us30-stage-")); smp=work/"src.json"
    core.download_artifact(PROJECT,src,"manifest.json",smp); sm=json.loads(smp.read_text())
    files={}
    for key in ("engine","evaluator","profile","helper"):
        s=sm["files"][key]; p=work/Path(s["name"]).name; core.download_artifact(PROJECT,src,s["name"],p)
        if core.sha256_file(p).lower()!=str(s["sha256"]).lower(): raise RuntimeError(f"source hash mismatch {key}")
        if key=="profile":
            pr=json.loads(p.read_text()); ex={str(x).upper() for x in pr.get("primary_exclude",[])}
            primary=[str(x).upper() for x in pr["universe"] if str(x).upper() not in ex]
            pr["name"]=c["profile_name"]; pr["status"]="PREREGISTERED_TIMEFRAME_PROBE"; pr["timeframe_minutes"]=int(c["timeframe_minutes"]); pr["source_minutes"]=int(c["source_minutes"])
            pr["universe"]=primary; pr["primary_exclude"]=[]; pr["dates"]={"warmup":c["warmup"],"report_start":c["report_start"],"end":c["end"]}
            g=c["aggregate_gates"]; pr["gates"]={"coverage_min":len(primary),"trades_min":g["trades_min"],"actual_pf_min":g["actual_pf_min"],"actual_mean_bps_min":g["actual_mean_bps_min"],"mid_pf_min":g["mid_pf_min"],"positive_symbol_fraction_min":g["positive_symbol_fraction_min"],"median_symbol_pf_min":g["median_symbol_pf_min"],"pre2026_actual_pf_min":g["pre_holdout_pf_min"],"recent_year_pf_threshold":1.0,"recent_years_min":0}
            pr["lineage"]={"source_scope":src,"experiment":"US_EQUITIES_30M_TIMEFRAME_PROBE","holdout_start":c["holdout_start"],"parameter_changes":"TIMEFRAME_ONLY_60M_TO_30M","direction":"LONG_ONLY","session":"PRESERVED_FROM_CANONICAL"}; wj(p,pr)
        target="package/"+("profile.json" if key=="profile" else ("exp.py" if key=="helper" else f"{key}.py")); ct="application/json; charset=utf-8" if key=="profile" else "text/x-python; charset=utf-8"
        core.upload_artifact(PROJECT,scope,target,p,ct); files[key]={"name":target,"sha256":core.sha256_file(p)}
    m={"schema":1,"type":"super-rsi-us-timeframe-probe","scope":scope,"source_scope":src,"files":files,"shards":c["shards"],"retries":c["retries"],"symbol_timeout_seconds":c["symbol_timeout_seconds"],"holdout_start":c["holdout_start"],"stress_extra_rt_bps":c["stress_extra_rt_bps"],"aggregate_gates":c["aggregate_gates"],"symbol_gates":c["symbol_gates"]}
    mp=work/"manifest.json"; wj(mp,m); core.upload_artifact(PROJECT,scope,"manifest.json",mp,"application/json; charset=utf-8")
    core.put_json("/checkpoints/super-rsi/us-equities-30m-probe-v1",{"source":core.SOURCE,"status":"running","position":{"phase":"staged","scope":scope,"symbols":len(primary)},"dropbox_path":None,"last_error":None})
    print(json.dumps({"stage":"ready","scope":scope,"symbols":len(primary)})); return 0

def shard(a):
    c=cfg(a.config); scope=c["scope"]; sid=int(a.shard); work=Path(tempfile.mkdtemp(prefix=f"us30-{sid}-")); pkg=work/"pkg"; out=work/"symbols"; helper=work/"helper"; pkg.mkdir(); out.mkdir(); helper.mkdir()
    m,l=fetch_scope(scope,pkg); shutil.copy2(l["helper"],helper/"exp.py"); pr=json.loads(l["profile"].read_text()); uni=[str(x).upper() for x in pr["universe"]]; assigned=[s for i,s in enumerate(uni) if i%int(m["shards"])==sid]; failed=[]; t=time.time()
    for s in assigned:
        good=False; last=None
        for _ in range(int(m["retries"])+1):
            last=core.run_symbol(l["engine"],l["profile"],helper,s,out,int(m["symbol_timeout_seconds"])); sp=out/s/f"summary-{s}.json"
            if last["returncode"]==0 and sp.exists() and json.loads(sp.read_text()).get("status")=="OK": good=True; break
        if not good: failed.append(s); wj(out/s/"runner-error.json",last or {"symbol":s})
    ar=work/f"shard-{sid:02d}.tar.gz"; sp=work/f"shard-{sid:02d}.json"
    with tarfile.open(ar,"w:gz") as tf: tf.add(out,arcname="symbols")
    wj(sp,{"shard":sid,"assigned":assigned,"failed_symbols":failed,"elapsed_seconds":round(time.time()-t,3)}); core.upload_artifact(PROJECT,scope,f"shards/shard-{sid:02d}.tar.gz",ar,"application/gzip"); core.upload_artifact(PROJECT,scope,f"shards/shard-{sid:02d}.json",sp,"application/json; charset=utf-8")
    print(json.dumps({"shard":sid,"assigned":len(assigned),"failed":failed})); return 0 if not failed else 2

def evaluate(a):
    c=cfg(a.config); scope=c["scope"]; work=Path(tempfile.mkdtemp(prefix="us30-eval-")); pkg=work/"pkg"; symbols=work/"symbols"; final=work/"final"; pkg.mkdir(); symbols.mkdir(); final.mkdir(); m,l=fetch_scope(scope,pkg); failed=[]; missing=[]
    for sid in range(int(m["shards"])):
        ar=work/f"shard-{sid:02d}.tar.gz"; sp=work/f"shard-{sid:02d}.json"
        try: core.download_artifact(PROJECT,scope,f"shards/shard-{sid:02d}.tar.gz",ar); core.download_artifact(PROJECT,scope,f"shards/shard-{sid:02d}.json",sp)
        except Exception: missing.append(sid); continue
        failed+=json.loads(sp.read_text()).get("failed_symbols",[])
        with tarfile.open(ar,"r:gz") as tf: tf.extractall(work)
    if missing or failed: raise RuntimeError(f"incomplete missing={missing} failed={sorted(set(failed))}")
    ev=subprocess.run(["python",str(l["evaluator"]),"--profile",str(l["profile"]),"--input",str(symbols),"--out",str(final)],capture_output=True,text=True,timeout=1800)
    if ev.returncode: raise RuntimeError(ev.stderr[-5000:])
    report=json.loads((final/"report.json").read_text()); rows=[json.loads(x) for x in (final/"trades.jsonl").read_text().splitlines() if x.strip()]; hs=c["holdout_start"]; rt=float(c["stress_extra_rt_bps"]); g=c["aggregate_gates"]
    vals=[float(r["actual_return_bps"]) for r in rows]; pre=[float(r["actual_return_bps"]) for r in rows if str(r.get("entry_time",""))<hs]; hold=[float(r["actual_return_bps"]) for r in rows if str(r.get("entry_time",""))>=hs]; stress=[x-rt for x in vals]
    b,pr,ho,st=met(vals),met(pre),met(hold),met(stress); p=report["primary"]; amid=p.get("midpoint",{}); midpf=amid.get("PF") if isinstance(amid,dict) else None
    flags={"coverage_all":int(p["ok_symbols"])==int(p["expected_symbols"]),"trades":b["n"]>=g["trades_min"],"actual_pf":ok(b["pf"],g["actual_pf_min"]),"actual_mean":ok(b["mean_bps"],g["actual_mean_bps_min"]),"mid_pf":ok(midpf,g["mid_pf_min"]),"positive_symbol_fraction":float(p["positive_symbol_fraction"])>=g["positive_symbol_fraction_min"],"median_symbol_pf":ok(p.get("median_symbol_PF_ge5"),g["median_symbol_pf_min"]),"pre_holdout_pf":ok(pr["pf"],g["pre_holdout_pf_min"]),"holdout_pf":ok(ho["pf"],g["holdout_pf_min"]),"holdout_mean_positive":ok(ho["mean_bps"],0,"gt"),"stress_pf":ok(st["pf"],g["stress_pf_min"]),"stress_mean_positive":ok(st["mean_bps"],0,"gt")}
    sg=c["symbol_gates"]; by={}
    for r in rows: by.setdefault(str(r.get("symbol","")).upper(),[]).append(r)
    eligible=[]; detail={}
    for s,rr in sorted(by.items()):
        av=[float(x["actual_return_bps"]) for x in rr]; pv=[float(x["actual_return_bps"]) for x in rr if str(x.get("entry_time",""))<hs]; hv=[float(x["actual_return_bps"]) for x in rr if str(x.get("entry_time",""))>=hs]; sv=[x-rt for x in av]; bm,pm,hm,sm=met(av),met(pv),met(hv),met(sv)
        sf={"trades":bm["n"]>=sg["trades_min"],"pre_trades":pm["n"]>=sg["pre_trades_min"],"holdout_trades":hm["n"]>=sg["holdout_trades_min"],"actual_pf":ok(bm["pf"],sg["actual_pf_min"]),"actual_mean":ok(bm["mean_bps"],sg["actual_mean_bps_min"]),"pre_pf":ok(pm["pf"],sg["pre_holdout_pf_min"]),"holdout_pf":ok(hm["pf"],sg["holdout_pf_min"]),"holdout_mean_positive":ok(hm["mean_bps"],0,"gt"),"stress_pf":ok(sm["pf"],sg["stress_pf_min"]),"stress_mean_positive":ok(sm["mean_bps"],0,"gt")}; passed=all(sf.values()); detail[s]={"pass":passed,"base":bm,"pre":pm,"holdout":hm,"stress":sm,"flags":sf}
        if passed: eligible.append(s)
    result={"scope":scope,"timeframe_minutes":c["timeframe_minutes"],"aggregate":{"base":b,"pre":pr,"holdout":ho,"stress":st,"mid_pf":midpf,"flags":flags,"pass":all(flags.values())},"eligible_count":len(eligible),"eligible_symbols":eligible,"symbol_results":detail}
    rp=work/"timeframe-probe.json"; wj(rp,result); core.upload_artifact(PROJECT,scope,"research/timeframe-probe.json",rp,"application/json; charset=utf-8")
    for n,ct in [("report.json","application/json; charset=utf-8"),("symbol_summary.csv","text/csv; charset=utf-8"),("yearly_summary.csv","text/csv; charset=utf-8"),("trades.jsonl","application/x-ndjson; charset=utf-8")]:
        pth=final/n
        if pth.exists(): core.upload_artifact(PROJECT,scope,f"final/{n}",pth,ct)
    core.put_json("/checkpoints/super-rsi/us-equities-30m-probe-v1",{"source":core.SOURCE,"status":"complete","position":{"phase":"evaluated","scope":scope,"aggregate_pass":result["aggregate"]["pass"],"eligible_symbols":eligible},"dropbox_path":None,"last_error":None}); print(json.dumps({"scope":scope,"aggregate_pass":result["aggregate"]["pass"],"eligible_count":len(eligible),"eligible_symbols":eligible,"base":b,"holdout":ho,"stress":st},indent=2)); return 0

def main():
    ap=argparse.ArgumentParser(); sub=ap.add_subparsers(dest="cmd",required=True)
    for cmd in ("stage","shard","evaluate"):
        p=sub.add_parser(cmd); p.add_argument("--config",required=True)
        if cmd=="shard": p.add_argument("--shard",required=True,type=int)
    a=ap.parse_args(); return globals()[a.cmd](a)
if __name__=="__main__": raise SystemExit(main())
