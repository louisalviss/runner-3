#!/usr/bin/env python3
"""Safe, bandwidth-bounded source SQLite checkpoint while crawler remains active."""
import datetime,hashlib,json,os,pathlib,shlex,sqlite3,subprocess,tempfile,sys
ROOT=pathlib.Path("/opt/bike-niche-corpus")
SOURCE=sys.argv[1] if len(sys.argv)>1 else ""
assert SOURCE in ("geometrygeeks","bikeinsights","rideinsights","sram"),"INVALID_SOURCE"
BASE=ROOT/"source-checkpoints"/SOURCE;BASE.mkdir(parents=True,exist_ok=True)
DB=ROOT/"crawls"/(SOURCE+".sqlite3")
INVENTORY=ROOT/"inventory"/(SOURCE+"-urls.jsonl")
STATE=BASE/"latest-checkpoint.json"
BUCKET="runner3-artifacts";ENV="/etc/vps-control/content-intelligence-bridge.env"
def now():return datetime.datetime.now(datetime.timezone.utc)
def sha(p):
 h=hashlib.sha256()
 with open(p,"rb") as f:
  for v in iter(lambda:f.read(4*1024*1024),b""):h.update(v)
 return h.hexdigest()
def atomic(p,data):
 tmp=pathlib.Path(str(p)+".tmp."+str(os.getpid()))
 tmp.write_text(json.dumps(data,ensure_ascii=False,indent=2));tmp.replace(p)
def run(c,timeout=900):
 p=subprocess.run(c,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,timeout=timeout)
 if p.returncode:raise RuntimeError(str(c[:3])+" FAILED: "+p.stdout[-1200:])
 return p.stdout
def wr(cmd,timeout=1200):
 c="set -a; . "+shlex.quote(ENV)+"; set +a; /usr/local/bin/wrangler "+cmd
 return run(["bash","-c",c],timeout)
def quote(s):return "'"+str(s).replace("'","''")+"'"
def put(p,key):
 remote=BUCKET+"/"+key
 wr("r2 object put "+shlex.quote(remote)+" --remote --file "+shlex.quote(str(p))+" --force",1600)
 fd,tmp=tempfile.mkstemp(prefix="bike-snap-verify-");os.close(fd)
 try:
  wr("r2 object get "+shlex.quote(remote)+" --remote --file "+shlex.quote(tmp),1600)
  if sha(tmp)!=sha(p) or os.stat(tmp).st_size!=p.stat().st_size:raise RuntimeError("R2_READBACK_MISMATCH")
 finally:pathlib.Path(tmp).unlink(missing_ok=True)
 return {"key":key,"bytes":p.stat().st_size,"sha256":sha(p),"readback_verified":True}
def main():
 con=sqlite3.connect(DB,timeout=120)
 queue=dict(con.execute("select status,count(*) from queue group by status"))
 n=queue.get("done",0)
 if STATE.exists():
  prev=json.loads(STATE.read_text())
  if int(prev.get("done",0))>=n:
   print(json.dumps({"ok":True,"skipped":"NO_NEW_SOURCE_ROWS","done":n,"previous":prev.get("checkpoint")}));return
 stamp=now().strftime("%Y%m%dT%H%M%SZ")
 d=BASE/stamp;d.mkdir(parents=True,exist_ok=True)
 snap=d/(SOURCE+".sqlite3")
 target=sqlite3.connect(snap,timeout=120);con.backup(target,pages=1000,sleep=0.05);target.close()
 con.close()
 check=sqlite3.connect(snap)
 if check.execute("pragma quick_check").fetchone()[0]!="ok":raise RuntimeError("SQLITE_CHECKPOINT_CORRUPT")
 snapshot_queue=dict(check.execute("select status,count(*) from queue group by status"))
 actual=check.execute("select count(*) from records").fetchone()[0]
 check.close()
 details={"source":SOURCE,"snapshot":stamp,"rows":actual,"queue":snapshot_queue,
          "sqlite_sha256":sha(snap),"sqlite_bytes":snap.stat().st_size,
          "inventory_sha256":sha(INVENTORY),"created_at":now().isoformat()}
 manifest=d/"manifest.json";atomic(manifest,details)
 tarball=d/(SOURCE+"-inprogress-"+stamp+".tar.zst")
 run(["tar","-I","zstd -3","--sort=name","--mtime=@0","--owner=0","--group=0","--numeric-owner",
      "-cf",str(tarball),"-C",str(d),snap.name,manifest.name,"-C",str(ROOT/"inventory"),INVENTORY.name],1200)
 prefix="core/bike-niche/sources/"+SOURCE+"/checkpoints/"+stamp
 package=put(tarball,prefix+"/"+tarball.name)
 man=put(manifest,prefix+"/manifest.json")
 detail={"phase":"crawling","checkpoint_r2_key":package["key"],"checkpoint_sha256":package["sha256"],
         "checkpoint_rows":actual,"queue":snapshot_queue,"not_final_release":True}
 raw=json.dumps(detail,separators=(",",":"))
 sql="INSERT INTO workflow_state(source,status,run_id,detail,updated_at) VALUES("+quote("bike-niche-"+SOURCE)+",'crawling',"+quote(stamp)+","+quote(raw)+",CURRENT_TIMESTAMP) ON CONFLICT(source) DO UPDATE SET status=excluded.status,run_id=excluded.run_id,detail=excluded.detail,updated_at=CURRENT_TIMESTAMP;"
 wr("d1 execute runner3-core --remote --yes --json --command "+shlex.quote(sql),180)
 check_sql="SELECT status,run_id,detail FROM workflow_state WHERE source="+quote("bike-niche-"+SOURCE)+" LIMIT 1"
 got=json.loads(wr("d1 execute runner3-core --remote --yes --json --command "+shlex.quote(check_sql),180))[0]["results"]
 if not got or got[0].get("status")!="crawling" or got[0].get("run_id")!=stamp or got[0].get("detail")!=raw:raise RuntimeError("D1_READBACK_MISMATCH")
 receipt={"ok":True,"checkpoint":stamp,"source":SOURCE,"done":actual,"r2":package,"manifest":man,"d1_readback":True}
 atomic(STATE,receipt)
 print(json.dumps(receipt,ensure_ascii=False))
main()
