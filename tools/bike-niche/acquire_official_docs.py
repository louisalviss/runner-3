#!/usr/bin/env python3
import requests,pathlib,json,hashlib,datetime,os,shlex,subprocess,tempfile,urllib.parse,re,shutil
from bs4 import BeautifulSoup
ROOT=pathlib.Path("/opt/bike-niche-corpus");D=ROOT/"official-docs";D.mkdir(parents=True,exist_ok=True)
OUT=ROOT/"releases"/"official-docs";OUT.mkdir(parents=True,exist_ok=True)
ENV="/etc/vps-control/content-intelligence-bridge.env"
SOURCES=[
 ("shimano","Compatibility_en.pdf","https://productinfo.shimano.com/pdfs/product/latest/Compatibility_en.pdf"),
 ("shimano","Specifications_en.pdf","https://productinfo.shimano.com/pdfs/product/latest/Specifications_en.pdf"),
 ("shimano","Line-up_chart_en.pdf","https://productinfo.shimano.com/pdfs/product/latest/Line-up_chart_en.pdf")
]
def sha(p):
 h=hashlib.sha256()
 with open(p,"rb") as f:
  for b in iter(lambda:f.read(1048576),b""):h.update(b)
 return h.hexdigest()
def run(args,timeout=900):
 p=subprocess.run(args,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,timeout=timeout)
 if p.returncode:raise RuntimeError("CMD_FAILED:"+str(args[:3])+":"+p.stdout[-1500:])
 return p.stdout
def cf(args,timeout=900):
 return run(["bash","-lc","set -a; . "+shlex.quote(ENV)+"; set +a; /usr/local/bin/wrangler "+args],timeout)
def atomic(p,o):
 tmp=p.with_name(p.name+".tmp");tmp.write_text(json.dumps(o,ensure_ascii=False,indent=2));tmp.replace(p)
def grab(brand,title,url):
 folder=D/brand;folder.mkdir(parents=True,exist_ok=True)
 name=re.sub(r"[^a-zA-Z0-9_.-]","_",title)
 dest=folder/name
 if dest.exists() and dest.stat().st_size>100 and dest.open("rb").read(4)==b"%PDF":
  return {"source":brand,"name":name,"url":url,"sha256":sha(dest),"bytes":dest.stat().st_size,"cached":True}
 resp=requests.get(url,timeout=(20,120),stream=True,headers={"User-Agent":"BikeCatalogResearch/1.0"})
 if resp.status_code!=200:raise RuntimeError("HTTP_"+str(resp.status_code)+" "+url)
 temp=dest.with_suffix(dest.suffix+".tmp")
 n=0
 with temp.open("wb") as f:
  for chunk in resp.iter_content(chunk_size=1024*1024):
   if not chunk:continue
   n+=len(chunk)
   if n>160*1048576:
    temp.unlink(missing_ok=True)
    raise RuntimeError("DOCUMENT_TOO_LARGE "+url)
   f.write(chunk)
 with temp.open("rb") as f:
  if f.read(4)!=b"%PDF":raise RuntimeError("NOT_PDF "+url)
 temp.replace(dest)
 return {"source":brand,"name":name,"url":url,"sha256":sha(dest),"bytes":dest.stat().st_size}
def sqlq(x):return "'"+str(x).replace("'","''")+"'"
def r2put(p,key):
 name="runner3-artifacts/"+key
 cf("r2 object put "+shlex.quote(name)+" --remote --file "+shlex.quote(str(p))+" --force")
 fd,tmp=tempfile.mkstemp(prefix="bike-doc-r2-");os.close(fd)
 try:
  cf("r2 object get "+shlex.quote(name)+" --remote --file "+shlex.quote(tmp))
  assert sha(tmp)==sha(p) and os.path.getsize(tmp)==p.stat().st_size,"R2_MISMATCH"
 finally:os.unlink(tmp)
 return {"key":key,"sha256":sha(p),"bytes":p.stat().st_size,"verified":True}
def d1(st,version,detail):
 source="bike-niche-official-docs";raw=json.dumps(detail,ensure_ascii=False,separators=(",",":"))
 sql=f"INSERT INTO workflow_state(source,status,run_id,detail,updated_at) VALUES({sqlq(source)},{sqlq(st)},{sqlq(version)},{sqlq(raw)},CURRENT_TIMESTAMP) ON CONFLICT(source) DO UPDATE SET status=excluded.status,run_id=excluded.run_id,detail=excluded.detail,updated_at=CURRENT_TIMESTAMP"
 cf("d1 execute runner3-core --remote --yes --json --command "+shlex.quote(sql))
 sel="SELECT status,run_id FROM workflow_state WHERE source="+sqlq(source)+" LIMIT 1"
 j=json.loads(cf("d1 execute runner3-core --remote --yes --json --command "+shlex.quote(sel)))
 assert j[0]["results"][0]["status"]==st
