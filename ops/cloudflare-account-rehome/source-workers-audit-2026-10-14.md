# Cloudflare Ducduy2411 — authenticated Worker inventory, 2026-10-14

**Evidence:** GitHub [run 38575674555](https://github.com/louisalviss/runner-3/actions/runs/38575674555), job 115892005330, PASS. Sanitized JSON artifact 11899043830 (expires 2026-10-21 UTC), SHA256 `0e3b430a1bf062749e48538de90bf7486eb5293d6325b39ad1720d8e2465ba24`. Artifact downloaded and inspected by assistant, not derived from old guesses. Source account `7415a87f6bce7884e73ad7cfed5782df`. All 38 script IDs had successful reads of settings/cron/subdomain/deployments/tail consumers, all reported workers.dev enabled, none had configured tail consumers. `safe_to_delete_count=0`, `source_mutated=false`. This audit **did not** retrieve 30-day request metrics, external callers, routes, restorable backups or the target account's matching live script deployments.

## All 38 Workers and classification

| Worker | Cron | Known in-account caller | Triage |
|---|---:|---|---|
| balatro-clef-api | 0 | None visible | PROTECT pending target parity |
| balatro-clef-video-viewer | 0 | None visible | REVIEW usage |
| clm-conversation-copilot-api | 0 | None visible | PROTECT active CLM D1 |
| clm-conversation-copilot-calibration | 0 | None visible | REVIEW recent stage |
| ema-forward-monitor | 0 | None visible | PROTECT pending live monitor check |
| ema-mt5-report-viewer | 0 | None visible | REVIEW usage |
| ema-mt5-viewer | 0 | None visible | REVIEW usage |
| fate-aio | 0 | None visible | REVIEW usage |
| imdb-stremio-addon | 0 | None visible | REVIEW usage |
| khotruyen-worker | 0 | None visible | PROTECT pending target parity |
| media-library | 0 | None visible | PROTECT D1/R2 bindings |
| ocr-pdf | 0 | None visible | REVIEW usage |
| rss-proxy | **1** | None visible | PROTECT cron + KV |
| runner3-audio-chatgpt-bridge | 0 | None visible | PROTECT R2 dependencies |
| runner3-audio-library | **1** | None visible | PROTECT cron + R2 |
| runner3-autocontent-ai | 0 | None visible | PROTECT AI automation |
| runner3-core | **1** | None visible | PROTECT main service + D1/R2 |
| runner3-core-reader-v33-preview | **1** | None visible | REVIEW old preview; cron must be resolved |
| runner3-core-reader-v34-preview | 0 | None visible | REVIEW old preview |
| runner3-core-reader-v35-preview | 0 | None visible | REVIEW old preview |
| runner3-direct-download | 0 | None visible | REVIEW publish pathway |
| runner3-rss-fastlane | 0 | **4 source Workers** | **PROTECT service dependency** |
| runner3-wp-control | 0 | None visible | REVIEW WP maintenance |
| runner3-x-fast-direct | 0 | None visible | PROTECT pending target parity |
| runner5-restore-proxy | 0 | None visible | PROTECT rollback route |
| seotrends-watchdog | 0 | None visible | REVIEW watchdog |
| telegram-bobvolman-archive | 0 | None visible | REVIEW archive service |
| tienvuc-vbook-proxy-louis | 0 | None visible | REVIEW VBook usage |
| tiktok-product-radar | 0 | None visible | REVIEW radar usage |
| truyenhub-vbook-proxy | 0 | None visible | REVIEW VBook usage |
| vbth-free-editorial-ai | 0 | None visible | PROTECT VPS references |
| volamidle-rogue | 0 | None visible | PROTECT D1 app |
| wave-rider-scanner | **1** | None visible | PROTECT cron |
| webcap | 0 | None visible | REVIEW old web capture |
| wordpress-edge-proxy | 0 | None visible | PROTECT WP route pending parity |
| wordpress-edge-proxy-lcp090 | 0 | None visible | REVIEW experimental LCP proxy |
| wordpress-edge-proxy-v2 | 0 | None visible | PROTECT WP route pending comparison |
| world-of-horror-reader | 0 | None visible | REVIEW newly updated reader |

Cron list: **5** workers: `rss-proxy`, `runner3-audio-library`, `runner3-core`, `runner3-core-reader-v33-preview`, `wave-rider-scanner`.

### Verified Worker-to-Worker service bindings

- `runner3-core` → `runner3-rss-fastlane`
- `runner3-core-reader-v33-preview` → `runner3-rss-fastlane`
- `runner3-core-reader-v34-preview` → `runner3-rss-fastlane`
- `runner3-core-reader-v35-preview` → `runner3-rss-fastlane`

`runner3-rss-fastlane` is not an orphan. Zero direct HTTP requests or cron for this Worker would **not** prove it is unused. Three preview Workers are plausible cleanup candidates, but v33 still has a scheduled trigger. No script has been established as safe to delete.

### Next safety gates

1. Collect request analytics for a representative 30-day window and route/consumer/service-binding inventory beyond Workers bound inside source account.
2. Associate each script with its GitHub/VPS/application owner; confirm target copy/target bindings+secrets/rollback backup.
3. Prioritize decommission of old preview variants only when traffic and external callers absent, cron removed safely, source backup/restoration verified, and active runner3-core regression PASS.
4. Delete **source Worker only**, never `force=true`, one by one with post-delete smoke tests. No R2/D1 deletion until full account-to-account parity and last-write delta.

### Related checkpoints

- `ops/cloudflare-account-rehome/workers-prune-review-2026-10-09.md`
- `ops/checkpoints/cloudflare-account-migration-2026-10-08.md`
