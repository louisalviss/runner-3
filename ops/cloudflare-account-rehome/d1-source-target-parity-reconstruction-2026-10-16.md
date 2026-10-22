# D1 source → target historic parity reconstruction — 2026-10-16

**STATUS: HISTORICAL_OFFLINE_EVIDENCE / NOT_LIVE_PARITY / NO_MIGRATION_PERFORMED**

## Identity and provenance

Source Cloudflare: `ducduy2411`, `7415a87f6bce7884e73ad7cfed5782df`. Destination: `louisalviss3`, `748a80810f77f447ee476543ef0e5014`.

Evidence obtained **read-only and offline on VPS** from preexisting October 8 2026 audit files:
- Source RSA-OAEP/AES-256-GCM **encrypted** schema + COUNT snapshot `/var/lib/cloudflare-migration/2026-10-08/ephemeral-courier/run-37749106300/d1-envelope.json`, audited original `cloudflare_d1_encrypted_parity.py`. Source snapshot timestamp **2026-10-08T08:19:57.619573Z**.
- Target authenticated historical summary `/var/lib/cloudflare-migration/2026-10-08/ephemeral-courier/d1-target-parity.json` (mode 0600). Only table names, row COUNT values, and SHA256 of sqlite_master DDL were compared. No key, token or row values were exported to this repository. Private RSA material remained on VPS.
- Oct8 target name/UUID map `/var/lib/cloudflare-migration/2026-10-08/target-d1-map.json`; now historic, not freshly verified.
- Most recent source-only [D1 Account Usage Watch #38776291301](https://github.com/louisalviss/runner-3/actions/runs/38776291301) logged 2026-10-15T17:18:57Z, `inventoryCount=9`, `rowsWritten=23173` at observed daily point, `projected=32118/day`, below 100,000/day free limit; shows source is still writing, NOT source-target table parity.

## Schema and COUNT comparison for exactly the two databases in the Oct8 encrypted source audit

| DB | Source tables | Target tables | Identical DDL SHA256 for common tables? | Result |
|---|---:|---:|---|---|
| `runner3-core` | **12** | **0** | No common tables | **BLOCKED / target empty** |
| `runner3-content-intelligence` | **11** | **8** | **8/8 PASS** | **PARTIAL; 3 tables absent, several row counts differ** |

**Runner3 Core** source table COUNTs vs target missing (all 12): `artifact_library_auth` (1), `artifact_library_magic_links` (4), `artifact_library_pin_attempts` (0), `checkpoints` (643), `d1_migrations` (28), `delivery_permalinks` (1), `ebook_reader_trace_v113` (0), `events` (93), `r2_receipts` (4), `typed_kv` (5), `vps_mailbox_jobs` (45), `workflow_state` (74).

These tables include live control-plane, authentication, mailbox, permalink and receipt state. Do **NOT** cut over, bulk-reseed or rebuild blindly; unique identifiers and idempotency must remain intact, and source writes require a final delta.

**Content Intelligence:**

| Table | Source rows | Target rows | Historic row count difference (source minus target) | DDL SHA256 |
|---|---:|---:|---:|---|
| `content_items` | 2,890 | 2,853 | +37 | MATCH |
| `content_features` | 14,531 | 14,328 | +203 | MATCH |
| `content_scores` | 2,076 | 2,061 | +15 | MATCH |
| `user_content_events` | 5,055 | 5,017 | +38 | MATCH |
| `interest_family_profile` | 13 | 13 | 0 | MATCH |
| `interest_profile` | 26 | 26 | 0 | MATCH |
| `personal_score_stage` | 0 | 0 | 0 | MATCH |
| `recommendation_runs` | 35 | 35 | 0 | MATCH |
| `checkpoints` | 0 | ABSENT | N/A | ABSENT |
| `link_interest_events` | 2 | ABSENT | N/A | ABSENT |
| `workflow_state` | 2 | ABSENT | N/A | ABSENT |

**Critical interpretation**: a positive count difference does NOT establish the identity of missing records or a row-subset relationship. Equal DDL hashes and row counts do NOT establish payload parity. Requires key-level reconciliation using explicit immutable PKs, checksums, and last-write delta before any apply. If target-only edits occurred after Oct8, preserve them.

## Nine physical D1 names in source/target historical inventories

- Historical target Oct8 had: `clm-copilot-v1`, `louis-context-index`, `louis-task-context`, `personal-library`, `runner3-content-intelligence`, `runner3-core`, `runner3-opportunity-radar`, `runner3-rss`, `volamidle-rogue-data`.
- Current **source-side inventory** in Oct15 Usage Watch had: `clm-copilot-calibration`, `clm-copilot-v1`, `louis-task-context`, `personal-library`, `runner3-content-intelligence`, `runner3-core`, `runner3-opportunity-radar`, `runner3-rss`, `volamidle-rogue-data`.
- 8 names in common, **`clm-copilot-calibration` appears source only**, **`louis-context-index` appears target only**; the source internally retired/merged `louis-context-index` into `louis-task-context`. **These are mixed-date snapshots, not current proof of target absence or source deletion eligibility.**
- Remaining seven source data stores beyond the two audited October 8 have no accepted source↔target schema/row/record-content parity results in this receipt. Even if names exist, treat their data as NOT VERIFIED.

## Execution priority with strict safety gates

1. **DO NOT REPEAT** internal source-account `D1 domain isolation` (already DONE); it is unrelated to account-to-account D1 migration.
2. Keep old `runner3-core` as production authority. First get a fresh **authorized read-only target metadata and D1 schema+COUNT snapshot** and pair with source same-time snapshot. Historical target Super Admin browser session was proven usable Oct8; its current authorized usability is unverified. GitHub Secret absence is not absence of the user's Cloudflare permissions. The previously blocked direct Wrangler exec and credential-transfer routes **must not be bypassed**.
3. Once new snapshots confirm, reconcile `runner3-core` all 12 tables; use **logical key-level and last-write catch-up**, auth/mailbox idempotence; no blind truncate/replace, copy of sensitive secrets into logs, or stale restore.
4. Handle `runner3-content-intelligence`: compare keys for four count-divergent tables and preserve 3 absent source tables if still required by live code. Validate key-level content hashes, not just COUNT.
5. Classify `clm-copilot-calibration` vs stale `louis-context-index` before choosing retain/archive. Do not auto-delete/rename database or write to D1 from a read-only audit.
6. Audit all remaining canonical D1s then selected required Workers+bindings/cron/secrets/rollback. Old source **38 Workers, five cron, no delete eligible**; target historic six Worker names not sufficient for parity. R2 **COST_HOLD** remains even if D1 read-only parity eventually succeeds. No source deletes/production cutover without full R2+D1+Worker parity and explicit user authorization.

## Operational restrictions
- R2 `CLOUDFLARE-R2-COST-001` canonical Dropbox rev7: residual artifacts PUT source unattributed; GitHub seven R2 migration workflows offline HOLD-gated. No R2 LIST/PUT/GET made for this reconstruction.
- Offline RSA use was solely to decode the previously generated source schema/count receipt on the same VPS; no Cloudflare bearer token, browser profile, cookie, or RSA private bytes copied or displayed.
- D1 table counts represent **October 8 2026 only**. Treat Oct15 Watch 9 DB and write-rate as latest source presence evidence, not fresh content parity.


## Source Worker cutover dependency cross-check (historical target)

A separate static cross-check of authenticated source Worker inventory Oct14 versus Oct8 historical **six target Worker names** finds **18 source scripts classified PROTECT**, including service-bound `runner3-rss-fastlane`; 6 were present by name in the historical target snapshot. **12 retained/PROTECT workers had no same-named match in that old target snapshot**:

`clm-conversation-copilot-api`, `ema-forward-monitor`, `media-library`, `rss-proxy`, `runner3-audio-chatgpt-bridge`, `runner3-audio-library`, `runner3-autocontent-ai`, `runner3-core`, `runner3-rss-fastlane`, `vbth-free-editorial-ai`, `wordpress-edge-proxy`, `wordpress-edge-proxy-v2`.

This is **not current proof of 12 missing scripts**; target Oct8 list is stale and even matching names can have different code, cron, secrets and bindings. This defines the read-only parity backlog, NOT a deploy/delete list.

Five source scheduled Workers: `rss-proxy`, `runner3-audio-library`, `runner3-core`, `runner3-core-reader-v33-preview`, `wave-rider-scanner`. `runner3-core-reader-v33-preview` has cron despite being classified REVIEW; no Worker is delete-eligible. `runner3-rss-fastlane` has **four inbound service bindings** and must not be omitted even with zero direct requests.

Current GitHub `cloudflare/runner3-core/wrangler.jsonc` uses SOURCE account D1 UUIDs and Worker origin `https://runner3-core.ducduy2411.workers.dev`, cron `17 * * * *`, D1 bindings `DB`, `OPPORTUNITY_DB`, `LIBRARY_DB`, `BUSINESS_OPPORTUNITY_DB`, `TASK_CONTEXT_DB`, `CONTEXT_INDEX_DB`, `CONTENT_DB`, `RSS_DB`; R2 `ARTIFACTS=runner3-artifacts` and `AUDIO_MEDIA=runner3-wp-media`; Worker service `RSS_FASTLANE=runner3-rss-fastlane`. Binding the new target Worker without fresh target D1/R2, service and endpoint parity would point active production to incomplete data and could restart previously held R2 polling; **forbid blind deploy**.

**Safe sequencing remains**: (a) fresh target name/metadata read-only audit by an explicitly permitted existing connected path, (b) live source+target D1 schema/primary-key/last-delta parity, (c) target Workers code/bindings/secrets references/cron staging with no production cron duplicates, (d) end-to-end rollback-ready smoke then user-approved reversible cutover, (e) old source cleanup last. R2 migration still blocked by billing policy.


## 2026-10-16 — Offline validation update

- Fixed D1 inventory completeness validation in `scripts/cloudflare_target_readonly_inventory.py` (commit `36e32f75`). It now verifies page 1, result count and total_count, and fails closed if a first page might be incomplete; it does not silently accept missing pagination metadata.
- Expanded synthetic tests in `scripts/tests/test_cloudflare_target_readonly_inventory.py` (commit `f055f20b`) to cover truncated first pages and missing pagination metadata.
- Executed the synthetic tests on VPS with no Cloudflare calls: PASS for absent-token behavior, redacted bindings, incomplete/missing D1 pagination, and invalid bindings. Test process exited 0.
- Executed the offline R2 migration guard tests: PASS. With current `COST_HOLD`, the guard exits 3 as designed before any Cloudflare request.
- These are local test results, not proof of live target D1/Workers parity. No migration, production cutover, R2 operation, or source deletion occurred.


## 2026-10-16 — Archived target D1 binding staging matrix

- Inspected current `cloudflare/runner3-core/wrangler.jsonc`, Git blob SHA `c8b1b84e9d503954e1933b4aacc4e34fa887ff82`. Eight source D1 **binding slots** resolve to **six unique D1 databases** (two intentional duplicate aliases).
- Matched every required database name to the original authenticated Oct8 `louisalviss3` target DB ID map stored on VPS; **8/8 slots and 6/6 distinct names have a historical target ID**, but no current schema, row, or content parity has been verified.
- Created machine-readable **NO_DEPLOY** staging matrix `ops/cloudflare-account-rehome/runner3-core-target-d1-binding-draft-2026-10-16.json` commit `03d9809077f7eaea9899808452dc99bacb0aa4ee`. This is evidence and a future staging reference, **not** an active Wrangler config, D1 import instruction, Worker deployment or authorization to enable cron.
- Offline GitHub readback validation **PASS**: source config Git SHA pinned; all 8 slot names/source IDs aligned with current main; six distinct target IDs; intentional aliases retained: `OPPORTUNITY_DB` = `BUSINESS_OPPORTUNITY_DB` → `runner3-opportunity-radar`, and `TASK_CONTEXT_DB` = `CONTEXT_INDEX_DB` → `louis-task-context`. Do not incorrectly bind `CONTEXT_INDEX_DB` to old target-only `louis-context-index`.
- The manifest explicitly marks live target parity false, target D1 migration false, production cutover false, target cron enable false, every R2 bucket unverified and R2 `COST_HOLD` true. `RSS_FASTLANE` service target remains unverified; source `runner3-core` cron is `17 * * * *` but must not duplicate on target.
- Other 3 physical D1 databases not used directly by these six Core bindings (for example `clm-copilot-v1`, `volamidle-rogue-data`, `clm-copilot-calibration`) remain separate domain migrations, **not** omitted from whole-account plan. Source account has 9 physical D1 in latest source audit, historic target also had 9, but the names differ. Do not confuse a six-DB Core dependency map with full D1 migration progress.
- Confirmed source Core production deploy workflow `.github/workflows/runner3-core-public-hosted-reader-deploy.yml` can deploy and migrate **the source** account; staging manifest is in `ops/`, not a trigger for the production Worker deploy. No new GitHub dispatch, Cloudflare API call, R2 operation, D1 SQL mutation, cron adjustment, source removal or cutover.


## 2026-10-16 — Full 9-source / historical 9-target D1 name reconciliation

- Checked newest available source-only D1 Account Usage Watch [run #38822449766](https://github.com/louisalviss/runner-3/actions/runs/38822449766), completed 2026-10-15T23:15Z: **nine physical D1**, daily `rowsWritten=25,225` and `projected=26,034/day` as observed at that point. Source `clm-copilot-calibration` remains in inventory, `rowsWritten=0` in the usage window (NOT proof empty). This supersedes older source watch counts; not target parity.
- Reconciled those nine source names against the **Oct8 historical** target nine-name/UUID map (read-only VPS file). **Eight same-named stores**, **one source-only snapshot name** `clm-copilot-calibration`, and **one target-only snapshot name** `louis-context-index`. This is a mixed-date name comparison, **not** proof of current target absence, target data completeness, or free space.
- For calibration, separately reopened authenticated 2026-10-14 source Worker audit [artifact 11899043830](https://github.com/louisalviss/runner-3/actions/runs/38575674555): the Worker `clm-conversation-copilot-calibration` exists, classified REVIEW/HOLD_NOT_DELETE, with D1 binding **`DB`** and configuration field **`CLM_STAGE_DB_UUID`**; no cron. **The actual referenced D1 UUID was deliberately redacted in that audit**, so link to `clm-copilot-calibration` is a *plausible owner hypothesis only*. Do not drop, omit or copy/repoint this database until actual binding UUID, schema, row count, consumers and backup are verified.
- For legacy `louis-context-index`, the [Oct8 source-account completed review/merge checkpoint](https://github.com/louisalviss/runner-3/blob/main/ops/checkpoints/d1-review-merge-cleanup-2026-10-08-0515-VN.md) explicitly records **12 context-index checkpoints merged into `louis-task-context`**, both source production aliases `TASK_CONTEXT_DB`/`CONTEXT_INDEX_DB` pointing at `louis-task-context`, and source legacy DB retired after backup/readback. The **target's** old `louis-context-index` remains **UNVERIFIED CONTENT / NO_DELETE**; do not assume it is empty, equivalent or automatically removable.
- Created machine-readable evidence-only matrix `ops/cloudflare-account-rehome/d1-nine-store-source-target-matrix-2026-10-16.json`, commit `1d658408370b9e14b05eeea68be4eb9397e39b2b`. Re-fetched GitHub matrix, 8-to-6 Core binding draft and R2 HOLD policy; offline invariant check **PASS**: nine source names, nine historical target names, eight common, two distinct exceptions, all Core aliases consistent, no current target parity, no R2 allowance and no D1 source/target writes. It is **NO_DEPLOY** evidence, not a deployment plan.
- Canonical Dropbox `/Task/active/CLOUDFLARE-R2-COST-001.md` now **rev11**, `VERIFYING`. A YouTube mirror duplicate PUT mechanism had a 6/6 offline SHA256-skip simulation PASS but fix NOT deployed; *other* residual PUT source still unresolved, hence global `COST_HOLD` continues. No R2 operations performed for this D1 reconciliation.

**Mandatory next verification:** With existing legitimately authorized Cloudflare account access, obtain current target inventory/Worker calibration `DB` binding UUID, then source+target D1 schema/PK/row digests and write-delta plan. Do not rerun source-domain isolation; do not deploy duplicated cron or cut over source.


## 2026-10-16 — Calibration D1 owner confirmed from original staging repository

- Found the original linked project code on VPS (not in `runner-3`): `/opt/clm-clef-calibration-20261009/worker/wrangler.calibration.toml` and `/opt/clm-clef-calibration-qa/worker/wrangler.calibration.toml`. Both explicitly bind script `clm-conversation-copilot-calibration` → D1 binding `DB` → database **`clm-copilot-calibration`**, UUID `7a7498ce-ece3-4fdd-9588-49e41834b942`, account `ducduy2411` `7415a87f6bce7884e73ad7cfed5782df`. No trigger cron configured. Configuration fields selected only; no tokens, secrets or session data read.
- Verified **original remote staging branch code** `louisalviss/android-secure-input-bridge` `clm-calibration-isolated-staging-20261009`, `worker/wrangler.calibration.toml` Git blob `3c5e4ed346e1f92a318bc760c1d69150c784d0da` agrees with both local source configs. Project staging checkpoint `ops/checkpoints/clm-calibration-staging-2026-10-09.md` from VPS reports D1 `clm_stage_identity` DB identity check, isolated `clm_samples` schema initialized, staging GET health PASS and **no production records copied**. Production D1 is a separate `clm-copilot-v1`; its migration remains an independent mandatory lane.
- Read-only GitHub [PR #13](https://github.com/louisalviss/android-secure-input-bridge/pull/13) verified `OPEN`, `DRAFT`, `mergedAt=null` when checked; staging provider secrets were never confirmed installed due a security block. Neither paid inference nor full 30-case acceptance proven; staging project is **NOT production**, but its DB and Worker are not deletable without explicit retention decision and restoreability check. Do not use secret-install workarounds or attempt unauthorized PR merge/deploy.
- Revised matrix `ops/cloudflare-account-rehome/d1-nine-store-source-target-matrix-2026-10-16.json` commit `6e6569b985c461716a5f0ce788d8cb70f7a8f502`: calibration Worker→D1 owner upgraded from HYPOTHESIS to **CONFIG_VERIFIED** with original repo branch evidence. **Current live Cloudflare binding and current D1 schema/content still unverified**, target lacks confirmed current calibration D1, no migration/deletion/release approved. Retain `clm-copilot-calibration` as isolated staging asset pending explicit keep/archive/migrate determination; do not merge into `clm-copilot-v1`.
- R2 cost task rev12 remains `VERIFYING` with `COST_HOLD`; separate task identified old `runner3-core-reader-v33-preview` cron deployment/config drift but explicitly found no link to residual R2 PUT. No R2 operation, D1 remote query/write, Worker deployment or production cutover in this source review.


## 2026-10-23 — Live cross-account D1 schema audit checkpoint

**New authoritative source:** [manual cross-account audit run #39826582807](https://github.com/louisalviss/runner-3/actions/runs/39826582807), run on merged `main` commit `3a37b8e4796189467624dca6607c62fcff3c479e`. Offline-preflight, source-readonly and target-readonly jobs succeeded. Compare job intentionally exited code 2 (`SCHEMA_GAPS_FOUND`), not a connectivity or permission failure. Nine source and nine target physical D1 stores were inspected through read-only schema metadata only; no table payload scans, mutations or R2.

- **Six schema-matching databases:** `clm-copilot-v1`, `louis-task-context`, `personal-library`, `runner3-opportunity-radar`, `runner3-rss`, `volamidle-rogue-data`. This is schema matching only, not any form of row/content/delete parity.
- **runner3-core:** 21 source-only objects = 12 application tables and nine indexes; zero target-only/differing same-name objects; one shared object. All 21 identities were matched offline against repository SQL/Worker source and existing checkpoint documents. The missing source tables are `artifact_library_auth`, `artifact_library_magic_links`, `artifact_library_pin_attempts`, `checkpoints`, `d1_migrations`, `delivery_permalinks`, `ebook_reader_trace_v113`, `events`, `r2_receipts`, `typed_kv`, `vps_mailbox_jobs`, `workflow_state`. `d1_migrations`, `r2_receipts` and `typed_kv` do not have canonical CREATE definitions in the old 26-file Core SQL migration chain; do not guess their DDL or replay that chain.
- **runner3-content-intelligence:** 18 source-only objects = three identified tables (`checkpoints`, `link_interest_events`, `workflow_state`), 12 identified indexes, one trigger and two unresolved opaque identifiers. The identified trigger is `trg_user_content_events_render_dedupe`. Nine schema objects are shared; zero differing same-name and target-only objects. Two remaining IDs are not available by name in public repository/checkpoint vocabulary.
- **Separate D1 name reconciliation:** source-only `clm-copilot-calibration`, target-only legacy `louis-context-index`. Protect both; a nine-to-nine physical DB count does not prove a matching inventory.

**Additional authorized live source receipt:** [manual source nine-schema encrypted audit #39848842550](https://github.com/louisalviss/runner-3/actions/runs/39848842550) PASS on `main` `9dbe263535604780b0eb29bb50c34d334e836992`. Artifact `cloudflare-d1-source-nine-schema-encrypted`, ID `12456272546`, SHA-256 `0c78c116cd5bb4b4b1ef2ced9ff3e4235a4818fac32773970bc1a4460aa8ec16` (1-day retention to 2026-10-23T20:26:53Z). It is RSA/AES encrypted. Tool safety blocked local courier decryption; no plaintext object identities were obtained from it and no attempt was made to bypass that restriction.

**Unresolved Content Intelligence object IDs**, copied byte-exactly from run #39826582807:

```text
051949606d6f5fada917fdf190f98379802546af2829a17845076323e3d577a8
7217ecdaa220de7e8cd00527f462853b9269c228eb4e49a35b450eda1ebefd02
```

**Release gates (unchanged):** 37/39 object identities identified, not 39/39. Do not silently treat unidentified IDs as indexes or new tables. Before target schema creation require separately approved secret-safe inspection of source applied `sqlite_master` (DDL/PK/FK/unique constraints/indexes/triggers), plus verification of source and target object owners. Then build non-destructive stage only; never blindly run historic SQL scripts with `DROP`, `DELETE`, `UPDATE`, auth/mailbox backfills, or source export that may block writers. Validate source and target row-key/payload equality, target-only records, and deletions/tombstones under bounded read constraints; writer quiescence and rollback are required for final parity. Preserve all source and target database data. No Worker/binding/cron cutover or duplicate timers. R2 retains `COST_HOLD rev28`. `row_parity=false`, `deletion_parity=false`, `cutover_ready=false`.

**Important history note:** The row COUNTS earlier in this document are dated 2026-10-08; they are not live 2026-10-23 counts. This checkpoint upgrades live schema evidence only, not payload parity.
