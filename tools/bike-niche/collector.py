#!/usr/bin/env python3
"""Public structured bicycle niche collector. One independent SQLite database per origin."""
import argparse,concurrent.futures,datetime,hashlib,json,random,re,sqlite3,time,urllib.parse,zlib,threading,pathlib
import requests
from bs4 import BeautifulSoup

ROOT=pathlib.Path("/opt/bike-niche-corpus")
DBDIR=ROOT/"crawls"
LOGDIR=ROOT/"logs"
UA="BikeCatalogResearch/1.0 (structured public bicycle specifications)"
TLS=threading.local()
STOP=threading.Event()
ALLOWED={
 "bikeinsights":lambda p: p.startswith(("/bikes/","/brands/","/categories/","/cyclopedia/")),
 "rideinsights":lambda p: p.startswith("/parts/"),
 "sram":lambda p: p.startswith("/en/service/") or (
      p.startswith(("/en/sram/","/en/rockshox/","/en/zipp/")) and
      any(x in p for x in ("/products/","/series/","/collections/")))
}

def now():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def log(name,obj):
 LOGDIR.mkdir(parents=True,exist_ok=True)
 line=json.dumps({"ts":now(),"source":name,**obj},ensure_ascii=False)
 print(line,flush=True)
 with (LOGDIR/(name+".jsonl")).open("a") as f:f.write(line+"\n")
def connect(name):
 DBDIR.mkdir(parents=True,exist_ok=True)
 db=sqlite3.connect(DBDIR/(name+".sqlite3"),timeout=60)
 db.execute("PRAGMA journal_mode=WAL")
 db.execute("PRAGMA busy_timeout=30000")
 db.executescript("""
 CREATE TABLE IF NOT EXISTS queue(url TEXT PRIMARY KEY,ordinal INTEGER,status TEXT NOT NULL DEFAULT 'pending',attempts INTEGER NOT NULL DEFAULT 0,http_status INTEGER,error TEXT,checked_at TEXT);
 CREATE INDEX IF NOT EXISTS queue_status_ix ON queue(status,ordinal);
 CREATE TABLE IF NOT EXISTS records(url TEXT PRIMARY KEY,source TEXT NOT NULL,page_type TEXT,title TEXT,h1 TEXT,canonical TEXT,final_url TEXT,headings_json TEXT,geometry_json TEXT,tables_json TEXT,jsonld_json TEXT,images_json TEXT,text_excerpt TEXT,html_zlib BLOB,raw_bytes INTEGER,content_hash TEXT,fetched_at TEXT);
 """)
 db.commit();return db
def seed(name,db):
 src=ROOT/"inventory"/(name+"-urls.jsonl")
 rows=[]
 for line in src.open():
  row=json.loads(line);url=row["url"];path=urllib.parse.urlparse(url).path
  if ALLOWED[name](path):rows.append(url)
 db.executemany("INSERT OR IGNORE INTO queue(url,ordinal) VALUES(?,?)",[(u,i) for i,u in enumerate(rows)])
 db.commit();return len(rows)
def sess():
 s=getattr(TLS,"session",None)
 if s is None:
  s=requests.Session();s.headers.update({"User-Agent":UA,"Accept":"text/html,application/xhtml+xml;q=0.9,*/*;q=0.8"})
  TLS.session=s
 return s
def parse(url,resp,name):
 raw=resp.content
 soup=BeautifulSoup(raw,"html.parser")
 h1=soup.find("h1");h1=h1.get_text(" ",strip=True) if h1 else ""
 title=soup.title.get_text(" ",strip=True) if soup.title else ""
 canonical=soup.select_one('link[rel="canonical"]')
 headings=[{"level":int(h.name[1]),"text":h.get_text(" ",strip=True)[:250]} for h in soup.select("h1,h2,h3")[:80]]
 tables=[]
 for tbl in soup.select("table")[:30]:
  rows=[]
  for tr in tbl.select("tr")[:160]:
   cells=[e.get_text(" ",strip=True)[:220] for e in tr.find_all(["th","td"],recursive=False)[:35]]
   if cells:rows.append(cells)
  if rows:tables.append(rows)
 geo=[t for t in tables if ("stack" in str(t).lower() and "reach" in str(t).lower())]
 ld=[]
 for script in soup.select('script[type="application/ld+json"]')[:25]:
  try:ld.append(json.loads(script.get_text()))
  except:pass
 for e in soup.select("script,style,noscript,nav,footer,header"):e.decompose()
 body=soup.get_text(" ",strip=True)
 imgs=[]
 for e in soup.select("img[src],img[data-src]")[:40]:
  u=e.get("src") or e.get("data-src")
  if u and u not in imgs:imgs.append(u)
 typ=urllib.parse.urlparse(url).path.strip("/").split("/")[0]
 return {"url":url,"source":name,"page_type":typ,"title":title[:400],"h1":h1[:400],
  "canonical":canonical.get("href") if canonical else None,"final_url":resp.url,
  "headings_json":json.dumps(headings,ensure_ascii=False),"geometry_json":json.dumps(geo,ensure_ascii=False),
  "tables_json":json.dumps(tables,ensure_ascii=False),"jsonld_json":json.dumps(ld,ensure_ascii=False),
  "images_json":json.dumps(imgs,ensure_ascii=False),"text_excerpt":body[:12000],
  "html_zlib":sqlite3.Binary(zlib.compress(raw,level=5)),"raw_bytes":len(raw),
  "content_hash":hashlib.sha256(raw).hexdigest(),"fetched_at":now()}
