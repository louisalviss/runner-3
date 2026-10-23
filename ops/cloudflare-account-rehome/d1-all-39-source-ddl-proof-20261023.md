# D1 39/39 source DDL proof → private staging candidate (2026-10-23)

**Milestone: all 39 source-only schema objects in the two discrepant D1 databases have been identified and verified against the authenticated source fingerprints. This is schema readiness only, not actual target schema deployment or row parity.**

## Live authorized evidence — SUCCESS

Manual workflow [#39987228477](https://github.com/louisalviss/runner-3/actions/runs/39987228477) on pinned main commit `c1a46d4eebe5f0c3c43666aef5d2bda0f0b808f8` completed successfully. Source-only schema extraction queried only two source D1 databases, using **six metadata queries total**, and reported `SOURCE_SCHEMA_GAP_PROOF 6/6 METADATA_MATCH no_rows no_d1_writes no_r2`. Artifact `d1-six-source-ddl-private-review` ID **12515444248**, exact ZIP SHA-256 `7a3e2ce1ea57c26b6e0aee22f037c9ac4617ed3ad3839a88e6dfbbf7786a7a0d`, expires **2026-10-24T16:29:51Z**.

I independently opened the downloaded ZIP and replayed each of the six CREATE statements in an **isolated local in-memory SQLite database**, then independently recomputed its complete `sqlite_master` SQL + `PRAGMA table_xinfo` metadata fingerprint. **6/6 match**. The applied DDL is not copied into this repository, issue comments, or CI logs.

Identified remaining source-only objects:
- `runner3-core`: the three tables `typed_kv`, `r2_receipts`, `d1_migrations`.
- `runner3-content-intelligence`: `link_interest_events` table and the two previously unknown indexes **`idx_link_interest_platform`** and **`idx_link_interest_sent_at`**.

Together with the previously approved offline source-matched candidates `runner3-core-additive-proven-18.sql` and `content-intelligence-additive-proven-15.sql`, this establishes **Core 21/21 and Content Intelligence 18/18** *exact source-applied DDL objects identified*.

## Security-preserving staging assembly

Tool `scripts/cloudflare_d1_final_39_private_bundle.py` accepts **only the exact original artifact ZIP SHA** and verifies source ID, six object identities, all metadata hashes, zero D1/R2 writes, and a complete six-object census; then it compiles all six DDL definitions in SQLite scratch memory. It regenerates the **other 33** from repository code with their independent SHA source checks. Only then does it create two private SQL review files, one per database, with restrictive directory/file permissions.

Run from the `runner-3` checkout **on a trusted local machine** after downloading the original restricted Actions artifact, before its expiration:

```bash
umask 077
python3 scripts/cloudflare_d1_final_39_private_bundle.py \
  --artifact /secure/local/d1-six-source-ddl-run-39987228477.zip \
  --outdir /secure/local/d1-39-review
```

Files emitted with no overwrite permitted:
- `runner3-core-source-matched-21.REVIEW.sql`
- `runner3-content-intelligence-source-matched-18.REVIEW.sql`

These contain operational applied DDL and are **private**. Do not upload the actual six source DDL to public GitHub or issue/PR text, and do not post them into an unrestricted CI artifact. The generator itself is generic and contains **no raw six-source DDL**.

## Actual migration requirements still open

1. **Fresh live target `sqlite_master` preflight immediately before any apply.** The Oct 22 target snapshot is not proof of current state. Existing target tables/indexes must not be overwritten or silently accepted with `IF NOT EXISTS`.
2. Review precise dependency order and target same-name/unique constraints. Adding a unique event index or trigger against existing target rows can fail or alter behavior. This helper does not apply a single statement to target D1.
3. Obtain separately authorized controlled target **schema write** and validate every resulting DDL + PK fingerprint (not merely 39 statements executed).
4. Reconcile **actual rows/keyed values**, immutable idempotency IDs, target-only rows, deletions/tombstones, and source writer catch-up. The already prepared bounded read-only `recommendation_runs` pilot has not yet been manually dispatched.
5. Complete Workers, service bindings, secrets/cron safety, rollback and separate **R2 COST_HOLD rev28** release. Do not enable duplicate cron or retire source production yet.

**Explicit status:** `source_ddl_objects_identified=39/39`, `source_d1_writes=0`, `target_d1_writes=0`, `r2_requests=0`, `worker_deploys=0`, `row_parity_verified=false`, `cutover_ready=false`. Whole-account D1 migration is **not complete** merely because this two-database schema DDL set is fully reconstructed.
