# D1 Content Intelligence — verified 15-object schema staging (2026-10-23)

Status: REVIEW ONLY; no Cloudflare schema apply, data copy, Worker deploy, or R2 operation.

The authenticated source and target schema-digest workflow #39826582807 recorded 18 source-only CI schema objects. Offline scratch SQLite reconstruction from existing repository SQL matched 15 object identity hashes and full source DDL/column metadata hashes exactly. These are two tables (workflow_state, checkpoints), twelve indexes, and one trigger (trg_user_content_events_render_dedupe).

Candidate: staging/content-intelligence-additive-proven-15.sql. Generator: scripts/cloudflare_d1_ci_source_matched_schema.py. Both are offline-only and fail closed on source DDL drift. This is a staging review artifact, not a script to run against Cloudflare.

Three source-only objects remain outside this candidate: the named link_interest_events table without verified CREATE DDL, and two anonymous source object fingerprints. No guessed schemas.

Key protections: the repository-only idx_content_items_last_seen_at is deliberately excluded because it was not observed in the authenticated source schema. The 0009 event dedupe migration contains DELETE FROM and is never executed; its matching CREATE TRIGGER is isolated for scratch validation and staging. The existing personal_score_stage table is not recreated; only its missing index is included.

Indexes may depend on current live target data constraints. Before any application, independently confirm current DDL, PK/FK/unique constraints and data duplicates, take an authorized snapshot, and explicitly approve bounded CREATE operations. IF NOT EXISTS is not proof of data or DDL equality. Source remains writer authority.

Core staging coverage 18/21 plus CI staging coverage 15/18 equals 33/39 exact source DDL candidates. No actual D1 row parity, deletion parity or migration is claimed. R2 COST_HOLD rev28, no target cron, and no source retirement remain mandatory.
