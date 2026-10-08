#!/usr/bin/env python3
"""Durable, source-complete-independent checkpoint of normalized bike geometry.

Snapshots live in a separate checkpoint workspace, never the final release
workspace. Uses verified R2 shards and protects any already-published D1 pointer.
"""
import datetime,hashlib,json,os,pathlib,shlex,sqlite3,subprocess
from r2_verified import put
ROOT=pathlib.Path("/opt/bike-niche-corpus")
INPUT=ROOT/"derived/geometry-index.sqlite3"
BASE=ROOT/"releases/normalized-geometry/checkpoints"
BASE.mkdir(parents=True,exist_ok=True)
ENV="/etc/vps-control/content-intelligence-bridge.env"
def run(cmd,timeout=1200):
 p=subprocess.run(cmd,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,timeout=timeout)
 if p.returncode:raise RuntimeError("COMMAND_FAILED "+str(cmd[:3])+": "+p.stdout[-600:])
 return p.stdout
def wr(cmd,timeout=200):
 shell="set -a; . "+shlex.quote(ENV)+"; set +a; /usr/local/bin/wrangler "+cmd
 return run(["bash","-c",shell],timeout)
def sha(p):
 h=hashlib.sha256()
 with open(p,"rb") as f:
  for b in iter(lambda:f.read(4*1024*1024),b""):h.update(b)
 return h.hexdigest()
def atomic(path,data):
 tmp=path.with_name(path.name+".tmp."+str(os.getpid()))
 tmp.write_text(json.dumps(data,ensure_ascii=False,indent=2))
 tmp.replace(path)
def quote(s):return "'"+str(s).replace("'","''")+"'"
def main():
 latest=BASE/"latest-checkpoint.json"
 prior=json.loads(latest.read_text()) if latest.exists() else {}
 inp=sqlite3.connect(INPUT,timeout=120)
 try:
  current=inp.execute("SELECT COUNT(*) FROM geometry").fetchone()[0]
  rejected=inp.execute("SELECT COUNT(*) FROM rejected_measurements").fetchone()[0]
 finally:inp.close()
 if prior and prior.get("measurements")==current and prior.get("outliers_audited")==rejected:
  print(json.dumps({"ok":True,"skipped":"UNCHANGED_MEASUREMENTS_AND_AUDIT","checkpoint":prior["checkpoint"]}))
  return
 stamp=datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
 dest=BASE/stamp;dest.mkdir(parents=True,exist_ok=True)
 snap=dest/"geometry-index.sqlite3"
 src=sqlite3.connect(INPUT,timeout=180)
 target=sqlite3.connect(snap,timeout=180)
 src.backup(target,pages=1600,sleep=0.05)
 target.close();src.close()
 check=sqlite3.connect(snap,timeout=90)
 if check.execute("PRAGMA quick_check").fetchone()[0]!="ok":raise RuntimeError("SQLITE_QUICK_CHECK_FAIL")
 n=check.execute("SELECT count(*) FROM geometry").fetchone()[0]
 audited=check.execute("SELECT count(*) FROM rejected_measurements").fetchone()[0]
 cov=[{"source":row[0],"measurements":row[1],"bike_pages":row[2]} for row in
   check.execute("SELECT source,count(*),count(distinct url) FROM geometry GROUP BY source")]
 check.close()
 state={"source":"bike-niche-normalized-geometry","checkpoint":stamp,
   "measurements":n,"outliers_audited":audited,
   "coverage":cov,"sqlite_sha256":sha(snap),"sqlite_bytes":snap.stat().st_size,
   "site_crawls_complete":False,
   "checkpoint_at":datetime.datetime.now(datetime.timezone.utc).isoformat()}
 manifest=dest/"manifest.json";atomic(manifest,state)
 archive=dest/("geometry-index-checkpoint-"+stamp+".tar.zst")
 run(["tar","-I","zstd -3","--sort=name","--mtime=@0","--owner=0","--group=0",
      "--numeric-owner","-cf",str(archive),"-C",str(dest),snap.name,manifest.name],1800)
 prefix="core/bike-niche/normalized-geometry/checkpoints/"+stamp
 file=put(archive,prefix+"/"+archive.name)
 man=put(manifest,prefix+"/manifest.json")
 detail={"phase":"checkpoint","bucket":"runner3-artifacts","artifact_r2_key":file["key"],
         "artifact_format":file.get("format","single-tar"),"r2_part_count":file.get("part_count",1),
         "sha256":file["sha256"],"bytes":file["bytes"],"measurements":n,"outliers_audited":audited}
 raw=json.dumps(detail,separators=(",",":"))
 sql=("INSERT INTO workflow_state(source,status,run_id,detail,updated_at) VALUES("
   "'bike-niche-normalized-geometry','checkpoint',"+quote(stamp)+","+quote(raw)+",CURRENT_TIMESTAMP)"
   " ON CONFLICT(source) DO UPDATE SET status=excluded.status,run_id=excluded.run_id,"
   "detail=excluded.detail,updated_at=CURRENT_TIMESTAMP "
   "WHERE workflow_state.status!='published';")
 wr("d1 execute runner3-core --remote --yes --json --command "+shlex.quote(sql))
 sql="SELECT status,run_id,detail FROM workflow_state WHERE source='bike-niche-normalized-geometry' LIMIT 1"
 rows=json.loads(wr("d1 execute runner3-core --remote --yes --json --command "+shlex.quote(sql)))[0]["results"]
 if not rows or (rows[0].get("status")=="checkpoint" and
     (rows[0]["run_id"]!=stamp or rows[0]["detail"]!=raw)):
  raise RuntimeError("D1_READBACK_FAIL")
 receipt={"ok":True,"checkpoint":stamp,"measurements":n,"outliers_audited":audited,
          "r2_archive":file,"r2_manifest":man,"d1_status":rows[0]["status"],
          "d1_readback_verified":True}
 atomic(dest/"receipt.json",receipt)
 atomic(latest,receipt)
 print(json.dumps(receipt,ensure_ascii=False))
if __name__=="__main__":main()
