#!/usr/bin/env python3
"""Enumerate Geometry Geeks public bike directory through its normal Next links.

Only the site's public directory and linked bike geometry pages are in scope.
Resumes from an atomic per-page checkpoint; no guessed IDs or bypasses.
"""
import datetime,json,pathlib,random,sqlite3,time,urllib.parse
import requests
from bs4 import BeautifulSoup

ROOT=pathlib.Path("/opt/bike-niche-corpus")
INV=ROOT/"inventory"
STATE=ROOT/"state"
INV.mkdir(parents=True,exist_ok=True);STATE.mkdir(parents=True,exist_ok=True)
DIR_DB=STATE/"geometrygeeks-directory.sqlite3"
STATE_FILE=STATE/"geometrygeeks-directory-state.json"
OUT=INV/"geometrygeeks-urls.jsonl"
START="https://geometrygeeks.bike/bike-directory/all/"
ORIGIN="https://geometrygeeks.bike"
USER_AGENT="BikeCatalogResearch/1.0 (public geometry directory)"

def now():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def atom(obj):
 tmp=STATE_FILE.with_suffix(".tmp")
 tmp.write_text(json.dumps(obj,ensure_ascii=False,indent=2),encoding="utf-8")
 tmp.replace(STATE_FILE)
def load():
 try:return json.loads(STATE_FILE.read_text(encoding="utf-8"))
 except:return {"page":0,"next_url":START,"done":False,"pages_seen":[]}
def stop(reason,state):
 state.update({"stopped":reason,"updated_at":now()});atom(state)
 print(json.dumps({"state":"stopped","reason":reason,"pages":state.get("page")}),flush=True)
 raise SystemExit(21)
def page_links(page_url,soup):
 found=[]
 for a in soup.select('a[href]'):
  href=urllib.parse.urljoin(page_url,a.get("href",""))
  path=urllib.parse.urlparse(href).path
  if urllib.parse.urlparse(href).netloc=="geometrygeeks.bike" and path.startswith("/bike/") and path.rstrip("/")!="/bike":
   found.append(href.split("?")[0])
 return list(dict.fromkeys(found))
def next_page(page_url,soup):
 for a in soup.select("a[href]"):
  label=a.get_text(" ",strip=True).lower()
  if label in ("next", "next page", "›", "»"):
   href=urllib.parse.urljoin(page_url,a.get("href",""))
   if href.startswith(ORIGIN+"/bike-directory/all/"):return href
 return None
def main():
 db=sqlite3.connect(DIR_DB,timeout=40)
 db.executescript("""
 CREATE TABLE IF NOT EXISTS urls (url TEXT PRIMARY KEY, discovered_page INTEGER, discovered_at TEXT);
 CREATE TABLE IF NOT EXISTS pages (url TEXT PRIMARY KEY, ordinal INTEGER, urls_found INTEGER, fetched_at TEXT);
 """)
 db.commit()
 s=load();session=requests.Session()
 session.headers.update({"User-Agent":USER_AGENT,"Accept":"text/html,application/xhtml+xml"})
 if not s.get("done"):
  while s.get("next_url") and int(s.get("page",0))<5000:
   url=s["next_url"]
   if db.execute("SELECT 1 FROM pages WHERE url=?",(url,)).fetchone():
    stop("CHECKPOINT_PAGE_ALREADY_SEEN_WITHOUT_ADVANCE",s)
   try:resp=session.get(url,timeout=35)
   except Exception as e:stop("REQUEST_FAILED "+str(e)[:160],s)
   if resp.status_code in (403,429):stop(f"BLOCKED_HTTP_{resp.status_code}",s)
   if resp.status_code!=200:stop(f"HTTP_{resp.status_code}",s)
   body=resp.text
   if ("cf-chl-" in body.lower() or "verify you are human" in body.lower() or "just a moment" in body.lower()):
    stop("CHALLENGE",s)
   if "text/html" not in resp.headers.get("Content-Type","").lower():stop("NON_HTML",s)
   doc=BeautifulSoup(body,"html.parser")
   urls=page_links(url,doc)
   if not urls:stop("NO_BIKE_LINKS",s)
   pg=int(s.get("page",0))+1
   nxt=next_page(url,doc)
   if nxt==url:stop("SELF_REFERENTIAL_PAGINATION",s)
   db.executemany("INSERT OR IGNORE INTO urls(url,discovered_page,discovered_at) VALUES(?,?,?)",[(u,pg,now()) for u in urls])
   db.execute("INSERT INTO pages(url,ordinal,urls_found,fetched_at) VALUES(?,?,?,?)",(url,pg,len(urls),now()))
   db.commit()
   s.update({"page":pg,"next_url":nxt,"last_url":url,"updated_at":now()})
   atom(s)
   if pg<=3 or pg%50==0:
    count=db.execute("SELECT COUNT(*) FROM urls").fetchone()[0]
    print(json.dumps({"page":pg,"url_count":count,"last_page_links":len(urls),"has_next":bool(nxt)}),flush=True)
   if not nxt:break
   time.sleep(0.9+random.uniform(0,0.6))
  if s.get("next_url"):
   stop("MAX_PAGES_REACHED",s)
  s.update({"done":True,"finished_at":now()});atom(s)
 # Deterministic export: no duplicate URL, one source provenance label each.
 with OUT.open("w",encoding="utf-8") as f:
  for (u,) in db.execute("SELECT url FROM urls ORDER BY discovered_page,url"):
   f.write(json.dumps({"source":"geometrygeeks","url":u},ensure_ascii=False)+"\n")
 print(json.dumps({"state":"inventory_complete","pages":s["page"],"urls":db.execute("SELECT COUNT(*) FROM urls").fetchone()[0],"file":str(OUT)}),flush=True)
 db.close()
if __name__=="__main__":main()
