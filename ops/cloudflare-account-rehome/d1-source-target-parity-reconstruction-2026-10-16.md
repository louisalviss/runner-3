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
