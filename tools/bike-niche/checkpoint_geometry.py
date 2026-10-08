#!/usr/bin/env python3
"""Durable checkpoint of incrementally normalized bicycle geometry metrics."""
import datetime,hashlib,json,os,pathlib,shlex,sqlite3,subprocess,tempfile
ROOT=pathlib.Path("/opt/bike-niche-corpus")
INPUT=ROOT/"derived/geometry-index.sqlite3"
DEST=ROOT/"releases/normalized-geometry"
DEST.mkdir(parents=True,exist_ok=True)
CFENV="/etc/vps-control/content-intelligence-bridge.env"
BUCKET="runner3-artifacts"
def run(c,timeout=600):
 p=subprocess.run(c,text=True,capture_output=True,timeout=timeout)
 if p.returncode:raise RuntimeError(str(c[:3])+":"+p.stdout[-1200:]+p.stderr[-1200:])
 return p.stdout
def sha(p):
 h=hashlib.sha256()
 with open(p,"rb") as f:
  for b in iter(lambda:f.read(4*1048576),b""):h.update(b)
 return h.hexdigest()
def wr(args,timeout=900):
 c="set -a; . "+shlex.quote(CFENV)+"; set +a; /usr/local/bin/wrangler "+args
 return run(["bash","-lc",c],timeout)
def quote(x):return "'"+str(x).replace("'","''")+"'"
def r2(p,key):
 target=BUCKET+"/"+key
 wr("r2 object put "+shlex.quote(target)+" --remote --file "+shlex.quote(str(p))+" --force",1100)
 fd,t=tempfile.mkstemp(prefix="bike-index-r2-verify-");os.close(fd)
 try:
  wr("r2 object get "+shlex.quote(target)+" --remote --file "+shlex.quote(t),1100)
  assert sha(t)==sha(p) and os.stat(t).st_size==p.stat().st_size,"R2_SHA256_OR_LENGTH_MISMATCH"
 finally:os.unlink(t)
 return {"bucket":BUCKET,"key":key,"sha256":sha(p),"bytes":p.stat().st_size,"readback_verified":True}
def main():
 src=sqlite3.connect(INPUT,timeout=100)
 stamp=datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
 snap=DEST/"geometry-index.sqlite3"
 dst=sqlite3.connect(snap,timeout=100)
 src.backup(dst);dst.close();src.close()
 dc=sqlite3.connect(snap)
 assert dc.execute("PRAGMA quick_check").fetchone()[0]=="ok"
 counts=dc.execute("SELECT source,count(*) measurements,count(distinct url) pages FROM geometry GROUP BY source").fetchall()
 n=dc.execute("SELECT count(*) FROM geometry").fetchone()[0]
 dc.close()
 manifest=DEST/"manifest.json"
 state={"release_id":stamp,"status":"checkpoint","source":"bike-niche-normalized-geometry","measurements":n,"coverage":[{"source":s,"measurements":nm,"bike_pages":pg} for s,nm,pg in counts],"db_sha256":sha(snap),"db_bytes":snap.stat().st_size,"checkpoint_at":datetime.datetime.now(datetime.timezone.utc).isoformat(),"site_crawls_complete":False}
 manifest.write_text(json.dumps(state,ensure_ascii=False,indent=2))
 out=DEST/("geometry-index-checkpoint-"+stamp+".tar.zst")
 run(["tar","-I","zstd -3","--sort=name","--mtime=@0","--owner=0","--group=0","--numeric-owner","-cf",str(out),"-C",str(DEST),snap.name,manifest.name],1000)
 prefix="core/bike-niche/normalized-geometry/checkpoints/"+stamp
 file=r2(out,prefix+"/"+out.name)
 man=r2(manifest,prefix+"/manifest.json")
 detail={"phase":"checkpoint","r2_bucket":BUCKET,"r2_key":file["key"],"sha256":file["sha256"],"bytes":file["bytes"],"measurements":n,"sources":3}
 raw=json.dumps(detail,separators=(",",":"))
 sql="INSERT INTO workflow_state(source,status,run_id,detail,updated_at) VALUES('bike-niche-normalized-geometry','checkpoint',"+quote(stamp)+","+quote(raw)+",CURRENT_TIMESTAMP) ON CONFLICT(source) DO UPDATE SET status=excluded.status,run_id=excluded.run_id,detail=excluded.detail,updated_at=CURRENT_TIMESTAMP;"
 wr("d1 execute runner3-core --remote --yes --json --command "+shlex.quote(sql),180)
 sel="SELECT status,run_id,detail FROM workflow_state WHERE source='bike-niche-normalized-geometry' LIMIT 1"
 db=json.loads(wr("d1 execute runner3-core --remote --yes --json --command "+shlex.quote(sel),180))[0]["results"]
 assert db and db[0]["status"]=="checkpoint" and db[0]["run_id"]==stamp and db[0]["detail"]==raw,"D1_READBACK_MISMATCH"
 receipt={"checkpoint":stamp,"r2":file,"manifest":man,"d1":"checkpoint_readback_verified","measurements":n,"source_coverage":state["coverage"]}
 (DEST/"checkpoint-receipt.json").write_text(json.dumps(receipt,ensure_ascii=False,indent=2))
 print(json.dumps(receipt,ensure_ascii=False))
main()
