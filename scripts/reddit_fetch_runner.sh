#!/usr/bin/env bash
set -euo pipefail

WORKDIR="${WORKDIR:-work/reddit-unsolved}"
mkdir -p "$WORKDIR"
out="$WORKDIR/reddit.json"

rm -rf "$WORKDIR/crawl-http" "$WORKDIR/crawl-browser"

http_ok=0
if python crawler.py config/reddit-narrator-http.json --output "$WORKDIR/crawl-http"; then
  cat "$WORKDIR/crawl-http/manifest.json" || true
  if python scripts/reddit_crawl_adapter.py "$WORKDIR/crawl-http" "$out" | tee "$WORKDIR/reddit-http-summary.json"; then
    http_ok=1
  fi
fi

if [ "$http_ok" -ne 1 ]; then
  echo 'Runner HTTP path did not expose enough Best-thread content; using Chromium.'
  python -m playwright install --with-deps chromium
  python crawler.py config/reddit-narrator-browser.json --output "$WORKDIR/crawl-browser"
  cat "$WORKDIR/crawl-browser/manifest.json"
  python scripts/reddit_crawl_adapter.py "$WORKDIR/crawl-browser" "$out" | tee "$WORKDIR/reddit-browser-summary.json"
fi

python - "$out" <<'PY'
import json,sys
p=sys.argv[1]
d=json.load(open(p,encoding='utf-8'))
assert isinstance(d,list) and len(d)>=2
children=d[1]['data']['children']
assert len(children)>=5, f'only {len(children)} matched cases'
print('MATCHED_VERIFIED_CASES='+str(len(children)))
PY
