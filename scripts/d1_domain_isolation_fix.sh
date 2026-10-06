#!/usr/bin/env bash
set -euo pipefail

: "${CLOUDFLARE_API_TOKEN:?CLOUDFLARE_API_TOKEN is required}"
: "${CLOUDFLARE_ACCOUNT_ID:?CLOUDFLARE_ACCOUNT_ID is required}"

SOURCE_DB="runner3-core"
LEGACY_INTEREST_DB="link-interest-profile"
ROOT="cloudflare/runner3-core"
WRANGLER=(npx --yes wrangler@4)

declare -A TARGETS=(
  [TASK_CONTEXT_DB]="louis-task-context"
  [CONTEXT_INDEX_DB]="louis-context-index"
  [CONTENT_DB]="runner3-content-intelligence"
  [RSS_DB]="runner3-rss"
  [REDDIT_DB]="runner3-reddit"
  [EBOOK_DB]="runner3-ebook"
)

list_json=/tmp/d1-domain-list.json

refresh_list() {
  "${WRANGLER[@]}" d1 list --json >"$list_json"
}

find_id() {
  python3 - "$list_json" "$1" <<'PY'
import json,sys
data=json.load(open(sys.argv[1]))
name=sys.argv[2]
def walk(x):
    if isinstance(x,dict):
        if x.get("name")==name:
            for k in ("uuid","database_id","id"):
                if x.get(k): return str(x[k])
        for v in x.values():
            r=walk(v)
            if r:return r
    elif isinstance(x,list):
        for v in x:
            r=walk(v)
            if r:return r
    return None
r=walk(data)
if not r: raise SystemExit(1)
print(r)
PY
}

resolve_db() {
  local binding="$1" name="$2" id=""
  refresh_list
  id="$(find_id "$name" 2>/dev/null || true)"
  if [[ -z "$id" ]]; then
    "${WRANGLER[@]}" d1 create "$name" --location apac
    refresh_list
    id="$(find_id "$name")"
  fi
  printf -v "$binding" '%s' "$id"
  export "$binding"
  echo "RESOLVED $binding=$name:$id"
}

for binding in TASK_CONTEXT_DB CONTEXT_INDEX_DB CONTENT_DB RSS_DB REDDIT_DB EBOOK_DB; do
  resolve_db "$binding" "${TARGETS[$binding]}"
done

apply_file() {
  local db="$1" file="$2"
  "${WRANGLER[@]}" d1 execute "$db" --remote --file="$file"
}

clear_table() {
  local db="$1" table="$2"
  "${WRANGLER[@]}" d1 execute "$db" --remote --command "DELETE FROM \"$table\""
}

copy_table() {
  local src="$1" dst="$2" table="$3"
  local file="/tmp/d1-copy-${src//[^A-Za-z0-9]/_}-${table}.sql"
  rm -f "$file"
  "${WRANGLER[@]}" d1 export "$src" --remote --skip-confirmation --table="$table" --no-schema --output="$file"
  if grep -q '^INSERT INTO' "$file"; then
    "${WRANGLER[@]}" d1 execute "$dst" --remote --file="$file"
  fi
}

table_exists() {
  local db="$1" table="$2"
  "${WRANGLER[@]}" d1 execute "$db" --remote --command "SELECT COUNT(*) AS n FROM sqlite_schema WHERE type='table' AND name='$table'" --json |
  python3 -c 'import json,sys
d=json.load(sys.stdin)
def rows(x):
    if isinstance(x,dict):
        if isinstance(x.get("results"),list): return x["results"]
        for v in x.values():
            r=rows(v)
            if r is not None:return r
    if isinstance(x,list):
        for v in x:
            r=rows(v)
            if r is not None:return r
    return None
r=rows(d) or []
print(int((r[0] if r else {}).get("n",0)))'
}

ensure_schema_from_source() {
  local src="$1" dst="$2" table="$3"
  if [[ "$(table_exists "$dst" "$table")" == "1" ]]; then return 0; fi
  local full="/tmp/d1-schema-${src//[^A-Za-z0-9]/_}-${table}.sql"
  local schema="/tmp/d1-schema-only-${src//[^A-Za-z0-9]/_}-${table}.sql"
  rm -f "$full" "$schema"
  "${WRANGLER[@]}" d1 export "$src" --remote --skip-confirmation --table="$table" --output="$full"
  python3 - "$full" "$schema" <<'PY'
import pathlib,sys
src=pathlib.Path(sys.argv[1]).read_text()
out=[]
for line in src.splitlines():
    if line.startswith("INSERT INTO "): continue
    out.append(line)
pathlib.Path(sys.argv[2]).write_text("\n".join(out)+"\n")
PY
  "${WRANGLER[@]}" d1 execute "$dst" --remote --file="$schema"
}

