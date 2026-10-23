# Runner3 Core — target account staging candidate (2026-10-23)

**STATUS: PREPARED_OFFLINE / NOT_DEPLOYABLE / NO_CUTOVER / ZERO_CLOUDFLARE_WRITES**

This is the first explicit target Worker dependency handoff for the Cloudflare account migration. It does not represent target service activation.

## Authenticated new target evidence — October 23, 2026

[Target read-only inventory #39893435140](https://github.com/louisalviss/runner-3/actions/runs/39893435140) has now confirmed **all 9 target D1 name+UUID identities match** the historical target map. The target has eight canonical named D1s and preserves target-only `louis-context-index`; isolated source-only `clm-copilot-calibration` does not appear in target. Sanitized artifact ID `12475319253` (archive SHA-256 `8ad3426e515adac48875e43a00a5a717f3d5daa4c94e706132e1542b8d240010`). Recorded in `staging/target-d1-live-id-evidence-20261023.json`.

**Eight source Worker D1 binding names now have verified live target UUID candidate identities** across six unique databases. This does not verify underlying D1 schema or row equality. Target Workers remain unresolved: `/workers/scripts` returned zero while the alternative endpoint could not be queried successfully, and the six-Worker historical snapshot conflicts with an empty list. Do not promote an empty list to proof of zero Workers, deploy a duplicate service, or enable target crons.
 The authoritative live production source remains account `ducduy2411`; target `louisalviss3` is not yet promoted.

## What is prepared

The source Worker `cloudflare/runner3-core/wrangler.jsonc` has **8 D1 binding names mapped to 6 unique D1 authorities**, 2 R2 buckets, 1 service binding and the hourly cron `17 * * * *`. The historical target UUID candidate source is `ops/cloudflare-account-rehome/runner3-core-target-d1-binding-draft-2026-10-16.json`; the UUIDs were first observed 2026-10-08 and **all 9 have now been reconfirmed** by the independent target read-only inventory #39893435140.

Artifacts:
- `staging/runner3-core-target-stage-plan.json`: explicit source→target D1 binding map, candidate-only target UUIDs, alias preservation, cron/R2/service disabled and every cutover blocker false.
- `scripts/cloudflare_runner3_target_stage_plan.py`: standard-library offline check `--check` compares that committed plan against the exact current Worker source config and historical target lookup; fail-closed on identity or source-origin drift.
- `scripts/tests/test_cloudflare_runner3_target_stage_plan.py`: synthetic-only regression tests.
- `.github/workflows/cloudflare-runner3-target-stage-offline-ci.yml`: PR-only, contents-read CI; no Cloudflare credentials and **no deployment**.

## Operational decisions

1. Keep `runner3-core` **source production authority**. Do not change DNS/routes, traffic or sources until data and service cutover gates pass.
2. Preserve six physical target candidate D1s rather than creating duplicates or modifying account inventory. The 2026-10-23 target inventory independently reconfirms all 9 UUIDs, but not table schema or row parity. Existing live D1 audit confirmed 9 databases by name on each side, but it did not release row/schema object parity.
3. **Do not activate** the candidate Worker `runner3-core-migration-preview`, because source-backed Core tables (12 in source) are still absent from target per latest schema audit; this plan is **intentionally not a `wrangler.jsonc`** and contains no executable deployment invocation.
4. No cron enabled in staging; never duplicate source scheduled tasks. The source Worker origin `runner3-core.ducduy2411.workers.dev` is deliberately not copied as a target runtime var.
5. No R2 `ARTIFACTS`/`AUDIO_MEDIA` requests or service `RSS_FASTLANE` binding activation; those depend on independent parity and R2 `COST_HOLD rev28`.
6. No auth material is transferred, displayed or copied by this plan. `RUNNER3_CORE_WRITE_AUTH` stays a production auth requirement, not a deployable placeholder secret.
7. The remaining two unknown Content Intelligence schema objects and source key/delete parity are unchanged. Do not replay the old destructive 26-file Core SQL migration chain.

## Narrow critical path after this PR

- **D1 source applied DDL (highest-priority remaining data gate):** obtain the exact current applied table/index/trigger metadata by an authorized secret-safe channel. Create a reviewed additive-only target schema set **for the 12 Core tables first**, and the missing CI tables separately; no automatic bulk writes.
- **Source/target snapshot:** obtain bounded consistent key+HMAC payload manifests under the existing read-only account scope. An offline comparator already exists at `scripts/cloudflare_d1_keyed_parity_offline.py`, but there is still no live row parity evidence.
- **Data copy and reconcile:** only after source/target content and delete/conflict policy are explicit; preserve auth, mailbox, target-only rows and service idempotency.
- **Worker readiness:** compare code, settings, encrypted secret references, bindings, service dependencies and cron. Only then produce a real target `wrangler` config on a review branch; validate via non-public smoke before cutover.
- **R2:** continue COST_HOLD independently until provider billing and residual PUT origin is resolved. R2 is not a reason to rerun D1 audits or to allow early source retirement.

**Execution in repo:** `python3 scripts/cloudflare_runner3_target_stage_plan.py --check`. This validates plan consistency only; **not** live Cloudflare identity, data safety, target deployment or cutover. No R2, D1 or Worker API calls.
