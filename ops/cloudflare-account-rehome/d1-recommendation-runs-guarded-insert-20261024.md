# Guarded target D1 recommendation_runs insert — deployment hold (2026-10-24)

**Status: CODE_READY_FOR_TEST / NO LIVE WRITE APPROVED OR PERFORMED / NO CUTOVER.**

## Verified prerequisites already achieved

- [Live parity run #40089305352](https://github.com/louisalviss/runner-3/actions/runs/40089305352): 47 source rows, 35 target rows, 35 matching typed payloads, 12 source-only, no target-only, no changed payloads.
- [In-memory additive rehearsal #40091169404](https://github.com/louisalviss/runner-3/actions/runs/40091169404): repeated real source/target reads, 12 missing rows passed scratch-only INSERT+readback; no target writes.
- [Time Travel eligibility #40092563094](https://github.com/louisalviss/runner-3/actions/runs/40092563094): correct target D1 UUID, `version=production`, GET bookmark PASS. **Bookmark was NOT preserved, and no rollback is approved**. Source account production continues; R2 `COST_HOLD rev28`.

## New actual bounded writer — deliberately not authorized to execute

`scripts/cloudflare_d1_recommendation_runs_guarded_insert.py` and manual workflow `.github/workflows/cloudflare-d1-recommendation-runs-guarded-insert.yml` are implemented for **this one table only**, target account and D1 UUID hardcoded. Workflow runs **only on explicit manual dispatch**. The runner refuses operation unless `--apply` plus *all* independent conditions:

1. Three distinct Cloudflare credentials: existing source `CLOUDFLARE_API_TOKEN` **read-only**, existing target `CLOUDFLARE_TARGET_AUDIT_TOKEN` **read-only**, and a **separately created target-account D1 Write** token `CLOUDFLARE_TARGET_D1_WRITE_TOKEN`. Never increase or reuse audit-token permissions.
2. A privately preserved **fresh pre-apply target Time Travel bookmark**, installed as masked GitHub **environment** secret `CLOUDFLARE_TARGET_PREAPPLY_BOOKMARK`, equal to the current bookmark fetched from the target before issuing any INSERT. The previously hashed/read-only bookmark cannot satisfy this gate. Do not paste secrets or raw bookmark into issues, chats or workflow inputs.
3. A human-reviewed operational checklist: all target writers identified/paused, a **row-safe recovery mechanism** independently rehearsed, and GitHub environment `cloudflare-target-d1-writes` configured with required reviewers. If environment protection is missing, **do not dispatch**: an environment name alone does not imply reviewer enforcement.
4. GitHub workflow inputs `approval_phrase=APPROVE_TARGET_ONLY_RECOMMENDATION_RUNS_12_INSERTS`, `target_writers_quiesced=YES`, `row_safe_recovery=YES`. Defaults are unsafe/NO. Never programmatically submit a dispatch.

### On every actual write attempt

- Re-read both D1 schemas and **four** bounded row snapshots; require exact matching 8 columns, PK metadata, all common key+typed payloads match, zero unexplained target-only rows, *exactly 12 missing*. All data stays in workflow process memory.
- Run full bounded additive SQLite in-memory rehearsal again, then match target current bookmark against privately stored pre-apply bookmark before *any* write.
- For each missing primary key: reread entire bounded target table; abort on target changes, then **ordinary parameter-bound INSERT** of one row; nullable values use literal SQL `NULL`, all other values are positional Cloudflare D1 API `params` strings. Do **not** use UPSERT, REPLACE, UPDATE, DELETE, DROP or CREATE. Fail on unique collisions rather than mask conflict.
- Require D1 API `changes=1` and verify the newly inserted row and all previously existing rows by target readback. After all 12, read source and target again; any source writer activity or drift yields a HOLD, not an unsafe cutover claim.
- No raw keys/rows, parameter values, bookmark or tokens in logs/retained artifact. Successful result contains counts only.

### Failure handling and rollback

An interrupted POST may have committed, and any mid-batch failure may leave **some additive target rows inserted**. The script **never automatically deletes** an inserted row and **never invokes Time Travel restore**. On any failure, stop and run the existing read-only parity workflow before considering a later add-only reconciliation. **Do not automatically rerun the same 12-row write**: it insists on exactly 12 source-only records and will fail after partial success.

A Time Travel restore would replace the **entire target database**, potentially destroying unrelated updates. Cloudflare Time Travel support is not by itself a safe row-level rollback. The bookmarked state and its restore authority must be protected separately; a recovery rehearsal must ensure no other target writes are lost. Cloudflare docs: https://developers.cloudflare.com/d1/reference/time-travel/ and https://developers.cloudflare.com/api/resources/d1/subresources/database/methods/query/.

## Still blocked

- Separate D1 Write credentials not verified/provisioned. No independent evidence target writers are quiesced or protected GitHub environment configured.
- Source writer changes after capture, full D1 row/deletion parity, all D1 schema apply, Worker inventory/bindings/cron and R2 cost hold are separate migration gates.
- **Do not run the new write workflow now.** Do not cut over source production.

**Recorded flags:** `live_target_rows_inserted_by_this_work=0`; `rollback_ready=false`; `source_deleted=false`; `target_write_approved=false`; `r2_requests=0`; `cutover_ready=false`.
