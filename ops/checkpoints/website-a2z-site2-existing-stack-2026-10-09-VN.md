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
