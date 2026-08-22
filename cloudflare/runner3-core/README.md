# Runner3 Core

Purpose: shared Cloudflare backend layer.

Architecture:

- Worker: API gateway
- D1: operational state/events
- R2: large artifacts
- KV: low-frequency config/cache only

Migration order:

1. Deploy Worker
2. Create D1 database
3. Apply migrations
4. Bind D1 to Worker
5. Migrate one lane at a time

Current phase: shadow mode. Existing GitHub Actions flows remain unchanged.
