#!/usr/bin/env python3
"""VPS reboot/resume guard for one-time bike niche acquisitions.

Runs briefly from systemd timer; DOES NOT act on blocked challenge sources.
Does not repeat completed publishes, start concurrent fetchers or reset terminal errors.
"""
import datetime,json,pathlib,sqlite3,subprocess
ROOT=pathlib.Path("/opt/bike-niche-corpus")
SOURCES=("bikeinsights","rideinsights","sram","geometrygeeks")
LEGACY={"bikeinsights":"bike-niche-bikeinsights.service","rideinsights":"bike-niche-ride-and-sram.service","sram":"bike-niche-ride-and-sram.service","geometrygeeks":"bike-niche-geometrygeeks.service"}

def active(unit):
 p=subprocess.run(["systemctl","is-active","--quiet",unit],timeout=15)
 return p.returncode==0

def report(source,decision,**kwargs):
 print(json.dumps({"source":source,"decision":decision,**kwargs},ensure_ascii=False),flush=True)

def load_json(p):
 try:return json.loads(p.read_text())
 except: return {}

for source in SOURCES:
 unit="bike-niche-resume-"+source+".service"
 db=ROOT/"crawls"/(source+".sqlite3")
 discovery=load_json(ROOT/"state"/"geometrygeeks-directory-state.json") if source=="geometrygeeks" else {}
 if not db.exists():
  if source!="geometrygeeks":
   report(source,"no_checkpoint");continue
  # Directory inventory may have been interrupted before the crawler DB existed.
  q={};remaining=1;n=int(discovery.get("page",0))
 else:
  con=sqlite3.connect(db,timeout=10)
  q=dict(con.execute("SELECT status,COUNT(*) FROM queue GROUP BY status").fetchall())
  con.close()
  remaining=sum(q.get(k,0) for k in ("pending","retry","in_progress"))
  n=q.get("done",0)
 if (ROOT/"releases"/source/"publication-state.json").exists():
  state=load_json(ROOT/"releases"/source/"publication-state.json")
  if state.get("phase")=="published":
   report(source,"already_published",done=n);continue
 dedicated_delivery=source in ("rideinsights","sram") and active("bike-niche-release-delivery.service")
 if active(LEGACY[source]) or active(unit) or dedicated_delivery:
  report(source,"already_running",done=n,remaining=remaining);continue
 if (ROOT/"state"/(source+"-blocked.json")).exists():
  report(source,"blocked_manual_review",done=n);continue
 if source=="geometrygeeks" and not discovery.get("done"):
  stopped=str(discovery.get("stopped",""))
  if "BLOCKED" in stopped or "CHALLENGE" in stopped:
   report(source,"directory_challenge_hold",reason=stopped,done=n);continue
 info=ROOT/"state"/(source+"-resume.json")
 prior=load_json(info)
 past_done=int(prior.get("last_done",-1))
 repeated=int(prior.get("stalled_attempts",0)) if n<=past_done else 0
 # Publishing can fail transiently even after the crawl is complete; allow a few
 # additional bounded attempts without recrawling data. Active crawl restarts
 # remain capped tightly.
 max_restarts=6 if remaining==0 else 3
 if repeated>=max_restarts:
  report(source,"max_stalled_restarts",done=n,attempts=repeated,terminal=remaining==0);continue
 # Both queue-terminal (publish retry) and active pending sources may resume.
 next_info={"last_done":n,"stalled_attempts":repeated+1,"last_resumed_at":datetime.datetime.now(datetime.timezone.utc).isoformat()}
 info.write_text(json.dumps(next_info,indent=2))
 if source=="geometrygeeks" and not db.exists():
  pipeline=[str(ROOT/"run_geometrygeeks.sh")]
 else:
  pipeline=[str(ROOT/"run_pipeline.sh"),source]
 cmd=["systemd-run","--unit=bike-niche-resume-"+source,"--collect","--property=MemoryMax=1024M","--property=CPUQuota=60%","/bin/bash",*pipeline]
 p=subprocess.run(cmd,capture_output=True,text=True,timeout=25)
 report(source,"resume_started" if p.returncode==0 else "resume_failed",rc=p.returncode,message=(p.stdout+p.stderr)[-280:],done=n,remaining=remaining)
