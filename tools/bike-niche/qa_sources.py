#!/usr/bin/env python3
"""Non-destructive quality gate for automated geometry comparison pages."""
import json,sqlite3,pathlib,re,datetime
R=pathlib.Path("/opt/bike-niche-corpus")
OUT=R/"derived/source-quality.sqlite3"
SOURCES={"bikeinsights":"bikes","rideinsights":"parts","geometrygeeks":"bike"}
def meaningful(s):
 s=(s or "").replace("Geometry Details:","").strip()
 return bool(re.search("[a-zA-Z]{2}",s)) and s.lower() not in ("unknown","test","untitled")
con=sqlite3.connect(OUT,timeout=90)
con.executescript("""
CREATE TABLE IF NOT EXISTS checks(
 source TEXT,url TEXT,title TEXT,geometry_tables INTEGER,eligible INTEGER,
 reject_reason TEXT,PRIMARY KEY(source,url));
CREATE TABLE IF NOT EXISTS offsets(source TEXT PRIMARY KEY,last_rowid INTEGER);
""")
summary=[]
for source,kind in SOURCES.items():
 db=sqlite3.connect(R/"crawls"/(source+".sqlite3"),timeout=90)
 pos=con.execute("SELECT last_rowid FROM offsets WHERE source=?",(source,)).fetchone()
 pos=pos[0] if pos else 0
 while True:
  batch=db.execute("SELECT rowid,url,title,page_type,geometry_json FROM records WHERE rowid>? ORDER BY rowid LIMIT 500",(pos,)).fetchall()
  if not batch:break
  out=[]
  for rowid,url,title,page_type,g in batch:
   try:n=len(json.loads(g or "[]"))
   except:n=0
   reason="bad_title" if not meaningful(title) else "not_detail" if page_type!=kind else "no_geometry" if n==0 else None
   out.append((source,url,title,n,int(reason is None),reason))
   pos=rowid
  con.executemany("INSERT OR REPLACE INTO checks VALUES(?,?,?,?,?,?)",out)
  con.execute("INSERT INTO offsets(source,last_rowid) VALUES(?,?) ON CONFLICT(source) DO UPDATE SET last_rowid=excluded.last_rowid",(source,pos))
  con.commit()
 c=dict(con.execute("SELECT coalesce(reject_reason,'eligible'),count(*) FROM checks WHERE source=? GROUP BY reject_reason",(source,)))
 summary.append({"source":source,"total":sum(c.values()),"eligibility":c})
 db.close()
(R/"derived/source-quality-summary.json").write_text(json.dumps({"at":datetime.datetime.now(datetime.timezone.utc).isoformat(),"results":summary},ensure_ascii=False,indent=2))
print(json.dumps(summary,ensure_ascii=False))
