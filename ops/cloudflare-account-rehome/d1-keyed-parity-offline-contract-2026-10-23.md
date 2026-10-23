# D1 keyed row-fingerprint parity — offline-only contract (2026-10-23)

**STATUS: SYNTHETIC CONTRACT IMPLEMENTED / NO LIVE ROW READ / NO MIGRATION / NO CUTOVER.**

## Motivation

The manual read-only D1 schema comparison run [#39826582807](https://github.com/louisalviss/runner-3/actions/runs/39826582807) discovered 21 source-only schema objects in \`runner3-core\`, 18 in \`runner3-content-intelligence\`, and matching *schemas* in six other D1 databases. It provides no row parity. The supplementary source-only encrypted run [#39848842550](https://github.com/louisalviss/runner-3/actions/runs/39848842550) did not supply decrypted identities for the last two source-only CI objects: attempts to use the VPS private courier key were blocked by tool safety. **Do not bypass that restriction.**

The production Worker actively deletes events, scores, derived interests and stale features. An insert-only or timestamp-only replication procedure can *resurrect* deleted rows.

## Deliverable

- \`scripts/cloudflare_d1_keyed_parity_offline.py\` compares **already captured** local opaque HMAC key/payload receipts for one named D1 table. It has no Cloudflare SDK, credentials, SQL executor, or network calls.
- \`scripts/tests/test_cloudflare_d1_keyed_parity_offline.py\` uses 21 synthetic-only tests for equality, changed payload, source-only vs target-only, composite PKs, incompleteness, schema mismatch, duplicate IDs, malformed or plaintext fields, key/capture mismatch and fail-closed return codes.
- The existing cross-schema **pull-request-only synthetic CI** is extended to run these tests. No credentialed workflow is created or dispatched.

Receipts require exact fields:

| Field | Contract |
| --- | --- |
| \`format\`, \`role\` | \`d1-hmac-keyed-snapshot-v1\`, one of \`source\` and \`target\` |
| \`database\`, \`table\`, \`pk_columns\` | Exact DB, SQL table and declared stable, ordered PK column names |
| \`schema_sha256\` | 64 lowercase hex; must agree for row-digest comparison |
| \`capture_window\`, \`hmac_key_id\` | Identical coordinated opaque identifiers for both accounts |
| \`capture_complete\` | Boolean from future independently audited bounded reader; *claim*, not verified here |
| \`rows\` | At most 100,000 unique \`key_hmac\` / \`payload_hmac\` 64-hex pairs; **no raw keys or values** |

The future (not yet implemented or approved) read-only capture must use an independently generated shared, high-entropy session secret for **HMAC-SHA256**, not unkeyed SHA-256 of low-entropy IDs. Apply **domain separation** for key vs payload HMACs and exact versioned canonical serialization of typed column values (SQL NULL vs empty string, integer vs REAL, BLOB, key ordering, Unicode, decimal time). Bind the fingerprint to the table+schema identity and avoid key reuse across unrelated windows. Store receipts only in an authorized restricted location; do not upload fingerprint lists, HMAC secrets, row values or credentials to public GitHub artifacts.

Run only when two approved receipts already exist:

\`\`\`bash
python3 scripts/cloudflare_d1_keyed_parity_offline.py \
  --source /secure/local/source.json \
  --target /secure/local/target.json \
  --out /secure/local/summary.json
\`\`\`

**Exit contract:** \`2\` for *all* valid comparisons (including identical HMACs, because parity/cutover remains unproven); \`3\` on invalid/unsafe inputs; never exit \`0\` as a release-pass. The public summary does not contain row fingerprints, source values or key identities beyond the DB/table names. No operation writes to either D1.

Counts distinguish:
- \`source_only\`: key exists only in source snapshot.
- \`target_only_unresolved\`: key exists only in target snapshot. **Not equivalent to proof it was deleted from source.**
- \`payload_different\`: matching key, different payload fingerprint.
- \`matching\`: matching key and payload fingerprint.

Even if matching is 100%, \`row_parity_verified=false\`, \`deletion_parity_verified=false\` and \`cutover_ready=false\`. Completeness depends on the provenance of future read-only capture, stable PKs, simultaneous quiesced snapshots and delete/tombstone policy. These are not verified by the comparator.

## Next production gates (NOT implemented here)

1. Resolve the two unidentified Content Intelligence schema objects by an approved secret-safe path, inspect exact current source/target applied DDL/PK/FK/unique constraints and the 12 Core table owners. Do **not** replay the historical destructive SQL migration chain.
2. Separately review and authorize a bounded read-only source/target HMAC receipt capture with D1 read budget, pagination/consistent snapshot and deletion policy. Current snapshots are not present.
3. Determine \`source_only\`, \`target_only\`, \`payload_changed\`, and provably deleted rows using explicit authoritative lineage; preserve target-only rows until separately approved. Do not migrate auth/mailbox or reset idempotency blindly.
4. After verified staging, writer quiescence, final delta, rollback tests, Worker/binding/service/cron parity, obtain separate production cutover approval.
5. Continue R2 \`COST_HOLD rev28\` until its separate cost/safety gate clears. **This task never touches R2.**

**Current state:** schema identities 37/39; six DBs schema-matched, but **0 verified live row/payload/delete parity results**. No D1 writes, no R2 requests, no production cutover.
