#!/usr/bin/env python3
from __future__ import annotations

import argparse, json, shutil, statistics, subprocess, tarfile, tempfile, time
from pathlib import Path
import private_backtest_worker_v2 as core

PROJECT="private-backtest"

def wj(p,o): p.parent.mkdir(parents=True,exist_ok=True); p.write_text(json.dumps(o,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
def cfg(path): return json.loads(Path(path).read_text(encoding="utf-8"))
def met(vals):
    gp=sum(v for v in vals if v>0); gl=-sum(v for v in vals if v<0)
    return {"n":len(vals),"pf":(gp/gl if gl>0 else (999.0 if gp>0 else None)),"mean_bps":(statistics.fmean(vals) if vals else None),"median_bps":(statistics.median(vals) if vals else None),"win_rate_pct":(100*sum(v>0 for v in vals)/len(vals) if vals else None)}

def helper_text(venue, half_spread_bps):
    base="https://api.binance.com/api/v3/klines" if venue=="spot" else "https://fapi.binance.com/fapi/v1/klines"
    return f'''from __future__ import annotations
import json, time, urllib.parse, urllib.request
import pandas as pd
BID=0; ASK=1; BASE={base!r}; HALF={float(half_spread_bps)!r}

def resolve_symbol(symbol):
    s=str(symbol).strip().upper()
    return s if s in ("BTCUSDT","ETHUSDT") else None

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
        nxt=(cur+pd.offsets.MonthBegin(1)).normalize()
        yield cur,min(nxt,stop); cur=nxt

def _ms(v):
    t=pd.Timestamp(v); t=t.tz_localize("UTC") if t.tzinfo is None else t.tz_convert("UTC")
    return int(t.timestamp()*1000)

def fetch_side(instrument,offer_side,start,end,source_minutes):
    interval=f"{{int(source_minutes)}}m"; cur=_ms(start); stop=_ms(end); rows=[]
    while cur<stop:
        q=urllib.parse.urlencode({{"symbol":instrument,"interval":interval,"startTime":cur,"endTime":stop-1,"limit":1000}})
        req=urllib.request.Request(BASE+"?"+q,headers={{"User-Agent":"runner3-super-rsi/1"}})
        with urllib.request.urlopen(req,timeout=60) as r: data=json.load(r)
        if not data: break
        rows.extend(data); nxt=int(data[-1][0])+int(source_minutes)*60*1000
        if nxt<=cur: break
        cur=nxt; time.sleep(0.03)
    if not rows: return pd.DataFrame(columns=["open","high","low","close"])
    idx=pd.to_datetime([int(x[0]) for x in rows],unit="ms",utc=True)
    out=pd.DataFrame({{"open":[float(x[1]) for x in rows],"high":[float(x[2]) for x in rows],"low":[float(x[3]) for x in rows],"close":[float(x[4]) for x in rows]}},index=idx)
    mult=1.0 + (HALF/10000.0 if offer_side==ASK else -HALF/10000.0)
    out=out*mult; return out[~out.index.duplicated(keep="last")].sort_index()
'''

def package(scope,root):
    mp=root/"manifest.json"; core.download_artifact(PROJECT,scope,"manifest.json",mp); m=json.loads(mp.read_text()); loc={}
    for k,s in m["files"].items():
        p=root/s["name"]; core.download_artifact(PROJECT,scope,s["name"],p)
        if core.sha256_file(p).lower()!=str(s["sha256"]).lower(): raise RuntimeError(f"hash {k}")
        loc[k]=p
    return m,loc

def stage(a):
    c=cfg(a.config); v=c["venues"][a.venue]; scope=v["scope"]; src=c["source_scope"]; work=Path(tempfile.mkdtemp(prefix="crypto-stage-")); sm=work/"source.json"
    core.download_artifact(PROJECT,src,"manifest.json",sm); smj=json.loads(sm.read_text()); files={}
    for k in ("engine","evaluator","profile"):
        s=smj["files"][k]; p=work/Path(s["name"]).name; core.download_artifact(PROJECT,src,s["name"],p)
        if k=="profile":
            pr=json.loads(p.read_text()); pr.update({"name":v["profile_name"],"status":"PREREGISTERED_CRYPTO_30M_SCREEN","asset_class":v["asset_class"],"timeframe_minutes":30,"source_minutes":30,"universe":["BTCUSDT","ETHUSDT"],"primary_exclude":[]})
            pr["session"]={"timezone":"UTC","open_minute":0,"close_minute":1440,"allow_final_partial_bar":False}; pr["dates"]={"warmup":c["warmup"],"report_start":c["report_start"],"end":c["end"]}; pr["pre_cutoff_year"]=2024; pr["recent_years"]=[2024,2025,2026]
            pr["gates"]={"coverage_min":2,"trades_min":int(c["gates"]["trades_min"]),"actual_pf_min":1.0,"actual_mean_bps_min":0.0,"mid_pf_min":1.0,"positive_symbol_fraction_min":0.0,"median_symbol_pf_min":0.0,"pre2026_actual_pf_min":1.0,"recent_year_pf_threshold":1.0,"recent_years_min":1}
            pr["lineage"]={"source_scope":src,"venue":a.venue,"pair_quote":"USDT","holdout_start":c["holdout_start"],"parameter_changes":"NONE","direction":"LONG_ONLY","execution_note":"synthetic historical bid/ask + explicit fee model; provisional only"}; wj(p,pr)
        target=f"package/{k}.py" if k in ("engine","evaluator") else "package/profile.json"; core.upload_artifact(PROJECT,scope,target,p,"text/x-python; charset=utf-8" if k!="profile" else "application/json; charset=utf-8"); files[k]={"name":target,"sha256":core.sha256_file(p)}
    hp=work/"exp.py"; hp.write_text(helper_text(a.venue,v["half_spread_slippage_bps"]),encoding="utf-8"); core.upload_artifact(PROJECT,scope,"package/exp.py",hp,"text/x-python; charset=utf-8"); files["helper"]={"name":"package/exp.py","sha256":core.sha256_file(hp)}
    m={"schema":1,"venue":a.venue,"scope":scope,"source_scope":src,"files":files,"shards":2,"retries":1,"symbol_timeout_seconds":5400,"holdout_start":c["holdout_start"],"fee_bps_per_side":v["fee_bps_per_side"],"half_spread_slippage_bps":v["half_spread_slippage_bps"],"gates":c["gates"],"promotion_blocker":v["promotion_blocker"]}; mp=work/"manifest.json"; wj(mp,m); core.upload_artifact(PROJECT,scope,"manifest.json",mp,"application/json; charset=utf-8")
    core.put_json(f"/checkpoints/super-rsi/crypto-30m-{a.venue}-v1",{"source":core.SOURCE,"status":"running","position":{"phase":"staged","scope":scope,"venue":a.venue},"dropbox_path":None,"last_error":None}); print(json.dumps({"stage":"ready","venue":a.venue,"scope":scope})); return 0

def shard(a):
    c=cfg(a.config); v=c["venues"][a.venue]; scope=v["scope"]; sid=int(a.shard); work=Path(tempfile.mkdtemp(prefix="crypto-shard-")); pkg=work/"pkg"; out=work/"symbols"; h=work/"helper"; pkg.mkdir(); out.mkdir(); h.mkdir(); m,l=package(scope,pkg); shutil.copy2(l["helper"],h/"exp.py"); pr=json.loads(l["profile"].read_text()); ass=[s for i,s in enumerate(pr["universe"]) if i%2==sid]; failed=[]
    for s in ass:
        last=core.run_symbol(l["engine"],l["profile"],h,s,out,5400); sp=out/s/f"summary-{s}.json"; ok=last["returncode"]==0 and sp.exists() and json.loads(sp.read_text()).get("status")=="OK"
        if not ok: failed.append(s); wj(out/s/"runner-error.json",last)
    ar=work/f"shard-{sid:02d}.tar.gz"; 
    with tarfile.open(ar,"w:gz") as tf: tf.add(out,arcname="symbols")
    st=work/f"shard-{sid:02d}.json"; wj(st,{"shard":sid,"failed_symbols":failed}); core.upload_artifact(PROJECT,scope,f"shards/shard-{sid:02d}.tar.gz",ar,"application/gzip"); core.upload_artifact(PROJECT,scope,f"shards/shard-{sid:02d}.json",st,"application/json; charset=utf-8"); print(json.dumps({"venue":a.venue,"shard":sid,"failed":failed})); return 0 if not failed else 2

def evaluate(a):
    c=cfg(a.config); v=c["venues"][a.venue]; scope=v["scope"]; work=Path(tempfile.mkdtemp(prefix="crypto-eval-")); pkg=work/"pkg"; sy=work/"symbols"; fi=work/"final"; pkg.mkdir(); sy.mkdir(); fi.mkdir(); m,l=package(scope,pkg); failed=[]
    for sid in (0,1):
        ar=work/f"shard-{sid:02d}.tar.gz"; st=work/f"shard-{sid:02d}.json"; core.download_artifact(PROJECT,scope,f"shards/shard-{sid:02d}.tar.gz",ar); core.download_artifact(PROJECT,scope,f"shards/shard-{sid:02d}.json",st); failed+=json.loads(st.read_text()).get("failed_symbols",[]); 
        with tarfile.open(ar,"r:gz") as tf: tf.extractall(work)
    if failed: raise RuntimeError(f"failed symbols {failed}")
    ev=subprocess.run(["python",str(l["evaluator"]),"--profile",str(l["profile"]),"--input",str(sy),"--out",str(fi)],capture_output=True,text=True,timeout=1800)
    if ev.returncode: raise RuntimeError(ev.stderr[-4000:])
    rep=json.loads((fi/"report.json").read_text()); rows=[json.loads(x) for x in (fi/"trades.jsonl").read_text().splitlines() if x.strip()]; fee=float(m["fee_bps_per_side"])/10000.0
    def netbps(r): return (((1.0+float(r["actual_return"]))*(1-fee)*(1-fee))-1.0)*10000.0
    vals=[netbps(r) for r in rows]; hold=[netbps(r) for r in rows if str(r.get("entry_time",""))>=c["holdout_start"]]; stress=[((1+x/10000.0)*(1-float(c["gates"]["stress_extra_rt_bps"])/10000.0)-1)*10000.0 for x in vals]
    base,ho,ss=met(vals),met(hold),met(stress); p=rep["primary"]
    flags={"coverage_all":p["ok_symbols"]==2,"trades":base["n"]>=c["gates"]["trades_min"],"pf":base["pf"] is not None and base["pf"]>=c["gates"]["actual_pf_min"],"mean":base["mean_bps"] is not None and base["mean_bps"]>=c["gates"]["actual_mean_bps_min"],"holdout_pf":ho["pf"] is not None and ho["pf"]>=c["gates"]["holdout_pf_min"],"holdout_mean":ho["mean_bps"] is not None and ho["mean_bps"]>0,"positive_symbols":p["positive_symbol_fraction"]>=c["gates"]["positive_symbol_fraction_min"],"median_symbol_pf":p["median_symbol_PF_ge5"] is not None and p["median_symbol_PF_ge5"]>=c["gates"]["median_symbol_pf_min"],"stress_pf":ss["pf"] is not None and ss["pf"]>=c["gates"]["stress_pf_min"],"stress_mean":ss["mean_bps"] is not None and ss["mean_bps"]>0}; tech=all(flags.values()); state="PROVISIONAL_"+m["promotion_blocker"] if tech else "FAIL"
    res={"schema":1,"venue":a.venue,"scope":scope,"base_fee_adjusted":base,"holdout_fee_adjusted":ho,"stress":ss,"fee_bps_per_side":m["fee_bps_per_side"],"synthetic_half_spread_slippage_bps":m["half_spread_slippage_bps"],"gate_flags":flags,"technical_pass":tech,"promotion_state":state,"limitations":["historical top-of-book not used","funding not modeled" if a.venue=="perp" else "spot fee fixed preregistered assumption"]}; rp=work/"crypto-30m-v1.json"; wj(rp,res); core.upload_artifact(PROJECT,scope,"research/crypto-30m-v1.json",rp,"application/json; charset=utf-8"); core.put_json(f"/checkpoints/super-rsi/crypto-30m-{a.venue}-v1",{"source":core.SOURCE,"status":"complete","position":{"phase":"evaluated","scope":scope,"technical_pass":tech,"promotion_state":state,"artifact_project":PROJECT,"artifact_scope":scope,"artifact_name":"research/crypto-30m-v1.json"},"dropbox_path":None,"last_error":None}); print(json.dumps(res,indent=2)); return 0

def main():
    ap=argparse.ArgumentParser(); sub=ap.add_subparsers(dest="cmd",required=True)
    for cmd in ("stage","shard","evaluate"):
        p=sub.add_parser(cmd); p.add_argument("--config",required=True); p.add_argument("--venue",choices=["spot","perp"],required=True); 
        if cmd=="shard": p.add_argument("--shard",type=int,required=True)
    a=ap.parse_args(); return globals()[a.cmd](a)
if __name__=="__main__": raise SystemExit(main())
