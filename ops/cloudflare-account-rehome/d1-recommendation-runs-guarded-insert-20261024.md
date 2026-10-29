# D1 recommendation_runs — one-person, two-step guarded migration (2026-10-24)

## Live two interest profile tables keyed-parity & column attribution — 2026-10-29 (NEW, HOLD)

[Two-profile first bounded live HMAC comparison #40868655035](https://github.com/louisalviss/runner-3/actions/runs/40868655035) and follow-up [column-level aggregate #40869143828](https://github.com/louisalviss/runner-3/actions/runs/40869143828), implemented in the **existing** read-only row-parity workflow through [PR #489](https://github.com/louisalviss/runner-3/pull/489) and [PR #490](https://github.com/louisalviss/runner-3/pull/490), all PASS operationally. Both runs used independently scoped source and target read credentials; validated exact source/target column metadata and declared PKs, read each table twice with a strict 100-row cap, and compared one-time in-memory HMACs for identity, complete typed payloads and non-PK column values. Sensitive row content, PKs, per-row HMACs, session secrets and profile names/values were never exported. D1 writes, R2 and Worker deploys = 0.

**Detailed sanitized evidence (data equality did NOT pass):**

| D1 table | Source | Target | Identical key+payload | Source-only PK | Target-only PK | Shared-PK payload mismatch |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `runner3-content-intelligence.interest_family_profile` | 13 | 13 | 1 | 0 | 0 | 12 |
| `runner3-content-intelligence.interest_profile` | 28 | 26 | 4 | 3 | 1 | 21 |

**Column-level counts among 13 shared family keys**: `weight` 12, `updated_at` 12, `evidence_count` 1, `positive_count` 1, `confidence` 1, `negative_count` 0. The counts are per-column: affected keys may overlap, and do not reveal values or change direction.

**Column-level counts among 25 shared interest keys**: `weight` 21, `updated_at` 21; `evidence_count`, `positive_count`, `negative_count` and `confidence` **0**. The remaining four shared keys have identical payloads. There are **three source-only and one target-only** profile keys, so a blind source overwrite could discard target-only state. The source/target changes may reflect derived score and timestamp drift, but the root cause or authoritative latest state is **NOT verified**. Timestamp columns are not reliable substitute for sequence/deletion lineage and do not justify merging.

**Action gate:** Do not auto-copy or overwrite profile tables. Determine authoritative owner and the recomputation model for `weight` and `updated_at`, compare source/target upstream `content_items`, `user_content_events`, `content_features`, `content_scores` and derived-profile lineage with bounded PK snapshots and a tombstone policy. An explicit resolution policy is needed for one target-only interest key and all shared-PK payload differences before any writer quiescence/cutover. The extant [recommendation_runs 47/35 read-only dry-run #40867548676](https://github.com/louisalviss/runner-3/actions/runs/40867548676) remains only one separate additive-table result (12 source-only, no conflicts).

**Migration status:** D1 row/content parity **HOLD**; source production remains authoritative; current snapshots are not atomic across accounts, not proof of absence of external writers. `CLOUDFLARE_TARGET_PREAPPLY_BOOKMARK` remains absent at last verified metadata check, and real tested rollback remains unavailable. No production D1 writes/restores, no Worker changes, no R2 migration, no cutover.


## Refreshed 2026-10-29 recommendation_runs source/target bounded dry-run (latest; NOT authorized to write)

[Workflow #40867548676](https://github.com/louisalviss/runner-3/actions/runs/40867548676) completed PASS on the existing `cloudflare-d1-recommendation-runs-additive-dryrun.yml` read-only workflow. Re-read and compared small `runner3-content-intelligence.recommendation_runs` on both Cloudflare accounts twice, then simulated additive INSERT and row-safe reverse entirely in ephemeral local SQLite. Observed **47 source rows, 35 target rows, 35 existing matching rows, 12 missing target rows, 0 payload conflicts, 0 unexplained target-only rows**. Source and target each stable within the two reads; schema metadata equal. The local 12-row additive insertion and subsequent 12-row deletion simulation both PASS; scratch baseline restored exactly to the original 35 rows. This is one table only, not atomic cross-account snapshot or full-account row parity.

As of 2026-10-29, the GitHub guarded production D1 INSERT workflow had **no prior runs** returned by run listing. Repo Secret metadata still lists `CLOUDFLARE_TARGET_AUDIT_TOKEN_NEW` but **does not list `CLOUDFLARE_TARGET_PREAPPLY_BOOKMARK`**. Neither `target_writers_quiesced` nor `row_safe_recovery` is established, so **do not dispatch the real write job**, and do not set either safety confirmation to YES. No D1 write/restore, R2 request or Worker deploy occurred in this repeat dry-run. The target's production Time Travel API working is **not** a usable installed rollback bookmark.

Evidence scope: current only for `recommendation_runs`, source production unchanged and remains authoritative. Next needed gates are secure authorized fresh bookmark/rollback verification, independent live writer ownership/quiescence, and safe bounded keyed row reconciliation of additional DBs/tables. R2 migration remains HOLD. Do not infer global data parity or production migration readiness from this PASS.


## Current target write analytics and Time Travel — 2026-10-29 (latest, no writes, HOLD)

**Read-only evidence only; NOT proof of writer quiescence or rollback readiness.**

- [Target D1 GraphQL write-query analytics #40866816956](https://github.com/louisalviss/runner-3/actions/runs/40866816956) PASS, under [PR #486](https://github.com/louisalviss/runner-3/pull/486). Audited `CLOUDFLARE_TARGET_AUDIT_TOKEN_NEW` fetched read-only `d1AnalyticsAdaptiveGroups` for two pinned target D1s, `runner3-content-intelligence` and `runner3-core`, requested **2026-10-26 to 2026-10-29 UTC**. The GraphQL API returned **only 2026-10-26**, with `writeQueries=0` for each D1. **Dates 2026-10-27, 28 and 29 had no returned group**. Missing groups are NOT evidence of zero writes, no background clients or source-to-target quiescence. The workflow recorded `writer_quiescence_proven=false`, `d1_sql_requests=0`, `d1_writes=0`, `r2_requests=0`, `cutover_ready=false`. No write token was passed to the workflow. No per-client attribution is possible from these aggregate metrics.
- [Fresh target Time Travel eligibility #40866983692](https://github.com/louisalviss/runner-3/actions/runs/40866983692) PASS at **2026-10-29T11:39:01Z** for `runner3-content-intelligence`. Read-only GET confirmed correct target identity and production backend; current bookmark endpoint works. Raw bookmark was **not exported or preserved**; `bookmark_preserved_for_actual_restore=false`, `pre_apply_fresh_bookmark_verified=false`, `target_writers_quiesced=false`, `safe_restore_approved=false`, `cutover_ready=false`. Production restore is a whole-database, potentially destructive operation; none was attempted.
- GitHub Actions Secret `CLOUDFLARE_TARGET_PREAPPLY_BOOKMARK` is **still absent** in the authenticated repo secret-name listing on 2026-10-29. The original VPS courier private-key decrypt/install action had been caller-side blocked. **Do not circumvent or reroute to extract the courier key or bookmark**. The prior encrypted 1-day evidence artifact is not proof of installed escrow. New escrow must be handled via separately authorized, secure process and a tested row-safe recovery plan, immediately before any approved target write.
- Earlier [39/39 DDL empty isolated SQLite rehearsal #40388871787](https://github.com/louisalviss/runner-3/actions/runs/40388871787) PASS structurally; [15 source missing-table data presence #40389799662](https://github.com/louisalviss/runner-3/actions/runs/40389799662) found **12 nonempty, 3 empty**. This does not mean data in any common-named DB matches. Authentication, magic-link and migration bookkeeping tables must have explicit retention/security handling, not automatic copying. Do not run unbounded `COUNT(*)` across all tables without a cost limit and review; D1 bills by rows read.
- **Remaining decisive gates**: explicitly identify/control non-Worker target D1 writers, prove bounded quiescence at time of cutover; secure an immediately pre-apply bookmark and tested rollback route without private-key policy bypass; reconcile all needed D1 keyed content, tombstones and preserved target-only stores; separately release R2 cost gate and cutover with user approval. No D1 schema apply, INSERT/DELETE, restore, Worker deployment, R2 migration, source deletion or cutover occurred in these audits.
- **Do not set either `target_writers_quiesced=YES` or `row_safe_recovery=YES` on the guarded INSERT workflow. Preserve all production services and keep migration on HOLD.**


## Live 15-table content-presence and FK-dependency checks — 2026-10-27 (latest, HOLD)

Two authenticated, bounded **read-only** workflows passed; both were synthetic-tested and run manually from `main`, with sanitized artifacts and no production writes.

1. [Source-only 15-table existence run #40389799662](https://github.com/louisalviss/runner-3/actions/runs/40389799662), from [PR #483](https://github.com/louisalviss/runner-3/pull/483). It made exactly 15 bounded `SELECT 1 AS present FROM "<allowlisted_table>" LIMIT 1` queries on SOURCE, not `COUNT(*)`, and returned only empty/nonempty flags with **no application row content**. 12/15 missing-on-target source tables were nonempty; 3 were empty.
2. [Isolated 39-DDL replay with FK dependencies #40390362550](https://github.com/louisalviss/runner-3/actions/runs/40390362550), from [PR #484](https://github.com/louisalviss/runner-3/pull/484). The already PASS full source-pinned 39/39 additive CREATE-only rehearsal now additionally fails closed if any source FK parent table is absent and summarizes table-level FK edges. Nine independent synthetic tests PASS. Still **zero D1 writes**.

**Source tables confirmed empty (no rows in source at time of query):**
- `runner3-content-intelligence.checkpoints` (composite PK)
- `runner3-core.artifact_library_pin_attempts` (one-column PK)
- `runner3-core.ebook_reader_trace_v113` (composite PK)

**Source tables confirmed nonempty (at least one row; exact row count and content are NOT known):**
- `runner3-content-intelligence`: `link_interest_events`, `workflow_state`.
- `runner3-core`: `artifact_library_auth`, `artifact_library_magic_links`, `checkpoints`, `d1_migrations`, `delivery_permalinks`, `events`, `r2_receipts`, `typed_kv`, `vps_mailbox_jobs`, `workflow_state`.

**Foreign keys in reconstructed `runner3-content-intelligence` source schema (all three are on tables ALREADY present at target):**
- `content_features` → `content_items`, `ON DELETE CASCADE`.
- `content_scores` → `content_items`, `ON DELETE CASCADE`.
- `user_content_events` → `content_items`, `ON DELETE CASCADE`.

`runner3-core` has zero declared FKs. **None of the 15 source-only missing tables is the parent or child of those three source-declared FKs**. This removes a DDL topological blocker in *empty scratch SQLite* but does not validate uniqueness, dependent triggers on populated targets, application referential consistency, or row copying order.

### Required migration treatment — policy, not automatic permission

- **Schema-only candidates:** three source-empty tables can be considered for CREATE-only staging, provided a fresh source check, target-empty/absence identity check and tested recovery are performed immediately before any actual DDL. Do not equate a source-empty snapshot with permanently empty tables.
- **Data-backed candidates:** 12 source-nonempty tables require bounded keyed row reconciliation, source/target create-definition/constraint verification, append-only or explicit conflict policy, and handling of changes while copying.
- **High-risk authentication/session state:** `artifact_library_auth`, `artifact_library_magic_links` must not be blindly migrated as live credentials or session links; require deliberate invalidate/reissue/preserve policy and leakage safeguards. `artifact_library_pin_attempts` is empty only at this snapshot.
- **Operational state and history:** `d1_migrations`, `workflow_state`, `vps_mailbox_jobs` require single-owner replay/idempotency and source authority decisions. Never automatically replay jobs or copy migration history.
- **R2-related metadata:** `r2_receipts` is nonempty and may encode external R2 references; remains separately subject to `CLOUDFLARE-R2-COST-001 HOLD` and its explicit operation-cost budget.
- **Triggers and remaining objects:** One missing trigger is verified locally as CREATE-only but **has never fired on a populated target**; 23 missing indexes have not been checked for unique-key conflicts against populated target rows.

GitHub Actions Secret metadata rechecked after these runs: `CLOUDFLARE_TARGET_AUDIT_TOKEN_NEW` and `CLOUDFLARE_TARGET_D1_WRITE_TOKEN` present; **`CLOUDFLARE_TARGET_PREAPPLY_BOOKMARK` still absent**. No validated immediately-pre-apply recovery/restore capability. External writer quiescence, full source/target keyed row/content/delete parity and authorization are missing. **DO NOT schedule or run live DDL, row INSERT, restore, Worker cutover or R2 operations; production migration remains HOLD.**


## All 39 source-pinned missing CREATE DDL — isolated empty SQLite rehearsal PASS (2026-10-27)

[Dispatch-only isolated replay #40388871787](https://github.com/louisalviss/runner-3/actions/runs/40388871787) on merged [PR #481](https://github.com/louisalviss/runner-3/pull/481) **PASS**. Uses the verified NEW Cloudflare target read-only Audit Secret plus independent source read-only token. Re-ran the existing source-pinned exact-six DDL capture and independently checked the 33 source-fingerprint-pinned CREATE candidates from versioned repository input. Both current target database identities and their schema metadata were checked via Cloudflare API without row content or any schema/data write. Candidate raw SQL existed **only in transient GitHub Action memory**; no raw CREATE SQL was stored in the artifact or log.

The workflow constructed the existing TARGET schema in empty, ephemeral in-memory SQLite, then applied source CREATE-only candidates in isolation and compared every resulting schema object name/CREATE definition against the LIVE SOURCE schema. It also checked no silent IF NOT EXISTS no-ops, no changes to preexisting target catalog objects, SQLite `integrity_check=ok` and FK schema metadata. Eight independent synthetic tests passed (including destructive statement and no-op rejection).

| D1 | Target existing objects | Source-pinned CREATE objects rehearsed | Simulated final schema objects |
| --- | ---: | ---: | ---: |
| `runner3-core` | 1 | 21 | 22 |
| `runner3-content-intelligence` | 9 | 18 | 27 |
| **Total** | **10** | **39** | **49** |

The reconstructed Content Intelligence schema contains **three foreign key constraints**, Core zero, as reported by local SQLite `foreign_key_list`. This counts constraint definitions, NOT live target FK compliance, target table size, source/target row count, or row-safety of schema migration. No real row content was loaded; uniqueness, FK enforcement on production rows, trigger execution/side-effects, migration ordering on data, table-by-table PK/row/delete/tombstone parity and retention of auth/migration state remain **UNPROVEN**. SQLite simulation confirms structural compatibility in empty scratch only, not actual apply safety.

**DO NOT auto-apply the 39 CREATE statements.** This result does not release `target_writers_quiesced`, `row_safe_recovery`, or the separate D1 WRITE approval. `CLOUDFLARE_TARGET_PREAPPLY_BOOKMARK` secret still absent at last metadata check and previous private-key secret-install path blocked (do not reroute). External writers and full D1 rows are not reconciled; R2 cost gate remains HOLD; no Cloudflare writes, restore calls, Worker deploys, R2 operations or cutover occurred.


## Live source-only table PK census — 2026-10-27 (latest, still HOLD)

[Manual read-only PK workflow #40384940380](https://github.com/louisalviss/runner-3/actions/runs/40384940380) PASS after [PR #479](https://github.com/louisalviss/runner-3/pull/479), using the source-account read-only API credential and exact allowlisted `PRAGMA table_xinfo` for all 15 previously identified source-only tables. Independent six offline synthetic tests passed. There were **zero table row reads, zero D1 writes, zero R2 or target requests**. No raw column values/names, UUIDs, token values, or DDL definitions were serialized.

**Result: 15/15 source-only tables have a declared primary key**. 12 tables single-column PK; exactly three tables have two-column composite PKs:
- `runner3-content-intelligence.checkpoints` (8 total columns, two-column PK)
- `runner3-core.checkpoints` (8 total columns, two-column PK)
- `runner3-core.ebook_reader_trace_v113` (7 total columns, two-column PK)

The remaining 12 tables have a one-column PK: `link_interest_events`, `workflow_state` (in both DBs), `artifact_library_auth`, `artifact_library_magic_links`, `artifact_library_pin_attempts`, `d1_migrations`, `delivery_permalinks`, `events`, `r2_receipts`, `typed_kv`, `vps_mailbox_jobs`.

**Interpretation:** The PK design permits future deterministic key-based reconciliation in principle, subject to verifying index/constraint semantics, row payloads, deletion policy and auth/migration-state ownership. It **does not** prove one row is safe to copy, or that the target schema can be applied; target still lacks 15 tables, 23 indexes and 1 trigger. Avoid automatically copying auth secrets, magic links or migration bookkeeping merely because a PK exists.

GitHub secret `CLOUDFLARE_TARGET_PREAPPLY_BOOKMARK` remains absent at last check. No approved independently tested escrow / row-safe recovery. External writer quiescence is unproven. Source production and R2 HOLD remain unchanged. **Never attest YES to the guarded D1 production INSERT workflow on this evidence.**


## Live 39-object schema gap decomposition — 2026-10-27 (latest, READ-ONLY)

[Source/target D1 schema diff #40384015167](https://github.com/louisalviss/runner-3/actions/runs/40384015167) completed **PASS** after [PR #477](https://github.com/louisalviss/runner-3/pull/477) (8 offline unit tests PASS independently, 0 D1 writes, 0 R2 requests). Source and target both have 9 D1; 8 names shared, 6 shared schema-identical. Source-only `clm-copilot-calibration` and target-only `louis-context-index` remain preserved pending independent owner/retention review.

The **39 source-only schema objects** are classified using live `sqlite_master` metadata (SQL definitions were compared but **not published**):

| Target database with incomplete schema | Missing tables | Missing indexes | Missing triggers | Missing views | Total |
| --- | ---: | ---: | ---: | ---: | ---: |
| `runner3-content-intelligence` | 3 | 14 | 1 | 0 | 18 |
| `runner3-core` | 12 | 9 | 0 | 0 | 21 |
| **Total** | **15** | **23** | **1** | **0** | **39** |

Tables missing on target, **names only**:
- `runner3-content-intelligence`: `checkpoints`, `link_interest_events`, `workflow_state`.
- `runner3-core`: `artifact_library_auth`, `artifact_library_magic_links`, `artifact_library_pin_attempts`, `checkpoints`, `d1_migrations`, `delivery_permalinks`, `ebook_reader_trace_v113`, `events`, `r2_receipts`, `typed_kv`, `vps_mailbox_jobs`, `workflow_state`.

**Safety and implementation order:** This is a schema-only census. No table counts, PK-based row digests, deletions, FK dependencies, trigger semantics, schema application or data reconciliation were established by this run. Some table names imply authentication or migration bookkeeping; name-based classification alone cannot establish retention or copy authorization. Verify **source-exact DDL plus table PK/constraints and indexes**, separately review credential-related and migration-history tables, validate dependencies in isolated SQLite, then construct additive-only DDL and independent keyed row reconciliation. A trigger must not be enabled before examining how it affects copied or preexisting rows. Do not automatically recreate all 39 objects from names.

Target Worker read-only binding census #40377262061 proves no *deployed target Worker* binds `runner3-content-intelligence`, but does not eliminate external token/API clients. On VPS, an additional read-only configuration scan on 2026-10-27 checked six relevant services, resolved two service EnvironmentFiles (without printing values), and found source Worker/account references but no literal target account UUID, target D1 UUID, or target Worker address. This is **negative static evidence only**: dynamically loaded settings and other clients remain possible writers. Do not set `target_writers_quiesced=YES` from these findings.

**Production readiness remains HOLD**: `CLOUDFLARE_TARGET_PREAPPLY_BOOKMARK` GitHub Secret absent when last checked; authorized usable escrow + tested recovery unproven; full-account row/delete/tombstone parity missing; R2 cost HOLD. No D1 writes or Worker deployments, no source/target deletion or cutover.


## Target live D1 Worker binding attribution — 2026-10-27 (latest; migration HOLD)

**New result: complete read-only Worker-to-D1 attribution for the target account**. [Workflow #40377262061](https://github.com/louisalviss/runner-3/actions/runs/40377262061), after [PR #475](https://github.com/louisalviss/runner-3/pull/475) merged on main. The workflow uses scoped `CLOUDFLARE_TARGET_AUDIT_TOKEN_NEW`; both Worker lists show 6 matching Workers, all settings/schedules read successfully, target has 9 matching historical D1 identities. Zero cron schedules. It matches physical D1 binding IDs only in memory against the same **live target** D1 UUID map and publishes target D1 **names only**, no UUID or raw binding/secret.

- `volamidle-rogue`: binding `DB` matches live target D1 `volamidle-rogue-data`.
- The remaining 5 deployed Workers have **no D1 bindings**.
- `worker_d1_binding_attribution_complete=true`; `recommendation_runs_db_worker_binding_absent_verified=true`, referring **only to this account's currently deployed Worker bindings**. No target Worker binds directly to `runner3-content-intelligence`.
- **`target_nonworker_writers_excluded=false`, `writer_quiescence_proven=false`, `cutover_ready=false`**. API tokens and other external clients, source scripts, runners, remote jobs, and future Worker deploys have not all been proven idle; the Worker finding is not an authorization to attest quiescence or run INSERT.
- GitHub Secret metadata rechecked: `CLOUDFLARE_TARGET_AUDIT_TOKEN_NEW` and independent `CLOUDFLARE_TARGET_D1_WRITE_TOKEN` are present, but **`CLOUDFLARE_TARGET_PREAPPLY_BOOKMARK` remains absent**. No escrow recovery test, rollback readiness, real restore test or production D1 writes. Earlier encrypted bookmark may expire and must not be treated as installed.
- Earlier 39 source-only schema objects missing on target across `runner3-core` and `runner3-content-intelligence` remain an **unresolved historical gap**, not a statement of newly measured parity. Preserve source-only and target-only D1 objects. R2 remains cost-gated HOLD.
- Next safe work: investigate **non-Worker writers** without stopping source production; independently establish a verifiable bounded target quiescence procedure, solve authorized restoration bookmark escrow without bypassing prior caller-side private-key block, and build a full row/schema reconciliation plan. No automatic production write.


## New verified target Workers census — 2026-10-27 (supersedes earlier HTTP 403 findings)

**Worker audit token unblocked.** Operator created a **separate** GitHub Actions Secret `CLOUDFLARE_TARGET_AUDIT_TOKEN_NEW`, verified present in repository secret metadata 2026-10-26T17:08:50Z. Prior legacy `CLOUDFLARE_TARGET_AUDIT_TOKEN` was unchanged. Do not confuse either audit Secret with independent Write-only migration Secret `CLOUDFLARE_TARGET_D1_WRITE_TOKEN`.

[Manual read-only validation #40366950155](https://github.com/louisalviss/runner-3/actions/runs/40366950155) used the **NEW** Secret explicitly; target 9 D1 identity verification PASS and both Worker-list endpoints returned 6 matching workers (**Workers API HTTP 403 resolved**). All 6 settings and cron reads PASS, zero cron schedules reported. Redacted Worker binding summary:

- `balatro-clef-api`: Workers AI binding `AI`; zero cron.
- `khotruyen-worker`: no bindings; zero cron.
- `runner3-x-fast-direct`: no bindings; zero cron.
- `runner5-restore-proxy`: no bindings; zero cron.
- `volamidle-rogue`: one D1 binding `DB`; zero cron.
- `wave-rider-scanner`: no bindings; zero cron.

**IMPORTANT: NOT target writer quiescence proof.** The inventory deliberately redacts physical D1 binding UUIDs and does not prove whether the sole D1 Worker binding points to `runner3-content-intelligence`. Non-Worker clients and external calls have not been completely excluded. No Worker disabled or redeployed.

The canonical manual D1+Workers metadata inventory workflow has been remapped to `CLOUDFLARE_TARGET_AUDIT_TOKEN_NEW`. The legacy audit Secret is retained for other existing workflows unless separately reviewed. No INSERT/DELETE/RESTORE, R2 action or cutover authorized.

## Consolidated account-wide audit — 2026-10-26 evening (historical snapshot)

**Outcome: SAFE_READ_ONLY_AUDIT_COMPLETE / ACCOUNT_MIGRATION_HOLD.** User requested end-to-end execution in one pass, not a sequence of repeated dry-runs. Safe, authorized diagnostic workflows were run together. No Cloudflare D1 INSERT/DELETE/RESTORE, Worker deploy, Worker disable, R2 operation or source cutover was performed.

### Fresh authenticated evidence (main)

- [Cross-account 9-D1 schema comparison #40324195505](https://github.com/louisalviss/runner-3/actions/runs/40324195505): 9 D1 databases source and 9 target; 8 shared names. **6/8 shared databases have identical sqlite_master object names/types and CREATE SQL**, but **NO row/key/content/deletion parity proof**:
  - `clm-copilot-v1`: 4/4 object parity PASS.
  - `louis-task-context`: 4/4 PASS.
  - `personal-library`: 26/26 PASS.
  - `runner3-opportunity-radar`: 21/21 PASS.
  - `runner3-rss`: 31/31 PASS.
  - `volamidle-rogue-data`: 4/4 PASS.
  - `runner3-content-intelligence`: 27 source / 9 target; **18 source-only schema objects absent on target**, no target-only objects or changes to common CREATE SQL.
  - `runner3-core`: 22 source / 1 target; **21 source-only objects absent on target**, no target-only objects or changes to common CREATE SQL.
  - Total missing source-side schema objects in the two shared D1s: **39**. This is schema inventory, **not** 39 rows or safe-to-apply DDL.
  - Source-only named DB: `clm-copilot-calibration`; target-only named DB: `louis-context-index`. Do not conflate or silently drop either.
- [Source nine-schema encrypted audit #40322914590](https://github.com/louisalviss/runner-3/actions/runs/40322914590): PASS; source metadata encrypted artifact, no plaintext DDL/row export.
- [Target nine-schema encrypted audit #40322929050](https://github.com/louisalviss/runner-3/actions/runs/40322929050): PASS; target metadata encrypted artifact.
- [Target Worker read-only inventory #40323345810](https://github.com/louisalviss/runner-3/actions/runs/40323345810), with sanitized diagnostic from PR #470: 9 target D1 UUIDs match their historical identities; legacy /workers/scripts gives 0, **independent /workers/workers returns HTTP 403**. Thus `target_workers_zero_verified=false`, binding/cron/Worker permissions unverified. **Workers Metadata Read-Only / Workers Scripts Read** permission for account `louisalviss3` is required for a reliable census; do not substitute source/global credentials.
- [Target bookmark encryption #40322947069](https://github.com/louisalviss/runner-3/actions/runs/40322947069): PASS. The one-day **ciphertext-only** artifact expires 2026-10-27T12:29:52Z. A successful encrypted artifact **does not mean recoverable private key escrow was tested or the GitHub Secret installed**. Previous private-key decryption/install path was caller-side blocked: no circumvention.
- [Target Time Travel GET #40321609830](https://github.com/louisalviss/runner-3/actions/runs/40321609830): PASS, not rollback-ready.
- [Reversible read-only D1 table rehearsal #40321583016](https://github.com/louisalviss/runner-3/actions/runs/40321583016): source 47, target 35, 12 source-only rows, matching 35, 0 conflicts; insert and row-safe reverse rehearsal in ephemeral SQLite restored 35/35, never applied to Cloudflare. This is **one table only**, not full-account row parity, source writer quiescence, or production rollback proof.
- GitHub Actions secret metadata as of 2026-10-26: `CLOUDFLARE_TARGET_D1_WRITE_TOKEN` present, `CLOUDFLARE_TARGET_PREAPPLY_BOOKMARK` absent.
- Source Worker config in `cloudflare/runner3-core/wrangler.jsonc` still binds `CONTENT_DB` to source D1, not target. VPS `library-index-d1-sync.service` uses source Worker URL. This narrows obvious writers but **does not prove target has no other writers**.
- R2 migration operation gate `ops/cloudflare-account-rehome/r2-migration-operation-gate.json` remains `HOLD`, `permit_r2_migration=false`. No R2 requests made in these D1 audits.

### Consolidated remaining external dependencies — do not start target D1 writes

1. Owner must grant appropriate **target-account Workers Metadata Read-Only or Workers Scripts Read** to an authorized *read-only* Workers inventory identity. Current target D1 audit token gets HTTP 403 from the independently documented Worker list endpoint. Do not assume a zero-worker count from incomplete API results. Re-run one full census after authorization to identify Worker bindings/crons/traffic and independently establish a bounded quiescence plan.
2. A currently **unblocked, authorized private escrow** must preserve an immediately-pre-write Time Travel bookmark in `CLOUDFLARE_TARGET_PREAPPLY_BOOKMARK` and independently verify usable restoration. An encrypted, expiring artifact alone is insufficient. No retry via alternate wrappers to evade the prior caller-side block.
3. Construct/review **source-exact and additive-only** DDL for the 39 missing objects, validate every dependency/constraint/uniqueness against populated target and source, preserve target-only data and source production. No bulk target DDL apply until backups/rollback, quiescence, actual row parity and approvals are ready.
4. Independently reconcile full keyed row payloads, source-only and target-only keys plus delete/tombstones on all databases. The schema-matched six are **not** data-matched merely from identical CREATE statements.
5. R2 remains `CLOUDFLARE-R2-COST-001 HOLD` until the residual PUT cost issue, bounded request budget and explicit release are resolved. Never treat user request to execute general migration as a verified cost-gate release.
6. Only then stage Workers privately, test bindings/schedules, perform separately approved bounded cutover and preserve source until checks pass. The guarded 12-row D1 INSERT workflow still requires same actor/SHA recent Dry-Run, exact phrase and honestly verified YES recovery/quiescence; do not fabricate these flags.

**No more re-running identical 47/35/12 dry-runs without a new prerequisite being fulfilled.** The next decisive operations are permissioned target Worker metadata census and an authorized recovery-secret installation, not a token-creation loop.

## Current evidence — 2026-10-26 (supersedes historical token claims below)

**Decision: HOLD.** No live D1 INSERT/DELETE/RESTORE, no R2 operation, no production cutover has been authorized or executed by this migration workflow.

- The independent target-account D1 write-credential GitHub Actions Secret `CLOUDFLARE_TARGET_D1_WRITE_TOKEN` **exists** (GitHub secret metadata reconfirmed 2026-10-26). Earlier text below referring to it as missing is *historical*. Target D1 metadata access via this token previously returned HTTP 200, but effective **D1 Edit has not been independently exercised**. Never test with an unapproved write.
- `CLOUDFLARE_TARGET_PREAPPLY_BOOKMARK` **does not exist** in current GitHub repository Actions Secrets. The 2026-10-25 encrypted bookmark artifact #12585997327 has expired; do not reuse a stale bookmark. [Encrypted escrow workflow #40160515174](https://github.com/louisalviss/runner-3/actions/runs/40160515174) passed, but private-key decryption / secret installation on VPS was blocked before execution by caller-side safety. Do not route around that block.
- Fresh same-main-commit **read-only** [Dry-Run #40321583016](https://github.com/louisalviss/runner-3/actions/runs/40321583016), 2026-10-26: source 47, target 35, existing 35 matched, 12 missing, no conflicts. Scratch in-memory 12-row insertion and reversal **both PASS**, restoring all 35 target baseline rows. Explicit output: `rollback_readiness_proven=false`, `writer_quiescence_proven=false`, `real_target_delete_requests=0`.
- Fresh [Time Travel eligibility #40321609830](https://github.com/louisalviss/runner-3/actions/runs/40321609830), 2026-10-26: correct target production D1, bookmark API GET succeeds; **no fresh bookmark escrow installed**, no rollback ready.
- Target [D1 + Workers inventory #40319460558](https://github.com/louisalviss/runner-3/actions/runs/40319460558), 2026-10-26: target D1 count 9; Workers scripts endpoint showed 0, but alternate Workers endpoint unavailable; **`target_workers_zero_verified=false`**, Workers/cron/settings coverage incomplete. Historical source records identified six Workers on target; do not interpret this limited API result as proof that none are deployed.
- [Dependency audit #40171237293](https://github.com/louisalviss/runner-3/actions/runs/40171237293): 9 schema tables, 3 tables with FKs, **zero inbound and zero outbound foreign-key relationships for `recommendation_runs`**, no triggers/views dependent on it, verified by rebuilding DDL in isolated SQLite memory. This is schema-only evidence, not production rollback proof.
- Static writer-route review 2026-10-26: `cloudflare/runner3-core/wrangler.jsonc` binds `CONTENT_DB` to source D1 UUID `9cbec4ec-c930-459d-9499-9c66166c9241`, not target `82613659-8d08-455f-b6e7-f8f6e4312e22`. VPS `library-index-d1-sync.service` explicitly points at source Worker `runner3-core.ducduy2411.workers.dev`. Examined `ai-scan-hub`, `ai-context-index`, `content-intelligence-dropbox-bridge` configs and script literals without finding target account/database IDs. These **limited static checks do not establish target writer quiescence**; environment-indirect, deployed Worker/cron and other remote writers remain unverified.
- R2 remains separate `CLOUDFLARE-R2-COST-001` **HOLD**. Do not invoke R2 operations during D1 inspection.

### Remaining gates and immediate next safe action

1. Establish **complete authorized read-only target Worker + cron + binding census**; current `CLOUDFLARE_TARGET_AUDIT_TOKEN` cannot independently prove that target Workers are absent. Identify all possible target D1 writers including deployed Workers, scheduled/event consumers and non-GitHub clients. Do not pause production source services on name alone.
2. Independently demonstrate and approve target writer pause/quiescence, including in-flight activity, only once all writer identities are known. Keep source production authoritative.
3. Obtain and securely preserve a **new immediately-pre-apply Time Travel bookmark**; prior encrypted artifact is expired and current GitHub bookmark Secret is missing. Do not bypass any credential/private-key caller-side policy block. Confirm a genuinely executable row-safe rollback plan in addition to the successful in-memory reversal rehearsal.
4. Only after the above: run a **fresh read-only Dry-Run** on the same current `main` SHA with same GitHub actor and within 30 minutes of separately explicit approval. Require 47/35/12 parity reverified at that time, exact bookmark equality, manual writer pause and row-recovery attestations. No automatic `YES` or approval phrase.

**No automatic migration and no silent security-gate relaxation.**

**Code only. NO live target insert authorized, no R2 calls, no source changes, no production cutover.**

## Why the two-person gate was removed

The repository `louisalviss/runner-3` has one operator. GitHub's **Prevent self-review** necessarily blocks a single operator from approving their own deployment. Requiring a second account is not a suitable operating model here. The previous named write environment `cloudflare-target-d1-writes` was absent in the public GitHub environment census (only `github-pages` existed, HTTP 404 for the write environment).

The workflow now has **no GitHub environment** and **no independent reviewer**, but preserves a two-stage operator-mediated transaction: *separate successful manual read-only dry-run* → *separate explicit manual target-only INSERT*. It never runs on push, PR or schedule.

## Step A: manually run read-only preflight

[Cloudflare D1 Recommendation Runs Additive Dry-Run (Read Only)](https://github.com/louisalviss/runner-3/actions/workflows/cloudflare-d1-recommendation-runs-additive-dryrun.yml) → **Run workflow → main**.

This workflow uses only separate existing source/target read-only Cloudflare credentials, captures both D1 tables twice, checks exact column/PK metadata and typed payloads, rejects conflicts and races, and rehearses missing source-only keys in scratch SQLite. It sends **no D1 INSERT**. It returns aggregate counts and status only. It must have **conclusion=success**.

Record its numeric GitHub Actions **run ID**, visible in its URL: `.../actions/runs/<ID>`. Do not reuse #40091169404: it was performed on an older commit and is no longer recent. The new preflight must be on the *identical `main` commit* as the later manual write job, created within the previous **30 minutes**.

## Step B: separately approve target-only write (NOT YET ENABLED)

[Cloudflare D1 Target Recommendation Runs ADDITIVE WRITE (Solo Two-Step Approval)](https://github.com/louisalviss/runner-3/actions/workflows/cloudflare-d1-recommendation-runs-guarded-insert.yml) → **Run workflow → main**.

The workflow has required manual inputs: `dryrun_run_id`, exact typed `APPROVE_TARGET_ONLY_RECOMMENDATION_RUNS_12_INSERTS` phrase and separate confirmations `target_writers_quiesced=YES`, `row_safe_recovery=YES`. Both confirmations default to **NO**. Never select YES without real evidence.

A standalone first GitHub job, `recent-dryrun-gate`, has **no Cloudflare credentials** and retrieves the exact previous GitHub run using only `GET /repos/louisalviss/runner-3/actions/runs/{id}` and the GitHub Actions read-only token. It requires:

- Exact previous workflow path/name and `workflow_dispatch` event, `status=completed`, `conclusion=success`, first attempt only.
- Identical initiating/triggering GitHub actor as the write job, identical `main` commit SHA, branch, current repository and event.
- Valid created/finished times and <=30 minutes old. Any stale/different/replayed/failed run **fails closed**.
- The target write job cannot begin unless this first job passes. The writer repeats proof validation before any Cloudflare mutation.

**IMPORTANT:** Two GitHub Actions runs by the same person are not independent approval. This deliberately trades independent review for a simpler solo operation without removing data integrity, rollback and source-of-truth gates.

## Atomicity hardening (2026-10-25)

The previous guarded executor issued twelve independent D1 API INSERT requests, risking a **partially written** target table if a later request failed. It has been replaced with **one SQLite SQL statement**:

`INSERT INTO "recommendation_runs" (...) VALUES (?,?,...),(?,?,...), ...`

Exactly **12 tuples, 8 allowlisted columns**, at most **96 positional bound string parameters**, no raw values embedded in SQL, no semicolon, no multi-statement batch, no DELETE, UPDATE, UPSERT or REPLACE. The writer accepts only this pinned SQL shape; rejects an unexpected number of tuples, duplicate IDs, additional statements, SQL injection, oversize SQL, or wrong D1 account. It requires the D1 API to report exactly 12 changed rows.

Since this is a **single ordinary SQLite INSERT statement**, any uniqueness/constraint error aborts the whole statement rather than committing earlier VALUES tuples. Synthetic integration tests use an isolated real SQLite engine to verify all-or-nothing behavior. A network error after POST still leaves **ambiguous 0-or-12 commit status**, requiring read-only reconciliation before any further action. Even an atomic successful commit does not replace a reviewed row-safe recovery strategy if copied data is later found incorrect.

The old per-row intermediate readback has been replaced by a **complete post-statement target readback** verifying all existing target rows remain untouched and all twelve inserted rows exactly match their sources or the SQLite REAL-affinity equivalent. The final source-to-target recheck remains mandatory and fails closed if production source writes occurred during the window. Raw keys, payloads and bookmark stay out of logs and artifacts.

Cloudflare documents the D1 REST `/query` API with `sql` and `params` string arrays: https://developers.cloudflare.com/api/resources/d1/subresources/database/methods/query/ . Its D1 SQL backend is SQLite: https://developers.cloudflare.com/d1/sql-api/sql-statements/ .

## Additional non-negotiable prerequisites before any real INSERT

- Three distinct tokens: source read-only `CLOUDFLARE_API_TOKEN`, target read-only `CLOUDFLARE_TARGET_AUDIT_TOKEN`, and separately provisioned target-account D1 Write token `CLOUDFLARE_TARGET_D1_WRITE_TOKEN`. The write token must be permission-scope restricted to the target account/database as supported. Never repurpose an audit token.
- Private, securely preserved **fresh target Time Travel bookmark** set as GitHub repository secret `CLOUDFLARE_TARGET_PREAPPLY_BOOKMARK`. Its exact value must match the target's *current* bookmark immediately before any INSERT. The old audit stored only a bookmark hash and is **not a rollback point**.
- **Target writers truly paused** and a **tested row-safe recovery plan**. Time Travel restore overwrites the **entire target D1 database**, including unrelated concurrent changes. No automatic restore is permitted.
- Read-only real preflight still shows exactly 12 source-only `recommendation_runs` rows, 35 matching existing target rows, no target-only keys, no differing typed payloads, same schema. If the delta changes, block and review; do not blindly replay 12.
- Ordinary parameter-bound `INSERT` only on the hardcoded D1 target UUID. The one atomic INSERT of 12 rows must be read back in full; previously present target rows must be preserved, and source/target re-read afterward. Network failure makes the commit outcome **unknown (zero or twelve rows)**; never auto-delete or retry, reconcile with a read-only audit. If SQLite REAL affinity changes typed representation, the writer explicitly records strict parity as **HOLD**, not a false 1:1 claim.

**Historical state at initial runbook creation (2026-10-24):** No separately approved target write credentials, private bookmark, paused writers or recovery rehearsals had been verified. See the 2026-10-26 section above for superseding credential and in-memory rehearsal evidence. **Do NOT dispatch Step B now**. Complete these gates first. R2 `COST_HOLD rev28`, source production and all other D1/Workers parity checks remain in force.

## Evidence

- [First live row audit #40089305352](https://github.com/louisalviss/runner-3/actions/runs/40089305352): 47 source, 35 target, 35 exact matching pairs, 12 source-only.
- [Authenticated additive dry-run #40091169404](https://github.com/louisalviss/runner-3/actions/runs/40091169404): scratch-only 12-row INSERT+readback passed, no target writes.
- [Target Time Travel capability #40092563094](https://github.com/louisalviss/runner-3/actions/runs/40092563094): production backend and bookmark API confirmed, raw bookmark **not preserved**.

**State:** `target_d1_writes=0`; `r2_requests=0`; `source_authoritative=true`; `row_rollback_ready=false`; `full_cutover_ready=false`.
