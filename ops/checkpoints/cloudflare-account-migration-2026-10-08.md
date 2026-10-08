# Cloudflare account migration — canonical checkpoint (2026-10-08 06:20 VN)

## Goal / authority
Move only necessary Cloudflare compute/storage from source `7415a87f6bce7884e73ad7cfed5782df` (Ducduy2411) into target `748a80810f77f447ee476543ef0e5014` (Louisalviss3). Preserve production, verify D1/R2/Worker parity, remove unused source resources **only after** verified cutover. This task is distinct from `d1-domain-isolation-2026-10-08-0503-VN-FINAL.md`; do not replay that completed isolation flow.

## Latest verified inventory
Source via account-scoped Cloudflare API (2026-10-08 approx. 06:16 VN):
- D1 **8**: `runner3-rss`, `clm-copilot-v1`, `volamidle-rogue-data`, `runner3-content-intelligence`, `louis-task-context`, `personal-library`, `runner3-opportunity-radar`, `runner3-core`.
- `louis-context-index` **no longer exists in source inventory**; it was present in earlier observations. Do not recreate blindly; context consolidation may be responsible.
- Workers **36**; R2 buckets **10**; DNS zones **0**. Earlier probes: Queues 0, DO namespaces 0, tunnels 0, Turnstile 0; Pages/KV permissions insufficient for a definitive source inventory.
- Source production remains the authority: no account-wide cutover confirmed.

Target via authenticated, same-browser API (no cookie export), 2026-10-08 approx. 06:18 VN:
- D1 **9** with distinct new UUIDs:
  - `runner3-core` — 0 application tables, 12,288 bytes (**NOT READY**)
  - `runner3-opportunity-radar` — 8 application tables, 204,800 bytes
  - `personal-library` — 13 application tables, 1,282,048 bytes
  - `louis-task-context` — 2 application tables, 438,272 bytes
  - `louis-context-index` — 2 application tables, 53,248 bytes (source DB retired; do not recreate)
  - `runner3-content-intelligence` — 8 application tables, 10,592,256 bytes (**parity not verified**)
  - `volamidle-rogue-data` — 2 application tables, 77,824 bytes
  - `clm-copilot-v1` — 1 application table, 241,664 bytes
  - `runner3-rss` — 13 application tables, 598,016 bytes
- Note: Cloudflare API field `num_tables` is deprecated/inaccurate. All counts above came from read-only `sqlite_master` SQL queries. Do not claim data parity from table presence or byte size; compare schema, PK/keyspace, row counts, checkpoints and recent writes.
- Workers **6**: `balatro-clef-api`, `khotruyen-worker`, `runner3-x-fast-direct`, `runner5-restore-proxy`, `volamidle-rogue`, `wave-rider-scanner`. Only `volamidle-rogue` target Worker is confirmed with target D1 binding.
- R2 **not enabled**: API HTTP 403, code 10042 `Please enable R2 through the Cloudflare Dashboard`. Cloudflare requires R2 subscription/checkout, even with free allowance.
- Pages **0**, Registrar domains **0**, DNS zones **0**; Workers subdomain `louisalviss3`.

## Current gates
1. **DO NOT re-import** the 8 populated target databases without schema+row+last-write parity. Earlier assistant wrongly inferred 8 empty from deprecated `num_tables` metadata; SQL corrected that.
2. `runner3-core` target has no application schema/data; requires deliberate source snapshot → import → validated delta catch-up during controlled cutover.
3. Source and target `runner3-content-intelligence` differ in file size and reported table counts; compare actual schemas/rows before cutover.
4. Source D1 count changed from 9 to 8 while parallel tasks ran. Always refresh inventory; do not use stale UUIDs. Attempted export of retired source `louis-context-index` correctly returned 404; no mutation made.
5. Credential boundary: do **not** extract browser cookies or API token values to scripts/logs. An old approach was blocked by security controls; use sanctioned connector/workflow session without exporting credentials. Never circumvent the block.
6. R2 target subscription must be activated before bucket migration. Do not invent payment authority or charge without explicit user approval for checkout.
7. Classify the source's 36 Workers and 10 R2 buckets as ACTIVE / LEGACY / UNUSED from bindings+traffic+consumer references; do not remove based only on age/HTTP root status.
8. For D1 export/import follow official Cloudflare API: export is polling `POST /accounts/{account_id}/d1/database/{id}/export` and import is init→upload→ingest→poll. Retain encrypted/safe source backup and verify target before any deletion.
9. Cloudflare source credentials currently only authorize source. Target is accessible via `gmail-otp-main` browser session with Super Admin. Do not leave an unrestricted persistent browser credential on VPS long term; replace post-migration with resource-scoped Ops token, revoke full browser session before acquiring domains.

