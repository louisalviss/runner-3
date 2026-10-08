# Cloudflare Workers source-account consolidation: prune review
Checkpoint: 2026-10-09 VN | Status: INVENTORY_INCOMPLETE / NO_DELETIONS

## User decision
- New domain has **NOT** been purchased; domain setup excluded.
- Migrate retained data/essential runtimes to target `Louisalviss3` (account `748a80810f77f447ee476543ef0e5014`).
- In source `Ducduy2411` (`7415a87f6bce7884e73ad7cfed5782df`), delete **only proven-unused** Workers rather than carrying all historical previews/probes to target.
- Never delete D1 or R2 data as a side effect of Worker cleanup. Preserve backup, rollback and source application while data parity/cutover incomplete.

## Actual evidence (not a complete Cloudflare Worker list)
- Source Worker count **36** via authenticated Cloudflare API snapshot 2026-10-08 ~06:16 VN, but Worker IDs/full list, routes, schedules and requests are **not** stored in a complete up-to-date report.
- Target snapshot **6** Workers (previously reported, not independently refreshed in this check):
  `balatro-clef-api`, `khotruyen-worker`, `runner3-x-fast-direct`, `runner5-restore-proxy`, `volamidle-rogue`, `wave-rider-scanner`.
  Target already having a same-named Worker does not establish source no longer serves traffic.
- The connected SentinelX Cloudflare-integration registry returned **zero** saved Cloudflare integrations; direct zone-level inventory is unavailable there.
- GitHub canonical runner-3 source and VPS local read-only repo searches show live/configured references to:
  - `runner3-core` — many independent repository and host environment references; **PROTECT / MIGRATE**.
  - `runner3-audio-library` — deployment/browser probe references; **PROTECT pending live traffic check**.
  - `runner3-autocontent-ai` — script and workflow references; **PROTECT pending live traffic check**.
  - `clm-conversation-copilot-api` — D1 CLM healthy HTTP 200 in canonical D1 final checkpoint; **PROTECT**.
  - `wordpress-edge-proxy`, `wordpress-edge-proxy-v2` — WordPress asset and PageSpeed workflows; **PROTECT pending redirect/usage comparison**.
  - `runner3-wp-control` — WP plugin control/install workflow; **PROTECT pending endpoint check**.
  - `runner3-direct-download` — direct R2 publish workflow; **PROTECT pending usage check**.
  - `runner5-restore-proxy` — deployment workflow and previous target Workers snapshot; **PROTECT pending source dependency review**.
  - `vbth-free-editorial-ai` — VPS environment references; **PROTECT pending service liveness review**.
- Old test/preview URLs referenced only by historical workflow smoke tests:
  `runner3-core-reader-v33-preview`, `runner3-core-reader-v34-preview`, `runner3-core-reader-v35-preview`.
  These are **CANDIDATE_REVIEW**, **NOT VERIFIED UNUSED**; they may not exist now, may have routes/cron/service bindings, and cannot yet be deleted.
- Unknown remainder: source Worker list not fully enumerated. Do not invent the other names.

## Safe classification gates
For each exact source Worker, independently collect:
1. Exact Worker ID, account, version/deployment and routes/workers.dev exposure.
2. 30-day request/invocation volume, cron schedules and external event/Queue consumers. Zero HTTP requests does NOT prove zero cron or service-to-service consumers.
3. Service bindings, Durable Objects and any other Worker references; any reference or missing evidence = KEEP.
4. Search active GitHub deployment manifests, VPS configured services/jobs, worker-to-worker calls and connected applications.
5. Export restorable Worker source/configuration/secrets **references** to controlled backup. Never print or copy plaintext secrets into GitHub/Dropbox/logs. Explicitly verify restoration instructions/source hash.
6. If and only if all dependency/traffic/consumer checks are PASS and source backup verified, mark `DELETE_ELIGIBLE`.
7. Deletion must target source account only and MUST NOT use `force=true`. Cloudflare documents that force-delete can break dependent service bindings and delete referenced Durable Object namespaces.
8. After deletion, verify Worker absent plus all retained endpoints, cron pipelines and source production smoke healthy. If uncertainty, halt without deleting further scripts.

## Source data gate / deployment order
- WP Media R2 auto-small GitHub run [37824948164](https://github.com/louisalviss/runner-3/actions/runs/37824948164) was still IN_PROGRESS at last read; no final receipt at this review.
- Full R2 (historical 10 buckets ~5.59 GB) and D1 schema+row/delta parity to `Louisalviss3` still incomplete. Source R2 and D1 must not be deleted.
- D1 domain-isolation task is already closed: canonical `ops/cloudflare-capability/d1-domain-isolation.json` / `ops/checkpoints/d1-domain-isolation-2026-10-08-0503-VN-FINAL.md`. Do not resurrect retired Reddit D1, force CLM into R2, or replay Ebook migration.
- Move only required Workers to target, with secrets/bindings created for target account and end-to-end smoke tests, before source traffic switches.
- Keep unused/unknown scripts on source until restored code, no-traffic + no-reference evidence and safe deletion gates exist. **None are currently DELETE_ELIGIBLE.**

## Tool and authorization status
- Native Github connector supports repository writes and reading Actions logs but no direct workflow_dispatch.
- Assistant-originated migration dispatch via another execution surface previously hit security enforcement. Do not circumvent using push, alternate agent/DHS, scheduler, or renamed steps.
- The current checkpoint documents classification and allows future cleanup execution only through a permitted, directly authorized Cloudflare account operation. User need not repeatedly run per-Worker/batch actions.

## Reference
- Canonical migration checkpoint `ops/checkpoints/cloudflare-account-migration-2026-10-08.md`
- Cloudflare API: `GET /accounts/{account_id}/workers/scripts`
- Cloudflare Worker metrics: aggregate request/invocation counts; absence of traffic alone insufficient
- Cloudflare API: `DELETE /accounts/{account_id}/workers/scripts/{script_name}` (**no force**)
