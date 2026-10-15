# D1 source → target historic parity reconstruction — 2026-10-16

**STATUS: HISTORICAL_OFFLINE_EVIDENCE / NOT_LIVE_PARITY / NO_MIGRATION_PERFORMED**

## Identity and provenance

Source Cloudflare: `ducduy2411`, `7415a87f6bce7884e73ad7cfed5782df`. Destination: `louisalviss3`, `748a80810f77f447ee476543ef0e5014`.

Evidence obtained **read-only and offline on VPS** from preexisting October 8 2026 audit files:
- Source RSA-OAEP/AES-256-GCM **encrypted** schema + COUNT snapshot `/var/lib/cloudflare-migration/2026-10-08/ephemeral-courier/run-37749106300/d1-envelope.json`, audited original `cloudflare_d1_encrypted_parity.py`. Source snapshot timestamp **2026-10-08T08:19:57.619573Z**.
- Target authenticated historical summary `/var/lib/cloudflare-migration/2026-10-08/ephemeral-courier/d1-target-parity.json` (mode 0600). Only table names, row COUNT values, and SHA256 of sqlite_master DDL were compared. No key, token or row values were exported to this repository. Private RSA material remained on VPS.
- Oct8 target name/UUID map `/var/lib/cloudflare-migration/2026-10-08/target-d1-map.json`; now historic, not freshly verified.
- Most recent source-only [D1 Account Usage Watch #38776291301](https://github.com/louisalviss/runner-3/actions/runs/38776291301) logged 2026-10-15T17:18:57Z, `inventoryCount=9`, `rowsWritten=23173` at observed daily point, `projected=32118/day`, below 100,000/day free limit; shows source is still writing, NOT source-target table parity.

## Schema and COUNT comparison for exactly the two databases in the Oct8 encrypted source audit

| DB | Source tables | Target tables | Identical DDL SHA256 for common tables? | Result |
|---|---:|---:|---|---|
| `runner3-core` | **12** | **0** | No common tables | **BLOCKED / target empty** |
| `runner3-content-intelligence` | **11** | **8** | **8/8 PASS** | **PARTIAL; 3 tables absent, several row counts differ** |

**Runner3 Core** source table COUNTs vs target missing (all 12): `artifact_library_auth` (1), `artifact_library_magic_links` (4), `artifact_library_pin_attempts` (0), `checkpoints` (643), `d1_migrations` (28), `delivery_permalinks` (1), `ebook_reader_trace_v113` (0), `events` (93), `r2_receipts` (4), `typed_kv` (5), `vps_mailbox_jobs` (45), `workflow_state` (74).

These tables include live control-plane, authentication, mailbox, permalink and receipt state. Do **NOT** cut over, bulk-reseed or rebuild blindly; unique identifiers and idempotency must remain intact, and source writes require a final delta.

**Content Intelligence:**

| Table | Source rows | Target rows | Historic row count difference (source minus target) | DDL SHA256 |
|---|---:|---:|---:|---|
| `content_items` | 2,890 | 2,853 | +37 | MATCH |
| `content_features` | 14,531 | 14,328 | +203 | MATCH |
| `content_scores` | 2,076 | 2,061 | +15 | MATCH |
| `user_content_events` | 5,055 | 5,017 | +38 | MATCH |
| `interest_family_profile` | 13 | 13 | 0 | MATCH |
| `interest_profile` | 26 | 26 | 0 | MATCH |
| `personal_score_stage` | 0 | 0 | 0 | MATCH |
| `recommendation_runs` | 35 | 35 | 0 | MATCH |
| `checkpoints` | 0 | ABSENT | N/A | ABSENT |
| `link_interest_events` | 2 | ABSENT | N/A | ABSENT |
| `workflow_state` | 2 | ABSENT | N/A | ABSENT |

**Critical interpretation**: a positive count difference does NOT establish the identity of missing records or a row-subset relationship. Equal DDL hashes and row counts do NOT establish payload parity. Requires key-level reconciliation using explicit immutable PKs, checksums, and last-write delta before any apply. If target-only edits occurred after Oct8, preserve them.

## Nine physical D1 names in source/target historical inventories

- Historical target Oct8 had: `clm-copilot-v1`, `louis-context-index`, `louis-task-context`, `personal-library`, `runner3-content-intelligence`, `runner3-core`, `runner3-opportunity-radar`, `runner3-rss`, `volamidle-rogue-data`.
- Current **source-side inventory** in Oct15 Usage Watch had: `clm-copilot-calibration`, `clm-copilot-v1`, `louis-task-context`, `personal-library`, `runner3-content-intelligence`, `runner3-core`, `runner3-opportunity-radar`, `runner3-rss`, `volamidle-rogue-data`.
- 8 names in common, **`clm-copilot-calibration` appears source only**, **`louis-context-index` appears target only**; the source internally retired/merged `louis-context-index` into `louis-task-context`. **These are mixed-date snapshots, not current proof of target absence or source deletion eligibility.**
- Remaining seven source data stores beyond the two audited October 8 have no accepted source↔target schema/row/record-content parity results in this receipt. Even if names exist, treat their data as NOT VERIFIED.

## Execution priority with strict safety gates

1. **DO NOT REPEAT** internal source-account `D1 domain isolation` (already DONE); it is unrelated to account-to-account D1 migration.
2. Keep old `runner3-core` as production authority. First get a fresh **authorized read-only target metadata and D1 schema+COUNT snapshot** and pair with source same-time snapshot. Historical target Super Admin browser session was proven usable Oct8; its current authorized usability is unverified. GitHub Secret absence is not absence of the user's Cloudflare permissions. The previously blocked direct Wrangler exec and credential-transfer routes **must not be bypassed**.
3. Once new snapshots confirm, reconcile `runner3-core` all 12 tables; use **logical key-level and last-write catch-up**, auth/mailbox idempotence; no blind truncate/replace, copy of sensitive secrets into logs, or stale restore.
4. Handle `runner3-content-intelligence`: compare keys for four count-divergent tables and preserve 3 absent source tables if still required by live code. Validate key-level content hashes, not just COUNT.
5. Classify `clm-copilot-calibration` vs stale `louis-context-index` before choosing retain/archive. Do not auto-delete/rename database or write to D1 from a read-only audit.
6. Audit all remaining canonical D1s then selected required Workers+bindings/cron/secrets/rollback. Old source **38 Workers, five cron, no delete eligible**; target historic six Worker names not sufficient for parity. R2 **COST_HOLD** remains even if D1 read-only parity eventually succeeds. No source deletes/production cutover without full R2+D1+Worker parity and explicit user authorization.

## Operational restrictions
- R2 `CLOUDFLARE-R2-COST-001` canonical Dropbox rev7: residual artifacts PUT source unattributed; GitHub seven R2 migration workflows offline HOLD-gated. No R2 LIST/PUT/GET made for this reconstruction.
- Offline RSA use was solely to decode the previously generated source schema/count receipt on the same VPS; no Cloudflare bearer token, browser profile, cookie, or RSA private bytes copied or displayed.
- D1 table counts represent **October 8 2026 only**. Treat Oct15 Watch 9 DB and write-rate as latest source presence evidence, not fresh content parity.