## Resume point
- Verify whether any parallel migration has run since this checkpoint.
- R2 target subscription enablement is the blocking prerequisite for transferring 10 source buckets.
- Establish approved scoped target operations access, then source snapshots and table/row parity for D1, starting with `runner3-core`.
- Migrate R2 with object inventory/bytes/hash sampling and readback; redeploy only required Workers with fresh target bindings+secrets, smoke test and replay/delta gate; only then retire old account.
- No source deletes and no target overwrites have been performed in this conversation.


## Progress update — 2026-10-08 14:35+ VN
- Target R2 was successfully enabled by user: authenticated Cloudflare account API returned HTTP 200, success=true, initially 0 buckets.
- Created and read-back verified in TARGET account 748a80810f77f447ee476543ef0e5014 three empty R2 buckets: `runner3-artifacts`, `runner3-wp-media`, `runner3-rss-fastlane-artifacts`. No data copied, no Worker bindings switched.
- Source GitHub-hosted read-only inventory succeeded via preinstalled GitHub Actions secret, commit `010b1a759025d2b3adf3b1ff4dbb9e112daab01f`, report `ops/cloudflare-account-rehome/r2-inventory.json` (source account 7415...).
- Source totals at 2026-10-08T07:33:50Z: 10 buckets, 5,498 objects and 5,587,865,922 bytes (R2 metrics). `runner3-artifacts` first 2,000 objects = 3,115,124,382 bytes, truncated, so not entire bucket. `runner3-wp-media`: 285 objects, 260,456,867 bytes. `ai-vps-common-access`: 10 objects, 195,463,623 bytes. `runner3-reddit-opportunity-raw`: 9 objects, 1,179,565 bytes. `clm-copilot-data` 1 object/411 bytes, `runner3-telegram-bobvolman-raw` 2/113722 bytes, `runner3-telegram-raw` 3/3812254 bytes. `runner-vps-dr` and `runner3-direct-download-test` empty. `runner3-rss-fastlane-artifacts` empty.
- Added bounded copy workflow `.github/workflows/cloudflare-r2-rehome-copy.yml` commit `97cafb9da66580bddbd9aa0fe28f55c2ceae9617`. Workflow uses existing SOURCE GitHub Action token and requires new TARGET secret `CLOUDFLARE_TARGET_MIGRATION_R2_TOKEN` with only R2 Bucket Item Write permissions for exactly three destination buckets. It defaults to DRY_RUN and max 5 objects; cap 300 MB/run; it never deletes source or overwrites destination, and SHA-256 verifies uploaded objects by target GET.
- Credential protection blocked automated creation-and-transfer of target token from logged-in browser to GitHub Secret. Respect the security restriction and **do not retry through alternate extraction paths**. User must provision a narrowly scoped temporary **Cloudflare API bearer token** directly into GitHub Actions repository secret (not an R2 S3 Access Key). Token should expire quickly and be revoked after migration. Permissions: Workers R2 Storage Bucket Item Write; resources limited to target buckets named above; never grant Registrar/Billing/Account Management.
- NO data copy/cutover/source deletion yet. Next: user provisions target secret, launch bounded dry-run/test 5 objects of `runner3-wp-media`, verify per-object SHA-256, complete bucket in batches, then migrate `runner3-artifacts` with manifest-based incremental copy. Only after R2 and D1 parity should runtime move and source cleanup be considered.
