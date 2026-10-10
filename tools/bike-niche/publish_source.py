#!/usr/bin/env python3
"""Publish a completed, provenance-isolated bike niche public-source corpus."""
import datetime,hashlib,json,os,pathlib,shlex,shutil,sqlite3,subprocess,tempfile,sys
ROOT=pathlib.Path("/opt/bike-niche-corpus")
NAME=sys.argv[1] if len(sys.argv)>1 else ""
assert NAME in ("bikeinsights","rideinsights","sram","geometrygeeks")
DIR=ROOT/"releases"/NAME;DIR.mkdir(parents=True,exist_ok=True)
DB=ROOT/"crawls"/(NAME+".sqlite3")
INV=ROOT/"inventory"/(NAME+"-urls.jsonl")
STATE=DIR/"publication-state.json"
ENV="/etc/vps-control/content-intelligence-bridge.env"
BUCKET="runner3-artifacts"
PREFIX="core/bike-niche/sources/"+NAME
def run(args,timeout=300):
 p=subprocess.run(args,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=timeout)
 if p.returncode:raise RuntimeError(f"command {args[:3]} returned {p.returncode}: {p.stdout[-1500:]}")
 return p.stdout
def sha(p):
 h=hashlib.sha256()
 with open(p,"rb") as f:
  for b in iter(lambda:f.read(4*1048576),b""):h.update(b)
 return h.hexdigest()
def atomic(p,data):
 q=p.with_name(p.name+".tmp");q.write_text(json.dumps(data,indent=2,ensure_ascii=False));q.replace(p)
def cf(args,timeout=500):
 # Non-login shell: /root/.profile prints unrelated warnings on stdout,
 # otherwise corrupting --json parsing even when Wrangler succeeds.
 return run(["bash","-c","set -a; . "+shlex.quote(ENV)+"; set +a; /usr/local/bin/wrangler "+args],timeout)
def r2_put(p,key):
 # Bounded chunks + SHA256 readback avoid R2 Gateway 502 on large archives.
 from r2_verified import put
 return put(p,key)
def sqlquote(x):return "'"+str(x).replace("'","''")+"'"
def d1(status,stamp,detail):
 src="bike-niche-"+NAME
 raw=json.dumps(detail,ensure_ascii=False,separators=(",",":"))
 sql=f"INSERT INTO workflow_state(source,status,run_id,detail,updated_at) VALUES({sqlquote(src)},{sqlquote(status)},{sqlquote(stamp)},{sqlquote(raw)},CURRENT_TIMESTAMP) ON CONFLICT(source) DO UPDATE SET status=excluded.status,run_id=excluded.run_id,detail=excluded.detail,updated_at=CURRENT_TIMESTAMP;"
 # Wrangler can return empty stdout for successful D1 mutations even with --json.
 # The authoritative success criterion is the subsequent remote readback.
 cf("d1 execute runner3-core --remote --yes --json --command "+shlex.quote(sql),160)
 check=f"SELECT status,run_id,detail FROM workflow_state WHERE source={sqlquote(src)} LIMIT 1"
 output=cf("d1 execute runner3-core --remote --yes --json --command "+shlex.quote(check),160)
 try:
  payload=json.loads(output)
  rows=payload[0]["results"]
 except Exception as exc:
  raise RuntimeError("D1_READBACK_NON_JSON: "+repr(output[:400])) from exc
 assert rows and rows[0]["status"]==status and rows[0]["run_id"]==stamp and rows[0]["detail"]==raw,"D1_READBACK_MISMATCH"
def tg_upload(p,caption):
 # Small deterministic shards keep Telegram MTProto transfers bounded and
 # checkpointed. Large full-archive uploads have timed out on this VPS.
 from telegram_parts import upload_archive
 return upload_archive(p,DIR,caption)
def main():
 con=sqlite3.connect(DB,timeout=90)
 q=dict(con.execute("SELECT status,COUNT(*) FROM queue GROUP BY status").fetchall())
 busy=sum(q.get(x,0) for x in ("pending","retry","in_progress"))
 assert busy==0,("NOT_TERMINAL",q)
 errors=q.get("error",0)
 assert errors<=max(5,int(sum(q.values())*0.01)),("TOO_MANY_ERRORS",q)
 n=con.execute("SELECT COUNT(*) FROM records").fetchone()[0]
 assert n>0,"NO_RECORDS"
 if STATE.exists():s=json.loads(STATE.read_text())
 else:
  stamp=datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
  s={"release_id":stamp};atomic(STATE,s)
 stamp=s["release_id"];release=f"{PREFIX}/releases/{stamp}"
 snap=DIR/(NAME+".sqlite3");archive=DIR/(NAME+"-"+stamp+".tar.zst")
 manifest=DIR/"manifest.json"
 if not archive.exists() or not s.get("sha256") or sha(archive)!=s.get("sha256"):
  a=sqlite3.connect(snap);con.backup(a);a.close()
  contents={
   "source":NAME,"release":stamp,"inventory_sha256":sha(INV),"queue":q,
   "records":n,"snapshot_sha256":sha(snap),"source_pages_stored_as_compressed_html":True,
   "storage":{"bucket":BUCKET,"prefix":release,"telegram":"VPS Control/Data"}
  }
  atomic(manifest,contents)
  run(["tar","-I","zstd -4","--sort=name","--mtime=@0","--owner=0","--group=0","--numeric-owner","-cf",str(archive),"-C",str(DIR),snap.name,manifest.name,"-C",str(ROOT/"inventory"),INV.name],1400)
  s.update({"sha256":sha(archive),"bytes":archive.stat().st_size,"count":n})
  atomic(STATE,s)
 con.close()
 a=r2_put(archive,f"{release}/{archive.name}")
 b=r2_put(manifest,f"{release}/manifest.json")
 curr=DIR/"CURRENT.json";atomic(curr,{"source":NAME,"release":stamp,"artifact_key":a["key"],"sha256":a["sha256"],"records":n,"artifact_format":a.get("format","single-tar"),"part_count":a.get("part_count",1)})
 c=r2_put(curr,f"{PREFIX}/CURRENT.json")
 details={"phase":"published_pending_telegram","bucket":BUCKET,"r2_key":a["key"],"sha256":a["sha256"],"bytes":a["bytes"],"records":n,"queue":q,"artifact_format":a.get("format","single-tar"),"r2_part_count":a.get("part_count",1)}
 d1("published_pending_telegram",stamp,details)
 cap=f"BIKE NICHE — {NAME.upper()}\nRelease: {stamp}\nRecords: {n}\nSHA256: {a['sha256']}\n#dataset_bike #src_{NAME}"
 sent=tg_upload(archive,cap)
 details.update({"phase":"published","telegram_message_id":sent["message_id"],
                 "telegram_part_message_ids":sent["part_message_ids"],
                 "telegram_part_count":sent["part_count"]})
 d1("published",stamp,details)
 receipt={"source":NAME,"status":"published","counts":q,"r2":[a,b,c],"d1":"published",
          "telegram_message_id":sent["message_id"],
          "telegram_part_message_ids":sent["part_message_ids"],
          "telegram_part_count":sent["part_count"]}
 atomic(DIR/"publish-receipt.json",receipt)
 r2_put(DIR/"publish-receipt.json",f"{release}/publish-receipt.json")
 s.update({"phase":"published","telegram_message_id":sent["message_id"],"published_at":datetime.datetime.now(datetime.timezone.utc).isoformat()});atomic(STATE,s)
 print(json.dumps(receipt,ensure_ascii=False))
main()
