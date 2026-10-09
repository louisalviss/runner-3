# Website A→Z — existing stack acceptance checkpoint (2026-10-09 VN)

Scope: existing WordPress **test** site2 only. **Do not change jeff-vn.com**; it is discussion-only unless explicitly requested. No domain purchase, no new VPS, no database creation or destructive production action.

## Reused authorities
- GitHub source and CI: `louisalviss/runner-3`.
- Site2: `https://runner3-wp-a94b8fd2.wasmer.app/` mapped by `ops/wordpress/site-map.json`.
- Auth: pre-existing GitHub Actions `WASMER_TOKEN`; test relies on WordPress/Wasmer magic login and does not expose its value.
- VPS inspection: SentinelX on runner-vps1.
- Cloudflare: existing source-account token and R2. **Target-account migration is not complete.**

## Fresh checks / execution receipts
1. **Website/REST/WooCommerce PASS:** Site2 home, `/shop/`, WP REST types all HTTP 200. Astra active; WooCommerce active.
2. **Authenticated WP admin PASS:** `.github/workflows/website-az-existing-site2-preflight.yml` on Github Actions run `37828787453`, GitHub `WASMER_TOKEN` reuses authenticated site2 admin; `wp-admin/plugins.php` accessible, no new login request to user.
3. **Cloudflare R2 query PASS** via existing GitHub Actions token; 10 buckets visible in source account during test.
4. **Optimizer D1 FAIL:** `runner3-wp-optimizer` missing in queried source account. Independent schema-only inspection of all 9 source-account D1s found none of `optimization_runs`, `measurements`, `gates`, `decisions`. Verified `ops/cloudflare-capability/d1-domain-isolation.json` **explicitly marks `wp_optimizer: retired`**. **Do not recreate it reflexively**. Current flow references obsolete D1 authority.
5. Existing live `site2-performance-diagnose.yml` read-first run `37828306198` failed before site mutation at D1 fixture/baseline gate. Old run `32925531916` passed A/B functional, visual, PageSpeed and final live-state guards; old baseline run `32926706549` successful, but historical success is not current E2E acceptance.
6. Site1 legacy `wordpress-control.yml` run `37824461546` failed at decrypt credential (`bad decrypt`). Do not reuse Cloudflare API bearer token as storage-encryption key; earlier encrypted file is incompatible with current secret. Existing Wasmer browser auth route is independently functional **for Site2**.
7. No candidate was activated/changed during the fresh A→Z acceptance; no D1/R2 mutations, no domain setup, no changes to `jeff-vn.com`.

## Final verdict
**PARTIAL / NOT PRODUCTION READY:** Site2 hosting + Wasmer-authenticated admin + WooCommerce + R2 read-only access PASS. Current optimizer D1 source of truth intentionally retired, so `baseline → controlled change → compare → KEEP/ROLLBACK → verified durable record` has **not** passed a fresh E2E.

## Next gate (single recommended route)
- Resolve optimizer experiment authority **before** another A/B mutation. Reuse existing source/CI and Cloudflare R2 or a deliberately approved dedicated domain store; do not silently write WP data into unrelated D1s or recreate a retired D1.
- Update old control workflow's obsolete encryption boundary to reuse existing Wasmer-scoped site auth safely, with no passwords/tokens in logs or repos. Test `inspect` on Site2.
- Once durable state/backup/rollback is proven, run one **isolated reversible** Site2 candidate with functional + visual + repeated PageSpeed comparison and verified final rollback/KEEP record.
- Full VPS-level WordPress A→Z still requires separately validating OS/PHP/DB-level operations; Wasmer site-admin success does not prove dedicated-VPS management.

Operational rule: do not operate `jeff-vn.com` unless user explicitly says to do so.


## VPS-hosted WordPress full-stack acceptance — 2026-10-09 02:10 VN (continued)

**Host**: runner-vps1; existing Docker HawkHost migration stack. This is distinct from Wasmer Site2. All checks excluded jeff-vn.com.

### Verified live capability
- SentinelX root-level OS access on Linux: PASS. Nginx 1.26.3 config `nginx -t`: PASS. Controlled temporary local file write/readback/cleanup: PASS.
- Existing web containers running (zero restarts in test): Apache/PHP 5.6.40, PHP 7.4.33, PHP 8.1.34. Apache config syntax on PHP 8.1: PASS.
- Existing database `hawkhost-db`: MariaDB 10.11.19, health healthy, SQL SELECT: PASS.
- PHP 8.1 `mysqli` end-to-end connections for existing WordPress `wp`, `wp2`, `canary`: 3/3 PASS (`SELECT 1`), without disclosing DB credentials.
- Independent scratch-only MariaDB transaction: create unique ephemeral schema, INSERT/SELECT, SQL dump, drop, restore, exact readback — PASS; scratch schema cleaned.
- **Real WordPress file/database recovery proof** (source: existing `wp2`, read-only):
  - Full site file tar 116,746,240 bytes, extracted to temporary isolated directory; `diff -rq` PASS.
  - Existing `louisalv_wp337` database dumped as SQL (1,706,887 bytes), restored to a unique new isolated schema. All **19 tables** and exact source/restored row counts matched.
  - Re-dumping the restored schema produced a **byte-identical SQL dump**; SHA256 `3ac042ca82e2327b03255b0ebd538dab535c0dac5ba9a883556bfd067ec6b2dc`.
  - Verified no `az_restore_wp2_*` / `az_accept_*` scratch schema remains; no temporary file staging remains. Existing web containers have restart count 0. Nginx syntax PASS; database healthy.
