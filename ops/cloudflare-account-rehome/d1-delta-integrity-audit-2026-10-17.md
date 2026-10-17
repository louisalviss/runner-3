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
7. Keep R2 `COST_HOLD` (Dropbox `/Task/active/CLOUDFLARE-R2-COST-001.md` rev18), pending native PutObject attribution and fresh provider billing; no R2 migration or Worker cutover until independently released.

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

## 2026-10-17 continuation — audited coverage gap (source 2/9; target names only)

**Read-only review of current GitHub main and canonical Dropbox R2 cost task rev18; no Cloudflare source/target D1 query and no production mutation.**

- The existing manually-dispatched source script `scripts/cloudflare_d1_encrypted_parity.py` hard-codes `ALLOW={"runner3-core","runner3-content-intelligence"}`. It only collects schema DDL digests and `COUNT(*)` for those **two** physical D1 databases, not all nine. Even if re-run successfully, it cannot establish 9/9 parity; row-body / primary-key comparisons are not implemented.
- `scripts/cloudflare_target_readonly_inventory.py` and `.github/workflows/cloudflare-target-d1-workers-readonly-inventory.yml` enumerate target database **names** and Worker metadata only. They do not fetch target per-table schema, row counts, stable primary keys or row content digests. An empty set of matching names proves no data equivalence.
- Read-only `gh secret list` on `louisalviss/runner-3` on 17 Oct still shows **no** `CLOUDFLARE_TARGET_AUDIT_TOKEN` name. The presence of source Cloudflare API and target R2 S3 secret names is not proof of target D1 Read privileges. Earlier authenticated Super Admin session evidence is retained, but current approved target D1 audit surface has not been demonstrated. Do not reroute a denied command or reuse unrelated credentials.
- Current reference matrix has **9 source D1 names, 9 historical target names, 8 common names** (different observation dates). `clm-copilot-calibration` exists in source and is staging/retention-review; old `louis-context-index` appears in historical target and has no deletion approval. Two database name mismatches cannot be auto-resolved from inventory names.
- October 8 source/target schema+row-count audit is confined to `runner3-core` (12 versus 0 tables) and `runner3-content-intelligence` (11 versus 8 tables). Keyed row-content parity for **all nine** remains unverified.
- Source `D1 Account Usage Watch` run 38987762461 at 2026-10-17T00:44:36Z finished SUCCESS; this is source-only activity, not a target transfer receipt.
- Canonical Dropbox `/Task/active/CLOUDFLARE-R2-COST-001.md` has advanced to rev18, remains `VERIFYING` and `COST_HOLD`; R2 operations must not resume from this D1 task.

**Next precise executable gate:** Use a sanctioned target-account read-only session for a fresh **complete** D1 database list. Extend source/target audit capture to all retained physical D1 databases, collecting schema and key-level digests with D1 read-budget preflight and no sensitive row exports. Compare same-window receipts, preserve target-only data, then stage bounded import and final writer-quiesced full keyed reconciliation including deletions. Keep Core auth/mailbox invariant, R2 hold and Worker cutover independent. A read-only list of database names alone does **not** release the migration gate.

## 2026-10-17 — Two complementary encrypted schema audits, no duplicate source flow

**Concurrent source audit was already staged in independent draft PR #430**: `https://github.com/louisalviss/runner-3/pull/430`. That branch contains source-only `scripts/cloudflare_d1_nine_schema_encrypted.py`, its eight offline mock tests and workflow `cloudflare-d1-source-nine-schema-readonly.yml`. Its source receipt is RSA/AES-encrypted and contains DDL hashes plus PK metadata for all nine source D1 databases, **not** row contents. No production dispatch or Cloudflare data query was performed.

**This PR #428 now complements PR #430 with target-only inspection**, not a duplicate source workflow:
- `scripts/cloudflare_d1_nine_schema_readonly.py`: CLI permits only `--role target`; it uses **only** `CLOUDFLARE_TARGET_AUDIT_TOKEN`. Target account ID is pinned. It inventories existing target D1 databases and obtains schema object DDL digests and declared PK columns through read-only `sqlite_master` and `PRAGMA table_xinfo` queries, including legacy target-only `louis-context-index` if present.
- Its JSON manifest is encrypted with the existing migration courier public key (RSA-OAEP/AES-256-GCM), **never exported as plaintext to GitHub artifacts**. Manual-only `.github/workflows/cloudflare-d1-nine-schema-readonly.yml` runs target only; no source credential, schedule, push trigger, R2 operation, import, export or write.
- Exact source blob readback + SentinelX offline fixtures: `OFFLINE_D1_NINE_SCHEMA_CONTRACT: PASS (9 checks, 0 external requests)`. Actual PyYAML workflow structure/secret assertions: `TARGET_D1_WORKFLOW_ENCRYPTED_AUDIT_YAML_PASS 7/7`. Running target command with explicitly empty target token exits 3 with `D1_SCHEMA_AUDIT_BLOCKED TOKEN_UNAVAILABLE`; zero Cloudflare requests.
- Historical target had nine physical D1 names. Cloudflare D1 Free maximum is 10 DB/account, so nine fresh D1 staging DBs cannot be assumed available in the target Free account. Avoid any in-place target overwrite or source hot export; use separately reviewed local/offline staging, verify source-target DDL/PK and reconcile payload keys with deletes at final writer quiesce.
- **NO LIVE D1 PARITY YET.** Newest secret-name audit still shows no `CLOUDFLARE_TARGET_AUDIT_TOKEN`. The already-granted historical Super Admin browser session is not currently exposed as a sanctioned callable target D1 query surface; do not bypass security-blocked Wrangler or credential handoff.
- Canonical R2 cost task `/Task/active/CLOUDFLARE-R2-COST-001.md` reached rev19 and remains `VERIFYING / COST_HOLD`. No R2 migration, no Worker deployment/cutover, no source deletion.

Neither PR should be merged as permission to cut over. Next accepted evidence: approved target D1 Read access and independently invoked audited workflow, decrypt source and target schema receipts locally, then build a separate bounded row-key/payload parity plan before any import.