# Task/context schemas.
apply_file "${TARGETS[TASK_CONTEXT_DB]}" "$ROOT/migrations/0002_state_checkpoints.sql"
apply_file "${TARGETS[CONTEXT_INDEX_DB]}" "$ROOT/migrations/0002_state_checkpoints.sql"

# Content Intelligence schema.
apply_file "${TARGETS[CONTENT_DB]}" "$ROOT/migrations/0002_state_checkpoints.sql"
for f in   0008_content_intelligence.sql   0009_content_event_dedupe.sql   0015_personal_score_stage.sql   0016_interest_family_profile.sql   0017_user_content_event_idempotency.sql
do
  apply_file "${TARGETS[CONTENT_DB]}" "$ROOT/migrations/$f"
done
ensure_schema_from_source "$LEGACY_INTEREST_DB" "${TARGETS[CONTENT_DB]}" "link_interest_events"

# RSS schema.
for f in   0004_rss_library.sql   0006_rss_library_search_keys.sql   0010_rss_reader_state.sql   0011_rss_reader_library_plus.sql
do
  apply_file "${TARGETS[RSS_DB]}" "$ROOT/migrations/$f"
done

# Reddit schema.
apply_file "${TARGETS[REDDIT_DB]}" "$ROOT/migrations/0003_reddit_deep_sweep.sql"

# Ebook schemas come from the live source so legacy v65 is preserved exactly.
for t in ebook_reader_progress_v65 ebook_reader_state_v72 ebook_reader_trace_v113; do
  ensure_schema_from_source "$SOURCE_DB" "${TARGETS[EBOOK_DB]}" "$t"
done

# Re-copy checkpoint state, then retain only the intended namespace.
clear_table "${TARGETS[TASK_CONTEXT_DB]}" checkpoints
copy_table "$SOURCE_DB" "${TARGETS[TASK_CONTEXT_DB]}" checkpoints
"${WRANGLER[@]}" d1 execute "${TARGETS[TASK_CONTEXT_DB]}" --remote --command   "DELETE FROM checkpoints WHERE project NOT IN ('task-context','task-context-history','task-catalog') AND project NOT LIKE 'task-context-%'"

clear_table "${TARGETS[CONTEXT_INDEX_DB]}" checkpoints
copy_table "$SOURCE_DB" "${TARGETS[CONTEXT_INDEX_DB]}" checkpoints
"${WRANGLER[@]}" d1 execute "${TARGETS[CONTEXT_INDEX_DB]}" --remote --command   "DELETE FROM checkpoints WHERE project <> 'context-index'"

# Content data. Delete children first to keep reruns idempotent.
for t in user_content_events content_features content_scores personal_score_stage interest_family_profile interest_profile recommendation_runs content_items workflow_state link_interest_events; do
  clear_table "${TARGETS[CONTENT_DB]}" "$t"
done
for t in content_items content_features user_content_events content_scores interest_profile interest_family_profile personal_score_stage recommendation_runs; do
  copy_table "$SOURCE_DB" "${TARGETS[CONTENT_DB]}" "$t"
done
copy_table "$SOURCE_DB" "${TARGETS[CONTENT_DB]}" workflow_state
"${WRANGLER[@]}" d1 execute "${TARGETS[CONTENT_DB]}" --remote --command   "DELETE FROM workflow_state WHERE source NOT LIKE 'content-intelligence-%'"
copy_table "$LEGACY_INTEREST_DB" "${TARGETS[CONTENT_DB]}" link_interest_events

# RSS data. FTS is rebuilt by the existing insert/update triggers.
for t in rss_preference_events rss_reader_state rss_processing_events rss_translations rss_article_versions rss_articles rss_reader_categories; do
  clear_table "${TARGETS[RSS_DB]}" "$t"
done
for t in rss_articles rss_article_versions rss_translations rss_processing_events rss_reader_state rss_preference_events rss_reader_categories; do
  copy_table "$SOURCE_DB" "${TARGETS[RSS_DB]}" "$t"
