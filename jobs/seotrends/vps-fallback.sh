#!/usr/bin/env bash
set -euo pipefail
umask 077
BASE=/var/lib/seotrends-public
REPO=louisalviss/runner-3
WORKFLOW=seotrends-public.yml
DAY=$(date -u +%F)
LOCK=/run/seotrends-github-fallback.lock
STATE="$BASE/fallback-state.json"
exec 9>"$LOCK"
flock -n 9 || exit 0

log(){ printf '[%s] %s\n' "$(date -u +%FT%TZ)" "$*"; }
run_local(){
  log 'GitHub primary unavailable; running VPS fallback compute'
  python3 "$BASE/scripts/refresh.py"
  python3 "$BASE/scripts/daily_scan.py" --max 300 --workers 16 --timeout 5
  timeout 10m /usr/local/sbin/seotrends-telegram-sync || log 'Telegram sync timed out or returned non-zero'
  python3 - "$STATE" "$DAY" <<'PY'
import json,sys,os
p,day=sys.argv[1:]; t=p+'.tmp'
open(t,'w').write(json.dumps({'date':day,'source':'vps-fallback'},indent=2)+'\n')
os.replace(t,p)
PY
}
latest=$(gh run list --repo "$REPO" --workflow "$WORKFLOW" --limit 10 \
  --json databaseId,status,conclusion,createdAt,event,url \
  --jq ".[] | select(.createdAt | startswith(\"$DAY\")) | @json" | head -1 || true)

if [[ -z "$latest" ]]; then
  run_local
  exit 0
fi

run_id=$(python3 -c 'import json,sys; print(json.loads(sys.stdin.read())["databaseId"])' <<<"$latest")
status=$(python3 -c 'import json,sys; print(json.loads(sys.stdin.read())["status"])' <<<"$latest")
conclusion=$(python3 -c 'import json,sys; print(json.loads(sys.stdin.read()).get("conclusion") or "")' <<<"$latest")

if [[ "$status" != completed || "$conclusion" != success ]]; then
  log "GitHub run $run_id is $status/$conclusion"
  run_local
  exit 0
fi

TMP=$(mktemp -d /tmp/seotrends-gh-XXXXXX)
trap 'rm -rf "$TMP"' EXIT
if ! gh run download "$run_id" --repo "$REPO" -n seotrends-state -D "$TMP"; then
  log "Could not download GitHub artifact for run $run_id"
  run_local
  exit 0
fi
hb="$TMP/heartbeat.json"
cur="$TMP/data/domains-current.csv.gz"
manifest="$TMP/data/manifest.json"
if [[ ! -s "$hb" || ! -s "$cur" || ! -s "$manifest" ]]; then
  log 'GitHub artifact missing required state files'
  run_local
  exit 0
fi

hb_day=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["date"])' "$hb")
if [[ "$hb_day" != "$DAY" ]]; then
  log "GitHub artifact date mismatch: $hb_day != $DAY"
  run_local
  exit 0
fi
had_prev=$(python3 -c 'import json,sys; print(str(bool(json.load(open(sys.argv[1])).get("had_previous_state"))).lower())' "$manifest")
if [[ "$had_prev" != true && -s "$BASE/data/domains-current.csv.gz" ]]; then
  log 'GitHub artifact is bootstrap-only; preserve VPS prior state and compute local diff'
  run_local
  exit 0
fi

log "Using GitHub primary run $run_id"
install -d -m 0750 "$BASE/data" "$BASE/changes" "$BASE/scans"
cp -f "$cur" "$BASE/data/domains-current.csv.gz"
cp -f "$cur" "$BASE/data/domains-$DAY.csv.gz"
cp -f "$manifest" "$BASE/data/manifest.json"
cp -f "$TMP/changes/$DAY-added.txt" "$BASE/changes/$DAY-added.txt" 2>/dev/null || :
cp -f "$TMP/changes/$DAY-removed.txt" "$BASE/changes/$DAY-removed.txt" 2>/dev/null || :
cp -f "$TMP/scans/$DAY-candidates.jsonl" "$BASE/scans/$DAY-candidates.jsonl" 2>/dev/null || :
cp -f "$TMP/scans/$DAY-candidates.csv" "$BASE/scans/$DAY-candidates.csv" 2>/dev/null || :
cp -f "$TMP/scans/$DAY-shortlist.md" "$BASE/scans/$DAY-shortlist.md" 2>/dev/null || :
python3 "$BASE/scripts/rebuild_sqlite.py" "$cur" "$BASE/data/domains.sqlite"
timeout 10m /usr/local/sbin/seotrends-telegram-sync || log 'Telegram sync timed out or returned non-zero'
printf '{\n  "date": "%s",\n  "source": "github-primary",\n  "run_id": "%s"\n}\n' "$DAY" "$run_id" > "$STATE.tmp"
mv -f "$STATE.tmp" "$STATE"
log "GitHub primary mirrored successfully: run $run_id"
