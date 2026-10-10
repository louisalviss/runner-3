#!/usr/bin/env python3
"""Consistent, retry-safe source SQLite checkpoint. Store large backups as verified R2 shards."""
import datetime,hashlib,json,os,pathlib,shlex,sqlite3,subprocess,tempfile,sys
ROOT=pathlib.Path("/opt/bike-niche-corpus")
SOURCE=sys.argv[1] if len(sys.argv)>1 else ""
assert SOURCE in ("geometrygeeks","bikeinsights","rideinsights","sram"),"INVALID_SOURCE"
BASE=ROOT/"source-checkpoints"/SOURCE;BASE.mkdir(parents=True,exist_ok=True)
DB=ROOT/"crawls"/(SOURCE+".sqlite3")
INVENTORY=ROOT/"inventory"/(SOURCE+"-urls.jsonl")
LATEST=BASE/"latest-checkpoint.json"
PENDING=BASE/"pending-checkpoint.json"
BUCKET="runner3-artifacts";ENV="/etc/vps-control/content-intelligence-bridge.env"
SHARD_BYTES=30*1024*1024
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
 if p.returncode:raise RuntimeError("COMMAND_FAILED "+str(c[:2])+" "+p.stdout[-500:])
 return p.stdout
def wr(cmd,timeout=1200):
 c="set -a; . "+shlex.quote(ENV)+"; set +a; /usr/local/bin/wrangler "+cmd
 return run(["bash","-c",c],timeout)
def quote(s):return "'"+str(s).replace("'","''")+"'"
def put(p,key):
 remote=BUCKET+"/"+key
 wr("r2 object put "+shlex.quote(remote)+" --remote --file "+shlex.quote(str(p))+" --force",600)
 fd,tmp=tempfile.mkstemp(prefix="bike-source-r2-verification-");os.close(fd)
 try:
  wr("r2 object get "+shlex.quote(remote)+" --remote --file "+shlex.quote(tmp),600)
  if sha(tmp)!=sha(p) or os.stat(tmp).st_size!=p.stat().st_size:raise RuntimeError("R2_READBACK_MISMATCH "+key)
 finally:pathlib.Path(tmp).unlink(missing_ok=True)
 return {"key":key,"bytes":p.stat().st_size,"sha256":sha(p),"readback_verified":True}
def get_existing_or_snapshot():
 if PENDING.exists():
  st=json.loads(PENDING.read_text())
  stamp=st["checkpoint"];d=BASE/stamp
  package=d/(SOURCE+"-inprogress-"+stamp+".tar.zst")
  if not package.exists() or sha(package)!=st["archive_sha256"]:raise RuntimeError("UNUSABLE_PENDING_BACKUP")
  return st,package,d,False
 con=sqlite3.connect(DB,timeout=120)
 queue=dict(con.execute("select status,count(*) from queue group by status"))
 n=queue.get("done",0)
 if LATEST.exists():
  prev=json.loads(LATEST.read_text())
  if int(prev.get("done",0))>=n:
   con.close()
   return {"skipped":"NO_NEW_SOURCE_ROWS","done":n,"previous":prev["checkpoint"]},None,None,False
 stamp=now().strftime("%Y%m%dT%H%M%SZ")
 d=BASE/stamp;d.mkdir(parents=True,exist_ok=True)
 snap=d/(SOURCE+".sqlite3")
 target=sqlite3.connect(snap,timeout=120);con.backup(target,pages=1000,sleep=0.05);target.close();con.close()
 check=sqlite3.connect(snap)
 if check.execute("pragma quick_check").fetchone()[0]!="ok":raise RuntimeError("SQLITE_CHECKPOINT_CORRUPT")
 snapshot_queue=dict(check.execute("select status,count(*) from queue group by status"))
 actual=check.execute("select count(*) from records").fetchone()[0]
 check.close()
 details={"source":SOURCE,"snapshot":stamp,"rows":actual,"queue":snapshot_queue,
          "sqlite_sha256":sha(snap),"sqlite_bytes":snap.stat().st_size,
          "inventory_sha256":sha(INVENTORY),"created_at":now().isoformat()}
 manifest=d/"manifest.json";atomic(manifest,details)
 package=d/(SOURCE+"-inprogress-"+stamp+".tar.zst")
 run(["tar","-I","zstd -3","--sort=name","--mtime=@0","--owner=0","--group=0","--numeric-owner",
      "-cf",str(package),"-C",str(d),snap.name,manifest.name,"-C",str(ROOT/"inventory"),INVENTORY.name],1200)
 st={"checkpoint":stamp,"done":actual,"queue":snapshot_queue,
      "archive_sha256":sha(package),"archive_bytes":package.stat().st_size}
 atomic(PENDING,st)
 return st,package,d,True
