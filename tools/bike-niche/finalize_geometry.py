#!/usr/bin/env python3
"""Release the final size-by-size geometry index when all source crawls are published."""
import datetime,hashlib,json,os,pathlib,shlex,sqlite3,subprocess,tempfile
ROOT=pathlib.Path("/opt/bike-niche-corpus")
DIR=ROOT/"releases/normalized-geometry";DIR.mkdir(parents=True,exist_ok=True)
STATE=DIR/"publication-state.json"
SOURCE_NAMES=("bikeinsights","rideinsights","geometrygeeks")
BUCKET="runner3-artifacts";BASE="core/bike-niche/normalized-geometry"
ENV="/etc/vps-control/content-intelligence-bridge.env"
def run(cmd,timeout=1200):
 p=subprocess.run(cmd,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,timeout=timeout)
 if p.returncode:raise RuntimeError("FAILED: "+str(cmd[:3])+" "+p.stdout[-1200:])
 return p.stdout
def wr(s,timeout=900):
 cmd="set -a; . "+shlex.quote(ENV)+"; set +a; /usr/local/bin/wrangler "+s
 return run(["bash","-c",cmd],timeout)
def sha(p):
 h=hashlib.sha256()
 with open(p,"rb") as f:
  for b in iter(lambda:f.read(4*1024*1024),b""):h.update(b)
 return h.hexdigest()
def atomic(p,obj):
 q=pathlib.Path(str(p)+".tmp."+str(os.getpid()))
 q.write_text(json.dumps(obj,ensure_ascii=False,indent=2));q.replace(p)
def sq(v):return "'"+str(v).replace("'","''")+"'"
def publish_d1(status,release,detail):
 raw=json.dumps(detail,ensure_ascii=False,separators=(",",":"))
 sql=("INSERT INTO workflow_state(source,status,run_id,detail,updated_at) VALUES("
      "'bike-niche-normalized-geometry',"+sq(status)+","+sq(release)+","+sq(raw)+",CURRENT_TIMESTAMP) "
      "ON CONFLICT(source) DO UPDATE SET status=excluded.status,run_id=excluded.run_id,detail=excluded.detail,updated_at=CURRENT_TIMESTAMP;")
 wr("d1 execute runner3-core --remote --yes --json --command "+shlex.quote(sql),180)
 select="SELECT status,run_id,detail FROM workflow_state WHERE source='bike-niche-normalized-geometry' LIMIT 1;"
 result=json.loads(wr("d1 execute runner3-core --remote --yes --json --command "+shlex.quote(select),180))
 items=result[0].get("results") or []
 if not items or items[0].get("status")!=status or items[0].get("run_id")!=release or items[0].get("detail")!=raw:
  raise RuntimeError("D1_READBACK_FAILED")
def upload(local,key):
 remote=BUCKET+"/"+key
 wr("r2 object put "+shlex.quote(remote)+" --remote --file "+shlex.quote(str(local))+" --force",1800)
 fd,temp=tempfile.mkstemp(prefix="bike-geom-verify-");os.close(fd)
 try:
  wr("r2 object get "+shlex.quote(remote)+" --remote --file "+shlex.quote(temp),1800)
  if sha(temp)!=sha(local) or os.stat(temp).st_size!=local.stat().st_size:raise RuntimeError("R2_READBACK_MISMATCH")
 finally:
  pathlib.Path(temp).unlink(missing_ok=True)
 return {"key":key,"bytes":local.stat().st_size,"sha256":sha(local),"verified":True}
def done(name):
 rel=ROOT/"releases"/name/"publication-state.json"
 if not rel.exists():raise RuntimeError("SOURCE_NOT_PUBLISHED: "+name)
 state=json.loads(rel.read_text())
 if state.get("phase")!="published":raise RuntimeError("SOURCE_NOT_PUBLISHED: "+name)
 con=sqlite3.connect(ROOT/"crawls"/(name+".sqlite3"),timeout=60)
 q=dict(con.execute("select status,count(*) from queue group by status"))
 con.close()
 if any(q.get(k,0) for k in ("pending","retry","in_progress")):raise RuntimeError("SOURCE_NOT_TERMINAL: "+name)
 return {"source":name,"release":state["release_id"],"queue":q}
