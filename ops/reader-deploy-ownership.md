# Reader deploy ownership

Production Worker: `runner3-core`

Rule: exactly one GitHub Actions workflow owns production Reader/Core promotion and deploy.

Allowed production owner:
- `.github/workflows/runner3-core-public-hosted-reader-deploy.yml`

Canonical concurrency group:
- `runner3-core-production`

All Reader smoke, legacy artifact-library deploy, and retired Core trigger workflows must be validation/no-deploy only. They must not contain production Cloudflare credentials or call `wrangler deploy` for `runner3-core`.

Enforcement:
- `scripts/verify_runner3_core_single_deploy_owner.mjs`
- `.github/workflows/runner3-core-deploy-owner-guard.yml`

The Reader Audio Core and its browser E2E remain isolated from the production Reader entry until acceptance tests pass.
