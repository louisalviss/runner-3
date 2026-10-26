# D1 recommendation_runs — one-person, two-step guarded migration (2026-10-24)

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
