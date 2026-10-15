# Cloudflare R2 billing incident — cross-task HOLD — 2026-10-15

**STATUS: BILLING_HOLD / NO_NEW_R2_MIGRATION_RUNS**. This is an **operational instruction**, not a claim that Cloudflare permissions, billing, or GitHub workflows have been programmatically disabled. Do not advise launching further `runner3-wp-media` migrations/copies/repair workflows while investigation is open. Do not revert or restart the separately disabled cost-generating VPS tasks. A direct, explicit user decision to resume with cost visibility is required.

## Background / observed usage from parallel Cloudflare billing incident
User says "Tôi không muốn mất thêm tiền" and specifically asks if ongoing WP Media migration causes the Cloudflare R2 bill.

Other billing incident reported for old account `Ducduy2411`:
- Billing R2 Standard Class A indicated **USD 4.50**; storage and Class B reported USD 0.
- **1,022,801** Class A operations in ~27 days; 1,000,000/month free, exceeded by **22,801**.
- Operation-group source R2 metrics: `runner3-wp-media` **676,412 LIST** (~66.1% of observed Class A), `runner3-artifacts` **345,182 PUT** (~33.7%). LIST root process remains UNATTRIBUTED (not proven due to GitHub WP migration). Historic 27-day period predates the first Oct 8 migration runs.
- `youtube-story-r2-mirror.timer` previously reported executing ~515 times/day and explaining ~97.3% of `runner3-artifacts` PUT. Parallel cost triage previously disabled YouTube mirror and nonessential Ebook Reader/RSS Reader TTS polling without deleting stored data.
- Current assistant read-only `systemctl is-enabled youtube-story-r2-mirror.timer` -> `disabled`; `systemctl is-active` -> `inactive`; no matching live process. System `ebook-reader-tts.timer` and `rss-reader-tts.timer` -> `not-found/inactive`; **user-scope systemd bus unavailable**, so never claim all background jobs/timers are fully eliminated.
- Official Cloudflare R2 pricing as of Oct 2026: Standard Class A $4.50 per one million after first one million free, billable operations rounded up to billing unit. Reference: https://developers.cloudflare.com/r2/pricing/ . Verify current **Amount** vs **Unit price** in billable usage before claiming final money charged.

## What assistant built, what it actually ran
- The assistant wrote scripts and **user-manually-dispatched** GitHub Actions moving media **from old Cloudflare `Ducduy2411` to new `Louisalviss3`**, not an unrelated WordPress site traffic service. `runner3-wp-media` is WordPress/media asset bucket, historical 285 objects/260,456,867 bytes.
- GitHub WP Media migration copied **271 objects /80,333,850 bytes** in old run 37824948164; subsequent auto-small run 38575546891 copied **5 more /45,757,136 bytes**. Latest confirmed old source285, new target277, **8 remaining missing** (~134,365,867 bytes: six medium, two large), one 14-byte target CacheControl drift that already has live source/target **matching payload SHA**. Metadata not yet repaired and whole bucket parity NOT PASS.
- Repeated GitHub workflow reruns for full audit/SHA/preflight create additional reads/listings and therefore could contribute to operations; but **no evidence they caused the 676,412 LIST over 27 days**, which vastly exceeds the number of bounded, manually triggered migration runs and starts before this migration.
- Existing manual-only explicit write workflow `.github/workflows/cloudflare-wp-explicit-repair-complete.yml` has **ZERO runs as checked 2026-10-15**; earlier `cloudflare-r2-wp-repair-and-complete.yml` runs 38655094307 and 38663333488 both ran read-only `preflight` only (repair/copy skipped).
- NO source R2 bucket/object deletion, Worker deletion, D1 cutover, domain or production route cutover. Source old account remains authoritative. Target partial copies retained but **must not re-initiate WP migration during cost investigation**.

## Required cross-task coordination
1. Prioritize stop-the-bleed: determine root cause of continuous `runner3-wp-media` LIST (which cron/workflow/service executes repeated LIST); verify **new daily Class A usage has ceased** using Cloudflare Billing Billable Usage and R2 bucket analytics. Do not equate a disabled timer with a verified billing stop.
2. Existing `youtube-story-r2-mirror.timer` and nonessential Ebook/RSS TTS jobs are HOLD/DISABLED per parallel incident; never proactively restart because another project says `Tiếp`.
3. Pause user prompts to run ANY additional R2 migration/copy/repair workflows and other nonessential write/list diagnostics for WP while money is unresolved. The GitHub manual Actions still technically exist: this checkpoint is **not a technical kill switch**.
4. After new daily cost is stable, decide whether old WordPress bucket is even needed. If used, schedule the smallest final migration with request-cost budget; if not used, archive/retire by explicit user authorization only after dependency/retention review. Do not assume "unused" merely because no traffic metric yet.
5. Preserve pending source Workers 38, D1, R2 and target buckets. Delete nothing now. Coordinate with billing incident before any source cleanup or quota mutation.

## Evidence and supporting checkpoints
- `ops/checkpoints/cloudflare-account-migration-2026-10-08.md`
- `ops/cloudflare-account-rehome/wp-metadata-drift-2026-10-14.md`
- User's parallel Cloudflare cost conversation from October 15, 2026 (billing dashboard and R2 metrics captured there)
