# runner-3 — Public Web Crawl Worker

`runner-3` is a public GitHub Actions project for crawling and processing **public Internet sources only**.

Current workloads include the generic crawler (for targets such as BHW public pages) and the Vidian public preservation pipeline.

## Security boundary

This repository is public. Treat every committed file, workflow definition, job URL, log, and approved artifact as non-secret.

Allowed:

- public `http://` / `https://` source URLs;
- generic HTTP or Playwright crawling of pages that do not require authentication;
- public-source text/raw artifacts when explicitly enabled;
- semantic/derived artifacts that contain no private data.

Forbidden in committed jobs or source URLs:

- cookies or authenticated sessions;
- `Authorization`, `Cookie`, API-key, or auth-token headers;
- passwords, tokens, OAuth secrets, private keys, service-account credentials;
- credential-bearing URL userinfo or sensitive query parameters;
- private/account-only URLs or private source content.

Credentials for **destination systems** such as Dropbox or Google may only be provided through GitHub Actions Secrets in a dedicated workflow. They must never be committed to this repository, embedded in job JSON, or written to public artifacts.

## Generic crawler jobs

A crawl request lives under `jobs/` and must explicitly declare that its source is public.

```json
{
  "name": "example-public-crawl",
  "source_visibility": "public",
  "artifact_policy": "text",
  "mode": "auto",
  "timeout_seconds": 30,
  "wait_after_load_ms": 1500,
  "urls": [
    "https://example.com/"
  ]
}
```

### `artifact_policy`

- `none` — default; do not upload crawl output as a GitHub Actions artifact.
- `text` — public sources only; save extracted `page.txt`, safe `meta.json`, and `manifest.json`.
- `raw` — public sources only; additionally save `page.html`.

The crawler does **not** persist response headers. Generic crawl artifacts are retained for 3 days.

Jobs missing `source_visibility: public`, jobs containing sensitive credential fields/headers, or URLs containing credential-like query parameters are rejected before crawling.

### Crawl modes

- `http` — normal HTTP request only.
- `browser` — Chromium/Playwright rendering.
- `auto` — try HTTP first, then browser when the response appears blocked, empty, or script-dependent.

The crawler does not attempt CAPTCHA solving, login bypass, or anti-bot circumvention.

## Vidian

Vidian has its own workflow at `.github/workflows/vidian.yml` and pipeline code under `scripts/vidian_pipeline.py`.

The Vidian pipeline crawls public pages and stores inventory/semantic reconstruction data rather than persisted source prose.

## Repository permissions

Workflows use least-privilege `contents: read`. Generic crawl checkout does not persist the GitHub token into git credentials.

See `SECURITY.md` for the repository policy.
