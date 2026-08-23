# Runner3 Core retention

Target: Runner3 Core D1 `events` telemetry.

- Retention window: 90 days for historical event rows.
- Preserve the latest `workflow_status` row for every source indefinitely so `/status` continues to represent dormant workloads.
- Large payloads and artifacts stay outside D1; D1 stores compact metadata and pointers only.
- Cleanup runs inside the Runner3 Core Cloudflare Worker via its `scheduled()` handler.
- Cron Trigger: `17 3 * * *` (03:17 UTC daily).
- Cleanup is idempotent: rerunning it only deletes rows that are already beyond the retention boundary.
- D1 itself does not run cron; Cloudflare invokes the Worker, and the Worker executes the D1 `DELETE`.

If a future flow needs a checkpoint that must live longer than 90 days, store that checkpoint as dedicated current-state/upsert data rather than relying on append-only event history.