def main():
 # Enumerate first-party SRAM public compatibility chart documents; dedupe URLs.
 urls=[]
 base="https://www.sram.com/en/service/manuals--documents/compatability-map"
 for page in (1,2,3,4):
  url=base+"?filters=language%7CEnglish&page="+str(page)+"&showRecent=false"
  h=requests.get(url,timeout=35,headers={"User-Agent":"BikeCatalogResearch/1.0"})
  if h.status_code!=200:continue
  soup=BeautifulSoup(h.text,"html.parser")
  for a in soup.select('a[href*=".pdf"]'):
   u=urllib.parse.urljoin(h.url,a.get("href",""))
   if "/globalassets/document-hierarchy/compatibility-map/" not in u:continue
   # Omit clearly non-English localized duplicates.
   name=urllib.parse.urlparse(u).path.lower().split("/")[-1]
   if any(t in name for t in ("_fr",".fr.pdf","_sp","_es",".de.pdf","_de","francais","deutsch","espanol","freno-de-disco","identifzierung-von")):continue
   urls.append(u)
 for u in sorted(set(urls)):
  SOURCES.append(("sram",urllib.parse.urlparse(u).path.split("/")[-1],u))
 rows=[]
 for src,name,url in SOURCES:
  try:
   row=grab(src,name,url);rows.append(row)
   print(json.dumps({"downloaded":src+"/"+name,"bytes":row["bytes"],"cached":row.get("cached",False)}),flush=True)
  except Exception as e:
   rows.append({"source":src,"name":name,"url":url,"status":"FAILED","error":str(e)[:300]})
   print(json.dumps(rows[-1]),flush=True)
 good=[x for x in rows if "sha256" in x]
 assert len(good)>=3,("INSUFFICIENT_DOCS",rows)
 version=hashlib.sha256(json.dumps([(x["url"],x["sha256"]) for x in good],sort_keys=True).encode()).hexdigest()[:16]
 release="official-compat-"+version
 manifest=OUT/"official-docs-manifest.json"
 atomic(manifest,{"release":release,"sources":rows,"successful":len(good),"failed":len(rows)-len(good),"source_provenance":"Manufacturer published technical PDFs only","downloaded_at":datetime.datetime.now(datetime.timezone.utc).isoformat()})
 package=OUT/("bike-compatibility-"+release+".tar.zst")
 if not package.exists():
  run(["tar","-I","zstd -4","--sort=name","--mtime=@0","--owner=0","--group=0","--numeric-owner","-cf",str(package),"-C",str(ROOT),"releases/official-docs/official-docs-manifest.json","official-docs"],1500)
 prefix="core/bike-niche/official-docs/releases/"+release
 archive=r2put(package,prefix+"/"+package.name)
 man=r2put(manifest,prefix+"/manifest.json")
 meta={"phase":"published_pending_telegram","bucket":"runner3-artifacts","artifact_key":archive["key"],"sha256":archive["sha256"],"bytes":archive["bytes"],"docs":len(good)}
 d1("published_pending_telegram",release,meta)
 tg=pathlib.Path("/var/lib/telegram-upload/bike-niche");tg.mkdir(parents=True,exist_ok=True)
 dst=tg/package.name;shutil.copy2(package,dst)
 try:
  caption=f"BIKE NICHE — OFFICIAL COMPATIBILITY DOCS\nShimano + SRAM · {len(good)} PDFs\nRelease: {release}\nSHA256: {archive['sha256']}\n#dataset_bike #compatibility"
  out=run(["/opt/telegram-mtproto/run-node-secure.sh","/opt/telegram-mtproto/vps-control-data-upload.js",str(dst),caption],2500)
  reply=json.loads([x for x in out.splitlines() if x.startswith("{")][-1])
  assert reply.get("ok") and reply.get("topic")=="Data"
 finally:dst.unlink(missing_ok=True)
 meta["phase"]="published";meta["telegram_message_id"]=reply["message_id"]
 d1("published",release,meta)
 result={"release":release,"documents":len(good),"failed":len(rows)-len(good),"bytes":archive["bytes"],"sha256":archive["sha256"],"r2":archive,"manifest":man,"d1":"published","telegram_message_id":reply["message_id"]}
 atomic(ROOT/"state"/"official-docs-acquisition.json",result)
 print(json.dumps({"published":result},ensure_ascii=False))
main()
