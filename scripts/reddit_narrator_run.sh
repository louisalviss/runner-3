#!/usr/bin/env bash
set -Eeuo pipefail

WORKDIR="${WORKDIR:-work/reddit-unsolved}"
OUTDIR="${OUTDIR:-artifacts/reddit-unsolved}"
BUCKET="${BUCKET:-runner3-wp-media}"
PREFIX="${PREFIX:-listen/reddit-creepiest-unsolved-v1}"
VOICE="${VOICE:-vi-VN-NamMinhNeural}"
VOICE_RATE="${VOICE_RATE:-+3%}"
STATUS="ops/reddit-narrator/latest.json"
CURRENT_STAGE="install"

mkdir -p "$WORKDIR" "$OUTDIR" "$(dirname "$STATUS")"
git config user.name 'github-actions[bot]'
git config user.email '41898282+github-actions[bot]@users.noreply.github.com'

commit_status() {
  local msg="$1"
  git add "$STATUS" || true
  git commit -m "$msg" || true
  git pull --rebase origin main || true
  git push origin HEAD:main || true
}

write_status() {
  local status="$1" install="$2" fetch="$3" render="$4" publish="$5"
  STATUS_VALUE="$status" INSTALL_VALUE="$install" FETCH_VALUE="$fetch" RENDER_VALUE="$render" PUBLISH_VALUE="$publish" \
  PREFIX="$PREFIX" OUTDIR="$OUTDIR" WORKDIR="$WORKDIR" CURRENT_STAGE_VALUE="$CURRENT_STAGE" python - <<'PY'
import datetime,json,os
from pathlib import Path
p=Path('ops/reddit-narrator/latest.json')
base=''
try:
    base=json.loads(Path('ops/r2-media/status.json').read_text(encoding='utf-8')).get('baseUrl','')
except Exception:
    pass
prefix=os.environ['PREFIX']
outdir=Path(os.environ['OUTDIR'])
workdir=Path(os.environ['WORKDIR'])
status=os.environ['STATUS_VALUE']
steps={
  'install':os.environ['INSTALL_VALUE'],
  'redditFetch':os.environ['FETCH_VALUE'],
  'render':os.environ['RENDER_VALUE'],
  'publish':os.environ['PUBLISH_VALUE'],
}
duration=None; case_count=None
try:
    ch=json.loads((outdir/'chapters.json').read_text(encoding='utf-8'))
    if ch.get('duration_seconds') is not None: duration=float(ch['duration_seconds'])
    if isinstance(ch.get('selected_cases'),list): case_count=len(ch['selected_cases'])
except Exception:
    pass
ready=status=='ready'
obj={
  'status':status,
  'episodeId':'reddit-creepiest-unsolved-v1',
  'playerUrl':f'{base}/{prefix}/index.html' if ready and base else '',
  'audioUrl':f'{base}/{prefix}/episode.mp3' if ready and base else '',
  'voice':'vi-VN-NamMinhNeural',
  'resume':'localStorage/same-browser',
  'steps':steps,
  'durationSeconds':duration,
  'caseCount':case_count,
  'updatedAt':datetime.datetime.now(datetime.timezone.utc).isoformat(),
}
if status == 'failed':
    stage=os.environ.get('CURRENT_STAGE_VALUE','unknown')
    obj['failedStage']=stage
    log_map={
      'redditFetch': workdir/'fetch.log',
      'render': outdir/'render-summary.txt',
      'publish': workdir/'publish.log',
    }
    lp=log_map.get(stage)
    if lp and lp.exists():
        txt=lp.read_text(encoding='utf-8',errors='ignore')
        obj['errorTail']=txt[-6000:]
p.parent.mkdir(parents=True,exist_ok=True)
p.write_text(json.dumps(obj,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps(obj,ensure_ascii=False))
PY
}

fail_handler() {
  local code=$?
  case "$CURRENT_STAGE" in
    install) write_status failed failure skipped skipped skipped ;;
    redditFetch) write_status failed success failure skipped skipped ;;
    render) write_status failed success success failure skipped ;;
    publish) write_status failed success success success failure ;;
    *) write_status failed unknown unknown unknown unknown ;;
  esac
  commit_status "Persist Reddit narrator failure at ${CURRENT_STAGE}"
  exit "$code"
}
trap fail_handler ERR

