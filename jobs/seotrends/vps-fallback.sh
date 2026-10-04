#!/usr/bin/env bash
set -euo pipefail
umask 077
BASE=/var/lib/seotrends-public
DAY=$(date -u +%F)
LOCK=/run/seotrends-github-fallback.lock
STATE="$BASE/fallback-state.json"
exec 9>"$LOCK"
flock -n 9 || exit 0

log(){ printf '[%s] %s\n' "$(date -u +%FT%TZ)" "$*"; }

run_semrush(){
  log "Consuming SeoTrends Semrush queue for $DAY"
  timeout 20m python3 "$BASE/scripts/semrush_daily.py" --date "$DAY" || log 'Semrush current batch returned non-zero'
}
run_terminal(){
  log "Running exact SERP terminal gate for $DAY"
  timeout 25m python3 "$BASE/scripts/terminal_funnel.py" --date "$DAY" || log 'Terminal gate returned degraded/non-zero'
}
already_done(){
  python3 - "$STATE" "$BASE/scans/$DAY-terminal-verdicts.json" "$DAY" <<'PY'
import json,sys
statep,termp,day=sys.argv[1:]
try: s=json.load(open(statep,encoding='utf-8'))
except Exception: s={}
try: t=json.load(open(termp,encoding='utf-8'))
except Exception: t={}
print('yes' if s.get('date')==day and s.get('source')=='vps-primary' and t.get('status')=='PASS' else 'no')
PY
}
if [[ "$(already_done)" == yes ]]; then
  log "Canonical batch already PASS for $DAY; only repairing backlog/sync"
  timeout 35m python3 "$BASE/scripts/repair_backlog.py" --days 14 --exclude-today || log 'Backlog repair returned non-zero'
  timeout 10m /usr/local/sbin/seotrends-telegram-sync || log 'Telegram sync returned non-zero'
  exit 0
fi
log 'Running VPS canonical SeoTrends daily compute'
python3 "$BASE/scripts/refresh.py"
python3 "$BASE/scripts/daily_scan.py" --workers 16 --timeout 5
run_semrush
run_terminal
timeout 35m python3 "$BASE/scripts/repair_backlog.py" --days 14 --exclude-today || log 'Backlog repair returned non-zero'
timeout 10m /usr/local/sbin/seotrends-telegram-sync || log 'Telegram sync returned non-zero'
python3 - "$STATE" "$DAY" <<'PY'
import json,sys,os
p,day=sys.argv[1:]; t=p+'.tmp'
open(t,'w').write(json.dumps({'date':day,'source':'vps-primary'},indent=2)+'\n')
os.replace(t,p)
PY
log "VPS canonical SeoTrends batch finished for $DAY"
