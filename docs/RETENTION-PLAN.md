# Retention implementation plan

Target: Runner3 Core D1 telemetry.

- Keep current-state/upsert tables indefinitely.
- Purge routine event history older than 90 days.
- Keep large payloads out of D1.
- Run cleanup in the Core Cloudflare Worker via a Scheduled Handler (Cron Trigger), not GitHub Actions.
- Default cadence: once daily; exact UTC minute is not operationally important.
- Cleanup must be idempotent and safe if a run is skipped or retried.

Before wiring SQL, confirm the live D1 table/schema names from the Core Worker migration/source files.
