#!/usr/bin/env bash
set -Eeuo pipefail
umask 077
root=/opt/bike-niche-corpus
echo "GEOMETRYGEEKS_DISCOVERY_START $(date -u +%FT%TZ)"
/usr/bin/python3 "$root/geometrygeeks_inventory.py"
echo "GEOMETRYGEEKS_DISCOVERY_DONE $(date -u +%FT%TZ)"
exec /bin/bash "$root/run_pipeline.sh" geometrygeeks
