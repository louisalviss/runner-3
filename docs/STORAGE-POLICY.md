# Runner3 storage policy

Use the smallest durable store that matches the data shape.

## D1
Use D1 for small structured state that must be queried, filtered, joined, deduplicated, or updated independently:
- current workload status
- run/event metadata
- checkpoints and cursors
- freshness timestamps
- retry/error state
- artifact pointers/URLs/keys

Do not store large payload bodies, media, scraped pages, ebooks, datasets, or long-lived raw logs in D1.

## Dropbox / R2
Use object/file storage for payloads and artifacts:
- audio/video/images
- EPUB/PDF/ZIP
- raw scrape captures
- large JSON/CSV datasets
- generated reports and exports
- archival logs

Store only the artifact pointer plus compact metadata in D1.

## Dropbox vs R2
- Dropbox: human-facing library, canonical project files, documents that need manual browsing/editing/backup.
- R2: machine-facing blobs, high-churn generated artifacts, raw captures, cache/archive objects consumed by automation.

## Retention
- current-state rows: keep indefinitely, one row per logical source/key via upsert.
- routine telemetry/events: keep 90 days by default.
- verbose/raw logs: do not put in D1; store externally when needed.
- important checkpoints/failures: retain until superseded or explicitly archived.

Rule of thumb: if a row is useful mainly because of its fields, put it in D1. If it is useful mainly as a whole file/blob, put it in Dropbox/R2 and keep only a pointer in D1.
