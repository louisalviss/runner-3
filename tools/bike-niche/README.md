# Bicycle niche data acquisition

Reusable modules for public bicycle specifications, geometry, sizing, component catalogs, and technical compatibility reference data. This supplements (rather than overwrites) the existing Biklo catalog.

## Source isolation

| Source | Public data | Local dataset |
|---|---|---|
| Biklo | Existing main catalog (117,402 records) | `/opt/biklo-catalog-crawl` |
| Bike Insights | Bike details, geometry, brands | `/opt/bike-niche-corpus/crawls/bikeinsights.sqlite3` |
| RideInsights | Part catalog and geometry | `/opt/bike-niche-corpus/crawls/rideinsights.sqlite3` |
| SRAM | Part/product and service pages | `/opt/bike-niche-corpus/crawls/sram.sqlite3` |
| Geometry Geeks | Geometry directory and bike measurements | `/opt/bike-niche-corpus/crawls/geometrygeeks.sqlite3` |
| Open GitHub data | Brand/model dictionaries and legacy geometry | `/opt/bike-niche-corpus/sources` |
| Shimano, SRAM, Schwalbe | Manufacturer compatibility references | `/opt/bike-niche-corpus/official-docs` and `sources/schwalbe` |

The Bikes.Fan bike-page sitemap was compared with Biklo and found to contain exactly the same 117,409 bike URL paths; it is intentionally not recrawled.

## Workflow

1. `geometrygeeks_inventory.py` walks the site's public paginated bike directory using real Next links. Other sitemap URL inventories are stored under `inventory/`.
2. `collector.py <source>` is source-isolated, checkpointed and single-worker by default. It preserves compressed HTML and structured data in SQLite. Stop on 403/429/challenge; do not attempt to evade access restrictions.
3. `publish_source.py <source>` snapshots a terminal SQLite source, archives it with the URL inventory and manifest, writes to Cloudflare R2 and verifies SHA256/bytes by readback, writes a D1 `workflow_state` pointer and uploads a delivery copy to Telegram VPS Control / Data.
4. `telegram_parts.py` batches long archives into 3-MiB parts with per-part SHA256, persistent message-ID checkpoints and a reassembly manifest. `vps-control-data-batch.js` executes inside the existing secure MTProto wrapper **once per source release**, rather than fetching BWS secrets on every part.
5. `normalize_geometry.py` incrementally extracts numeric Stack, Reach and other measurements into `derived/geometry-index.sqlite3`, retaining source URL and size provenance. `checkpoint_geometry.py` and `checkpoint_source.py` create verified interim R2/D1 snapshots.
6. `finalize_geometry.py` can only publish the final geometry index after Bike Insights, RideInsights and Geometry Geeks have all published their individual complete source releases. The persistent `bike-niche-resume-guard.timer` resumes interrupted crawls and triggers this finalization once its prerequisites pass.

## Storage contract

- **R2**: existing `runner3-artifacts/core/bike-niche/...` prefixes, with separate keys per source, release ID, immutable archive and manifests.
- **D1**: `runner3-core.workflow_state`, only metadata, checkpoint pointers and publication status; the binary dataset never belongs in D1.
- **Telegram**: group **VPS Control**, topic **Data** (forum topic ID 1) for validated delivery files.
- **GitHub**: only versioned module source and documentation; no large archives, live credentials or per-user session data.
- **Checkpoint**: SentinelX source continuity; never restart an active job or mark published until all independent source delivery steps have passed.

The deployed scripts live under `/opt/bike-niche-corpus` (except the secure Telegram batch uploader under `/opt/telegram-mtproto`). These modules depend on preconfigured VPS credentials and an existing secret-injection wrapper; credentials are intentionally absent from the repo.
