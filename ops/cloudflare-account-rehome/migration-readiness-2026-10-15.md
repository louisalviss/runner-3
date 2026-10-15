# Ducduy2411 → Louisalviss3 — migration readiness (2026-10-15 VN)
 
**Decision: HOLD_R2_COST / PARTIAL_ACCOUNT_PARITY.** This is a source-evidence and offline deployment-readiness assessment, **not** a production cutover or a newly executed Cloudflare account inventory. Old account `7415a87f6bce7884e73ad7cfed5782df`; target `748a80810f77f447ee476543ef0e5014`. Domain purchase explicitly deferred. Do not use percentages for unverified D1/Worker resource parity.

## Verified inventory and progress

| Domain | Old source evidence | Target proof | Interpretation |
|---|---|---|---|
| R2 | 10 buckets, 5,498 objects and 5,587,865,922 payload bytes, **as of Oct 8** | The three small buckets `clm-copilot-data` (1/1), `runner3-telegram-raw` (3/3), `runner3-telegram-bobvolman-raw` (2/2) had accepted snapshot parity. WP Media 277/285 present, 8 keys missing, one `CacheControl` mismatch, as of Oct14–15 read-only audit. Most `runner3-artifacts` and other nonempty buckets **not parity-proven** | A few exact small buckets verified, whole-account migration far from complete. Approx. 283/5,498 = 5.1% object **presence**, ~130MB/5.59GB = 2.3% byte **presence** from these known buckets, **not** full verified parity. WP alone 277/285 objects (97.2%) but 126.09/260.46 MB (48.4%). |
| D1 | 8 **canonical** business D1 authorities; newest [D1 Account Usage Watch #38662447212](https://github.com/louisalviss/runner-3/actions/runs/38662447212) on 2026-10-15T00:52Z **enumerated 9 physical databases**, including extra `clm-copilot-calibration` not named in the canonical eight. The 9 UUIDs include `runner3-core` UUID `514a2c61-...`, matching the repository's source `wrangler.jsonc` source binding. This watch's 227 rows written and projected 6,275/day is **usage**, not row-data parity | No current independently authenticated source↔target schema/row/primary-key/content checksum and final-delta proof. Old 2026-10-08 target `runner3-core` missed 12 source application tables; treat as **STALE OPEN BLOCKER**, reverify before acting | Existing `d1-domain-isolation` PASS refers **only** to internal source-account separation, NOT account-to-account migration. 9th `clm-copilot-calibration` must be explicitly retained or proven disposable based on content/owner/backups, not silently omitted. |
| Workers | All **38 old-account Workers** inventoried via authenticated [source audit #38575674555](https://github.com/louisalviss/runner-3/actions/runs/38575674555) on Oct14; **5 scheduled** source Workers, 4 callers to `runner3-rss-fastlane`. Triage from audit: **17 PROTECT**, **20 REVIEW**, **1 special service-bound PROTECT** (`runner3-rss-fastlane`). | Historic Oct8 target-side inventory mentioned **6 Worker names** only (balatro-clef-api, khotruyen-worker, runner3-x-fast-direct, runner5-restore-proxy, volamidle-rogue, wave-rider-scanner), **not refreshed** and **does not establish cross-account parity** | **0 of 38 source Workers safe to delete**. Required runtime set must be proved by traffic, cron, routes, service links, secrets and D1/R2/KV/Queue bindings; no guess from names alone. |
| Production/cutover | Old source still production authority | No accepted target end-to-end probes, routes/cron parity, delta snapshot, rollback proof | **0% cutover gates passed**, no source deletion/revocation. |
| R2 budget | Dropbox canonical `/Task/active/CLOUDFLARE-R2-COST-001.md` + source code prove Ebook/RSS empty-queue polling creates `runner3-wp-media` Class A LIST. Cost guard on 4 systemd units is active | Read-only GraphQL after stop in chat showed WP LIST **258→1→0 per 15min**, but artifacts PUT **124→23→29 per 15min**. Remaining writer not attributed | **BILLING_HOLD remains**, do not run existing `Cloudflare WP EXPLICIT Repair + Complete` or other R2 copy, HEAD, LIST, PUT jobs until cost review and user explicit approval. |

## Nine physically observed source D1 databases

The **eight canonical** physical D1 stores are:
1. `runner3-core` (control plane; 12 application tables in source checkpoint)
2. `runner3-opportunity-radar`
3. `personal-library` (Ebook/Media Library)
4. `louis-task-context` (including `context-index` project)
5. `runner3-content-intelligence`
6. `runner3-rss`
7. `volamidle-rogue-data`
8. `clm-copilot-v1`.

**Ninth, newly reconciled** by the current D1 Account Usage Watch: `clm-copilot-calibration`. It recorded zero write rows at that 00:52Z instant, which does **not** show it has no historic state or safe-to-delete status. Treat `INVENTORY_EXTRA_NEEDS_RETENTION_DECISION` until current schema, row counts, dependencies, backup, and owner corroborated. Do not recreate retired `runner3-reddit` D1 or replay completed source-account D1 `domain-isolation`.

## No-cost sequencing

1. **NOW / no R2 mutation:** reconcile the 9th source D1 store; build an explicit source↔target matrix including account ID, database UUIDs, table schemas, row counts, content-digest strategy, current writer/owner, last-write checkpoint, and rollback. Source↔target D1 data parity currently unverified; no destructive `wrangler d1 migrations apply` against unknown target.
2. **NOW / no production writes:** classify all 38 source Workers, beginning with 5 cron Workers and 4 `runner3-rss-fastlane` inbound dependencies. Determine minimum target runtime and target Worker live inventory; test source/config backup ownership without exposing secrets. Current `REVIEW` is **not** `DELETE_ELIGIBLE`.
3. **COST_HOLD:** do not restart Ebook/RSS TTS or Youtube mirror, no migration copy or R2 object listing. Diagnose residual `runner3-artifacts` PUT first. Inactive service != proven zero accrual. Cloudflare dashboard may continue showing already-accrued USD 4.50.
4. **After separate approval:** migrate missing unique data and delta in measured batches under explicit R2 Class A budget. Finish WP eight objects + 14B one-key CacheControl conditional repair and full 285 key SHA+metadata parity. Prioritize remaining large `runner3-artifacts`, protect storage-specific data and metadata.
5. **After target parity:** migrate needed Workers/bindings, service/cron/config secrets (never plaintext in logs), run real target integration tests, then reversible cutover, source delta catch-up, observation period, and only lastly remove source unneeded Workers **without force=true**.
6. **No domain:** do not block on or invent a purchased domain.

### Source evidence
- `ops/cloudflare-account-rehome/r2-inventory.json` (Oct8 historical source)
- `ops/cloudflare-account-rehome/source-workers-audit-2026-10-14.md` (38 source)
- `ops/cloudflare-account-rehome/r2-billing-freeze-2026-10-15.md` and Dropbox canonical `/Task/active/CLOUDFLARE-R2-COST-001.md`
- `ops/cloudflare-capability/d1-domain-isolation.json` (old account internal migration only)
- `ops/checkpoints/cloudflare-account-migration-2026-10-08.md` (full migration tracker)
- [D1 Account Usage Watch 2026-10-15](https://github.com/louisalviss/runner-3/actions/runs/38662447212) (9 physical DB inventory/usage, not parity)


## 2026-10-15 after R2 cost report rev4 — repository-level enforced migration HOLD

- Read canonical **Dropbox `/Task/active/CLOUDFLARE-R2-COST-001.md` rev4**, updated 2026-10-15T01:54:57Z, alongside VPS `cloudflare-r2-cost-hold-handoff-rev4-20261015.json`, `cloudflare-r2-residual-put-milestone-20261015.json`, and live systemd. Current phase **COST_HOLD_POSTSTOP_RESIDUAL_PUT_UNATTRIBUTED**; source `runner3-wp-media` 258 LIST→1→0/15min, but `runner3-artifacts` persists at 23–29 PUT/15min. Root writer UNKNOWN, NOT clear to resume WP Media/copy. Four VPS held units are all inactive with `RefuseManualStart=yes` and release-marker absent; no Core/Worker cutover/Cloudflare R2 operation performed in this migration task.
- Implemented a **technical guard** to prevent accidental repeat GitHub dispatch producing billable R2 requests: `ops/cloudflare-account-rehome/r2-migration-operation-gate.json` (`status=HOLD`, `permit_r2_migration=false`, both account IDs pinned), checked by a pure-offline `scripts/cloudflare_r2_migration_gate.py`. Fail-closed if policy missing/invalid/account mismatch/hold/without explicit `status=USER_APPROVED` and `permit_r2_migration=true`. Tests staged in `scripts/tests/test_cloudflare_r2_migration_gate.py` (mock/source contract only; runtime tests NOT yet executed). No env var override of HOLD.
- Inserted checkout→offline gate **before SDK install or any R2 request** into the seven **manually-dispatched** migrations/probes: `cloudflare-wp-explicit-repair-complete.yml`, `cloudflare-r2-wp-repair-and-complete.yml`, `cloudflare-r2-native-wp-batch.yml`, `cloudflare-r2-rehome-copy.yml`, `cloudflare-r2-encrypted-courier-canary.yml`, `cloudflare-r2-native-canary.yml`, `cloudflare-r2-wp-drift-sha-readonly.yml`. Re-fetched GitHub committed YAML, all seven gate step placements confirmed after checkout and before Cloudflare R2 access; no Cloudflare endpoint was called, no workflow was dispatched. This is a **main-branch workflow-level control**, **not** a global Cloudflare R2 usage firewall across unrelated Workers/timers, older workflow revisions or branches.
- Checked GitHub Actions **secret NAMES ONLY** (never values) for `louisalviss/runner-3`. Available `CLOUDFLARE_ACCOUNT_ID`, `CLOUDFLARE_API_TOKEN`, target `CLOUDFLARE_TARGET_R2_ACCESS_KEY_ID`/`CLOUDFLARE_TARGET_R2_SECRET_ACCESS_KEY`, and `CLOUDFLARE_WORKERS_AI_TOKEN`. No named **target Cloudflare account API token with D1+Workers read permissions** appears in this repository's secret-name inventory. The target R2 S3 credentials prove **R2 only**, not permission to enumerate target D1 or Workers. Do not assume target D1/Workers are migrated or that target account browser identity is validated. Existing source-to-target D1/Workers read-only parity must await an approved least-privilege target access route; do not bypass previously security-blocked browser/CLI credential handoffs.
- The R2 operations freeze is still binding, and Workers/D1 productive systems stay unchanged. Once the cost task explicitly reports clearance and the user authorizes a priced/capped transfer, change the policy through a reviewed GitHub commit then individually user-dispatch a bounded existing migration job. An operator must verify the new live result and restore cost policy as required. **No claim that clearance, runtime unit tests, D1 parity, Worker parity or production cutover completed now.**