def shards(archive,d):
 out=[]
 with archive.open("rb") as stream:
  idx=0
  while True:
   b=stream.read(SHARD_BYTES)
   if not b:break
   idx+=1
   target=d/(archive.name+".part-"+str(idx).zfill(4))
   digest=hashlib.sha256(b).hexdigest()
   if not target.exists() or target.stat().st_size!=len(b) or sha(target)!=digest:
    p=target.with_name(target.name+".tmp")
    p.write_bytes(b);p.replace(target)
   out.append((target,digest))
 if not out:raise RuntimeError("EMPTY_ARCHIVE")
 return out
def main():
 st,package,d,created=get_existing_or_snapshot()
 if package is None:print(json.dumps({"ok":True,**st}));return
 stamp=st["checkpoint"];prefix="core/bike-niche/sources/"+SOURCE+"/checkpoints/"+stamp
 parts=shards(package,d)
 stored=[]
 for i,(part,digest) in enumerate(parts,1):
  key=prefix+"/"+part.name
  receipt=put(part,key)
  stored.append({"number":i,**receipt})
  print(json.dumps({"r2_part_ok":i,"total":len(parts),"bytes":receipt["bytes"]}),flush=True)
 archive_manifest={"source":SOURCE,"checkpoint":stamp,"kind":"inprogress-checkpoint",
   "archive":package.name,"archive_sha256":st["archive_sha256"],"archive_bytes":st["archive_bytes"],
   "parts":stored,"part_bytes":SHARD_BYTES,
   "restore":"Download each part in ascending order and concatenate them, then verify archive_sha256."}
 manifest=d/"parts-manifest.json";atomic(manifest,archive_manifest)
 result_manifest=put(manifest,prefix+"/parts-manifest.json")
 source_manifest=put(d/"manifest.json",prefix+"/source-manifest.json")
 details={"phase":"crawling","checkpoint_r2_manifest":result_manifest["key"],
          "checkpoint_sha256":st["archive_sha256"],"checkpoint_rows":st["done"],
          "checkpoint_parts":len(parts),"queue":st["queue"],"not_final_release":True}
 raw=json.dumps(details,separators=(",",":"))
 sql=("INSERT INTO workflow_state(source,status,run_id,detail,updated_at) VALUES("
      +quote("bike-niche-"+SOURCE)+",'crawling',"+quote(stamp)+","+quote(raw)
      +",CURRENT_TIMESTAMP) ON CONFLICT(source) DO UPDATE SET "
      "status=excluded.status,run_id=excluded.run_id,detail=excluded.detail,updated_at=CURRENT_TIMESTAMP "
      "WHERE workflow_state.status!='published';")
 wr("d1 execute runner3-core --remote --yes --json --command "+shlex.quote(sql),180)
 check_sql="SELECT status,run_id,detail FROM workflow_state WHERE source="+quote("bike-niche-"+SOURCE)+" LIMIT 1"
 got=json.loads(wr("d1 execute runner3-core --remote --yes --json --command "+shlex.quote(check_sql),180))[0]["results"]
 if not got or (got[0].get("status")=="crawling" and (got[0].get("run_id")!=stamp or got[0].get("detail")!=raw)):
  raise RuntimeError("D1_READBACK_MISMATCH")
 receipt={"ok":True,"checkpoint":stamp,"source":SOURCE,"done":st["done"],
          "r2_archive_manifest":result_manifest,"r2_source_manifest":source_manifest,
          "r2_parts":len(parts),"full_archive_sha256":st["archive_sha256"],
          "d1_status":got[0]["status"],"d1_readback":True}
 atomic(LATEST,receipt)
 PENDING.unlink(missing_ok=True)
 print(json.dumps(receipt,ensure_ascii=False))
if __name__=="__main__":main()
