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


## Resilience, canonical linkage and quality gates (October 2026)

- `r2_verified.py` uses the existing `runner3-artifacts` bucket. For archives larger than 30 MiB, it writes **R2-sharded-tar**, with individual SHA256/byte readback for each part and an immutable `*.r2-parts-manifest.json` entrypoint. The original archive SHA256 remains in the manifest. This avoids the Cloudflare API Gateway 502 observed for a 213-MB single PUT. `CURRENT.json` and the D1 pointer identify the artifact format and number of parts; never assume every release key is a directly downloadable single `.tar.zst`.
- `entity_crosswalk.py` builds `derived/bike-crosswalk.sqlite3`. Links are only candidates where a unique normalized canonical bike slug and exact year match a Biklo URL, allowing common manufacturer aliases such as `brand bicycles`. Each link carries source URL, Biklo URL, year, geometry-presence flag and match rule. This is **not** proof of identical build/spec. Original source records remain separate.
- `qa_sources.py` produces `derived/source-quality.sqlite3` to withhold placeholder-title, non-detail or geometry-missing pages from **geometry pSEO** while preserving all raw records.
- The final geometry release includes numeric geometry, source quality flags, crosswalk and their summaries. `finalize_geometry.py` requires all three source release receipts before building, then performs R2 readback, D1 published pointer and Telegram / Data segmented delivery.
- A persistent `/etc/systemd/system/bike-niche-finalize-geometry.service`, started only by the source-aware resume guard, replaces the volatile transient finalizer. It remains **inactive** while Geometry Geeks is unfinished.
- Geometry Geeks partial snapshot at `sources/geometrygeeks/checkpoints/20261008T174448Z/`: 23,212 source records, seven separately verified R2 chunks, manifest and D1 `crawling` readback. It is a checkpoint, not the final release.


## Numeric geometry safety gate

`normalize_geometry.py` enforces conservative, metric-specific physical limits across 16 measurements (stack, reach, head/seat angles, tube dimensions, wheelbase, bottom bracket, fork, trail and standover). Nonphysical values (e.g. negative 7,730-mm bottom bracket height) are excluded from searchable numeric rows but retained in the original site snapshots and an audit table `rejected_measurements`. A live October 9 audit retired 5,714 pre-existing impossible rows; `PRAGMA quick_check` and twelve synthetic metric boundary tests passed. Avoid treating all manufacturer-reported field values as verified.

`checkpoint_geometry.py` now writes a separate immutable checkpoint workspace, never into the final publication directory, to avoid overwriting a concurrent final release. It stores the SQLite numeric index plus rejected-measurement audit in R2 (verified multi-part objects when above 30 MiB) and writes a guarded D1 checkpoint that cannot replace a `published` pointer.


## Restore-from-R2 acceptance

`restore_r2_shards.py` reads the **remote** immutable R2 manifest, downloads ordered parts, checks each part's SHA256/byte count, concatenates to a temporary file, checks the complete archive SHA256/byte count, and only then atomically promotes the reconstructed `.tar.zst`. This supports both archive layouts already deployed:

- `r2-sharded-tar`: normalized geometry and source releases using `*.r2-parts-manifest.json`.
- `inprogress-checkpoint`: the earlier Geometry Geeks partial backup using `parts-manifest.json` and `readback_verified` flags.

Recovery needs the exact R2 manifest key and an output directory. It does not change active D1 pointers, publish releases, or touch the source crawler. Do not regard R2 upload-only success as restore proof.
