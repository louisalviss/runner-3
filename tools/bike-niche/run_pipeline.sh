#!/usr/bin/env bash
set -Eeuo pipefail
umask 077
for source in "$@"; do
  echo "START $source $(date -u +%FT%TZ)"
  /usr/bin/python3 /opt/bike-niche-corpus/collector.py "$source" --workers 1 --batch 12 --min-delay 0.75 --max-delay 1.45
  echo "CRAWL_TERMINAL $source $(date -u +%FT%TZ)"
  /usr/bin/python3 /opt/bike-niche-corpus/publish_source.py "$source"
  echo "PUBLISHED $source $(date -u +%FT%TZ)"
done
