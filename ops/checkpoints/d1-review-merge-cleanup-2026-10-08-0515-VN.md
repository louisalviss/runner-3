# D1 Review / Merge / Cleanup Checkpoint — 2026-10-08 VN

## Completed
- Merged all 12 context-index checkpoints into louis-task-context.
- Deployed Runner3 Core with both TASK_CONTEXT_DB and CONTEXT_INDEX_DB bound to louis-task-context.
- Ran ai-context-index.service; live write landed in the merged DB at 2026-10-07 22:11:08 UTC.
- Verified R2 backup of retired louis-context-index (SHA-256 962b640a77f12c80451ffa1727dd1ef9b7ca77fa6a88f6b91603585108b2ee46).
- Retired louis-context-index. D1 inventory is now 8 databases, leaving 2 free slots.
- Reconciled Personal Library: all 1,655 Core library IDs exist in personal-library, including 37 comic rows and 1,618 ebook rows.
- Verified Ebook reader progress/state/trace key parity.
- Verified Content Intelligence dedicated DB is a superset for content items/features/scores/events.
- Verified Opportunity Radar dedicated DB is a superset for current/history keys.
- Backed up Core legacy domain tables to R2:
  runner3-artifacts/d1-migration-backups/2026-10-08/review-merge-cleanup/runner3-core-legacy.sql.gz
  SHA-256 0ea2b922e09aedcc67abc3e150e735a22e573a6a26fa7fe94155b5d808f1cf58.

## Pending
cloudflare/runner3-core/migrations/0018_drop_legacy_domain_tables.sql is prepared but not applied because the destructive migration invocation was blocked by the current tool safety gate.

The pending migration only removes legacy copies of:
- RSS
- Content Intelligence
- Opportunity regime
- Personal Library / Ebook reader

It does not remove Runner3 control-plane tables.
