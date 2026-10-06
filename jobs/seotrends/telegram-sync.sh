#!/usr/bin/env bash
set -euo pipefail
umask 077
BASE=/var/lib/seotrends-public
TARGET='-1004357761890'
WRAPPER=/opt/telegram-mtproto/run-secure.sh
STATE="$BASE/telegram-sync-state.json"
LOCK=/run/seotrends-telegram-sync.lock
ARCHIVE_SCHEMA='public-derived-v2'
exec 9>"$LOCK"
flock -n 9 || exit 0
[ -s "$BASE/data/manifest.json" ] || exit 2

DAY=$(date -u +%F)
SHORTLIST="$BASE/scans/$DAY-shortlist.md"
TERMINAL="$BASE/scans/$DAY-terminal-verdicts.json"
[ -s "$SHORTLIST" ] || exit 0
[ -s "$TERMINAL" ] || exit 0

FINGERPRINT=$(python3 - "$BASE/data/manifest.json" <<'PY'
import hashlib,json,sys
m=json.load(open(sys.argv[1],encoding='utf-8'))
p={'unique_domains':m.get('unique_domains'),'sitemaps':[(x.get('part'),x.get('sha256'),x.get('count')) for x in m.get('sitemaps',[])]}
print(hashlib.sha256(json.dumps(p,sort_keys=True,separators=(',',':')).encode()).hexdigest())
PY
)
TERMINAL_SHA=$(sha256sum "$TERMINAL" | awk '{print $1}')
SYNC_KEY="$ARCHIVE_SCHEMA:$DAY:$FINGERPRINT:$TERMINAL_SHA"
OLD_KEY=$(python3 - "$STATE" 2>/dev/null <<'PY' || true
import json,sys
try: s=json.load(open(sys.argv[1],encoding='utf-8'))
except Exception: s={}
print(s.get('sync_key',''))
PY
)
[[ "$OLD_KEY" = "$SYNC_KEY" ]] && exit 0

COUNT=$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))["unique_domains"])' "$BASE/data/manifest.json")
ADDED=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1])).get("added",0))' "$BASE/data/manifest.json")
REMOVED=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1])).get("removed",0))' "$BASE/data/manifest.json")
read -r SCANNED PENDING SHORT < <(python3 - "$SHORTLIST" <<'PY'
import re,sys
s=open(sys.argv[1],encoding='utf-8').read()
def n(label):
 m=re.search(rf'^- {label}: (\d+)\s*$',s,re.M)
 return int(m.group(1)) if m else 0
print(n('scanned'),n('pending'),n('shortlist'))
PY
)
read -r RUN_STATUS BUILD WATCH DROP BLOCKED < <(python3 - "$TERMINAL" <<'PY'
import json,sys
t=json.load(open(sys.argv[1],encoding='utf-8')); c=t.get('counts') or {}
print(t.get('status','UNKNOWN'),c.get('BUILD',0),c.get('WATCH',0),c.get('DROP',0),c.get('BLOCKED',0))
PY
)

OUT="/var/lib/telegram-upload/seotrends/daily/$DAY"
STAGE="$OUT/$ARCHIVE_SCHEMA-$TERMINAL_SHA"
install -d -m 0750 "$STAGE/data" "$STAGE/changes" "$STAGE/scans" "$STAGE/scripts" "$STAGE/systemd" "$STAGE/sbin"
cp -f "$BASE/data/domains-current.csv.gz" "$STAGE/data/"
cp -f "$BASE/data/domains-$DAY.csv.gz" "$STAGE/data/" 2>/dev/null || :
cp -f "$BASE/data/domains.sqlite" "$STAGE/data/" 2>/dev/null || :
cp -f "$BASE/data/manifest.json" "$STAGE/data/"
cp -f "$BASE/changes/$DAY-added.txt" "$STAGE/changes/" 2>/dev/null || :
cp -f "$BASE/changes/$DAY-removed.txt" "$STAGE/changes/" 2>/dev/null || :
cp -f "$SHORTLIST" "$STAGE/scans/"
cp -f "$BASE/scans/$DAY-candidates.jsonl" "$STAGE/scans/" 2>/dev/null || :
cp -f "$BASE/scans/$DAY-candidates.csv" "$STAGE/scans/" 2>/dev/null || :
cp -f "$BASE/scans/$DAY-semrush-results.md" "$STAGE/scans/" 2>/dev/null || :
cp -f "$BASE/scans/$DAY-terminal-verdicts.json" "$STAGE/scans/" 2>/dev/null || :
cp -f "$BASE/scans/$DAY-terminal-verdicts.md" "$STAGE/scans/" 2>/dev/null || :
find "$BASE/scripts" -maxdepth 1 -type f -name '*.py' -exec cp -f {} "$STAGE/scripts/" \;
cp -f "$BASE/README.md" "$STAGE/" 2>/dev/null || :
cp -f /etc/systemd/system/seotrends-public-refresh.service "$STAGE/systemd/"
cp -f /etc/systemd/system/seotrends-public-refresh.timer "$STAGE/systemd/"
cp -f /usr/local/sbin/seotrends-telegram-sync "$STAGE/sbin/"
cp -f /usr/local/sbin/seotrends-github-fallback "$STAGE/sbin/"

python3 - "$STAGE" "$DAY" "$ARCHIVE_SCHEMA" <<'PY'
import hashlib,json,pathlib,sys
root=pathlib.Path(sys.argv[1]); day=sys.argv[2]; schema=sys.argv[3]
files=[]
for p in sorted(root.rglob('*')):
    if p.is_file() and p.name!='archive-manifest.json':
        h=hashlib.sha256(p.read_bytes()).hexdigest()
        files.append({'path':str(p.relative_to(root)),'size':p.stat().st_size,'sha256':h})
(root/'archive-manifest.json').write_text(json.dumps({'schema':schema,'date':day,'retention':'public-data + derived summaries only; raw Semrush/SERP excluded','files':files},indent=2)+'\n',encoding='utf-8')
PY

ARCHIVE="$OUT/seotrends-public-$DAY-$ARCHIVE_SCHEMA.tar.gz"
tar -C "$STAGE" -czf "$ARCHIVE" .
SHA=$(sha256sum "$ARCHIVE" | awk '{print $1}')
"$WRAPPER" upload-local "$TARGET" "$ARCHIVE" "SeoTrends canonical public/derived snapshot $DAY | schema=$ARCHIVE_SCHEMA | status=$RUN_STATUS | domains=$COUNT | sha256=$SHA"
"$WRAPPER" send "$TARGET" "SeoTrends $RUN_STATUS | $DAY | domains=$COUNT | +$ADDED / -$REMOVED | scanned=$SCANNED | pending=$PENDING | shortlist=$SHORT | BUILD=$BUILD WATCH=$WATCH DROP=$DROP BLOCKED=$BLOCKED | archive=$ARCHIVE_SCHEMA | sha256=$SHA"
python3 - "$STATE" "$FINGERPRINT" "$TERMINAL_SHA" "$SYNC_KEY" "$DAY" "$SHA" "$RUN_STATUS" "$ARCHIVE_SCHEMA" <<'PY'
import json,sys,os
p,fp,tsha,key,day,sha,status,schema=sys.argv[1:]; t=p+'.tmp'
open(t,'w',encoding='utf-8').write(json.dumps({'fingerprint':fp,'terminal_sha256':tsha,'sync_key':key,'date':day,'archive_sha256':sha,'heartbeat_date':day,'status':status,'archive_schema':schema},indent=2)+'\n')
os.replace(t,p)
PY