done

# Reddit data.
for t in reddit_comments reddit_post_tags reddit_posts reddit_scan_runs; do
  clear_table "${TARGETS[REDDIT_DB]}" "$t"
done
for t in reddit_scan_runs reddit_posts reddit_comments reddit_post_tags; do
  copy_table "$SOURCE_DB" "${TARGETS[REDDIT_DB]}" "$t"
done

# Ebook data.
for t in ebook_reader_progress_v65 ebook_reader_state_v72 ebook_reader_trace_v113; do
  clear_table "${TARGETS[EBOOK_DB]}" "$t"
  copy_table "$SOURCE_DB" "${TARGETS[EBOOK_DB]}" "$t"
done

normalize_export() {
  local db="$1" table="$2" file="$3"
  local raw="$file.raw"
  rm -f "$raw" "$file"
  "${WRANGLER[@]}" d1 export "$db" --remote --skip-confirmation --table="$table" --no-schema --output="$raw"
  python3 - "$raw" "$file" <<'PY'
import pathlib,sys
lines=[]
for line in pathlib.Path(sys.argv[1]).read_text().splitlines():
    s=line.strip()
    if not s or s.startswith("--") or s in ("BEGIN TRANSACTION;","COMMIT;") or s.startswith("PRAGMA "): continue
    lines.append(line)
pathlib.Path(sys.argv[2]).write_text("\n".join(sorted(lines))+"\n")
PY
}

compare_table() {
  local src="$1" dst="$2" table="$3"
  local a="/tmp/verify-${table}-src.sql" b="/tmp/verify-${table}-dst.sql"
  normalize_export "$src" "$table" "$a"
  normalize_export "$dst" "$table" "$b"
  if ! cmp -s "$a" "$b"; then
    echo "VERIFY_MISMATCH:$table:$src:$dst" >&2
    sha256sum "$a" "$b" >&2
    exit 31
  fi
  echo "VERIFY_EQUAL:$table"
}

for t in content_items content_features user_content_events content_scores interest_profile interest_family_profile personal_score_stage recommendation_runs; do
  compare_table "$SOURCE_DB" "${TARGETS[CONTENT_DB]}" "$t"
done
compare_table "$LEGACY_INTEREST_DB" "${TARGETS[CONTENT_DB]}" link_interest_events

for t in rss_articles rss_article_versions rss_translations rss_processing_events rss_reader_state rss_preference_events rss_reader_categories; do
  compare_table "$SOURCE_DB" "${TARGETS[RSS_DB]}" "$t"
done

for t in reddit_scan_runs reddit_posts reddit_comments reddit_post_tags; do
  compare_table "$SOURCE_DB" "${TARGETS[REDDIT_DB]}" "$t"
done

for t in ebook_reader_progress_v65 ebook_reader_state_v72 ebook_reader_trace_v113; do
  compare_table "$SOURCE_DB" "${TARGETS[EBOOK_DB]}" "$t"
done

# Verify filtered checkpoint namespaces and FTS parity.
"${WRANGLER[@]}" d1 execute "${TARGETS[TASK_CONTEXT_DB]}" --remote --command   "SELECT CASE WHEN COUNT(*)=(SELECT COUNT(*) FROM checkpoints WHERE project IN ('task-context','task-context-history','task-catalog') OR project LIKE 'task-context-%') THEN 1 ELSE 0 END AS ok FROM checkpoints" --json >/tmp/task-context-proof.json
"${WRANGLER[@]}" d1 execute "${TARGETS[CONTEXT_INDEX_DB]}" --remote --command   "SELECT COUNT(*) AS n, SUM(CASE WHEN project='context-index' THEN 1 ELSE 0 END) AS good FROM checkpoints" --json >/tmp/context-index-proof.json
"${WRANGLER[@]}" d1 execute "${TARGETS[RSS_DB]}" --remote --command   "SELECT (SELECT COUNT(*) FROM rss_articles) AS articles,(SELECT COUNT(*) FROM rss_articles_fts) AS fts" --json >/tmp/rss-fts-proof.json

python3 - /tmp/task-context-proof.json /tmp/context-index-proof.json /tmp/rss-fts-proof.json <<'PY'
import json,sys
def rows(path):
    d=json.load(open(path))
    def find(x):
        if isinstance(x,dict):
            if isinstance(x.get("results"),list): return x["results"]
            for v in x.values():
                r=find(v)
                if r is not None:return r
        if isinstance(x,list):
            for v in x:
                r=find(v)
                if r is not None:return r
        return None
    return find(d) or []
