#!/usr/bin/env python3
"""Source-provenanced candidate Biklo geometry-to-fit lookup.

Only include conservative same-year URL crosswalks and vetted source geometry
with paired stack/reach. Keep model/build equivalence unverified; NEVER write
back to Biklo's original database or claim matching exact bike configuration.
"""
import datetime,json,os,pathlib,sqlite3
ROOT=pathlib.Path("/opt/bike-niche-corpus")
D=ROOT/"derived";D.mkdir(parents=True,exist_ok=True)
STAGE=D/"biklo-fit-candidates.sqlite3.tmp"
OUT=D/"biklo-fit-candidates.sqlite3"
def main():
 if STAGE.exists():STAGE.unlink()
 conn=sqlite3.connect(STAGE,timeout=90)
 conn.executescript("""
 PRAGMA journal_mode=DELETE;
 CREATE TABLE fit_candidates(
  biklo_url TEXT NOT NULL,source TEXT NOT NULL,source_url TEXT NOT NULL,
  model_year INTEGER NOT NULL,frame_size TEXT NOT NULL,
  stack_mm REAL NOT NULL,reach_mm REAL NOT NULL,
  stack_reach_ratio REAL NOT NULL,
  source_title TEXT,link_rule TEXT NOT NULL,
  identity_status TEXT NOT NULL DEFAULT 'candidate_model_year_only',
  cross_source_conflict INTEGER NOT NULL DEFAULT 0,
  same_source_conflict INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY(source,source_url,frame_size)
 );
 CREATE INDEX fit_by_biklo ON fit_candidates(biklo_url,frame_size);
 CREATE INDEX fit_by_source ON fit_candidates(source,source_url);
 """)
 conn.execute("ATTACH DATABASE ? AS geom",(str(D/"geometry-index.sqlite3"),))
 conn.execute("ATTACH DATABASE ? AS crosswalk",(str(D/"bike-crosswalk.sqlite3"),))
 conn.execute("ATTACH DATABASE ? AS quality",(str(D/"source-quality.sqlite3"),))
 # No fuzzy source joins. BOTH measured stack and reach must exist on the
 # same source URL and frame size, and the geometry page must pass QA.
 conn.execute("""
 INSERT INTO fit_candidates(
  biklo_url,source,source_url,model_year,frame_size,
  stack_mm,reach_mm,stack_reach_ratio,source_title,link_rule)
 SELECT l.biklo_url,l.source,l.source_url,l.model_year,
  stack.frame_size,stack.value,reach.value,
  round(stack.value/reach.value,5),stack.title,l.match_rule
 FROM crosswalk.links AS l
 JOIN quality.checks AS q
  ON q.source=l.source AND q.url=l.source_url AND q.eligible=1
 JOIN geom.geometry AS stack
  ON stack.source=l.source AND stack.url=l.source_url AND stack.metric='stack'
 JOIN geom.geometry AS reach
  ON reach.source=stack.source AND reach.url=stack.url AND
     reach.frame_size=stack.frame_size AND reach.metric='reach'
 WHERE stack.value BETWEEN 200 AND 1000 AND reach.value BETWEEN 150 AND 950
 """)
 conn.commit()
 # A model-year name match is NEVER proof of identical build. Explicitly flag
 # inconsistent measurements rather than arbitrarily selecting a source.
 conn.execute("""CREATE TEMP TABLE cross_source_conflicts AS
 SELECT biklo_url,frame_size FROM fit_candidates GROUP BY biklo_url,frame_size
 HAVING COUNT(DISTINCT source)>1 AND
  (MAX(stack_mm)-MIN(stack_mm)>10 OR MAX(reach_mm)-MIN(reach_mm)>10)""")
 conn.execute("""CREATE TEMP TABLE same_source_conflicts AS
 SELECT biklo_url,frame_size,source FROM fit_candidates
 GROUP BY biklo_url,frame_size,source
 HAVING COUNT(*)>1 AND
  (MAX(stack_mm)-MIN(stack_mm)>10 OR MAX(reach_mm)-MIN(reach_mm)>10)""")
 conn.execute("""UPDATE fit_candidates SET cross_source_conflict=1 WHERE
  (biklo_url,frame_size) IN (SELECT biklo_url,frame_size FROM cross_source_conflicts)""")
 conn.execute("""UPDATE fit_candidates SET same_source_conflict=1 WHERE
  (biklo_url,frame_size,source) IN
  (SELECT biklo_url,frame_size,source FROM same_source_conflicts)""")
 conn.commit()
 q=conn.execute("PRAGMA quick_check").fetchone()[0]
 if q!="ok":raise RuntimeError("FIT_INDEX_QUICK_CHECK_FAILED "+q)
 count=conn.execute("SELECT COUNT(*) FROM fit_candidates").fetchone()[0]
 nmodels=conn.execute("SELECT COUNT(DISTINCT biklo_url) FROM fit_candidates").fetchone()[0]
 bysrc=[{"source":s,"size_rows":n,"biklo_urls":u} for s,n,u in
  conn.execute("SELECT source,COUNT(*),COUNT(DISTINCT biklo_url) FROM fit_candidates GROUP BY source")]
 conflict=conn.execute("SELECT COUNT(*) FROM cross_source_conflicts").fetchone()[0]
 same_conflict=conn.execute("SELECT COUNT(*) FROM same_source_conflicts").fetchone()[0]
 multi_source=conn.execute("""SELECT COUNT(*) FROM (
  SELECT biklo_url FROM fit_candidates GROUP BY biklo_url
  HAVING COUNT(DISTINCT source)>1)""").fetchone()[0]
 conn.execute("DETACH DATABASE geom");conn.execute("DETACH DATABASE crosswalk");conn.execute("DETACH DATABASE quality")
 conn.close()
 STAGE.replace(OUT)
 report={"dataset":"biklo-fit-candidates","created_at":datetime.datetime.now(datetime.timezone.utc).isoformat(),
  "size_rows":count,"distinct_biklo_bikes":nmodels,"source_counts":bysrc,
  "cross_source_same_size_disagreements_over_10mm":conflict,
  "within_source_same_size_disagreements_over_10mm":same_conflict,
  "biklo_urls_with_both_sources":multi_source,
  "identity_note":"Same model slug/year candidates only; configuration and size label not guaranteed identical. Neither conflicting nor nonconflicting candidates are verified exact builds.",
  "constraints":"Verified source QA, positive Stack+Reach, independent full URL provenance; raw sources unchanged."}
 (D/"biklo-fit-candidates-summary.json").write_text(json.dumps(report,ensure_ascii=False,indent=2))
 print(json.dumps(report,ensure_ascii=False))
if __name__=="__main__":main()
