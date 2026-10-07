# D1 Domain Isolation Checkpoint — 2026-10-08 04:43 VN

## Objective
Physically isolate Cloudflare D1 data by bounded domain without data loss, while respecting the account D1 quota.

## Completed and verified

### Consolidations completed
1. `ai-vps-common-access` → `runner3-core`
   - Tables: `typed_kv`, `r2_receipts`
   - Exact export comparison passed.
   - Common-access helper now points D1 to `runner3-core`.
   - R2 bucket `ai-vps-common-access` remains unchanged.
   - Source D1 retired after backup/verification.

2. `media-library` → `personal-library`
   - Tables: auth_bootstrap, auth_pairing, auth_pin_attempts, auth_pin_config, media_items.
   - Exact export comparison passed.
   - media-library Worker binding is live on `personal-library`.
   - Health smoke returned HTTP 200.
   - Source D1 retired after backup/verification.

3. `runner3-business-opportunity` → `runner3-opportunity-radar`
   - business_opportunity_* tables copied and verified.
   - Runner3 Core BUSINESS_OPPORTUNITY_DB is live on `runner3-opportunity-radar`.
   - Bootstrap/live proof passed.
   - Source D1 retired after backup/verification.

### Dedicated authorities completed
4. `louis-task-context`
   - 90 task-context related checkpoint rows migrated.
   - Live Runner3 binding: TASK_CONTEXT_DB.

5. `louis-context-index`
   - 12 context-index checkpoint rows migrated.
   - Live Runner3 binding: CONTEXT_INDEX_DB.

6. `runner3-content-intelligence`
   - Dedicated content/interest tables migrated.
   - `link_interest_events` merged from legacy `link-interest-profile`.
   - Verify workflow passed.
   - Legacy `link-interest-profile` retired only after proof.
   - Live Runner3 binding: CONTENT_DB.
   - Live smoke: `/content-intelligence/profile?limit=3` → HTTP 200, ok=true, model_version=personal-v4.

7. `runner3-rss`
   - Dedicated D1 created.
   - RSS tables migrated.
   - Exact table verification passed.
   - RSS FTS parity passed.
   - Live Runner3 binding: RSS_DB.
   - Live smoke: `/api/rss/library?limit=1` → HTTP 200, ok=true.

### Production proof
- Quota-aware migration workflow: GitHub Actions run 37539808103 — SUCCESS.
- Runner3 Core production deploy: GitHub Actions run 37540460307 — SUCCESS.
- Cloudflare live binding readback confirms:
  - DB → runner3-core
  - OPPORTUNITY_DB → runner3-opportunity-radar
  - BUSINESS_OPPORTUNITY_DB → runner3-opportunity-radar
  - LIBRARY_DB → personal-library
  - TASK_CONTEXT_DB → louis-task-context
  - CONTEXT_INDEX_DB → louis-context-index
  - CONTENT_DB → runner3-content-intelligence
  - RSS_DB → runner3-rss

## Backups
SQL backups for the retired/changed source D1s were produced before destructive steps and copied to:
- R2 bucket: `runner3-artifacts`
- Prefix: `d1-migration-backups/2026-10-06/`

## Current live D1 inventory (10/10)
1. runner3-core
2. runner3-wp-optimizer
3. runner3-opportunity-radar
4. personal-library
5. louis-task-context
6. louis-context-index
7. runner3-content-intelligence
8. runner3-rss
9. volamidle-rogue-data
10. clm-copilot-v1

## Remaining blocker
Two domains are still physically inside `runner3-core` because the Cloudflare account is at the 10-D1 limit:
- Reddit
- Ebook reader state/progress

Do NOT mix them into unrelated D1s merely to bypass quota.

## Chosen next plan
1. Move Ebook reader state/progress into `personal-library` because Ebook/Reader belongs to the Library bounded-domain. This does not require another D1 slot.
2. Free one D1 slot by migrating `clm-copilot-v1` dataset from D1 to dedicated R2 bucket `clm-copilot-data`.
3. Use the freed slot to create `runner3-reddit`, migrate/verify Reddit tables, then bind Reddit traffic to it.
4. Keep old tables in `runner3-core` rollback-only until multiple healthy production cycles prove the new authorities. Do not drop them yet.

## CLM → R2 work already started
- R2 bucket `clm-copilot-data` has been created.
- `clm-copilot-v1.clm_samples` exported: 7 rows.
- Current CLM Worker bindings are:
  - AI
  - DB → clm-copilot-v1
  - RATE_LIMITER
- Current Worker code was recovered to `/tmp/clm-worker-index.js`.
- Local patch started:
  - `saveSample()` changed from D1 INSERT to `env.DATASET.put("samples/<id>.json")`.
  - Feedback path locally changed from D1 UPDATE to R2 get/update/put.
- One R2 sample object upload was confirmed before tool safety blocked subsequent batch upload:
  - `samples/62c6a677-38c0-495e-a055-c74efad7e8fc.json`
- The other six sample objects are not yet confirmed uploaded.
- CLM Worker has NOT been redeployed with the R2 binding yet.
- `clm-copilot-v1` D1 has NOT been deleted.
- Therefore CLM production remains on the known-good D1 version.

## Exact resume point
Resume at **CLM D1 → R2 migration**, starting with:
1. Validate `/tmp/clm-worker-index.js` syntax.
2. Upload all 7 exported CLM samples to `clm-copilot-data/samples/<id>.json`; verify 7/7 readback.
3. Deploy CLM Worker with binding `DATASET → clm-copilot-data`, preserving AI + RATE_LIMITER.
4. Smoke analysis + feedback and verify R2 persistence.
5. Back up and retire `clm-copilot-v1` D1.
6. Create `runner3-reddit`, migrate/verify Reddit.
7. Move Ebook DB usage to `personal-library`.
8. Re-audit all D1 bindings and mark legacy tables rollback-only.

## Safety state at checkpoint
- No known production outage.
- Source data needed for rollback is still retained/backed up.
- CLM production still uses its original D1 and has not been cut over.
- Do not rerun already-successful consolidation migrations unless verification shows drift.
