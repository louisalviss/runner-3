#!/usr/bin/env python3
"""VPS reboot/resume guard for one-time bike niche acquisitions.

Runs briefly from systemd timer; DOES NOT act on blocked challenge sources.
Does not repeat completed publishes, start concurrent fetchers or reset terminal errors.
"""
import datetime,json,pathlib,sqlite3,subprocess
ROOT=pathlib.Path("/opt/bike-niche-corpus")
SOURCES=("bikeinsights","rideinsights","sram")
LEGACY={"bikeinsights":"bike-niche-bikeinsights.service","rideinsights":"bike-niche-ride-and-sram.service","sram":"bike-niche-ride-and-sram.service"}

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
 if not db.exists():
  report(source,"no_checkpoint");continue
 con=sqlite3.connect(db,timeout=10)
 q=dict(con.execute("SELECT status,COUNT(*) FROM queue GROUP BY status").fetchall())
 con.close()
 remaining=sum(q.get(k,0) for k in ("pending","retry","in_progress"))
 n=q.get("done",0)
 if (ROOT/"releases"/source/"publication-state.json").exists():
  state=load_json(ROOT/"releases"/source/"publication-state.json")
  if state.get("phase")=="published":
   report(source,"already_published",done=n);continue
 if active(LEGACY[source]) or active(unit):
  report(source,"already_running",done=n,remaining=remaining);continue
 if (ROOT/"state"/(source+"-blocked.json")).exists():
  report(source,"blocked_manual_review",done=n);continue
 info=ROOT/"state"/(source+"-resume.json")
 prior=load_json(info)
 past_done=int(prior.get("last_done",-1))
 repeated=int(prior.get("stalled_attempts",0)) if n<=past_done else 0
 if repeated>=3:
  report(source,"max_stalled_restarts",done=n,attempts=repeated);continue
 # Both queue-terminal (publish retry) and active pending sources may resume.
 next_info={"last_done":n,"stalled_attempts":repeated+1,"last_resumed_at":datetime.datetime.now(datetime.timezone.utc).isoformat()}
 info.write_text(json.dumps(next_info,indent=2))
 cmd=["systemd-run","--unit=bike-niche-resume-"+source,"--collect","--property=MemoryMax=1024M","--property=CPUQuota=60%","/bin/bash",str(ROOT/"run_pipeline.sh"),source]
 p=subprocess.run(cmd,capture_output=True,text=True,timeout=25)
 report(source,"resume_started" if p.returncode==0 else "resume_failed",rc=p.returncode,message=(p.stdout+p.stderr)[-280:],done=n,remaining=remaining)
