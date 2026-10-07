# D1 Domain Isolation — FINAL Checkpoint — 2026-10-08 05:03 VN

## Status
**DONE — quota-safe domain isolation is complete.**

This checkpoint **supersedes**:
- `ops/checkpoints/d1-domain-isolation-2026-10-08-0443-VN.md`

The 04:43 checkpoint is retained as historical evidence only. Its resume plan is stale and MUST NOT be executed.

## Why the old resume point is invalid
The old checkpoint assumed:
1. Cloudflare D1 inventory was 10/10.
2. A D1 slot had to be freed by moving CLM from D1 to R2.
3. The freed slot would be used to create `runner3-reddit`.
4. Ebook reader state still needed migration into `personal-library`.

Canonical/live evidence after that checkpoint proves those assumptions are no longer true.

## Canonical authority
`ops/cloudflare-capability/d1-domain-isolation.json` is the current authority and records:
- status: `quota-safe-domain-isolation-complete`
- D1 inventory count: 9
- Reddit: R2 canonical + SQLite/JSONL query bundle + Telegram backup/delivery
- dedicated Reddit D1: deleted
- legacy Reddit tables in `runner3-core`: purged
- Ebook authority: `personal-library`
- CLM authority: `clm-copilot-v1`
- pending: `{}`

## Fresh production audit

### 1. Account D1 inventory / quota
Fresh manual dispatch of **D1 Account Usage Watch**:
- Run: `37693689645`
- Result: SUCCESS
- Timestamp: 2026-10-08 05:03 VN
- `inventoryCount = 9`
- `rowsWritten = 55,905`
- projected rows/day = `60,809`
- Guard result: `D1_ACCOUNT_USAGE_WATCH_PASS`

Current inventory observed by the watch:
1. `runner3-core`
2. `runner3-opportunity-radar`
3. `personal-library`
4. `louis-task-context`
5. `louis-context-index`
6. `runner3-content-intelligence`
7. `runner3-rss`
8. `volamidle-rogue-data`
9. `clm-copilot-v1`

A historical database UUID can still appear in same-day analytics after deletion; it is not part of the live inventory count.

### 2. Runner3 Core production bindings
Latest relevant production deploy:
- Run: `37685609334`
- Result: SUCCESS

Live deploy output confirms:
- `DB → runner3-core`
- `OPPORTUNITY_DB → runner3-opportunity-radar`
- `BUSINESS_OPPORTUNITY_DB → runner3-opportunity-radar`
- `LIBRARY_DB → personal-library`
- `TASK_CONTEXT_DB → louis-task-context`
- `CONTEXT_INDEX_DB → louis-context-index`
- `CONTENT_DB → runner3-content-intelligence`
- `RSS_DB → runner3-rss`

Reader verification in the same deploy:
- Reader v72/version endpoint: HTTP 200
- Ebook owner boundary: PASS
- Ebook list: PASS
- Opportunity Radar D1: PASS

### 3. Ebook migration
`D1 Domain Isolation Safe Prepare` run:
- Run: `37675165492`
- Result: SUCCESS

Verified steps:
- Personal Library ebook schema created
- Ebook reader state copied without destructive clears
- Source/destination counts verified

Therefore Ebook belongs to `personal-library`; do not rerun the migration unless a later drift audit proves a mismatch.

### 4. Reddit retirement
`Retire Empty RealDayTrading D1 (ARCHIVED)` run:
- Run: `37683136867`
- Result: SUCCESS
- Verified empty before deleting `runner3-reddit`

`Purge Legacy RealDayTrading D1 Rows` latest successful run:
- Run: `37685747444`
- Result: SUCCESS

Current live route:
- `/reddit/deep-sweep/*` → HTTP 410
- error: `REALDAYTRADING_D1_RUNTIME_RETIRED`
- storage: `R2_RAW_PLUS_SQLITE_JSONL_TELEGRAM`

**Guardrail:** do not create `runner3-reddit` again.

### 5. CLM
Current live CLM health:
- endpoint: `clm-conversation-copilot-api`
- HTTP 200
- dataset reports `clm-copilot-v1`

Therefore:
- keep `clm-copilot-v1`
- do **not** run `.github/workflows/clm-d1-to-r2-migration.yml` merely to free a D1 slot
- the old slot-pressure reason for that migration no longer exists

## Final operating rules
1. Keep 04:43 checkpoint for history only; never resume from it.
2. Use this checkpoint + `ops/cloudflare-capability/d1-domain-isolation.json` as the resume authority.
3. Do not recreate Reddit D1.
4. Do not migrate CLM to R2 unless CLM itself later has a technical/storage reason independent of D1 slot pressure.
5. Do not rerun completed Ebook migration unless drift is proven.
6. Keep D1 account usage watch active.
7. Existing domain-separated D1 authorities remain unchanged unless a future explicit migration is independently justified.

## Closure
Task: `SYSTEM-TASK-D1-ISOLATION-001`

State: **DONE**

No production cutover is pending.
No D1 slot-pressure migration is pending.
No destructive cleanup is pending.
