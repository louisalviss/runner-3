#!/usr/bin/env python3
"""Reliable, retry-safe MTProto delivery of large R2-backed archives.

Large releases are split into small deterministic numbered parts to avoid
unreliable long single-file Telegram uploads. Each part has SHA256 and its
own checkpointed message id; the full SHA256 is retained for reassembly.
"""
import hashlib,json,math,os,pathlib,shutil,subprocess,time
ROOT=pathlib.Path("/var/lib/telegram-upload/bike-niche")
NODE="/opt/telegram-mtproto/run-node-secure.sh"
SCRIPT="/opt/telegram-mtproto/vps-control-data-upload.js"
PARTSIZE=3*1024*1024
def sha(p):
 h=hashlib.sha256()
 with open(p,"rb") as f:
  for block in iter(lambda:f.read(1024*1024),b""):h.update(block)
 return h.hexdigest()
def write_atomic(path,obj):
 path=pathlib.Path(path);temp=path.with_name(path.name+".tmp."+str(os.getpid()))
 temp.write_text(json.dumps(obj,indent=2,ensure_ascii=False),encoding="utf-8")
 temp.replace(path)
def send(path,caption):
 ROOT.mkdir(parents=True,exist_ok=True)
 staged=ROOT/path.name
 shutil.copy2(path,staged)
 try:
  cmd=[NODE,SCRIPT,str(staged),caption]
  p=subprocess.run(cmd,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=360)
  if p.returncode:
   raise RuntimeError("TELEGRAM_SEND_FAILED: "+p.stdout[-800:])
  lines=[x.strip() for x in p.stdout.splitlines() if x.strip().startswith("{")]
  if not lines:raise RuntimeError("TELEGRAM_NO_RECEIPT: "+p.stdout[-500:])
  d=json.loads(lines[-1])
  if not d.get("ok") or d.get("forum")!="VPS Control" or d.get("topic")!="Data":
   raise RuntimeError("TELEGRAM_ROUTE_MISMATCH: "+repr(d))
  return int(d["message_id"])
 finally:
  staged.unlink(missing_ok=True)
def prepare_parts(archive,folder):
 size=archive.stat().st_size
 num=math.ceil(size/PARTSIZE)
 parts=[]
 folder.mkdir(parents=True,exist_ok=True)
 with archive.open("rb") as stream:
  for i in range(num):
   data=stream.read(PARTSIZE)
   pname=f"{archive.name}.part-{i+1:03d}-of-{num:03d}"
   target=folder/pname
   digest=hashlib.sha256(data).hexdigest()
   if not target.exists() or target.stat().st_size!=len(data) or sha(target)!=digest:
    tmp=target.with_name(target.name+".tmp")
    tmp.write_bytes(data);tmp.replace(target)
   parts.append({"number":i+1,"total":num,"name":pname,"bytes":len(data),"sha256":digest})
 return parts
def upload_archive(archive,folder,caption):
 archive=pathlib.Path(archive);folder=pathlib.Path(folder)
 if not archive.exists() or not archive.is_file():raise RuntimeError("ARCHIVE_MISSING")
 totalsha=sha(archive)
 release_folder=folder/"telegram_parts"
 statefile=folder/"telegram-part-state.json"
 prev=json.loads(statefile.read_text()) if statefile.exists() else {}
 if prev and (prev.get("archive_sha256")!=totalsha or prev.get("archive_bytes")!=archive.stat().st_size):
  raise RuntimeError("PUBLISH_STATE_ARCHIVE_CHANGED")
 parts=prepare_parts(archive,release_folder)
 state={"archive":archive.name,"archive_sha256":totalsha,"archive_bytes":archive.stat().st_size,
        "part_bytes":PARTSIZE,"parts":parts,"message_ids":prev.get("message_ids",{}),
        "manifest_message_id":prev.get("manifest_message_id")}
 write_atomic(statefile,state)
 # One BWS credential load and one Telegram session for all remaining parts.
 # The Node worker commits each sent message ID atomically; resume skips it.
 cmd=[NODE,"/opt/telegram-mtproto/vps-control-data-batch.js",str(statefile),caption]
 process=subprocess.Popen(cmd,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,
                          text=True,bufsize=1)
 last=None
 try:
  for line in process.stdout:
   line=line.strip()
   if not line:continue
   if line.startswith("{"):
    try:
     item=json.loads(line)
     if item.get("ok") and item.get("topic")=="Data" and item.get("part_count"):
      last=item
    except json.JSONDecodeError:pass
   print(line,flush=True)
  rc=process.wait(timeout=30)
 except Exception:
  process.kill()
  process.wait()
  raise
 if rc!=0 or not last:
  raise RuntimeError("TELEGRAM_BATCH_FAILED rc="+str(rc)+"; check per-part checkpoint")
 state=json.loads(statefile.read_text())
 if len(state.get("message_ids",{}))!=len(parts):
  raise RuntimeError("TELEGRAM_BATCH_INCOMPLETE")
 return last
