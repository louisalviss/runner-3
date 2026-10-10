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

## Continuation — 2026-10-10 VN: full WordPress application clone + reversible deploy PASS

**New canonical reusable acceptance:** `louisalviss/vps-control` main at `tests/website_a2z_wp2_restore_acceptance.py`, source commit `a36fd9486677ad2368d8aebce4392b55ca234783`. This uses the existing VPS/HawkHost migration fixture `wp2`, not `jeff-vn.com`.

### Fully isolated live run (2026-10-10 ~01:20 VN)
- Dumped source `wp2` MariaDB using single-transaction **read-only**. SQL 1,706,887 bytes. Full source file archive 116,695,040 bytes.
- Created a brand-new MariaDB 10.11 container with temporary credentials and database `a2zclone`. Restored **19** WordPress tables from dump.
- Created a brand-new Apache/PHP 8.1 container with the extracted site and modified **clone-only** `wp-config.php`; staged home/siteurl set to `http://127.0.0.1`, disabled cron/external HTTP/automatic updates.
- New **internal Docker network**, **no published host ports**, resource-bounded containers. All ephemeral PHP/SQL resources removed after test.
- Real HTTP application smoke: `/` 200; `/wp-login.php` 200; `/?rest_route=/` 200.
- Reversible candidate: create **clone-only** WordPress mu-plugin that adds HTTP response header `X-A2Z-Isolated-Candidate`. Deployment confirmation **PASS**; remove that plugin and verify header absent while HTTP remains 200: **ROLLBACK PASS**.
- Execution 9.81 seconds; final JSON verdict `PASS`.
- Cleanup verified separately: no `a2z-wp-*` or `azweb-*` containers/networks/temp dirs. Original `hawkhost-db` and `hawkhost-web56/web74/web81` running with **restartCount=0**; MariaDB healthy; Nginx syntax test PASS.

### Overall status
**VPS self-hosted WordPress component recovery, full isolated boot, admin/login + REST health, disposable candidate deploy, and rollback: PASS.**

**Still NOT a complete autonomous production A→Z deployment:** a durable encrypted full-site WordPress+MariaDB backup in private R2, R2 read-back + decrypt + disaster recovery verification, and a persistent optimizer authority replacing the retired `runner3-wp-optimizer` D1 have not passed current acceptance. Existing `vps-state-backup` covers select SQLite only. Its `verify-latest` must use the existing systemd credential unit; direct CLI missed systemd LoadCredential. SentinelX service-start policy disallows direct start of `vps-state-backup-verify.service`; do not bypass or alter policies implicitly. No source WordPress data/settings/containers were changed, no domain/VPS purchased, no `jeff-vn.com` operations.



## 2026-10-10 VN — Encrypted Offsite Backup + Optimizer Ledger E2E verified

Scope: existing `wp2` WordPress fixture on `runner-vps1` **only**. No operations on `jeff-vn.com`; no domain purchase/new VPS. Source WordPress/DB and production services remain unchanged.

### Private encrypted R2 backup — PASS
- Canonical backup source: `louisalviss/vps-control:stack/website_a2z_backup.py`, commit `14c670aeb57be7f21d7a90d01b9031374a72c0ba`.
- New bounded BWS project: `website-a2z`; secret reference **name only** `WEBSITE_A2Z_BACKUP_AGE_V1`. Dedicated machine backup encryption via BWS; no secret bytes in logs, GitHub, Dropbox, or R2. Existing Session Vault secret and protected service config unchanged.
- Writer: Runner3 Core private R2 durable_put_file, including exact byte + SHA256 readback, **followed by a separately fetched GET** and age-scrypt decrypt using existing reviewed age helper.
- Proof: recovered 7,102 WordPress files and SQL restored to isolated temp MariaDB (19 tables); validated SQL SHA and archive safety; latest pointer written **after** restore proof and read back.
- Private artifact address: project `wordpress-backup`, scope `wp2`, name `snapshots/20261009T223256Z-239dbb/site.tar.zst.age`.
- Encrypted size **27,789,650 bytes**, SHA-256 `7484f39d100ba2121568a56c9612969f78f53b4ddee83f46e7defc9a6f7e0a20`.
- Stable private pointer: `wordpress-backup/wp2/latest.json`; live readback `PASS`.
- Test result: R2_UPLOAD=PASS, R2_GET=PASS, CIPHERTEXT_SHA=PASS, DECRYPT=PASS, FILE_RESTORE=PASS, SQL_RESTORE=PASS, POINTER=PASS. Duration approx. 19.8 sec.
- Never publish a public permalink for this private backup. Restoring requires BWS access and site-scoped authorization.

