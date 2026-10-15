# R2 artifact PUT source attribution — opt-in diagnostics

**State: DRAFT / NOT DEPLOYED / NOT ENABLED** — 2026-10-16.

## Incident

The old `ducduy2411` R2 account still showed 23–29 `runner3-artifacts PutObject` operations per 15 minutes in clean windows after three high-frequency jobs were stopped. These are bucket/action counts, **not caller IDs**. Do not blame unrelated scanner jobs without request-level evidence.

Cost incident authority: D1 `task-context/task/CLOUDFLARE-R2-COST-001`, human projection in Dropbox `/Task/active/CLOUDFLARE-R2-COST-001.md`. Protected `EBOOK` / RSS audio consumer services and YouTube story mirror remain held under systemd. This diagnostic patch never changes those holds.

## Proposed trace

- New `src/r2-put-provenance.js`: only emits a single bounded JSON `console.info` line after a **successful** Worker R2 write *when* `env.R2_PUT_PROVENANCE === "enabled"`.
- Enumerated fixed labels; **no object key, username, source header, token, cookie, request body, arbitrary URL, PII or dynamic identifier** is logged.
- Categories: direct artifact API, RSS original/translation, imported-media writes, cached images, and occasional SEOtrends watchdog writes.
- When the env flag is missing, logging is **OFF**. A failed logger does not change the write result.
- Tests use Node and mock `console.info`. They issue **zero** Cloudflare requests or R2 operations.

## Limitations / rollout gates

1. Source patch only. **No Worker deployed, no telemetry activated**. Browser/CI/VPS/R2 traffic must remain unchanged.
2. Direct AWS S3 API uploads, Wrangler R2 writes, other Workers or GitHub scripts bypass the Runner3 Worker code; this patch **cannot attribute those PUTs**. Even with successful logging, unlogged R2 PUT would need a different authorized tracing method.
3. Cloudflare Worker log transport and retention must be reviewed for **their own costs and privacy controls** before enabling; do not enable unlimited log retention.
4. Before activation: approve exact diagnostic window, log/retention costs, release workflow; deploy only compatible source, keep `COST_HOLD`, verify no R2 write behavior regression. Analyze bucket PutObject totals against the count of labeled logs. If totals remain higher, investigate direct S3/other Worker origins.
5. Do not resume WordPress migration, unmask protected jobs or run bucket `LIST`/`PUT` as a diagnostic.

## Evidence

- Previously reported Cloudflare Analytics: 07:55–08:10 VN: 23 PUT, 08:10–08:25 VN: 29 PUT on `runner3-artifacts`.
- GitHub Actions `38663333488` WP preflight had no copy/repair step; cannot explain continuing PUT.
- `scripts/tests/test_r2_put_provenance.mjs`: tests opt-in behavior, fixed safe payload, error isolation, and source-instrumentation coverage (7 files staged into a temporary VPS directory, no deployment).
