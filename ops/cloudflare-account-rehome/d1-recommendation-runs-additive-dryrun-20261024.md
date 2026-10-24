# D1 recommendation_runs — guarded additive copy rehearsal (2026-10-24)

**State: OFFLINE_REHEARSAL_IMPLEMENTED / SOURCE+TARGET READ-ONLY WORKFLOW PREPARED / ZERO TARGET WRITES / NO CUTOVER.**

Authenticated [live pilot #40089305352](https://github.com/louisalviss/runner-3/actions/runs/40089305352) observed **47 source rows, 35 target rows, 12 source-only keys, 35 byte-typed-payload-matching existing rows**, no target-only rows and no changed payloads. This observation is a previous capture, not current proof; source writes continue.

## Actual advancement after the pilot

`scripts/cloudflare_d1_recommendation_runs_dryrun.py` is a **concrete rehearsal of the missing-row migration**, not merely another COUNT or schema report. It uses the same tightly scoped read-only D1 API calls as the verified pilot, but adds:

- A strict 8-column SQLite affinity + `render_id` PK gate; bounded 250 source/target rows, at most 50 missing.
- Two repeated source/target snapshots and exact typed content comparisons. Abort on source/target changes during the read window, duplicate keys, conflicts for existing keys, unexplained target-only keys or unexpected SQL types.
- Reconstruct existing target rows in isolated in-memory SQLite; insert only source-missing rows **into that scratch database**, validate each newly inserted row by key+typed-payload readback, verify all original target rows remain unmodified, then verify complete scratch state against the source.
- Export only counts + hold/ready booleans. Raw keys, record bodies and hashes remain in process memory.
- **No target D1 write code, no target write token, no R2, no Worker deploy, no route/cron.** Even `ADDITIVE_REHEARSAL_PASS_NOT_AUTHORIZED` explicitly means **not approved to write**.

The standalone workflow `.github/workflows/cloudflare-d1-recommendation-runs-additive-dryrun.yml` is **manual dispatch only**. It uses separately configured source and target *read-only* tokens, runs offline regression tests and uploads a one-day sanitized counts-only artifact. PR CI also runs synthetic tests with no secrets.

## Separate authorization still required for actual copy

Passing a scratch rehearsal **does not mean the 12 keys are still missing now**. A real copy requires a fresh preflight, a separately configured *target D1 Write* permission, reviewed bounded `INSERT` operations, explicit source-authority and conflict behavior, a verified target snapshot/rollback procedure, per-row readback and subsequent source-writer catch-up. Do not re-use either audit token for writes. The Cloudflare D1 query API supports parameterized statements but this workflow deliberately sends only read-only SQL.

**Other gates remain:** the 39/39 source-only DDL is recovered, not yet applied to target; other D1 tables require row parity, target Workers are not verified, and R2 remains `COST_HOLD rev28`. Source stays production authority. No source cleanup or production cutover.