task=rows(sys.argv[1]); ctx=rows(sys.argv[2]); rss=rows(sys.argv[3])
if not task or int(task[0].get("ok",0)) != 1: raise SystemExit("TASK_CONTEXT_PROOF_FAILED")
if not ctx or int(ctx[0].get("n",0)) != int(ctx[0].get("good",0)): raise SystemExit("CONTEXT_INDEX_PROOF_FAILED")
if not rss or int(rss[0].get("articles",0)) != int(rss[0].get("fts",0)): raise SystemExit("RSS_FTS_PROOF_FAILED")
print("FILTER_AND_FTS_PROOF_OK")
PY

# Patch Worker bindings only after all data verification passes.
python3 - <<'PY'
import json,os,pathlib
p=pathlib.Path("cloudflare/runner3-core/wrangler.jsonc")
cfg=json.loads(p.read_text())
wanted=[
  ("TASK_CONTEXT_DB","louis-task-context",os.environ["TASK_CONTEXT_DB"]),
  ("CONTEXT_INDEX_DB","louis-context-index",os.environ["CONTEXT_INDEX_DB"]),
  ("CONTENT_DB","runner3-content-intelligence",os.environ["CONTENT_DB"]),
  ("RSS_DB","runner3-rss",os.environ["RSS_DB"]),
  ("REDDIT_DB","runner3-reddit",os.environ["REDDIT_DB"]),
  ("EBOOK_DB","runner3-ebook",os.environ["EBOOK_DB"]),
]
bindings=cfg.setdefault("d1_databases",[])
by={x.get("binding"):i for i,x in enumerate(bindings)}
for binding,name,dbid in wanted:
    item={"binding":binding,"database_name":name,"database_id":dbid}
    if binding in by: bindings[by[binding]]=item
    else: bindings.append(item)
p.write_text(json.dumps(cfg,indent=2)+"\n")
PY

mkdir -p ops/cloudflare-capability
python3 - <<'PY'
import json,os,pathlib,datetime
doc={
  "schema_version":1,
  "status":"cutover-prepared",
  "recorded_at":datetime.datetime.now(datetime.timezone.utc).isoformat(),
  "source_database":"runner3-core",
  "authorities":{
    "control_plane":"runner3-core",
    "task_context":"louis-task-context",
    "context_index":"louis-context-index",
    "content_intelligence":"runner3-content-intelligence",
    "rss":"runner3-rss",
    "reddit":"runner3-reddit",
    "ebook":"runner3-ebook",
    "opportunity_radar":"runner3-opportunity-radar",
    "business_opportunity":"runner3-business-opportunity",
    "personal_library":"personal-library",
    "media_library":"media-library",
    "common_access":"ai-vps-common-access",
    "wp_optimizer":"runner3-wp-optimizer"
  },
  "legacy_retained_for_rollback":{
    "runner3-core":["content_*","user_content_events","interest_*","recommendation_runs","rss_*","reddit_*","ebook_reader_*","library_*","opportunity_*","task/context checkpoint rows"],
    "link-interest-profile":["link_interest_events"]
  },
  "cleanup_policy":"Do not delete legacy tables/databases until dedicated-D1 writes/readbacks remain healthy across multiple scheduled cycles."
}
pathlib.Path("ops/cloudflare-capability/d1-domain-isolation.json").write_text(json.dumps(doc,indent=2)+"\n")
PY

node --check "$ROOT/src/domain-db.js"
node --check "$ROOT/src/index.js"
node --check "$ROOT/src/rss-reader-learning.js"
node --check "$ROOT/src/rss-library-save.js"
node --check "$ROOT/rss-reader-read-fast-entry.js"
node --check "$ROOT/rss-article-fast-entry.js"
node --check "$ROOT/rss-entry.js"
node --check "$ROOT/reader-media-entry.js"
node --check "$ROOT/reddit-entry.js"
node --check "$ROOT/audio-entry.js"
node --check "$ROOT/artifact-library-reader-v7-github-audio-entry.js"
node --check "$ROOT/artifact-library-reader-v82-stable-shell-entry.js"

echo "D1_DOMAIN_ISOLATION_MIGRATION_OK"
