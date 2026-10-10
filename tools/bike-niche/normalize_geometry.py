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
# Broad, conservative bicycle geometry limits. These reject impossible
# measurement artifacts but retain source HTML and original raw tables.
# Some children's and cargo bike measurements are legitimately unusual.
METRIC_LIMITS={
 "stack":(200,1000),"reach":(150,950),
 "head_tube_angle":(45,90),"seat_tube_angle":(45,90),
 "top_tube_length":(180,1300),"head_tube_length":(10,500),
 "seat_tube_length":(80,1300),"chainstay_length":(150,800),
 "wheelbase":(500,2100),"bb_drop":(-60,250),
 "bb_height":(100,700),"standover":(100,1600),
 "fork_offset":(-20,200),"trail":(-20,350),
 "front_center":(150,1500),"fork_length":(150,1100)
}
def clean(x):return re.sub(r"\s+"," ",str(x)).strip()
def normalize(k,value):
 s=clean(value)
 if not s or s.casefold() in ("-","n/a","unknown","—","not available"):return None
 # Source pages mix decimal commas (461,25) and grouped thousands (1,234).
 # Convert only a terminal 1- or 2-digit decimal comma; leave 3-digit
 # groups as thousands. The raw value remains available for audit.
 normalized_text=re.sub(r"(?<=\d),\s*(?=\d{1,2}(?!\d))",".",s)
 m=NUMBER.search(normalized_text)
 if not m:return None
 n=float(m.group().replace(",",""))
 if k not in ("head_tube_angle","seat_tube_angle"):
  suffix=s[m.end():].strip().lower()
  # Units must immediately follow the first numeric value; a trailing note
  # like "70.5 (toe overlap 4 more than M)cm" does not imply centimetres.
  if re.match(r"^cm(?:\\b|$)",suffix):n*=10
  elif re.match(r"^(?:in(?:ch(?:es)?)?|[”″\\\"])(?:\\b|$)",suffix):n*=25.4
 if k not in METRIC_LIMITS:return None
 lo,hi=METRIC_LIMITS[k]
 if not lo<=n<=hi:return None
 unit="deg" if k in ("head_tube_angle","seat_tube_angle") else "mm"
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
def repair_locale_units(db):
 # Reparse only older numeric rows carrying mixed locale or explicit units.
 # The source raw values remain unchanged. Audit every correction.
 db.execute("""CREATE TABLE IF NOT EXISTS numeric_corrections(
   source TEXT,url TEXT,frame_size TEXT,metric TEXT,
   old_value REAL,new_value REAL,unit TEXT,raw_value TEXT,
   reason TEXT,corrected_at TEXT,
   PRIMARY KEY(source,url,frame_size,metric)
 )""")
 sql="""SELECT source,url,frame_size,metric,value,unit,raw_value
        FROM geometry
        WHERE instr(raw_value,',')>0 OR lower(raw_value) LIKE '%cm%'
              OR lower(raw_value) LIKE '% in%'"""
 updates=[]
 count=0
 for source,url,size,metric,old_value,unit,raw in list(db.execute(sql)):
  norm=normalize(metric,raw)
  if norm is None:
   # Retain unusable legacy rows in the rejection audit before exclusion.
   db.execute("""INSERT OR IGNORE INTO rejected_measurements
     (source,url,frame_size,metric,value,unit,raw_value,reason,rejected_at)
     VALUES (?,?,?,?,?,?,?,?,?)""",
     (source,url,size,metric,old_value,unit,raw,'locale_unit_invalid',datetime.datetime.now(datetime.timezone.utc).isoformat()))
   db.execute("DELETE FROM geometry WHERE source=? AND url=? AND frame_size=? AND metric=?",
              (source,url,size,metric))
   count+=1
   continue
  new_value,new_unit=norm
  if abs(new_value-old_value)<0.000001 and new_unit==unit:continue
  db.execute("""INSERT OR IGNORE INTO numeric_corrections
    (source,url,frame_size,metric,old_value,new_value,unit,raw_value,reason,corrected_at)
    VALUES (?,?,?,?,?,?,?,?,?,?)""",
    (source,url,size,metric,old_value,new_value,new_unit,raw,'locale_or_explicit_unit',datetime.datetime.now(datetime.timezone.utc).isoformat()))
  db.execute("UPDATE geometry SET value=?,unit=? WHERE source=? AND url=? AND frame_size=? AND metric=?",
             (new_value,new_unit,source,url,size,metric))
  count+=1
 db.commit()
 print(json.dumps({"quality_gate":"locale_numeric_units","repaired_or_rejected":count}),flush=True)
 return count
def cleanup_outliers(db):
 # Old indexed records may predate METRIC_LIMITS. Preserve audit metadata
 # when retiring out-of-range values; never mutate original source SQLite.
 db.execute("""CREATE TABLE IF NOT EXISTS rejected_measurements(
   source TEXT,url TEXT,frame_size TEXT,metric TEXT,
   value REAL,unit TEXT,raw_value TEXT,reason TEXT,rejected_at TEXT,
   PRIMARY KEY(source,url,frame_size,metric)
 )""")
 rejected=0
 for metric,(low,high) in METRIC_LIMITS.items():
  condition="metric=? AND (value<? OR value>?)"
  params=(metric,low,high)
  count=db.execute("SELECT count(*) FROM geometry WHERE "+condition,params).fetchone()[0]
  if not count:continue
  db.execute("""INSERT OR IGNORE INTO rejected_measurements
    (source,url,frame_size,metric,value,unit,raw_value,reason,rejected_at)
    SELECT source,url,frame_size,metric,value,unit,raw_value,?,?
    FROM geometry WHERE """+condition,
    ("outside_conservative_range",datetime.datetime.now(datetime.timezone.utc).isoformat(),*params))
  db.execute("DELETE FROM geometry WHERE "+condition,params)
  rejected+=count
 db.commit()
 print(json.dumps({"quality_gate":"geometry_metric_limits","retired_existing_outliers":rejected}),flush=True)
 return rejected
def main():
 out=sqlite3.connect(OUT,timeout=60)
 init(out)
 cleanup_outliers(out)
 repair_locale_units(out)
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
