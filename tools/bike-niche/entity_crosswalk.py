#!/usr/bin/env python3
"""Conservative source URL crosswalk: exact normalized canonical bike URL + year.

Creates candidate links only. Raw data and specs remain source-isolated.
Model/build-level identity is NOT automatically inferred or merged.
"""
import collections,datetime,json,pathlib,re,sqlite3,unicodedata,urllib.parse
ROOT=pathlib.Path("/opt/bike-niche-corpus")
OUT=ROOT/"derived/bike-crosswalk.sqlite3"
def norm(value):
 s=unicodedata.normalize("NFKD",value or "").encode("ascii","ignore").decode().lower()
 return "".join(c for c in s if c.isalnum())
def index_biklo():
 b=sqlite3.connect("/opt/biklo-catalog-crawl/data/catalog.sqlite3",timeout=60)
 ix=collections.defaultdict(set)
 for url,brand,year in b.execute("select url,brand,year from bikes where year between 1980 and 2035"):
  stem=urllib.parse.urlparse(url).path.strip("/")
  stem=re.sub(r"-[12][0-9]{3}$","",stem)
  root=norm(stem);bn=norm(brand)
  if not bn or not root.startswith(bn):continue
  tail=root[len(bn):]
  for mid in ("","bikes","bicycles","bicyclecompany","bikecompany"):
   ix[(int(year),bn+mid+tail)].add(url)
 b.close()
 return ix
def rows_bikeinsights(ix):
 src=sqlite3.connect(ROOT/"crawls/bikeinsights.sqlite3",timeout=60)
 for url,geom in src.execute("select url,geometry_json from records where page_type='bikes'"):
  p=urllib.parse.urlparse(url)
  year=urllib.parse.parse_qs(p.query).get("version",[""])[0]
  if not (len(year)==4 and year.isdigit()):continue
  slug=re.sub(r"^[0-9a-f]{24}-","",p.path.strip("/").split("/")[-1])
  hits=ix.get((int(year),norm(slug)),set())
  if len(hits)==1:yield ("bikeinsights",url,next(iter(hits)),int(year),int(geom!="[]"))
 src.close()
def rows_geeks(ix):
 src=sqlite3.connect(ROOT/"crawls/geometrygeeks.sqlite3",timeout=60)
 for url,title,geom in src.execute("select url,title,geometry_json from records where page_type='bike'"):
  m=re.match(r"^Geometry Details:\s*(.*?)\s+(19\d{2}|20\d{2})\s*$",title or "")
  if not m:continue
  hits=ix.get((int(m.group(2)),norm(m.group(1))),set())
  if len(hits)==1:yield ("geometrygeeks",url,next(iter(hits)),int(m.group(2)),int(geom!="[]"))
 src.close()
def main():
 ix=index_biklo()
 conn=sqlite3.connect(OUT,timeout=90)
 conn.executescript("""
 CREATE TABLE IF NOT EXISTS links(
  source TEXT NOT NULL,source_url TEXT NOT NULL,biklo_url TEXT NOT NULL,
  model_year INTEGER NOT NULL,has_source_geometry INTEGER NOT NULL,
  match_rule TEXT NOT NULL,updated_at TEXT NOT NULL,
  PRIMARY KEY(source,source_url));
 CREATE INDEX IF NOT EXISTS crosswalk_by_biklo ON links(biklo_url);
 """)
 at=datetime.datetime.now(datetime.timezone.utc).isoformat()
 summaries=[]
 for src,rows in (("bikeinsights",rows_bikeinsights(ix)),("geometrygeeks",rows_geeks(ix))):
  data=[(*row,"unique_exact_normalized_canonical_url_and_year",at) for row in rows]
  conn.executemany("""INSERT INTO links(source,source_url,biklo_url,model_year,has_source_geometry,match_rule,updated_at)
 VALUES(?,?,?,?,?,?,?) ON CONFLICT(source,source_url) DO UPDATE SET
 biklo_url=excluded.biklo_url,model_year=excluded.model_year,has_source_geometry=excluded.has_source_geometry,updated_at=excluded.updated_at""",data)
  conn.commit()
  match_count=conn.execute("select count(*) from links where source=?",(src,)).fetchone()[0]
  geo_count=conn.execute("select count(*) from links where source=? and has_source_geometry=1",(src,)).fetchone()[0]
  summaries.append({"source":src,"exact_candidate_links":match_count,"with_geometry":geo_count})
 unique=conn.execute("select count(distinct biklo_url) from links").fetchone()[0]
 conn.close()
 doc={"generated_at":at,"rule":"unique exact normalized canonical URL stem + year with known generic manufacturer name aliases","identity_assumption":"Candidate same model/year; not a verified same build or size","distinct_biklo_urls_with_candidates":unique,"sources":summaries}
 (ROOT/"derived/bike-crosswalk-summary.json").write_text(json.dumps(doc,indent=2,ensure_ascii=False))
 print(json.dumps(doc,ensure_ascii=False))
if __name__=="__main__":main()
