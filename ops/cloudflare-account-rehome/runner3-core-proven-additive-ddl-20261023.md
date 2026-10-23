# Cloudflare D1 Core — exact source-fingerprint-matched additive staging bundle (2026-10-23)

**Status: OFFLINE_SQL_READY_FOR_REVIEW · NOT RUN ON D1 · SOURCE PRODUCTION PRESERVED.**

## Authenticated basis

- Actual source account read-only cross-schema run: [#39826582807](https://github.com/louisalviss/runner-3/actions/runs/39826582807), SOURCE and TARGET metadata jobs PASS, final comparison `SCHEMA_GAPS_FOUND`. Source opaque digest artifact ID `12447225966`, archived SHA-256 `df5a8e29f3c99ffcd72679c5aaa0db43baa7173982c642b45c5ecc0f0975b7f8`.
- Source Core has **21 source-only schema objects** (12 tables + 9 indexes) absent from the target schema snapshot.
- A second independent offline in-memory SQLite compilation of six exact Core migration files reproduced **16 out of those 21** `(type,name)` object IDs **AND** exact source metadata SHA-256, including `ddl_sha256`, `PRAGMA table_xinfo` column fingerprint and primary-key metadata for every table. These 16 object IDs are absent from the authenticated target fingerprint map.
- This is the first byte-exact corroboration of **8 Core table CREATE statements + 8 associated CREATE INDEX statements** to actual source metadata. It does not require the blocked courier private key or use live D1 row data.

## Candidate for later staging (not an executable deployment workflow)

`staging/runner3-core-additive-proven-16.sql` contains **only the 16 vetted CREATE IF NOT EXISTS statements** in table-before-index dependency order. It is not connected to `wrangler` and is never automatically executed. Exact original SQL extracted from:

- `0001_init.sql`: `events` and its two indexes
- `0002_state_checkpoints.sql`: `workflow_state`, `checkpoints`, checkpoint index
- `0010_artifact_library_magic_links.sql`: token table and expiry index
- `0010_vps_mailbox_jobs.sql`: mailbox jobs table and claim index
- `0011_artifact_library_pin_auth.sql`: PIN auth table, attempts table and blocked-until index
- `0012_delivery_permalinks.sql`: permalink table and indexes

Generator `scripts/cloudflare_d1_core_additive_schema.py` must verify all 16 source object fingerprint pairs and scratch SQLite schema before accepting any changed SQL. PR-only offline CI compiles and checks the committed candidate and exercises tamper/fail-closed tests.

**Do not replay the full 26-file migration chain:** it includes `DROP TABLE`, `DELETE`, `UPDATE` and data cleanup scripts; historical scratch migration execution does not recreate current source schema. This candidate intentionally contains none of those statements.

## Still missing in source-verified Core bundle

Four Core tables still lack source-verified **applied** CREATE DDL in the historical migration tree: `typed_kv`, `r2_receipts`, `d1_migrations`, `ebook_reader_trace_v113`, plus one other source-only index. These **5 objects remain out of scope**; do not fabricate their definitions or mark full Core parity.

**Content Intelligence:** authenticated source has 18 source-only objects. Separate offline replay of `content-intelligence-schema.sql` plus selectively indexed/trigger-only migrations corroborated **11 exact source-only** object fingerprints (7 more same-name source/target objects matched). Do **not** replay the entire CI SQL file: it contains `idx_content_items_last_seen_at`, an index that was **not present in the live source fingerprint set**.

## Actual target execution gates

1. Fresh read-only target `sqlite_master` preflight immediately before any apply; compare exact expected object absence, preserve any target-only objects and same-name changes. The Oct 22 snapshot is historical.
2. Use a separately authorized D1 **write** identity and reviewed bounded transaction. These audit tools deliberately have read-only credentials, and no writes are approved here.
3. Apply additive DDL only after source/target PK/FK/unique/index dependency validation; **IF NOT EXISTS alone does not verify schema equality**. Treat Core auth, mailbox and permalink tables as high consequence.
4. Migrate the entire data payload in bounded batches with key/value and deletion reconciliation. The DDL bundle does not copy **one row** and does not establish application readiness.
5. Maintain source writer authority until row parity, Worker bindings/service/cron/rollback and R2 cost gates are all independently released. Do not create a duplicate target cron or route.
6. R2 `COST_HOLD rev28` remains active; **zero** R2 LIST/GET/PUT operations in this work.

**Explicit flags:** `source_d1_writes=0`, `target_d1_writes=0`, `r2_requests=0`, `worker_deploys=0`, `row_parity_verified=false`, `cutover_ready=false`.

This artifact is concrete **DDL candidate readiness**, not evidence of any schema being applied to target D1.