def main():
 if STATE.exists():
  st=json.loads(STATE.read_text())
  if st.get("phase")=="published":
   print(json.dumps({"ok":True,"already_published":True,"release":st["release_id"],"telegram_message_id":st["telegram_message_id"]}))
   return
 else:st={}
 sources=[done(x) for x in SOURCE_NAMES]
 if not st.get("release_id"):
  st["release_id"]=datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
  st["phase"]="preparing"
  atomic(STATE,st)
 release=st["release_id"]
 run(["python3",str(ROOT/"normalize_geometry.py")],900)
 live=ROOT/"derived/geometry-index.sqlite3"
 snap=DIR/"geometry-index.sqlite3"
 arch=DIR/("bike-niche-geometry-final-"+release+".tar.zst")
 manifest=DIR/"manifest.json"
 if not arch.exists() or not st.get("sha256") or sha(arch)!=st.get("sha256"):
  src=sqlite3.connect(live,timeout=180)
  dst=sqlite3.connect(snap,timeout=180);src.backup(dst);dst.close();src.close()
  con=sqlite3.connect(snap)
  if con.execute("pragma quick_check").fetchone()[0]!="ok":raise RuntimeError("QUICK_CHECK_FAILED")
  n=con.execute("select count(*) from geometry").fetchone()[0]
  rows=[{"source":x[0],"measurements":x[1],"pages":x[2]} for x in con.execute("select source,count(*),count(distinct url) from geometry group by source")]
  con.close()
  d={"dataset":"bike-niche-geometry-normalized","release":release,"measurements":n,"sources":sources,
     "measurements_by_source":rows,"source_db_sha256":sha(snap),"source_db_bytes":snap.stat().st_size,
     "format":"SQLite geometry(source,url,title,frame_size,metric,value,unit,raw_value)",
     "provenance":"bikeinsights, rideinsights, geometrygeeks independently crawled; retain per-source origins",
     "created_at":datetime.datetime.now(datetime.timezone.utc).isoformat()}
  atomic(manifest,d)
  run(["tar","-I","zstd -4","--sort=name","--owner=0","--group=0","--numeric-owner","--mtime=@0",
       "-cf",str(arch),"-C",str(DIR),snap.name,manifest.name],1300)
  st.update({"sha256":sha(arch),"bytes":arch.stat().st_size,"measurements":n,"phase":"packaged"})
  atomic(STATE,st)
 prefix=BASE+"/releases/"+release
 package=upload(arch,prefix+"/"+arch.name)
 manifest_obj=upload(manifest,prefix+"/manifest.json")
 current=DIR/"CURRENT.json"
 atomic(current,{"dataset":"bike-niche-geometry-normalized","release":release,"r2_key":package["key"],"sha256":package["sha256"],"measurements":st["measurements"]})
 current_obj=upload(current,BASE+"/CURRENT.json")
 detail={"phase":"published_pending_telegram","bucket":BUCKET,"package":package["key"],"sha256":package["sha256"],"bytes":package["bytes"],"measurements":st["measurements"],"sources":sources}
 publish_d1("published_pending_telegram",release,detail)
 from telegram_parts import upload_archive
 cap="BIKE NICHE — NORMALIZED GEOMETRY FINAL\nRelease: "+release+"\nMetrics: "+str(st["measurements"])+"\nSHA256: "+package["sha256"]+"\n#dataset_bike #geometry"
 out=upload_archive(arch,DIR,cap)
 detail.update({"phase":"published","telegram_manifest_id":out["message_id"],"telegram_part_ids":out["part_message_ids"]})
 publish_d1("published",release,detail)
 receipt={"ok":True,"release":release,"measurements":st["measurements"],"r2":[package,manifest_obj,current_obj],"d1":"published","telegram_manifest_id":out["message_id"],"telegram_parts":out["part_message_ids"]}
 atomic(DIR/"publish-receipt.json",receipt)
 upload(DIR/"publish-receipt.json",prefix+"/publish-receipt.json")
 st.update({"phase":"published","published_at":datetime.datetime.now(datetime.timezone.utc).isoformat(),"telegram_message_id":out["message_id"]})
 atomic(STATE,st)
 print(json.dumps(receipt))
if __name__=="__main__":main()
