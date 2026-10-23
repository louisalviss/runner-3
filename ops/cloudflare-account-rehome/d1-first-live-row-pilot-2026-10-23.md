# First live D1 keyed-row pilot — recommendation_runs (2026-10-23)

**Scope:** manual, read-only, 1 table in 1 database on each account.
**Not a migration:** no SQL writes, no data copy, no Worker, cron, source export, or R2.

This is the first operational source-versus-target **row-content** audit, not
another nine-D1 schema scan. Existing credentials are separately installed:
`CLOUDFLARE_API_TOKEN` for source and `CLOUDFLARE_TARGET_AUDIT_TOKEN`
for destination. The relevant D1 query endpoint accepts a `D1 Read` token:
<https://developers.cloudflare.com/api/resources/d1/subresources/database/methods/query/>.

Chosen table: `runner3-content-intelligence.recommendation_runs`.
Production source and live-confirmed target UUIDs are pinned in the script.
Its checked-in DDL declares `render_id TEXT PRIMARY KEY` and eight
columns; historical Oct 8 records listed 35 rows per side, but **that
snapshot is stale** and no present-day parity is assumed.

## Guardrails

- Only two hard-coded SQL statements: `PRAGMA table_xinfo("recommendation_runs")`
  and bounded `SELECT` of all eight named columns, ordered by render_id,
  `LIMIT 251`. Reject 251 rows; maximum accepted 250. No broad DB scanning.
- Verify identical live column metadata and actual PK declarations before row reads.
- Read source, target, source again, target again. Reject stable parity assertions
  if either changes during this check. The reads are **not atomic across accounts**;
  a PASS does not prove cutover-safe final data parity.
- Generate an ephemeral HMAC key **inside the workflow process**. HMAC domain-
  separate key fingerprints from complete typed-payload fingerprints. Never
  persist or print the ephemeral key, raw primary keys, row bodies, or HMAC maps.
  Tokens never enter the artifact. Any unsupported SQL type fails closed.
- Emit only counts: source-only keys, target-only unresolved keys, changed
  payloads, matching rows, source/target within-probe stability and schema
  equality. `target_only` is not evidence of deletion from source.
- Safety limits: each response <= 1.5 MB, total <= 4 row queries plus two
  metadata queries; no R2 requests, D1 writes, or Worker deployment.
- Privacy: GitHub artifact contains only a sanitized summary JSON with no
  content values or key identifiers; 1-day retention. Python exception messages
  from API responses are suppressed.
- Output always has `cutover_ready: false` and
  `row_parity_verified_all_d1: false`, even if the pilot rows all match.

## Execution

After PR review and merge, manually dispatch exactly this workflow:
`.github/workflows/cloudflare-d1-first-live-row-parity.yml`.
Its offline preflight is checked by pull-request CI, and run-time secrets
are read only by the manually dispatched job.

One successful test shows whether the prescribed path can measure **real**
row diffs without exposing data or accidentally modifying production. Next
step would be to extend the same bounded, authorized approach table-by-table
with distinct delete/retention policies and a fully reviewed migration action.

**Other gates remain:** 37/39 CI schema identities, 12 absent target Core
tables, no whole-D1 keyed parity, Worker inventory unknown because API
census disagrees, R2 `COST_HOLD rev28`, source still authoritative.
This probe cannot promote or delete resources.