### New optimizer event authority — PASS on VPS
- Source `louisalviss/runner-3:scripts/wp-optimizer-r2-ledger.py`, commit `252a3552dde4680de9755f1c24d7d4ebbbc48556`. Existing Runner3 Core private R2 transport; immutable SHA-addressed events, site-scoped file lock, idempotent replay, verified per-run manifest.
- New experiment ledger R2: project `wordpress-optimizer`, scope `a2z`, run `wp2-a2z-integrated-20261010`. Integrated `vps-control:tests/website_a2z_wp2_restore_acceptance.py` commit `1a80ff510af623972ba8eb881dcd0fb7d6780c3b` tests ephemeral WordPress restore → HTTP homepage/login/REST 200 → clone-only plugin candidate deploy → rollback → append 6 structured events → readback verify.
- Integrated acceptance run duration approx. 39 sec, result `PASS`, event_count=6, manifest integrity=PASS, final verdict=`ROLLBACK` for an intentionally rejected fixture canary; no claim of performance gains or production promotion.
- Historical retired D1 `runner3-wp-optimizer` deliberately NOT recreated.
- Retired D1 bootstrap workflow set `if: false` in `.github/workflows/wp-optimizer-d1-bootstrap.yml`, commit `3ad2589325a2c428b5d4e163e3e868a297a83716` to avoid accidental database creation.
- Independently checked both private R2 pointers/events after tests: `PASS`.
- Cleanup: no temporary Docker containers/networks/directories. Original `hawkhost-db` healthy; `hawkhost-web81`, `hawkhost-web74`, `hawkhost-web56` all running; zero restarts.

### Remaining production gates (do not overclaim A-Z)
1. Existing hosted GitHub Site2 A/B workflows still refer to retired D1. They must be explicitly migrated to the same R2 ledger transport (or retired); current proof covers VPS-native optimizer only, **not** hosted CI A/B automation end-to-end.
2. Backup/restore test covered `wp2` and decrypted R2 site files + SQL. A fully functional HTTP WordPress app clone was independently proved on the same fixture, but this fresh run did not boot a clone directly from the *downloaded* encrypted R2 artifact.
3. One-shot backup was durable verified, but no recurring backup timer/retention/alerting has been enabled. Do not silently create a new unattended schedule without an appropriate authorized owner/integration.
4. Only fixture `wp2` has passed. Other existing sites are not declared automatically migrated/protected.
5. Site2 Wasmer flow is distinct from VPS-hosted `wp2`; do not conflate identities. `jeff-vn.com` is excluded.

**Current verdict: core VPS A→Z technical primitives verified; unattended multi-site website manager NOT YET production-ready.**

## Continuation — 2026-10-10 VN: unified manager and safe schedule preflight

### Completed
- Implemented an operator entry point in `louisalviss/vps-control:stack/website_a2z_manager.py` (subcommands `status`, `scheduled`, `backup`, `verify`, `acceptance`). Installed module set on runner-vps1 under `/opt/website-a2z/app/`. Live `status` PASS: MariaDB healthy, PHP81 container running, private R2 backup pointer resolves correctly.
- `scheduled` design: source SQL dump SHA + WordPress file metadata fingerprint; skip creating a new snapshot when unchanged and last backup < 7d old; instead rerun independent R2/decrypt/restore verification. New backup otherwise. Requires >2 GiB MemAvailable, single-site flock, `--run`.
- Added independent verifier `vps-control:stack/website_a2z_verify_backup.py`, on-demand test from existing R2 ciphertext PASS (R2 SHA, decrypt, 7,102 files, 19 MariaDB tables, temporary schema cleanup).
- Added no-secret CI `vps-control:tests/test_website_a2z_manager_schedule.py` and workflow `website-a2z-code-qa.yml` (GitHub Actions run 38002602747 PASS). Subsequent manager refactor also passed Python compile check on VPS.
- Staged `vps-control:deploy/systemd/website-a2z-wp2.service` and `.timer`. VPS timezone `Asia/Ho_Chi_Minh`; templates validated with `systemd-analyze verify` (PASS). **Not installed or enabled**, as the credentialed `scheduled --run` smoke is not verified. Automated backup is NOT active.
- All four other legacy D1-dependent Site2 workflows (`site2-realistic-fixture`, `site2-optimizer-baseline`, `site2-performance-diagnose`, `site2-hero-preload-ab`) explicitly `if: false` fail-closed, supplementing previously paused retired D1 bootstrap. They are historic code, not yet ported to the R2 query/measurement contract. Avoid accidental Wasmer mutation.
- Canonical manager document in `vps-control:docs/website-a2z-manager.md`.

