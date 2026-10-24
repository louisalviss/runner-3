# Target Content Intelligence D1 — Time Travel rollback eligibility (2026-10-24)

**Checkpoint:** one-table `recommendation_runs` live source 47 / target 35; **12 missing**. The real additive copy **passed an isolated SQLite rehearsal** in [run #40091169404](https://github.com/louisalviss/runner-3/actions/runs/40091169404), but no target D1 write has happened.

## Verified API capabilities (not yet live target-specific proof)

Cloudflare's documented Time Travel GET
`GET /accounts/{target_account}/d1/database/{target_uuid}/time_travel/bookmark`
accepts **D1 Read**. Database details GET returns `version` and UUID/name. Only a `version=production` D1 database is Time Travel eligible. Source: https://developers.cloudflare.com/api/resources/d1/subresources/database/subresources/time_travel/methods/get_bookmark/ and https://developers.cloudflare.com/d1/reference/time-travel/.

**Critical rollback warning:** `POST /time_travel/restore` overwrites **the entire D1 database**, including unrelated newer writes, not only the 12 `recommendation_runs` rows. Never enable an automatic restore as a row-level rollback. Time Travel retains recovery history for 7 days on Workers Free or 30 days on Workers Paid, subject to database backend/plan. The source account remains authoritative.

## Concrete target check now ready

New manual-only workflow [Cloudflare D1 Target Time Travel Read-only Check](https://github.com/louisalviss/runner-3/actions/workflows/cloudflare-d1-target-time-travel-readonly.yml):

1. Uses the **existing target D1 read-only token**, not a target write token.
2. Makes exactly **two allowlisted GET requests** for one pinned target `runner3-content-intelligence` D1: database details and current Time Travel bookmark.
3. Aborts unless UUID/name match the canonical target, backend is `production`, and the bookmark is returned.
4. Emits only current bookmark's **SHA-256** and readiness flags in a sanitized two-day artifact. The **actual bookmark is never logged, stored or exported**, so this read-only test **is not itself a recoverable pre-write bookmark**. An exact fresh, privately preserved bookmark is needed immediately before any future approved mutation.
5. Contains no restore/POST/SQL statements, no source account token, no Worker/R2 operations and no automatic scheduling.

CI runs 14 synthetic tests that reject a wrong account/DB, invalid/alpha backend, missing bookmark, bad URL, unsupported mutation, and overbroad claims.

## Requirements **before** actual target writes

- **Separate target-only `D1 Write` credential** deliberately provisioned for the correct Cloudflare account and as narrow a scope as supported. Do not elevate or repurpose the source/target audit tokens.
- Fresh, privately retained and verified *immediately pre-write* target bookmark and explicit restore disaster-recovery authorization. **Database-wide Time Travel alone is not sufficient to approve row-level rollback**: snapshot existing target rows, identify target writers, and rehearse an operation-specific recovery plan that never destroys unrelated concurrent writes.
- Re-read all source/target `recommendation_runs` columns and PKs just before apply; source/target snapshots are not atomic, so require a safe source-writer catch-up strategy.
- Target insert must be `INSERT` with explicit columns + bound parameters, never `REPLACE`, `UPDATE`, delete or overwrite. Any collision/conflict triggers a HOLD. Verify rows with readback; preserve 35 existing rows.
- No R2 operations while **COST_HOLD rev28**. Source is still production; Worker/cron/services, schema apply and all-table row/deletion parity are still blocked. Even a successful 12-row copy is NOT authorization for cutover.

**Explicit state**: `target_time_travel_bookmark_live_checked=false` (until workflow run), `target_write_permission_verified=false`, `safe_restore_approved=false`, `target_rows_written=0`, `r2_requests=0`, `cutover_ready=false`.
