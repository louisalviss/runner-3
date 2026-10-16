# Cloudflare R2 scheduled jobs billing HOLD hardening — 2026-10-16

**Status: LIVE_GITHUB_ACTIONS_HOLD_ADMISSION_PASS / NO R2 REQUESTS IN ACCEPTANCE RUNS / NOT AN ACCOUNT-WIDE CLASS-A FIREWALL.**

Cloudflare source account `ducduy2411` remains production; target `louisalviss3` not cut over. Canonical Dropbox incident `/Task/active/CLOUDFLARE-R2-COST-001.md` last observed **rev13**, `VERIFYING`, source PUT provenance/billing feed unresolved; `COST_HOLD` remains active. Assistant did not query Cloudflare R2 objects, copy/migrate, delete, enable cron or redeploy Core.

## Discovered unguarded scheduled R2 paths

| Workflow | Trigger | R2 source-code proof | Prior run evidence |
|---|---|---|---|
| `runner3-artifact-test-cleanup.yml` | `23 * * * *` | Core `/artifact-cleanup-tests` invokes `env.ARTIFACTS.list()`, optionally `env.ARTIFACTS.delete()`; also `/artifact-list` | Runs 38817295138 and 38792318067 SUCCESS, `deleted_count=0` but LIST still invoked |
| `reader-r2-catalog-enrich.yml` | `23 3 * * *` | `scripts/enrich_reader_r2_catalog.py` uses Cloudflare REST R2 object LIST/GET/PUT | [run 38705687812](https://github.com/louisalviss/runner-3/actions/runs/38705687812) listed 19 EPUB and emitted pre-enrich catalog backup, 19 books/17 covers |
| `audio-library-chatgpt-inbox.yml` | `*/5 * * * *` | `scripts/audio_library_extract_for_chatgpt_r2.py` invokes `audio_media_core.list_objects()` using Core `/audio-media` path, then GETs item JSON | Scheduled runs exist; request-level billable operation count **not quantified** |
| `audio-library-chatgpt-packets.yml` | `*/5 * * * *` | `scripts/audio_library_extract_packets_for_chatgpt.py` may GET Core `/audio-media/...json` per status item | Scheduled runs exist; **not proof** that every empty run issued R2 request |

These are independent from the previously hardened seven **manual** R2 migration workflows. Scheduled work may produce Class A even if no files were deleted or added. **None is established as the historical residual 23–29 PUT per 15 minutes**. Do not change other production jobs absent evidence.

## Implemented admission and proof

1. Existing migration HOLD gate `ops/cloudflare-account-rehome/r2-migration-operation-gate.json` remained `status=HOLD` / `permit_r2_migration=false`.
2. Added `ops/cloudflare-account-rehome/r2-scheduled-jobs-policy.json` commit `9e940a12032b45a0c8e8eaa71f195d733907f264`: separate pin of source+target IDs, `status=HOLD`, `permit_scheduled_r2_jobs=false`, all four job flags false. **Explicit per-job permission is required even if the general R2 migration policy is later released.**
3. Added `scripts/cloudflare_r2_scheduled_job_gate.py` commit `82927fe48e0e3299e549841d1332f8d135907b02`: offline, fails closed unless both general and scheduled policies are USER_APPROVED and the specific scheduled job is flagged true. No environment fallback, Cloudflare calls or secret logging.
4. Added tests `scripts/tests/test_cloudflare_r2_scheduled_job_gate.py` commit `f5fa14fb0a3c965c87fdb913f8a9656b9d760706`. Actually executed on VPS in temporary offline directory, isolated from Cloudflare credentials: compile exit0, synthetic regression exit0, current policy CLI expected exit3. PASS that general migration release **alone** does not activate scheduled jobs.
5. Changed four workflows to call the separate job gate before any Core/R2 endpoint:
    - R2 test cleanup: initial HOLD gate commit `be28e37dc226124d815132087359d98f3bb41c8c`, independent policy update `fc94d4b4cb18090f2cf3384bddbbb939b1b2a772`.
    - Reader R2 Catalog Enrich: initial HOLD gate `5cc5dc9b536f1f382a4046f9b47c4a8b7739b603`, independent update `836ae2ecdfc6981496517cc634b0fa96360262a1`.
    - Audio Library ChatGPT Source Inbox: initial HOLD gate `31bb4bec1581e0814a0ee27d8e695d5a9260b3db`, independent update `be34c916af86c155eb24c571a091094a2a2b6e0a`. Under HOLD, both Core audio-media polling and GitHub inbox status publication are **skipped**; no false status churn or source data deletion.
    - Audio Library ChatGPT Source Packets: initial HOLD gate `08bcc1d98ee50d28cd7751364d22a7bd735da941`, independent update `46201f8dc6c5cb804f5ea1f4b6eee862a3d7ca4d`. Under HOLD, no Core item GET, packet construction, or GitHub publication.

## Live GitHub Actions acceptance — independent gate on current main

| Workflow | Run | Admission | Core/R2 step | Result |
|---|---|---|---|---|
| R2 cleanup | [38829579761](https://github.com/louisalviss/runner-3/actions/runs/38829579761) | SUCCESS | SKIPPED | SUCCESS |
| Reader catalog | [38829596012](https://github.com/louisalviss/runner-3/actions/runs/38829596012) | SUCCESS | SKIPPED | SUCCESS |
| Audio inbox | [38829613414](https://github.com/louisalviss/runner-3/actions/runs/38829613414) | SUCCESS | SKIPPED | SUCCESS |
| Audio packets | [38829631047](https://github.com/louisalviss/runner-3/actions/runs/38829631047) | SUCCESS | SKIPPED | SUCCESS |

All four run metadata and job step conclusions fetched/read back through authenticated GitHub. No manual dispatch to R2, no Cloudflare API calls in these accepted paths. These workflow-level admission tests do not prove every Cloudflare action of unrelated Workers/VPS/jobs is stopped. The R2 Cost incident remains separately owned and unresolved.

**Operational impact:** While HOLD remains, automatic EPUB catalog enrichment, scheduled Audio Library source Inbox/Packets, and test artifact cleanup are paused. Existing persisted data and source account production Worker are unchanged. **Release requires both independent policies and explicit per-job approval; do not silently resume every scheduled job as a side-effect of authorizing a one-time R2 migration.**

**Next:** Continue evidence-based audit of other scheduled R2 access; attribute residual PUT from provider-side analytics/complete Data Access Logs via authorized access; only then consider separately approved selective release. Whole-account D1/Workers/R2 migration still incomplete.
