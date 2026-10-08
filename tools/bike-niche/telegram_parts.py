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
 for part in parts:
  key=part["name"]
  if str(key) in state["message_ids"]:continue
  item=release_folder/key
  msg="\n".join([
   caption,
   f"Archive: {archive.name}",
   f"Part {part['number']}/{part['total']}",
   f"Full SHA256: {totalsha}",
   f"Part SHA256: {part['sha256']}",
   "Restore: concatenate all numbered parts in order"
  ])
  mid=send(item,msg)
  state["message_ids"][key]=mid
  write_atomic(statefile,state)
  print(json.dumps({"part_sent":part["number"],"parts_total":part["total"],"message_id":mid}),flush=True)
  time.sleep(1.5)
 receipt={
   "archive":archive.name,"archive_sha256":totalsha,"archive_bytes":archive.stat().st_size,
   "part_bytes":PARTSIZE,"parts":[{**p,"telegram_message_id":state["message_ids"][p["name"]]} for p in parts],
   "reassemble_command":f"cat {archive.name}.part-* > {archive.name}",
   "r2_durable_master":True
 }
 manifest=folder/"telegram-parts-manifest.json"
 write_atomic(manifest,receipt)
 if not state["manifest_message_id"]:
  cap="\n".join(["BIKE NICHE — PARTS MANIFEST",f"Archive: {archive.name}",
   f"Parts: {len(parts)}",f"SHA256: {totalsha}", "Follow numbered parts to restore .tar.zst"])
  state["manifest_message_id"]=send(manifest,cap)
  write_atomic(statefile,state)
 receipt.update({
    "message_id":state["manifest_message_id"],
    "manifest_message_id":state["manifest_message_id"],
    "part_message_ids":[state["message_ids"][p["name"]] for p in parts],
    "part_count":len(parts),
    "bytes":archive.stat().st_size,
    "topic":"Data","forum":"VPS Control"
 })
 return receipt
