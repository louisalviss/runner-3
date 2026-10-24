# D1 recommendation_runs — one-person, two-step guarded migration (2026-10-24)

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

## Additional non-negotiable prerequisites before any real INSERT

- Three distinct tokens: source read-only `CLOUDFLARE_API_TOKEN`, target read-only `CLOUDFLARE_TARGET_AUDIT_TOKEN`, and separately provisioned target-account D1 Write token `CLOUDFLARE_TARGET_D1_WRITE_TOKEN`. The write token must be permission-scope restricted to the target account/database as supported. Never repurpose an audit token.
- Private, securely preserved **fresh target Time Travel bookmark** set as GitHub repository secret `CLOUDFLARE_TARGET_PREAPPLY_BOOKMARK`. Its exact value must match the target's *current* bookmark immediately before any INSERT. The old audit stored only a bookmark hash and is **not a rollback point**.
- **Target writers truly paused** and a **tested row-safe recovery plan**. Time Travel restore overwrites the **entire target D1 database**, including unrelated concurrent changes. No automatic restore is permitted.
- Read-only real preflight still shows exactly 12 source-only `recommendation_runs` rows, 35 matching existing target rows, no target-only keys, no differing typed payloads, same schema. If the delta changes, block and review; do not blindly replay 12.
- Ordinary parameter-bound `INSERT` only on the hardcoded D1 target UUID. Each insert must be read back, previously present target rows preserved, source and target re-read after the batch. Any unexpected write/connection error may leave a **partial 12-row append**; stop, never auto-delete or rerun, reconcile with a read-only audit. If SQLite REAL affinity changes typed representation, the writer explicitly records strict parity as **HOLD**, not a false 1:1 claim.

**As of this commit:** No separately approved target write credentials, private bookmark, paused writers or recovery rehearsals have been verified. **Do NOT dispatch Step B now**. Complete these gates first. R2 `COST_HOLD rev28`, source production and all other D1/Workers parity checks remain in force.

## Evidence

- [First live row audit #40089305352](https://github.com/louisalviss/runner-3/actions/runs/40089305352): 47 source, 35 target, 35 exact matching pairs, 12 source-only.
- [Authenticated additive dry-run #40091169404](https://github.com/louisalviss/runner-3/actions/runs/40091169404): scratch-only 12-row INSERT+readback passed, no target writes.
- [Target Time Travel capability #40092563094](https://github.com/louisalviss/runner-3/actions/runs/40092563094): production backend and bookmark API confirmed, raw bookmark **not preserved**.

**State:** `target_d1_writes=0`; `r2_requests=0`; `source_authoritative=true`; `row_rollback_ready=false`; `full_cutover_ready=false`.
