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
  timeout 20m python3 "$BASE/scripts/semrush_daily.py" --date "$DAY" || log 'Semrush current batch nonterminal; inspect result JSON'
}
run_terminal(){
  log "Running exact SERP terminal gate for $DAY"
  timeout 25m python3 "$BASE/scripts/terminal_funnel.py" --date "$DAY" || log 'Terminal gate returned degraded/non-zero'
}
is_auth_blocked(){
  python3 - "$BASE/scans/$DAY-semrush-results.json" <<'PY'
import json,sys
try: j=json.load(open(sys.argv[1],encoding='utf-8'))
except Exception: j={}
why=str(j.get('global_blocker') or '')
print('yes' if j.get('status')=='BLOCKED' and any(x in why for x in ('SEMRUSH_LIVE_AUTH_UNAVAILABLE','NOX_LOGIN_CHALLENGE','NOX_LOGIN_FORM_MISSING','NOX_DASHBOARD_CHALLENGE','NOX_LOGIN_REQUIRED','NOX_SEMRUSH_LINKS_MISSING','SEMRUSH_HUMAN_HANDOFF_ACTIVE')) else 'no')
PY
}
terminal_status(){
  python3 - "$BASE/scans/$DAY-terminal-verdicts.json" <<'PY'
import json,sys
try: j=json.load(open(sys.argv[1],encoding='utf-8'))
except Exception: j={}
print(j.get('status','MISSING'))
PY
}

is_provider_limited(){
  python3 - "$BASE/scans/$DAY-terminal-verdicts.json" "$BASE/scans/$DAY-semrush-results.json" <<'PY'
import json,sys
try: t=json.load(open(sys.argv[1],encoding='utf-8'))
except (OSError,ValueError):t={}
try: s=json.load(open(sys.argv[2],encoding='utf-8'))
except (OSError,ValueError):s={}
run=t.get('serp_run') or {}
err=str(run.get('reason') or '')+' '+str((run.get('state') or {}).get('blocker') or '')
err+=' '+str(s.get('global_blocker') or '')
print('yes' if any(x in err for x in ('SEMRUSH_RATE_LIMIT','SEMRUSH_REPORT_LIMIT','-2002','-2004')) else 'no')
PY
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
  timeout 10m python3 "$BASE/scripts/backfill_sync.py" || log 'Backfill Telegram sync returned non-zero'
  timeout 10m /usr/local/sbin/seotrends-telegram-sync || log 'Telegram sync returned non-zero'
  exit 0
fi
SOURCE_ALREADY_COMPLETE=$(python3 - "$BASE/scans/$DAY-semrush-queue.json" "$DAY" <<'PY'
import json,sys
try: j=json.load(open(sys.argv[1],encoding="utf-8"))
except Exception: j={}
ok=(j.get("date")==sys.argv[2] and j.get("scan_terminal") is True
    and int(j.get("added_total") or 0)>0
    and int(j.get("scanned") or 0)==int(j.get("added_total") or 0)
    and int(j.get("count") or 0)==len(j.get("items") or []))
print("yes" if ok else "no")
PY
)
if [[ "$SOURCE_ALREADY_COMPLETE" == yes ]]; then
  log "SeoTrends $DAY original source already complete; preserving added delta and 14-day snapshot on same-day replay"
else
  log 'Running VPS canonical SeoTrends daily compute'
  python3 "$BASE/scripts/refresh.py"
  python3 "$BASE/scripts/daily_scan.py" --workers 16 --timeout 5
fi
run_semrush
run_terminal
if [[ "$(is_auth_blocked)" == yes || "$(is_provider_limited)" == yes ]]; then
  log "Semrush auth/provider-limit blocker; skipping repeated historical broker calls"
else
  timeout 35m python3 "$BASE/scripts/repair_backlog.py" --days 14 --exclude-today || log 'Backlog repair returned non-zero'
  timeout 10m python3 "$BASE/scripts/backfill_sync.py" || log 'Backfill Telegram sync returned non-zero'
fi
timeout 10m /usr/local/sbin/seotrends-telegram-sync || log 'Telegram sync returned non-zero'
STATUS=$(terminal_status)
python3 - "$STATE" "$DAY" "$STATUS" <<'PY'
import json,sys,os
p,day,status=sys.argv[1:]; t=p+'.tmp'
with open(t,'w') as f:
 json.dump({'date':day,'source':'vps-primary','terminal_status':status},f,indent=2)
os.replace(t,p)
PY
log "VPS canonical SeoTrends batch finished for $DAY: terminal=$STATUS"
if [[ "$STATUS" != PASS ]]; then
  log "BLOCKED/DEGRADED is not systemd SUCCESS; daily public data and status were saved"
  exit 3
fi
