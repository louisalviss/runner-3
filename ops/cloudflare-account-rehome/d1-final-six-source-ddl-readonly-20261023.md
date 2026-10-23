# D1 Final Six: Applied DDL read-only provenance (2026-10-23)

**Status: MANUAL SOURCE-ONLY CAPTURE READY / NOT RUN / NO PRODUCTION D1 WRITE.**

The existing source↔target schema fingerprint receipt [run #39826582807](https://github.com/louisalviss/runner-3/actions/runs/39826582807) yielded 39 source-only objects in `runner3-core` and `runner3-content-intelligence`. **33/39** now have exact source metadata-matched, offline-reviewed additive CREATE DDL staging candidates. Six still lack a *source DDL-matched* candidate:

| D1 | Unresolved object identity |
| --- | --- |
| `runner3-core` | `typed_kv`, `r2_receipts`, `d1_migrations` — actual current `CREATE TABLE` and column/PK declarations needed |
| `runner3-content-intelligence` | `link_interest_events`, and two anonymous source-only object IDs (`051949606d6f5fa…`, `7217ecdaa220de7…`) |

These six objects' **opaque exact identity fingerprints and full schema metadata digests** are pinned in `scripts/cloudflare_d1_final_six_source_ddl.py` and originate from the already-authenticated source digest receipt artifact 12447225966, paired with the target-absent digest artifact 12447330783. This does not require access to the courier private key. Never reproduce DDL by guessing from application SQL SELECT/INSERT column names.

## Authorized next action (manual only)

Run exactly [Cloudflare D1 Final Six Applied DDL (Source Read Only)](https://github.com/louisalviss/runner-3/actions/workflows/cloudflare-d1-final-six-source-ddl-readonly.yml) from `main` **only after offline CI passes**. This workflow is **not** triggered by pushes, merges, schedules or another workflow.

The job uses the already configured source-scoped `CLOUDFLARE_API_TOKEN` and verifies `CLOUDFLARE_ACCOUNT_ID` is the known source account. It performs at most **12** read-only D1 SQL calls across exactly two pinned source database UUIDs. Allowed statements are `SELECT type,name,sql FROM sqlite_master ...` and `PRAGMA table_xinfo(...)` for selected tables, never `SELECT *` from application tables, `INSERT`, `UPDATE`, `DELETE`, `CREATE`, `DROP` or R2 commands.

Only six exact historical SOURCE-only object hashes may be emitted. Before writing its receipt, every selected object must match its original *whole schema metadata digest*: type/name identity, exact DDL hash and (if table) columns, nullability, default values, primary-key column order. A missing/extra/changed identity or digest fails closed; it must not be silently accepted as a new schema. This is a **freshness check** on six objects, not a source/target parity check.

Output is a **restricted, short-lived Actions artifact** holding six applied CREATE definitions. Although it contains no application rows, schema itself is operational information; avoid pasting the artifact into public issues, PR comments or chats. Artifact retention is **1 day**. GH job logs print only 6/6 PASS and counts; no tokens, row values, SQL statement contents, private keys or full source API responses.

## After capture

1. Review the applied `sqlite_master.sql` for all six objects including `FOREIGN KEY`, `UNIQUE`, `CHECK`, triggers, dependency sequencing and `PRAGMA table_xinfo`; ensure no unexpected side effects.
2. Generate **a new candidate staging file** from the artifact with exact DDL, with no R2 calls and **no automatic SQL apply**.
3. Reconfirm target current schema and account metadata before choosing which objects to create. `IF NOT EXISTS` does not guarantee parity.
4. Row key/value and source deletion treatment, Writer quiescence, Worker secrets/service bindings/cron, rollback and R2 `COST_HOLD rev28` are independent gates. Source production remains authoritative.

**No cutover ready claim:** `source_d1_writes=0`, `target_d1_queries=0`, `target_d1_writes=0`, `r2_requests=0`, `row_parity_verified=false`, `cutover_ready=false`. Source DDL fingerprint proof does **not** copy a single row. The separate `recommendation_runs` bounded keyed-row read-only workflow is already installed but has not yet been manually dispatched.