write_status running pending pending pending pending
commit_status 'Mark Reddit narrator run started'

CURRENT_STAGE="install"
python -m pip install -q -U requests beautifulsoup4 playwright edge-tts
if ! command -v ffmpeg >/dev/null 2>&1; then
  sudo apt-get update -qq
  sudo apt-get install -y -qq ffmpeg
fi
mkdir -p "$WORKDIR" "$OUTDIR"
write_status running success pending pending pending
commit_status 'Reddit narrator install complete'

CURRENT_STAGE="redditFetch"
bash scripts/reddit_fetch_runner.sh 2>&1 | tee "$WORKDIR/fetch.log"
write_status running success success pending pending
commit_status 'Reddit narrator fetch complete'

CURRENT_STAGE="render"
python -m py_compile scripts/reddit_unsolved_narrator.py
python scripts/reddit_unsolved_narrator.py 2>&1 | tee "$OUTDIR/render-summary.txt"
test -s "$OUTDIR/episode.mp3"
test -s "$OUTDIR/index.html"
ffprobe -v error -show_entries format=duration,size -of default=nw=1 "$OUTDIR/episode.mp3"
write_status running success success success pending
commit_status 'Reddit narrator render complete'

CURRENT_STAGE="publish"
{
  test -n "${CLOUDFLARE_API_TOKEN:-}"
  test -n "${CLOUDFLARE_ACCOUNT_ID:-}"
  echo '::add-mask::'"$CLOUDFLARE_API_TOKEN"
  echo '::add-mask::'"$CLOUDFLARE_ACCOUNT_ID"
  base="$(python -c "import json; print(json.load(open('ops/r2-media/status.json'))['baseUrl'])")"
  put() {
    npx -y wrangler@4.123.0 r2 object put "$BUCKET/$2" --file="$1" --content-type="$3" --cache-control="$4" --remote
  }
  put "$OUTDIR/episode.mp3" "$PREFIX/episode.mp3" 'audio/mpeg' 'public, max-age=300'
  put "$OUTDIR/index.html" "$PREFIX/index.html" 'text/html; charset=utf-8' 'public, max-age=60'
  put "$OUTDIR/chapters.json" "$PREFIX/chapters.json" 'application/json; charset=utf-8' 'public, max-age=60'
  put "$OUTDIR/top-comments.json" "$PREFIX/top-comments.json" 'application/json; charset=utf-8' 'public, max-age=60'
  put "$OUTDIR/transcript.txt" "$PREFIX/transcript.txt" 'text/plain; charset=utf-8' 'public, max-age=60'
  player="$base/$PREFIX/index.html"
  audio="$base/$PREFIX/episode.mp3"
  for _ in 1 2 3 4 5; do
    code_html="$(curl -sS -o /tmp/player.html -w '%{http_code}' "$player" || true)"
    code_audio="$(curl -sS -I -o /tmp/audio-head.txt -w '%{http_code}' "$audio" || true)"
    if [ "$code_html" = 200 ] && [ "$code_audio" = 200 ] && grep -q 'runner3:reddit-creepiest-unsolved-v1:position' /tmp/player.html; then
      break
    fi
    sleep 2
  done
  test "$code_html" = 200
  test "$code_audio" = 200
  grep -q 'runner3:reddit-creepiest-unsolved-v1:position' /tmp/player.html
} 2>&1 | tee "$WORKDIR/publish.log"

write_status ready success success success success
commit_status 'Publish Reddit narrator ready'
echo "PLAYER_URL=$player"
echo "AUDIO_URL=$audio"