- No production WordPress DB rows, content, PHP configuration or nginx settings were modified; only scratch schema and temporary files were created then deleted.

### Open gates — DO NOT promote to A→Z production-ready
1. `vps-state-backup` automated task (last run SUCCESS 2026-10-09 00:19 VN) backs up SQLite state, not verified to include whole WordPress site files or MariaDB. Existing `/opt/hawkhost-migration/runtime/backups` stores **partial** SQL/config/file backups; **full current WordPress backup and verified offsite restore are NOT proven**.
2. An actual independent WordPress app clone with altered `siteurl`/separate DB + private web server must boot and pass functional/visual smoke; file+DB readback alone is not application-state recovery.
3. Define encrypted private R2 backups + backup manifest/hash/retention/readback in the already existing artifact authority; avoid storing plaintext WordPress credentials or customer data in public GitHub/Dropbox.
4. Dedicated VPS stack operator (start/restart/deploy/rollback/health) needs one bounded reversible config/candidate test with production-safe visual and functionality gates.
5. Legacy PHP 5.6/7.4 must remain isolated, never treated as acceptable defaults for a new WordPress golden template. Future standard should use supported PHP release compatible with current WP/plugins and current MariaDB. No upgrade performed today.
6. Cloudflare `runner3-wp-optimizer` D1 was marked retired in current authority: don't resurrect it accidentally. WordPress experiment state needs a deliberately agreed current home before automatic optimization is re-enabled.

**Overall verdict:** Host OS, PHP, MariaDB, WordPress→DB link, isolated data backup/restore = PASS. Actual autonomous website restore / self-healing / offsite backup = NOT YET PASS. No domain purchase necessary for these gates.


## Continuation: full WordPress component recovery on VPS — 2026-10-10 VN

This is a fresh non-destructive rerun on existing HawKHost migration stack, `wp2` only; no changes to `jeff-vn.com`.

### Fresh evidence
- Host: `runner-vps1`. Existing DB container `hawkhost-db` healthy. High load, swap 8/8 GiB used; avoid unnecessary parallel/heavy runs.
- Verified all three WordPress sites (`wp`, `wp2`, `canary`) can read database via PHP 8.1 and mysqli. Existing source tables: `wp2` = 19; approximate data+index bytes = 5,177,344.
- `wp2` full file tar = **116,695,040 bytes**; isolated extraction + SHA-256 comparison for all file records = **PASS**, including 7,102 regular files out of 8,036 path records.
- `wp2` SQL dump = **1,706,887 bytes**; restored into a newly generated, temporary, separate MariaDB schema. **19/19 base tables** exact row-count match (**1,309 rows** total); PASS.
- Temporary SQL restore schema removed, private temporary SQL/archive directories removed. No production DB modified and no frontend/WordPress settings touched.
- Conclusion: file+SQL recovery is proven for components. Full application clone with private web stack, independent siteurl and functional/visual smoke is **not** yet proven.

### Offsite encrypted R2 restore verification gate — still open
- The existing `vps-state-backup` pipeline backs up **SQLite state only**, not this WordPress/MariaDB payload. Service has been previously successful but does not prove complete site backup.
- Direct invocation of `vps_state_backup.py verify-latest` **outside its configured systemd unit** returned `BITWARDEN_UNLOCK_REQUIRED`. Root cause is the dedicated systemd `LoadCredential` contract rather than a proven locked Bitwarden vault; the existing volatile Bitwarden session was independently checked as unlocked.
- The **existing** `vps-state-backup-verify.service` already provides that credential securely; however its start operation is **not allowlisted in the current SentinelX agent policy**. Attempts to start it were rejected; no SentinelX policy was edited or bypassed.
- Do not claim encrypted R2 decryption/readback PASS on the current run. Do not create/reuse unrelated encryption keys or put plaintext WP backups/DB credentials in R2.
- Next authorized gate: execute the existing verify service via an approved operator path **without changing guardrails**, then confirm actual R2 artifact readback/hash/decryption. Only afterward integrate a full-site encrypted backup of one controlled WordPress fixture with bounded IO, readback and checkpoint.
- No new domain, VPS, D1, public bucket, credential, account, or scheduled job created in this continuation.

**Verdict remains: PARTIAL / NOT YET A→Z PRODUCTION READY.**
