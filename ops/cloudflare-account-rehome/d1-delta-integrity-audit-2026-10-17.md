# Cloudflare account rehome — D1 delta-integrity audit (2026-10-17)

**Status:** OFFLINE_PROOF_PASS / LIVE_TARGET_PARITY_BLOCKED / NO_DEPLOY / NO_SOURCE_DELETE

**Accounts:** source `ducduy2411` remains production authority; target `louisalviss3` remains unverified. This is a scoped *account-to-account* migration audit, **not** the already-completed D1 domain-isolation task.

## Evidence and new finding

Authenticated source D1 Account Usage Watch reported 9 physical databases on 2026-10-16; daily cumulative `rowsWritten` advanced 14,722 → 23,161 between 12:41:58Z and 17:40:38Z (+8,439). Of that, `runner3-content-intelligence` accounted for +8,000 (94.8%). These figures measure database operations **not identifiable changed rows, inserts, updates, or deletes**. Grounding: [source-only write receipt](./d1-source-write-delta-watch-2026-10-16.json).

Inspection of current GitHub `main` source, with no Cloudflare request, reveals `DELETE` operations relevant to the source database:

- `cloudflare/runner3-core/src/rss-reader-learning.js`: `replaceReaderPreference` deletes `liked/disliked` records from `user_content_events`; `replaceReaderFeatured` deletes matching `saved` events. The table has `id INTEGER PRIMARY KEY AUTOINCREMENT` and `event_at`, **no row-level UPDATE/tombstone record for deleted event IDs**.
- `cloudflare/runner3-core/src/content-personalization.js`: personal scoring logic deletes stale `content_scores` rows for obsolete model versions; its composite PK is `(item_id, score_type, model_version)`. A cursor by `scored_at` will not describe those deletions.
- `cloudflare/runner3-core/migrations/0014_interest_ontology_v6.sql` explicitly deletes `content_features` legacy rows. Replaying old migrations against destination is unsafe; historical migration files are not a durable live change stream.
- `cloudflare/runner3-core/content-intelligence-schema.sql` defines `content_items(item_id)` with `last_seen_at` (not an all-mutations `updated_at`), `content_features(item_id,feature_type,feature_key)` and `content_scores(item_id,score_type,model_version)` as primary keys.

**Consequences:** An `updated_at`/high-watermark-only replay is incomplete unless every source mutation reliably records a change/tombstone. A naive `COUNT(*)` equality gate or monotonically increasing event-id gate can also miss source-target divergence.

## Offline reproducible check

Executed an isolated Python `sqlite3(:memory:)` fixture through the connected `runner-vps1` SentinelX script runner. The source and destination both had exactly **2 event rows** but key sets `{2,3}` versus `{1,2}`. Four assertions PASS:

1. Equal row counts were correctly rejected as a parity proof.
2. The source-only key `3` and target-only key `1` were independently identified; shared row hash matched.
3. `user_content_events` lacks a generic `updated_at` change marker, so removed event `1` is invisible to a timestamp-only catch-up.
4. Two scores for one `item_id` but different model versions prove why the composite PK must be preserved.

**Result:** `OFFLINE_D1_KEYDIFF_FIXTURE_PASS: 4/4`; zero Cloudflare API calls, zero R2 requests, zero D1 writes, zero production changes. This is algorithmic evidence **only**, not live data parity.

## Required read-only and migration gates

1. Refresh **source and target** D1 inventory through an already authorized read-only Cloudflare path, independently proving account identities, 9-store names, current UUIDs and actual table schemas. Historical target Oct8 contains 8/9 matching names but no current parity. Previously blocked Wrangler direct command / browser-credential transfer must not be bypassed through shell, scripts or other executors.
2. Capture `sqlite_master`, `PRAGMA table_xinfo`, primary/unique keys, indexes/FKs and same-time row counts. Hash full canonical typed row payloads per **actual primary key**; report source-only, target-only and changed counts without publishing identifiers or sensitive row bodies.
3. Preserve existing target-only records for owner review; do not delete just because an old source snapshot omitted them. Verify `runner3-core` auth, mailbox, permalink and receipt state separately. Do not apply the legacy 26-file SQL migration chain to production; earlier isolated scratch execution failed one file and source schema differed.
4. For `runner3-content-intelligence`, conduct schema-scoped, idempotent initial transfer to a distinct staged destination, then bounded delta catch-up. Use a proven complete CDC stream (including deletes/tombstones), **or** a final full primary-key/content reconciliation while source writers are quiesced. Newer timestamps alone do not close the delete gap.
5. Before cutover, pause/drain all writers and scheduled/event-driven consumers of the source D1, certify no in-flight transactions, perform final keyed reconciliation including deletions, inspect conflicts manually by owner policy, and re-check counts and row-hashes against a stable source point. Resume on target only after Worker/binding/cron/R2 parity, smoke and rollback PASS. No duplicate cron.
6. Cloudflare D1 export blocks other requests while running; do not export hot Core/CI blindly. D1 Free tier limits as documented: 5M rows read/day, 100k written/day, enforced from 2026-09-01. A read-backfill plan must be bounded with budget preflight. Time Travel may help restore but is **not** a cross-account copy, a substitute for parity or a license to overwrite target.
7. Keep R2 `COST_HOLD` (Dropbox `/Task/active/CLOUDFLARE-R2-COST-001.md` rev16), pending native PutObject attribution and fresh provider billing; no R2 migration or Worker cutover until independently released.

## Current blocker and safe resume

- Live `louisalviss3` D1 audit route **NOT VERIFIED** with current connected tools. Historical target `gmail-otp-main` Super Admin browser proof does not establish present availability. No need to reflexively request new credentials.
- `scripts/cloudflare_target_readonly_inventory.py` and manual-only workflow `.github/workflows/cloudflare-target-d1-workers-readonly-inventory.yml` are staged but require their explicitly scoped target audit credential; do not substitute source or R2 tokens.
- Next milestone is a **fresh sanctioned read-only target D1 schema/PK receipt**, not another guessed import, migration dry-run interpreted as live parity, or a production cutover.

## References

- `ops/cloudflare-account-rehome/d1-source-target-parity-reconstruction-2026-10-16.md`
- `ops/cloudflare-account-rehome/d1-sql-chain-offline-audit-2026-10-16.md`
- `ops/checkpoints/cloudflare-account-migration-2026-10-08.md`
- https://developers.cloudflare.com/d1/best-practices/import-export-data/
- https://developers.cloudflare.com/d1/platform/pricing/
- https://developers.cloudflare.com/changelog/post/2026-09-01-d1-free-tier-limit-enforcement/
- https://developers.cloudflare.com/d1/reference/time-travel/