### Open gates / safety boundary
- Credentialed manager `scheduled --run` live test remains BLOCKED / unverified. A SentinelX tool request involving runtime secret material was rejected by safety controls; do not route around it through a timer or alternate execution transport.
- Do not enable `website-a2z-wp2.timer` or claim automatic daily backup until approved live smoke + sandbox/notification verification succeeds.
- R2 ciphertext→decrypted WordPress **running application** restore as one E2E route is still pending; completed component SQL/file recovery and a separate local-source full-app clone must not be conflated.
- Retention/error alerting and Site2 PageSpeed baseline/R2 read semantics require future work before production A→Z.
- Strictly no `jeff-vn.com` operations.

**Verdict:** VPS manager installed and healthy; immutable R2 optimizer ledger, cryptographic WP backup/restore, isolated reversible canary PASS individually; unified scheduling production gate NOT PASS.

## 2026-10-10 VN — wp2 daily backup automation ACTIVATED (explicit user approval)

The user approved adding only `website-a2z-wp2.service` and `website-a2z-wp2.timer` to SentinelX's service policy. Applied using native `sentinel_edit`, YAML validated; agent reconnected and advertised both service entries with actions `[status,start,is-active,is-enabled]`. Original policy backed up; no unrelated service permissions changed.

Started the wp2 oneshot using native `sentinel_service_start` twice:
- First run: **new encrypted R2 backup** `snapshots/20261010T002231Z-171cd0/site.tar.zst.age`, 27,789,652 encrypted bytes, fingerprint prefix `14089e74e53d`; R2 download/decrypt/SQL restore PASS, service result SUCCESS/exit 0 (20.11s, ~496.8 MiB memory peak).
- Second run: **verify_unchanged** PASS (6.29s); same ciphertext, no duplicate R2 upload.

Started timer via SentinelX service action, persisted using `systemctl enable website-a2z-wp2.timer`; verified **active + enabled**, next execution 2026-10-11 04:38:15 +07. `website_a2z_manager.py status` now returns PASS, healthy wp2, fingerprinted fresh backup, active timer, no pending checks.

Existing Telegram VPS monitor is active and alerts on failed systemd units; first **unattended** timer occurrence and dedicated missed-run alert remain to validate. All activity limited to wp2 fixture; no `jeff-vn.com` changes. Old Wasmer Site2 / D1 workflows remain paused.

Current canonical operational documentation: `louisalviss/vps-control/docs/website-a2z-manager.md`.

## 2026-10-10 VN — Independent offsite full-application DR

- Latest wp2 private R2 snapshot manifest inspected; expected 27,789,652 encrypted bytes, 7,102 WordPress files, 19 SQL tables. Daily backup service/timer remains active (next local 11/10 ~04:38).
- New isolated full WordPress DR acceptance script in `louisalviss/vps-control/tests/website_a2z_r2_full_application_dr.py`: R2 GET → SHA → BWS age decrypt → unpack → disposable internal-network MariaDB + PHP, HTTP smoke, guaranteed cleanup. It intentionally has no original wp2 source / production database read path.
- First execution: **FAIL from subprocess argument bug**, not evidence of R2 recovery failure. Corrected, installed, syntax compiled. Reattempt with credentialed invocation was **blocked by tool safety**, not bypassed. No temporary containers/networks remain.
- Added no-secret negative/contract tests and GitHub CI: <https://github.com/louisalviss/vps-control/actions/runs/38042400017> PASS.
- **Overall DR-from-R2-to-running-app = NOT VERIFIED** until a permitted credentialed runtime rerun finishes. See canonical `vps-control/docs/website-a2z-manager.md`. `jeff-vn.com` unchanged.
