#!/usr/bin/env bash
set -euo pipefail
umask 077
BASE=/var/lib/seotrends-public
TARGET='-1004357761890'
WRAPPER=/opt/telegram-mtproto/run-secure.sh
STATE="$BASE/telegram-sync-state.json"
LOCK=/run/seotrends-telegram-sync.lock
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
SYNC_KEY="$DAY:$FINGERPRINT:$TERMINAL_SHA"
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
install -d -m 0750 "$OUT"
cp -f "$BASE/data/manifest.json" "$OUT/manifest.json"
cp -f "$BASE/changes/$DAY-added.txt" "$OUT/added.txt" 2>/dev/null || :
cp -f "$BASE/changes/$DAY-removed.txt" "$OUT/removed.txt" 2>/dev/null || :
cp -f "$SHORTLIST" "$OUT/shortlist.md"
cp -f "$BASE/scans/$DAY-candidates.jsonl" "$OUT/candidates.jsonl" 2>/dev/null || :
cp -f "$BASE/scans/$DAY-semrush-results.md" "$OUT/semrush-results.md" 2>/dev/null || :
cp -f "$BASE/scans/$DAY-terminal-verdicts.md" "$OUT/terminal-verdicts.md" 2>/dev/null || :
ARCHIVE="$OUT/seotrends-public-$DAY-full.tar.gz"
tar -C /var/lib -czf "$ARCHIVE" seotrends-public -C /etc/systemd/system seotrends-public-refresh.service seotrends-public-refresh.timer -C /usr/local/sbin seotrends-telegram-sync seotrends-github-fallback
SHA=$(sha256sum "$ARCHIVE" | awk '{print $1}')
"$WRAPPER" upload-local "$TARGET" "$ARCHIVE" "SeoTrends canonical snapshot $DAY | status=$RUN_STATUS | domains=$COUNT | sha256=$SHA"
"$WRAPPER" send "$TARGET" "SeoTrends $RUN_STATUS | $DAY | domains=$COUNT | +$ADDED / -$REMOVED | scanned=$SCANNED | pending=$PENDING | shortlist=$SHORT | BUILD=$BUILD WATCH=$WATCH DROP=$DROP BLOCKED=$BLOCKED | sha256=$SHA"
python3 - "$STATE" "$FINGERPRINT" "$TERMINAL_SHA" "$SYNC_KEY" "$DAY" "$SHA" "$RUN_STATUS" <<'PY'
import json,sys,os
p,fp,tsha,key,day,sha,status=sys.argv[1:]; t=p+'.tmp'
open(t,'w',encoding='utf-8').write(json.dumps({'fingerprint':fp,'terminal_sha256':tsha,'sync_key':key,'date':day,'archive_sha256':sha,'heartbeat_date':day,'status':status},indent=2)+'\n')
os.replace(t,p)
PY
