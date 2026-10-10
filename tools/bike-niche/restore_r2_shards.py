#!/usr/bin/env python3
"""Reconstruct a verified sharded bicycle-niche R2 artifact from its R2 manifest.

Does not depend on local publisher files. Reads one remote manifest, retrieves
each R2 part, verifies per-part digest and final whole-archive SHA256/length.
"""
import argparse,hashlib,json,os,pathlib,shlex,subprocess,tempfile
BUCKET="runner3-artifacts"
ENV="/etc/vps-control/content-intelligence-bridge.env"
def sha(path):
 h=hashlib.sha256()
 with open(path,"rb") as f:
  for block in iter(lambda:f.read(4*1024*1024),b""):h.update(block)
 return h.hexdigest()
def cf(args,seconds=900):
 cmd="set -a; . "+shlex.quote(ENV)+"; set +a; /usr/local/bin/wrangler "+args
 p=subprocess.run(["bash","-c",cmd],capture_output=True,text=True,timeout=seconds)
 if p.returncode:raise RuntimeError("R2_GET_FAILED "+p.stderr[-550:]+p.stdout[-550:])
 return p.stdout
def get(key,target):
 if not key.startswith("core/bike-niche/") or ".." in key.split("/"):
  raise RuntimeError("INVALID_DATASET_R2_KEY")
 cf("r2 object get "+shlex.quote(BUCKET+"/"+key)+" --remote --file "+shlex.quote(str(target)),900)
 return target
def main():
 parser=argparse.ArgumentParser()
 parser.add_argument("r2_manifest_key",help="Key under runner3-artifacts/")
 parser.add_argument("--destination",required=True)
 args=parser.parse_args()
 outdir=pathlib.Path(args.destination)
 outdir.mkdir(parents=True,exist_ok=True)
 with tempfile.TemporaryDirectory(prefix="bikeniche-r2-restore-") as tmp:
  tmpdir=pathlib.Path(tmp)
  manifestfile=get(args.r2_manifest_key,tmpdir/"manifest.json")
  manifest=json.loads(manifestfile.read_text())
  layout=manifest.get("format") or manifest.get("kind")
  if layout not in ("r2-sharded-tar","inprogress-checkpoint"):
   raise RuntimeError("MANIFEST_FORMAT_UNSUPPORTED")
  parts=manifest.get("parts") or []
  if not 1<=len(parts)<=3000:raise RuntimeError("INVALID_PART_COUNT")
  archive_name=manifest.get("artifact") or manifest.get("archive")
  expected_sha=manifest.get("artifact_sha256") or manifest.get("archive_sha256")
  expected_bytes=manifest.get("artifact_bytes") or manifest.get("archive_bytes")
  if not expected_sha or not isinstance(expected_bytes,int):
   raise RuntimeError("MANIFEST_MISSING_WHOLE_DIGEST_OR_SIZE")
  if not archive_name or pathlib.Path(archive_name).name!=archive_name or "/" in archive_name:
   raise RuntimeError("INVALID_ARTIFACT_NAME")
  dest=outdir/archive_name
  stage=outdir/(archive_name+".incomplete")
  digest=hashlib.sha256();size=0
  try:
   with open(stage,"wb") as stream:
    for index,part in enumerate(parts,1):
     if part.get("number")!=index or not (part.get("verified") or part.get("readback_verified")):
      raise RuntimeError("SHARD_ORDER_OR_VALIDATION_FLAG_MISSING")
     blob=get(part["key"],tmpdir/("part-"+str(index)))
     n=blob.stat().st_size;part_sha=sha(blob)
     if n!=part["bytes"] or part_sha!=part["sha256"]:
      raise RuntimeError("PART_SHA_SIZE_MISMATCH "+str(index))
     with blob.open("rb") as inp:
      while True:
       data=inp.read(4*1024*1024)
       if not data:break
       stream.write(data);digest.update(data);size+=len(data)
     blob.unlink()
     print(json.dumps({"verified_part":index,"of":len(parts),"bytes":n}),flush=True)
   if digest.hexdigest()!=expected_sha or size!=expected_bytes:
    raise RuntimeError("WHOLE_ARCHIVE_SHA_SIZE_MISMATCH")
   stage.replace(dest)
  except BaseException:
   stage.unlink(missing_ok=True)
   raise
  print(json.dumps({"ok":True,"archive":str(dest),"bytes":size,"sha256":digest.hexdigest(),"parts":len(parts)}))
if __name__=="__main__":main()
