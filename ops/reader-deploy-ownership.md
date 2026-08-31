# Reader deploy ownership

Production Worker: `runner3-core`

Rule: exactly one workflow owns production Reader promotion/deploy.

Allowed production owner:
- `.github/workflows/runner3-core-public-hosted-reader-deploy.yml`

Reader smoke workflows must not call `wrangler deploy` against the production Worker. They may run isolated unit/browser checks only, or validate an already-promoted revision.

The clean Reader Audio Core smoke workflow is isolated and contains no Cloudflare credentials/deploy step.
