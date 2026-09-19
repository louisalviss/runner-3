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
# Heartbeats are valid only after today's daily scan has produced its terminal summary.
[ -s "$SHORTLIST" ] || exit 0

FINGERPRINT=$(python3 - "$BASE/data/manifest.json" <<'PY'
import hashlib,json,sys
m=json.load(open(sys.argv[1],encoding='utf-8'))
p={'unique_domains':m.get('unique_domains'),'sitemaps':[(x.get('part'),x.get('sha256'),x.get('count')) for x in m.get('sitemaps',[])]}
print(hashlib.sha256(json.dumps(p,sort_keys=True,separators=(',',':')).encode()).hexdigest())
PY
)
mapfile -t STATE_FIELDS < <(python3 - "$STATE" 2>/dev/null <<'PY' || true
import json,sys
try:
 s=json.load(open(sys.argv[1],encoding='utf-8'))
except Exception:
 s={}
print(s.get('fingerprint',''))
print(s.get('heartbeat_date',''))
PY
)
OLD=${STATE_FIELDS[0]:-}
HEARTBEAT_DATE=${STATE_FIELDS[1]:-}

COUNT=$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))["unique_domains"])' "$BASE/data/manifest.json")
ADDED=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1])).get("added",0))' "$BASE/data/manifest.json")
REMOVED=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1])).get("removed",0))' "$BASE/data/manifest.json")
read -r SCANNED SHORT < <(python3 - "$SHORTLIST" <<'PY'
import re,sys
try:
 s=open(sys.argv[1],encoding='utf-8').read()
 def n(label):
  m=re.search(rf'^- {label}: (\d+)\s*$',s,re.M)
  return int(m.group(1)) if m else 0
 print(n('scanned'),n('shortlist'))
except Exception:
 print(0,0)
PY
)

# No corpus change: still publish one explicit RUN OK heartbeat per UTC day.
if [[ "$FINGERPRINT" = "$OLD" ]]; then
  [[ "$HEARTBEAT_DATE" = "$DAY" ]] && exit 0
  "$WRAPPER" send "$TARGET" "SeoTrends RUN OK | $DAY | domains=$COUNT | +$ADDED / -$REMOVED | scanned=$SCANNED | shortlist=$SHORT | corpus=unchanged"
  python3 - "$STATE" "$DAY" <<'PY'
import json,sys,os
p,day=sys.argv[1:]
try:
 s=json.load(open(p,encoding='utf-8'))
except Exception:
 s={}
s['heartbeat_date']=day
t=p+'.tmp'
open(t,'w',encoding='utf-8').write(json.dumps(s,indent=2)+'\n')
os.replace(t,p)
PY
  exit 0
fi

OUT="/var/lib/telegram-upload/seotrends/daily/$DAY"
install -d -m 0750 "$OUT"
cp -f "$BASE/data/manifest.json" "$OUT/manifest.json"
cp -f "$BASE/changes/$DAY-added.txt" "$OUT/added.txt" 2>/dev/null || :
cp -f "$BASE/changes/$DAY-removed.txt" "$OUT/removed.txt" 2>/dev/null || :
cp -f "$SHORTLIST" "$OUT/shortlist.md" 2>/dev/null || :
cp -f "$BASE/scans/$DAY-candidates.jsonl" "$OUT/candidates.jsonl" 2>/dev/null || :
ARCHIVE="$OUT/seotrends-public-$DAY-full.tar.gz"
tar -C /var/lib -czf "$ARCHIVE" seotrends-public -C /etc/systemd/system seotrends-public-refresh.service seotrends-public-refresh.timer -C /usr/local/sbin seotrends-telegram-sync seotrends-github-fallback
SHA=$(sha256sum "$ARCHIVE" | awk '{print $1}')
"$WRAPPER" upload-local "$TARGET" "$ARCHIVE" "SeoTrends daily full snapshot $DAY | domains=$COUNT | sha256=$SHA"
"$WRAPPER" send "$TARGET" "SeoTrends RUN OK | $DAY | domains=$COUNT | +$ADDED / -$REMOVED | scanned=$SCANNED | shortlist=$SHORT | corpus=changed | sha256=$SHA"
python3 - "$STATE" "$FINGERPRINT" "$DAY" "$SHA" <<'PY'
import json,sys,os
p,fp,day,sha=sys.argv[1:]
t=p+'.tmp'
open(t,'w',encoding='utf-8').write(json.dumps({'fingerprint':fp,'date':day,'archive_sha256':sha,'heartbeat_date':day},indent=2)+'\n')
os.replace(t,p)
PY
