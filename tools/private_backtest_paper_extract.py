#!/usr/bin/env python3
from __future__ import annotations
import argparse, heapq, json, statistics, tempfile
from datetime import datetime, timezone
from pathlib import Path
import private_backtest_worker_v2 as core

PROJECT="private-backtest"
def dt(v):
    s=str(v); s=s[:-1]+"+00:00" if s.endswith("Z") else s; x=datetime.fromisoformat(s); return (x if x.tzinfo else x.replace(tzinfo=timezone.utc)).astimezone(timezone.utc)
def pf(v):
    gp=sum(x for x in v if x>0); gl=-sum(x for x in v if x<0); return gp/gl if gl>0 else (999.0 if gp>0 else None)
def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--scope",required=True); ap.add_argument("--cutoff",required=True); ap.add_argument("--slots",type=int,default=40); a=ap.parse_args()
    w=Path(tempfile.mkdtemp(prefix="paper-extract-")); tp=w/"trades.jsonl"; rp=w/"report.json"; core.download_artifact(PROJECT,a.scope,"final/trades.jsonl",tp); core.download_artifact(PROJECT,a.scope,"final/report.json",rp); report=json.loads(rp.read_text()); primary=set(report["primary_symbols"]); cut=dt(a.cutoff)
    rows=[]
    for i,line in enumerate(tp.read_text().splitlines()):
        if not line.strip(): continue
        r=json.loads(line); sym=str(r.get("symbol","")).upper()
        if sym not in primary: continue
        en=dt(r["entry_time"]); ex=dt(r["exit_time"])
        if en<cut: continue
        rows.append({"idx":i,"symbol":sym,"entry":en,"exit":ex,"bps":float(r["actual_return_bps"]),"row":r})
    rows.sort(key=lambda x:(x["entry"],x["symbol"],x["idx"])); active=[]; accepted=[]; skipped=[]; seq=0
    for t in rows:
        while active and active[0][0] <= t["entry"]: heapq.heappop(active)
        if len(active) < a.slots:
            seq+=1; heapq.heappush(active,(t["exit"],seq)); accepted.append(t)
        else: skipped.append(t)
    vals=[t["bps"] for t in accepted]
    out={"schema":1,"scope":a.scope,"cutoff":a.cutoff,"slots":a.slots,"fill_mode":"Dukascopy exact historical next-bar ASK entry / BID exit reconstruction","closed_candidates":len(rows),"accepted_closed_trades":len(accepted),"skipped_closed_trades":len(skipped),"accepted_pf":pf(vals),"accepted_mean_bps":statistics.fmean(vals) if vals else None,"accepted_win_rate_pct":100*sum(x>0 for x in vals)/len(vals) if vals else None,"records":[{"symbol":t["symbol"],"signal_entry":t["row"].get("signal_entry"),"entry_time":t["row"].get("entry_time"),"entry_quote":t["row"].get("actual_entry"),"entry_spread_bps":t["row"].get("entry_spread_bps"),"signal_exit":t["row"].get("signal_exit"),"exit_time":t["row"].get("exit_time"),"exit_quote":t["row"].get("actual_exit"),"exit_spread_bps":t["row"].get("exit_spread_bps"),"return_bps":t["bps"]} for t in accepted],"limitations":["Layer-1 market-data paper reconstruction only; not broker paper fills","Open positions are not emitted by frozen engine, so live slot occupancy and MTM are not yet authoritative","Latency, rejected orders and market impact require broker-paper layer"]}
    p=w/"paper-sim-layer1.json"; p.write_text(json.dumps(out,ensure_ascii=False,indent=2)+"\n"); core.upload_artifact(PROJECT,a.scope,"research/paper-sim-layer1.json",p,"application/json; charset=utf-8"); core.put_json("/checkpoints/super-rsi/paper-sim-layer1-v1",{"source":core.SOURCE,"status":"active","position":{"phase":"layer1_closed_trade_reconstruction","scope":a.scope,"slots":a.slots,"accepted_closed_trades":len(accepted),"artifact_project":PROJECT,"artifact_scope":a.scope,"artifact_name":"research/paper-sim-layer1.json","broker_paper_pending":True},"dropbox_path":None,"last_error":None}); print(json.dumps({k:v for k,v in out.items() if k!="records"},indent=2))
if __name__=="__main__": main()