def fetch(name,url,min_delay,max_delay):
 if STOP.is_set():return {"kind":"cancelled","url":url}
 try:
  r=sess().get(url,timeout=35,allow_redirects=True)
  if r.status_code in (403,429):
   STOP.set();return {"kind":"blocked","url":url,"status":r.status_code,"error":f"HTTP_{r.status_code}"}
  if r.status_code==404:return {"kind":"missing","url":url,"status":404}
  if r.status_code>=500:return {"kind":"retry","url":url,"status":r.status_code,"error":"server_error"}
  if r.status_code>=400:return {"kind":"invalid","url":url,"status":r.status_code,"error":"HTTP_error"}
  ct=r.headers.get("content-type","")
  if "text/html" not in ct.lower():
   return {"kind":"invalid","url":url,"status":r.status_code,"error":"NON_HTML "+ct+" "+r.url}
  head=r.text[:8000].lower()
  if "just a moment" in head or "cf-chl-" in head or "verify you are human" in head:
   STOP.set();return {"kind":"blocked","url":url,"status":r.status_code,"error":"challenge"}
  p=parse(url,r,name)
  if not p["title"] or len(r.content)<1000:
   return {"kind":"retry","url":url,"status":r.status_code,"error":"no_title_or_short_content"}
  return {"kind":"ok","url":url,"status":r.status_code,"record":p}
 except Exception as e:return {"kind":"retry","url":url,"error":str(e)[:700]}
 finally:time.sleep(min_delay+random.random()*max(0,max_delay-min_delay))
def run(name,db,workers,batch,limit,min_delay,max_delay):
 db.execute("UPDATE queue SET status='pending' WHERE status='in_progress'")
 db.commit()
 n=0
 columns="url,source,page_type,title,h1,canonical,final_url,headings_json,geometry_json,tables_json,jsonld_json,images_json,text_excerpt,html_zlib,raw_bytes,content_hash,fetched_at".split(",")
 with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as ex:
  while not STOP.is_set():
   if limit and n>=limit:break
   want=min(batch,limit-n) if limit else batch
   rows=db.execute("SELECT url,attempts FROM queue WHERE status IN ('pending','retry') AND attempts<4 ORDER BY ordinal LIMIT ?",(want,)).fetchall()
   if not rows:break
   db.executemany("UPDATE queue SET status='in_progress' WHERE url=?",[(u,) for u,a in rows]);db.commit()
   futs={ex.submit(fetch,name,u,min_delay,max_delay):(u,a) for u,a in rows}
   for fut in concurrent.futures.as_completed(futs):
    u,old=futs[fut];r=fut.result();k=r["kind"];status=r.get("status")
    if k=="ok":
     p=r["record"];db.execute("INSERT OR REPLACE INTO records("+",".join(columns)+") VALUES("+",".join("?" for _ in columns)+")",tuple(p[k] for k in columns))
     state="done";err=None
    elif k=="retry":
     state="retry" if old<3 else "error";err=r.get("error")
    elif k=="blocked":
     state="pending";err=r.get("error");STOP.set()
     (ROOT/"state"/(name+"-blocked.json")).write_text(json.dumps({"url":u,"status":status,"error":err,"at":now()},indent=2))
    elif k=="cancelled":
     state="pending";err="cancelled"
    else:state=k;err=r.get("error")
    attempt=old+(0 if k in ("cancelled","blocked") else 1)
    db.execute("UPDATE queue SET status=?,attempts=?,http_status=?,error=?,checked_at=? WHERE url=?",(state,attempt,status,err,now(),u))
    db.commit();n+=1
    if n%100==0 or n==1:log(name,{"processed_session":n,"last":state})
   if STOP.is_set():break
 if STOP.is_set():db.execute("UPDATE queue SET status='pending' WHERE status='in_progress'");db.commit()
 return not STOP.is_set()
def stats(db):
 return {"queue":dict(db.execute("SELECT status,count(*) FROM queue GROUP BY status").fetchall()),
         "records":db.execute("SELECT COUNT(*) FROM records").fetchone()[0],
         "geometry_tables":db.execute("SELECT COUNT(*) FROM records WHERE geometry_json != '[]'").fetchone()[0],
         "has_html":db.execute("SELECT COUNT(*) FROM records WHERE html_zlib IS NOT NULL").fetchone()[0]}
def main():
 ap=argparse.ArgumentParser()
 ap.add_argument("source",choices=list(ALLOWED))
 ap.add_argument("--seed-only",action="store_true")
 ap.add_argument("--stats",action="store_true")
 ap.add_argument("--limit",type=int,default=0)
 ap.add_argument("--workers",type=int,default=1)
 ap.add_argument("--batch",type=int,default=12)
 ap.add_argument("--min-delay",type=float,default=0.6)
 ap.add_argument("--max-delay",type=float,default=1.2)
 a=ap.parse_args();db=connect(a.source)
 if a.stats:print(json.dumps(stats(db),indent=2));return
 n=seed(a.source,db);log(a.source,{"seeded_eligible":n,"stats":stats(db)})
 if a.seed_only:return
 success=run(a.source,db,max(1,min(a.workers,3)),max(1,min(a.batch,48)),a.limit,a.min_delay,a.max_delay)
 state=stats(db);log(a.source,{"terminal_run":True,"healthy":success,"stats":state})
 if not success:raise SystemExit(20)
 if a.limit and state["queue"].get("pending",0):return
 if any(state["queue"].get(k,0)>0 for k in ("pending","retry","in_progress","error")):raise SystemExit(12)
if __name__=="__main__":main()
