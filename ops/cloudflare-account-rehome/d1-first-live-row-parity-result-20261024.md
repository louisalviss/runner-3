# First authenticated live D1 row comparison — recommendation_runs (2026-10-24)

**Result: ROW_DIFFERENCES_HOLD. Live source and target were read, but not modified.**

Authoritative manual [run #40089305352](https://github.com/louisalviss/runner-3/actions/runs/40089305352), commit `abdd09690ab7b78728e1a0cfc0c8fdc55b44a928`, completed **SUCCESS**. It used both Cloudflare accounts' separate read-only token scopes, 20 offline privacy tests, a temporary in-process HMAC key, and two repeated bounded observations per account. GitHub artifact #12557794996, ZIP SHA-256 `872152970aac9f5c47c016294f0306004c24c47b403d503bcc7c5a8e4f213d58`, expires 2026-10-25 11:17:38Z. The immutable sanitized receipt is checked into `staging/d1-recommendation-runs-live-parity-20261024.json` so its aggregate finding persists beyond artifact expiry.

| runner3-content-intelligence.recommendation_runs | Observed result |
|---|---:|
| Source rows | **47** |
| Target rows | **35** |
| Same primary key + complete typed payload | **35** |
| Source-only keys | **12** |
| Target-only keys | **0** |
| Matching keys with divergent payload | **0** |
| Within-probe source/target stable | **both true** |
| Column metadata / PK equal | **true** |
| Rows written / R2 operations | **0 / 0** |

**Interpretation:** the target is a matching subset of source for this **one table at the observation time**; it is not full-table final parity for all D1 and not an atomic cross-account snapshot. No raw rows, keys, HMAC digests, tokens or secrets are exposed in the saved receipt.

## Next actionable migration lane: reconcile twelve missing rows

The next step is **a separately reviewed and authorized, bounded, target-only 12-row additive copy**, not another repeat of the same read-only pilot. Before the first write, re-read both sides and require exact schema/PK correspondence and a fresh key+payload diff. Preserve all target-existing rows; require unchanged target payloads for every common primary key. Restrict an apply to the `recommendation_runs` eight permitted columns with parameter-bound values; never use `REPLACE`, `DELETE`, `DROP`, table truncate, blind bulk restore, or source D1 mutations. An idempotent conflict policy must **abort** on any same-key payload disagreement rather than silently overwrite or ignore it. Perform row-by-row target readback and fresh source catch-up to identify records created since the snapshot. Rollback must be captured before any write and rehearsed, especially if target already serves traffic.

Do not export raw row bodies or keys to GitHub logs or public artifacts. Target D1 write credentials have **not** been verified or authorized for this operation. Existing D1 audit tokens are read-only by design; no attempts to reuse them for mutations.

**Status:** `schema_source_DDL_verified=39/39` in the two previously incomplete database schemas; `target_schema_applied_verified=false`; `row_parity_verified_all_d1=false`; `source_writer_still_authoritative=true`; `r2_COST_HOLD_rev28=true`; `cutover_ready=false`. Workers and R2 cannot be released by this one-table parity result.
