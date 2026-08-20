#!/usr/bin/env python3
import json
from pathlib import Path
from collections import defaultdict
from datetime import datetime, timezone

IN=Path("/tmp/all"); OUT=Path("/tmp/final"); OUT.mkdir(parents=True,exist_ok=True)
BPS=(4,6,8,10,12)
rows=[]
for p in sorted(IN.rglob("trades-*.jsonl")):
    for line in p.read_text().splitlines():
        if line.strip():rows.append(json.loads(line))
if not rows:raise SystemExit("no trades")

def year(ms):return datetime.fromtimestamp(ms/1000,tz=timezone.utc).year

def dd(seq):
    cur=peak=maxdd=0.0
    for x in seq:
        cur+=x; peak=max(peak,cur); maxdd=min(maxdd,cur-peak)
    return maxdd

def metrics(rs, field):
    vals=[float(r[field]) for r in sorted(rs,key=lambda x:(x["signal_time"],x["symbol"]))]
    n=len(vals)
    return {"trades":n,"total":sum(vals),"avg":sum(vals)/n if n else None,"dd":dd(vals)}

def portfolio_metrics(rs, field):
    g=defaultdict(list)
    for r in rs:g[int(r["signal_time"])].append(float(r[field]))
    vals=[sum(g[k])/len(g[k]) for k in sorted(g)]
    n=len(vals)
    return {"batches":n,"total":sum(vals),"avg_batch":sum(vals)/n if n else None,"dd":dd(vals),
            "positive_batch_pct":100*sum(x>0 for x in vals)/n if n else None,
            "max_batch_size":max((len(g[k]) for k in g),default=0)}

variants=sorted({r["variant"] for r in rows})
tfs=sorted({int(r["tf"]) for r in rows})
out={"schema":"wr-modular-trend-sweep-v1",
     "selection_policy":"No threshold optimization. Each variant changes one module. PASS requires net6 trade AvgR >0 and portfolio net6 >0 in both 2025 and 2026, with >=50 trades per year.",
     "results":{}}

for tf in tfs:
  out["results"][str(tf)]={}
  for v in variants:
    z=[r for r in rows if int(r["tf"])==tf and r["variant"]==v]
    rec={"all":{"gross":metrics(z,"R"),"portfolio_gross":portfolio_metrics(z,"R"),"cost":{},"portfolio_cost":{}},"years":{}}
    for b in BPS:
        rec["all"]["cost"][str(b)]=metrics(z,f"net{b}")
        rec["all"]["portfolio_cost"][str(b)]=portfolio_metrics(z,f"net{b}")
    for y in (2025,2026):
        zy=[r for r in z if year(int(r["signal_time"]))==y]
        yr={"gross":metrics(zy,"R"),"portfolio_gross":portfolio_metrics(zy,"R"),"cost":{},"portfolio_cost":{}}
        for b in BPS:
            yr["cost"][str(b)]=metrics(zy,f"net{b}")
            yr["portfolio_cost"][str(b)]=portfolio_metrics(zy,f"net{b}")
        rec["years"][str(y)]=yr
    y25=rec["years"]["2025"]; y26=rec["years"]["2026"]
    rec["pass_net6_both_years"]=(
        y25["cost"]["6"]["trades"]>=50 and y26["cost"]["6"]["trades"]>=50 and
        y25["cost"]["6"]["avg"]>0 and y26["cost"]["6"]["avg"]>0 and
        y25["portfolio_cost"]["6"]["total"]>0 and y26["portfolio_cost"]["6"]["total"]>0
    )
    out["results"][str(tf)][v]=rec

json.dump(out,open(OUT/"summary.json","w"),indent=2)
lines=["# Wave Rider Modular Trend Sweep","",
"Each variant changes one module only. Fixed TP retained; TP variants test 1.5R / 2.0R / 3.0R versus 2.3R baseline.",
"Primary decision metric: net @6bps and portfolio-normalized 1R per synchronized signal batch, split 2025 vs 2026.",""]
for tf in tfs:
    lines += [f"## {tf}m","",
              "| Variant | 2025 trades | 2025 net6 | 2025 port-R | 2026 trades | 2026 net6 | 2026 port-R | PASS |",
              "|---|---:|---:|---:|---:|---:|---:|:---:|"]
    for v in variants:
        r=out["results"][str(tf)][v]
        a=r["years"]["2025"]; b=r["years"]["2026"]
        lines.append(f"| {v} | {a['cost']['6']['trades']} | {a['cost']['6']['total']:.2f} | {a['portfolio_cost']['6']['total']:.2f} | {b['cost']['6']['trades']} | {b['cost']['6']['total']:.2f} | {b['portfolio_cost']['6']['total']:.2f} | {'YES' if r['pass_net6_both_years'] else 'NO'} |")
    lines.append("")
(OUT/"report.md").write_text("\n".join(lines))
print("\n".join(lines))
