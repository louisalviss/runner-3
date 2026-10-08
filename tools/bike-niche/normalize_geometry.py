#!/usr/bin/env python3
"""Normalize saved bike geometry tables without requesting source sites again.

Source-isolated (source,url,size,metric) data, immutable raw HTML remains in source databases.
Re-run is incremental even if an input source is still being crawled.
"""
import json,pathlib,re,sqlite3,datetime,sys,collections
ROOT=pathlib.Path("/opt/bike-niche-corpus")
D=ROOT/"derived"
D.mkdir(parents=True,exist_ok=True)
OUT=D/"geometry-index.sqlite3"
SOURCES=("bikeinsights","rideinsights","geometrygeeks")
FIELDS=[
 ("reach",r"^reach(?:\b|\s*\()"),
 ("stack",r"^stack(?:\b|\s*\()"),
 ("head_tube_angle",r"^(head\s*tube\s*angle|head\s*angle|head\s*angle\s*\()"),
 ("seat_tube_angle",r"^(seat\s*tube\s*angle|seat\s*angle)(?:\b|\s*\()"),
 ("top_tube_length",r"^(top\s*tube\s*(?:length|effective)|effective\s*top\s*tube|top\s*tube\s*\(effective\))"),
 ("head_tube_length",r"^head\s*tube\s*(?:length|height)"),
 ("seat_tube_length",r"^seat\s*tube\s*(?:length|height)"),
 ("chainstay_length",r"^(chain\s*stay|chainstay|rear\s*center)(?:\s*length)?"),
 ("wheelbase",r"^wheel\s*base|^wheelbase"),
 ("bb_drop",r"^(bottom\s*bracket\s*(?:drop|offset)|bb\s*drop)"),
 ("bb_height",r"^(bottom\s*bracket\s*height|bb\s*height)"),
 ("standover",r"^stand\s*over|^standover"),
 ("fork_offset",r"^(fork\s*(?:offset|rake)|rake)"),
 ("trail",r"^trail\s*($|\()"),
 ("front_center",r"^front\s*cent(?:re|er)"),
 ("fork_length",r"^fork\s*(?:length|installation\s*height)")
]
REGEX=[(k,re.compile(expr,re.I)) for k,expr in FIELDS]
NUMBER=re.compile(r"[-+]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?")
def clean(x):return re.sub(r"\s+"," ",str(x)).strip()
def normalize(k,value):
 s=clean(value)
 if not s or s.casefold() in ("-","n/a","unknown","—","not available"):return None
 m=NUMBER.search(s)
 if not m:return None
 n=float(m.group().replace(",",""))
 if n<=-10000 or n>20000:return None
 if k in ("head_tube_angle","seat_tube_angle"):
  if n<30 or n>95:return None
  unit="deg"
 else:
  if k in ("stack","reach") and not 150<=n<=900:return None
  if k not in ("stack","reach") and n>2500:return None
  unit="mm"
 return n,unit
def parse(tables):
 best=[]
 for table in tables:
  if not isinstance(table,list) or len(table)<4:continue
  header=table[0] if isinstance(table[0],list) else []
  if len(header)<2:continue
  sizes=[clean(x)[:64] for x in header[1:]]
  if not sizes or len(sizes)>35:continue
  candidates=[]
  for row in table[1:]:
   if not isinstance(row,list) or len(row)<2:continue
   label=clean(row[0]).lower()
   if "stack to reach" in label or "stack / reach" in label or "ratio" in label:continue
   key=next((key for key,pat in REGEX if pat.search(label)),None)
   if not key:continue
   for idx,size in enumerate(sizes):
    if idx+1>=len(row):continue
    nv=normalize(key,row[idx+1])
    if nv:
     number,unit=nv
     candidates.append((size or "size_"+str(idx+1),key,number,unit,clean(row[idx+1])[:120]))
  metrics=set(v[1] for v in candidates)
  if "stack" in metrics and "reach" in metrics:best.extend(candidates)
 return best
def init(db):
 db.execute("PRAGMA journal_mode=WAL")
 db.execute("PRAGMA synchronous=NORMAL")
 db.executescript("""
 CREATE TABLE IF NOT EXISTS geometry(
   source TEXT NOT NULL,
   url TEXT NOT NULL,
   title TEXT,
   frame_size TEXT NOT NULL,
   metric TEXT NOT NULL,
   value REAL NOT NULL,
   unit TEXT NOT NULL,
   raw_value TEXT,
   PRIMARY KEY(source,url,frame_size,metric)
 );
 CREATE INDEX IF NOT EXISTS idx_geom_metric ON geometry(metric,value);
 CREATE INDEX IF NOT EXISTS idx_geom_source ON geometry(source,url);
 CREATE TABLE IF NOT EXISTS progress(source TEXT PRIMARY KEY,last_rowid INTEGER NOT NULL DEFAULT 0,processed INTEGER NOT NULL DEFAULT 0,measured INTEGER NOT NULL DEFAULT 0,updated_at TEXT);
 """)
 db.commit()
def main():
 out=sqlite3.connect(OUT,timeout=60)
 init(out)
 for src in SOURCES:
  f=ROOT/"crawls"/(src+".sqlite3")
  if not f.exists():continue
  con=sqlite3.connect(f,timeout=60)
  seen=out.execute("SELECT last_rowid,processed,measured FROM progress WHERE source=?",(src,)).fetchone()
  pos,processed,measured=seen if seen else (0,0,0)
  batches=0
  while True:
   rows=con.execute("SELECT rowid,url,title,tables_json FROM records WHERE rowid>? ORDER BY rowid LIMIT 250",(pos,)).fetchall()
   if not rows:break
   out.execute("BEGIN")
   for rowid,url,title,data in rows:
    try:tables=json.loads(data or "[]");metrics=parse(tables)
    except Exception:metrics=[]
    out.execute("DELETE FROM geometry WHERE source=? AND url=?",(src,url))
    if metrics:
     out.executemany("INSERT OR REPLACE INTO geometry(source,url,title,frame_size,metric,value,unit,raw_value) VALUES (?,?,?,?,?,?,?,?)",[(src,url,title,size,key,num,unit,raw) for size,key,num,unit,raw in metrics])
     measured+=1
    processed+=1
    pos=rowid
   out.execute("INSERT INTO progress(source,last_rowid,processed,measured,updated_at) VALUES(?,?,?,?,?) ON CONFLICT(source) DO UPDATE SET last_rowid=excluded.last_rowid,processed=excluded.processed,measured=excluded.measured,updated_at=excluded.updated_at",(src,pos,processed,measured,datetime.datetime.now(datetime.timezone.utc).isoformat()))
   out.commit()
   batches+=1
   if batches%25==0:print(json.dumps({"source":src,"processed":processed,"last_rowid":pos}),flush=True)
  con.close()
  total=out.execute("SELECT count(*) FROM geometry WHERE source=?",(src,)).fetchone()[0]
  pages=out.execute("SELECT count(DISTINCT url) FROM geometry WHERE source=?",(src,)).fetchone()[0]
  print(json.dumps({"source":src,"processed":processed,"geometry_pages":pages,"numeric_measurements":total}),flush=True)
 out.close()
if __name__=="__main__":main()
