# D1 Core SQL migration-chain offline safety audit — 2026-10-16

**Evidence class:** OFFLINE SOURCE REVIEW ONLY. **Decision:** `DO_NOT_REPLAY_FULL_MIGRATION_CHAIN`.

Source account: `ducduy2411`; destination: `louisalviss3`. Production source unchanged. R2 `COST_HOLD` remains active; no Cloudflare data operations, deploy, deletion, cutover or credential manipulation took place.

## Evidence and scope

- Read current `louisalviss/runner-3` metadata and inspected SQL in the preexisting **October 8 VPS source checkout**, `/opt/cloudflare-migrate-runner3-20261008/cloudflare/runner3-core/migrations` (local checkout HEAD `264d097b3923fb326235fbd44e1dd7d31072562b`). **This is not a fresh validation of all SQL against current main**, nor a source-vs-target D1 parity check.
- 26 SQL migration files found. A conservative *static* scan found **12 files containing INSERT/UPDATE/DELETE/DROP TABLE** and 14 others without these operations. This is a statement-level screen, not proof that other files are side-effect-free.
- Risk-bearing files (12): `0005_rss_library_seed_20260825.sql`, `0006_rss_library_search_keys.sql`, `0007_rss_restricted_source_integrity.sql`, `0008_rss_replace_restricted_pilot.sql`, `0009_content_event_dedupe.sql`, `0009_rss_replace_huggingface_pilot.sql`, `0011_rss_reader_library_plus.sql`, `0011_vps_mailbox_opaque_ids.sql`, `0014_interest_ontology_v6.sql`, `0016_interest_family_profile.sql`, `0017_library_file_index_v1.sql`, `0018_drop_legacy_domain_tables.sql`.
- The last file contains **24 DROP TABLE statements**. The mailbox `0011_vps_mailbox_opaque_ids.sql` has an UPDATE that can mark queued/claimed historical IDs `failed`. Neither should be replayed blindly during account-to-account migration.

## Scratch-only sequential execution

Used Python `sqlite3.connect(':memory:')` (SQLite 3.46.1) on SQL texts in lexical file order. **No remote SQL or Cloudflare operation**:

- 25 scripts completed in this isolated scratch database; `0013_ebook_reader_state_v72.sql` **failed**: `no such table: ebook_reader_progress_v65`. It expects an earlier/source-domain state that this full SQL chain does not create. Do not interpret 25/26 as deploy success.
- Scratch result did **not** equal the 12 source Core application tables recorded in the authenticated Oct8 snapshot; it still included legacy `reddit_*` tables. The production source had gone through separate domain isolation, so merely applying all SQL has incorrect effects and ordering.
- Core source's Oct8 12 application tables: `artifact_library_auth`, `artifact_library_magic_links`, `artifact_library_pin_attempts`, `checkpoints`, `d1_migrations`, `delivery_permalinks`, `ebook_reader_trace_v113`, `events`, `r2_receipts`, `typed_kv`, `vps_mailbox_jobs`, `workflow_state`. Of those, the Oct8 SQL folder has explicit CREATE TABLE definitions for only **8**: `artifact_library_auth`, `artifact_library_magic_links`, `artifact_library_pin_attempts`, `checkpoints`, `delivery_permalinks`, `events`, `vps_mailbox_jobs`, `workflow_state`.
- **No CREATE TABLE found in that folder** for `d1_migrations` (migration bookkeeping; do not fabricate from source), `ebook_reader_trace_v113` (reader-specific flow), `r2_receipts`, or `typed_kv` (separate control-plane/common access lineage). Their creation and final production schema must be resolved through canonical owners and actual source `sqlite_master` snapshots, not guessed.
- `0018_drop_legacy_domain_tables.sql` drops `ebook_reader_trace_v113`, yet authenticated Oct8 production source snapshot still records that table (0 rows): another signal that file presence is **not** an authoritative migration-applied ledger.

## Safe preconditions for future work

1. Obtain a fresh permitted read-only **source and target** D1 inventory and `sqlite_master`/table PK/index/FK descriptors for each canonical database. Do not request re-provisioning credentials already known historically without checking existing authorized surfaces.
2. Record source and target row identity/content digests and last-write windows, not simply `COUNT(*)`. Source remains an active writer; plan a bounded final delta.
3. Build a **schema-only, non-destructive** target plan from actual source DDL. Explicitly exclude DROP/DELETE/UPDATE/backfills unless separately reviewed with data-specific evidence, backup, idempotency and rollback.
4. Treat `vps_mailbox_jobs`, `artifact_library_auth`, `delivery_permalinks`, `typed_kv`, and `r2_receipts` as high-consequence state. Preserve unique IDs, authorization material, replay semantics and existing target-only records.
5. Worker cutover must remain independent of schema preparation: verify source 38 Workers (18 protect, 5 cron, four incoming service bindings to `runner3-rss-fastlane`) against live target code/cron expression/bindings and avoid duplicate scheduled triggers.
6. Do not deploy `.github/workflows/runner3-core-public-hosted-reader-deploy.yml` to the target as a migration method; it deploys production from source config and runs remote D1 migrations. Keep source production until all D1/R2/Worker parity, tested rollback and explicit cutover approval.
7. R2 cost task canonical Dropbox `/Task/active/CLOUDFLARE-R2-COST-001.md` last observed **rev10**, `VERIFYING`; do not release `COST_HOLD`.

Cross-reference: `ops/cloudflare-account-rehome/d1-source-target-parity-reconstruction-2026-10-16.md`, `ops/checkpoints/cloudflare-account-migration-2026-10-08.md`.

**Outcome:** Static audit and scratch run executed, but **zero account-to-account D1 tables or Workers migrated in this pass**. This report is not approval to run remote migration SQL.
