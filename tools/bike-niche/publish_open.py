#!/usr/bin/env python3
import pathlib, subprocess, hashlib, json, shutil, datetime, tempfile, os, shlex, re
R=pathlib.Path("/opt/bike-niche-corpus"); S=R/"sources"; OUT=R/"releases"; OUT.mkdir(parents=True,exist_ok=True)
NAMES=["reaatech__bicycle-brands-models","dorianprill__dataset-bicycle-geometry","bikeindex__bike_data","bikeindex__bikebook"]
def run(cmd,timeout=300):
 p=subprocess.run(cmd,capture_output=True,text=True,timeout=timeout)
 if p.returncode: raise RuntimeError("command_failure:"+str(cmd[:4])+":"+p.stderr[-400:]+p.stdout[-400:])
 return p.stdout
def sha(p):
 h=hashlib.sha256()
 with open(p,'rb') as f:
  for b in iter(lambda:f.read(1048576),b''): h.update(b)
 return h.hexdigest()
commits=[]
for name in NAMES:
 d=S/name
 assert (d/".git").exists(),name
 commits.append({"name":name,"commit":run(["git","-C",str(d),"rev-parse","HEAD"]).strip()})
fingerprint=hashlib.sha256(json.dumps(commits,sort_keys=True).encode()).hexdigest()[:16]
version="open-v1-"+fingerprint
bundle=OUT/("bike-niche-open-sources-"+version+".tar.zst")
manifest=OUT/"open-sources-manifest.json"
if not manifest.exists() or json.loads(manifest.read_text()).get("version")!=version:
 manifest.write_text(json.dumps({"version":version,"dataset":"bicycle-niche-open-sources","sources":commits,"source_provenance":"Four public GitHub project snapshots. Separate from Biklo canonical corpus.","dataset_license_notice":"Each source retains original README/LICENSE; reuse follows source-specific license.","timestamp":datetime.datetime.now(datetime.timezone.utc).isoformat()},indent=2))
if not bundle.exists():
 args=["tar","-I","zstd -4","--exclude=.git","--sort=name","--owner=0","--group=0","--numeric-owner","--mtime=@0","-cf",str(bundle),"-C",str(R),"releases/open-sources-manifest.json"]
 for name in NAMES:args+=["-C",str(S),name]
 run(args,timeout=600)
digest=sha(bundle);size=bundle.stat().st_size
env='/etc/vps-control/content-intelligence-bridge.env';wr='/usr/local/bin/wrangler'
def cf(args,timeout=360):
 return run(["bash","-lc",f"set -a; . {shlex.quote(env)}; set +a; {wr} "+args],timeout)
bucket="runner3-artifacts";base="core/bike-niche/open-sources";key=f"{base}/releases/{version}/{bundle.name}"
def r2put(p,key):
 cf(f"r2 object put {shlex.quote(bucket+'/'+key)} --remote --file {shlex.quote(str(p))} --force",timeout=900)
 fd,path=tempfile.mkstemp(prefix="bike-r2-check.");os.close(fd)
 try:
  cf(f"r2 object get {shlex.quote(bucket+'/'+key)} --remote --file {shlex.quote(path)}",timeout=900)
  assert sha(path)==sha(p) and os.path.getsize(path)==p.stat().st_size, "R2_READBACK_MISMATCH"
 finally:os.unlink(path)
 return {"key":key,"sha256":sha(p),"bytes":p.stat().st_size,"readback":True}
rr=r2put(bundle,key)
manifestkey=f"{base}/releases/{version}/open-sources-manifest.json";rm=r2put(manifest,manifestkey)
state=R/"state"/"open-sources-published.json"
db="runner3-core";src="bike-niche-open-sources"
detail={"phase":"published_pending_telegram","bucket":bucket,"artifact_key":key,"manifest_key":manifestkey,"sha256":digest,"bytes":size,"sources":len(NAMES)}
def sqlq(s):return "'"+str(s).replace("'","''")+"'"
def d1(status):
 d={**detail,"phase":status}
 sql=f"INSERT INTO workflow_state(source,status,run_id,detail,updated_at) VALUES({sqlq(src)},{sqlq(status)},{sqlq(version)},{sqlq(json.dumps(d,separators=(',',':')))},CURRENT_TIMESTAMP) ON CONFLICT(source) DO UPDATE SET status=excluded.status,run_id=excluded.run_id,detail=excluded.detail,updated_at=CURRENT_TIMESTAMP;"
 cf(f"d1 execute {db} --remote --yes --json --command {shlex.quote(sql)}",timeout=120)
 out=cf(f"d1 execute {db} --remote --yes --json --command {shlex.quote('SELECT status,run_id,detail FROM workflow_state WHERE source='+sqlq(src)+' LIMIT 1;')}",timeout=120)
 rows=json.loads(out)[0]["results"]
 assert rows and rows[0]["status"]==status and rows[0]["run_id"]==version, "D1_READBACK_MISMATCH"
d1("published_pending_telegram")
tgt=pathlib.Path("/var/lib/telegram-upload/bike-niche");tgt.mkdir(parents=True,exist_ok=True)
copy=tgt/bundle.name;shutil.copy2(bundle,copy)
caption=f"BIKE NICHE — OPEN DATA SOURCES\nRelease: {version}\nGitHub: 4 source repositories\nSHA256: {digest}\n#dataset_bike #bike_database #open_sources"
try:
 t=run(["/opt/telegram-mtproto/run-node-secure.sh","/opt/telegram-mtproto/vps-control-data-upload.js",str(copy),caption],timeout=1000)
 lines=[x for x in t.splitlines() if x.strip().startswith("{")]
 reply=json.loads(lines[-1]);assert reply.get("ok") and reply.get("topic")=="Data",reply
finally:
 copy.unlink(missing_ok=True)
detail["telegram_message_id"]=reply["message_id"]
d1("published")
out={"version":version,"sources":commits,"bundle":str(bundle),"bytes":size,"sha256":digest,"r2":[rr,rm],"d1":"published","telegram_message_id":reply["message_id"],"telegram_topic":"VPS Control / Data"}
state.write_text(json.dumps(out,indent=2))
print(json.dumps(out,ensure_ascii=False))
