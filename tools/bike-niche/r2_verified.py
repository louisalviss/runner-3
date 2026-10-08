#!/usr/bin/env python3
"""Verified R2 artifact writer: direct for small files; deterministic shards for large files.

Each shard is uploaded to the existing R2 bucket and read back before the
release manifest is committed. No new R2 bucket or credentials are needed.
"""
import hashlib,json,os,pathlib,shlex,subprocess,tempfile,time
ENV="/etc/vps-control/content-intelligence-bridge.env"
BUCKET="runner3-artifacts"
LIMIT=30*1024*1024
def sha(path):
 h=hashlib.sha256()
 with open(path,"rb") as stream:
  for block in iter(lambda:stream.read(4*1024*1024),b""):h.update(block)
 return h.hexdigest()
def run(args,seconds=1200):
 p=subprocess.run(args,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,timeout=seconds)
 if p.returncode:
  raise RuntimeError("R2_CMD_FAILED:"+p.stdout[-450:])
 return p.stdout
def cf(args,seconds=1200):
 shell="set -a; . "+shlex.quote(ENV)+"; set +a; /usr/local/bin/wrangler "+args
 return run(["bash","-c",shell],seconds)
def atomic(p,obj):
 p=pathlib.Path(p)
 tmp=p.with_name(p.name+".tmp."+str(os.getpid()))
 tmp.write_text(json.dumps(obj,indent=2,ensure_ascii=False),encoding="utf-8")
 tmp.replace(p)
def direct(local,key,retries=3):
 local=pathlib.Path(local)
 local_sha=sha(local);local_size=local.stat().st_size
 target=BUCKET+"/"+key
 last=None
 for attempt in range(1,retries+1):
  fd,tmp=tempfile.mkstemp(prefix="bikeniche-r2-readback-");os.close(fd)
  try:
   cf("r2 object put "+shlex.quote(target)+" --remote --file "+shlex.quote(str(local))+" --force",1200)
   cf("r2 object get "+shlex.quote(target)+" --remote --file "+shlex.quote(tmp),1200)
   if os.stat(tmp).st_size!=local_size or sha(tmp)!=local_sha:
    raise RuntimeError("R2_READBACK_SHA_OR_SIZE_MISMATCH")
   return {"key":key,"sha256":local_sha,"bytes":local_size,"verified":True}
  except Exception as ex:
   last=ex
   if attempt>=retries:break
   time.sleep(2**attempt)
  finally:
   pathlib.Path(tmp).unlink(missing_ok=True)
 raise RuntimeError("R2_UPLOAD_FAILED_AFTER_RETRIES "+str(last)[:380])
def put(local,key):
 local=pathlib.Path(local)
 n=local.stat().st_size
 if n<=LIMIT:
  return direct(local,key)
 folder=local.parent/"r2-shards"/local.name
 folder.mkdir(parents=True,exist_ok=True)
 parts=[]
 with local.open("rb") as source:
  i=0
  while True:
   chunk=source.read(LIMIT)
   if not chunk:break
   i+=1
   name=local.name+".r2part-"+str(i).zfill(4)
   dest=folder/name
   digest=hashlib.sha256(chunk).hexdigest()
   if not dest.exists() or dest.stat().st_size!=len(chunk) or sha(dest)!=digest:
    temp=dest.with_name(dest.name+".tmp")
    temp.write_bytes(chunk);temp.replace(dest)
   shard_key=key+".parts/"+name
   receipt=direct(dest,shard_key)
   parts.append({"number":i,**receipt})
   print(json.dumps({"r2_verified_part":i,"key":shard_key,"total_bytes":len(chunk)}),flush=True)
 if not parts:raise RuntimeError("NO_R2_SHARDS")
 artifact_sha=sha(local)
 mf={"format":"r2-sharded-tar","bucket":BUCKET,"artifact":local.name,
     "artifact_sha256":artifact_sha,"artifact_bytes":n,"chunk_bytes":LIMIT,
     "parts":parts,"restore":"Download parts in ascending order and concatenate; verify artifact_sha256."}
 manifest=local.parent/(local.name+".r2-parts-manifest.json")
 atomic(manifest,mf)
 manifest_key=key+".r2-parts-manifest.json"
 verified_mf=direct(manifest,manifest_key)
 return {"key":manifest_key,"sha256":artifact_sha,"bytes":n,"verified":True,
         "format":"r2-sharded-tar","part_count":len(parts),"manifest_sha256":verified_mf["sha256"],
         "archive_name":local.name}
