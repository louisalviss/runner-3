#!/usr/bin/env python3
"""Fail-closed prepublication coverage audit for the bicycle geometry release.

Called after terminal source crawls and all incremental derived builders.
Validates rowid watermarks and record coverage *per source*, SQLite integrity,
paired Stack/Reach candidates, provenance, and quality summaries. Read-only.
"""
import datetime,json,pathlib,sqlite3,sys
ROOT=pathlib.Path("/opt/bike-niche-corpus")
DER=ROOT/"derived"
SRC=("bikeinsights","rideinsights","geometrygeeks")
def read_db(p):
 if not p.exists():raise RuntimeError("MISSING_DB "+str(p))
 conn=sqlite3.connect("file:"+str(p)+"?mode=ro",uri=True,timeout=60)
 val=conn.execute("PRAGMA quick_check").fetchone()
 if not val or val[0]!="ok":raise RuntimeError("SQLITE_QUICK_CHECK_FAILED "+str(p))
 return conn
def main():
 geom=read_db(DER/"geometry-index.sqlite3")
 qual=read_db(DER/"source-quality.sqlite3")
 cross=read_db(DER/"bike-crosswalk.sqlite3")
 fit=read_db(DER/"biklo-fit-candidates.sqlite3")
 results=[]
 for source in SRC:
  inp=read_db(ROOT/"crawls"/(source+".sqlite3"))
  last_id,rows=inp.execute("SELECT COALESCE(MAX(rowid),0),COUNT(*) FROM records").fetchone()
  statuses=dict(inp.execute("SELECT status,COUNT(*) FROM queue GROUP BY status"))
  pending=sum(statuses.get(x,0) for x in ("pending","retry","in_progress"))
  if pending:raise RuntimeError(f"SOURCE_NONTERMINAL:{source}:{statuses}")
  if rows!=statuses.get("done",0):
   raise RuntimeError(f"SOURCE_RECORD_QUEUE_MISMATCH:{source}:{rows}:{statuses}")
  g=geom.execute("SELECT last_rowid FROM progress WHERE source=?",(source,)).fetchone()
  q=qual.execute("SELECT last_rowid FROM offsets WHERE source=?",(source,)).fetchone()
  if not g or g[0]!=last_id:raise RuntimeError(f"GEOMETRY_INDEX_LAG:{source}:{g}:{last_id}")
  if not q or q[0]!=last_id:raise RuntimeError(f"QUALITY_INDEX_LAG:{source}:{q}:{last_id}")
  qc=qual.execute("SELECT COUNT(*) FROM checks WHERE source=?",(source,)).fetchone()[0]
  if qc!=rows:raise RuntimeError(f"QUALITY_COVERAGE_MISMATCH:{source}:{qc}:{rows}")
  measured=geom.execute("SELECT COUNT(*) FROM geometry WHERE source=?",(source,)).fetchone()[0]
  qa_valid=qual.execute("SELECT COUNT(*) FROM checks WHERE source=? AND eligible=1",(source,)).fetchone()[0]
  results.append({"source":source,"source_records":rows,"last_rowid":last_id,
                  "geometry_values":measured,"qa_eligible_pages":qa_valid,
                  "geometry_watermark":g[0],"quality_watermark":q[0],"source_errors":statuses.get("error",0)})
  inp.close()
 linked=cross.execute("SELECT COUNT(*) FROM links").fetchone()[0]
 matched=fit.execute("SELECT COUNT(*),COUNT(DISTINCT biklo_url) FROM fit_candidates").fetchone()
 if not linked or not matched[0] or not matched[1]:
  raise RuntimeError("FIT_CROSSWALK_EMPTY")
 invalid_fit=fit.execute("""SELECT COUNT(*) FROM fit_candidates WHERE
  source NOT IN ('bikeinsights','geometrygeeks') OR
  identity_status!='candidate_model_year_only' OR
  stack_mm<=0 OR reach_mm<=0""").fetchone()[0]
 if invalid_fit:raise RuntimeError("FIT_PROVENANCE_OR_MEASUREMENT_INVALID:"+str(invalid_fit))
 total=geom.execute("SELECT COUNT(*) FROM geometry").fetchone()[0]
 if total<matched[0]:raise RuntimeError("GEOMETRY_COUNT_BELOW_FIT_ROWS")
 report={"ok":True,"audit":"bike-niche-final-coverage",
         "at":datetime.datetime.now(datetime.timezone.utc).isoformat(),
         "sources":results,"geometry_values":total,"crosswalk_links":linked,
         "fit_size_records":matched[0],"fit_distinct_biklo_urls":matched[1],
         "sqlite_quick_check":"ok","unverified_exact_build_identity":True}
 for c in (geom,qual,cross,fit):c.close()
 print(json.dumps(report,ensure_ascii=False))
if __name__=="__main__":main()
