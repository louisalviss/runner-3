# runner-3 — Generic Web Crawler

A reusable crawl worker backed by GitHub-hosted Actions on this public repository.

## How it works

1. Add a JSON request under `jobs/`.
2. The push triggers `.github/workflows/crawl.yml` on `ubuntu-latest`.
3. `crawler.py` fetches each URL with HTTP, browser, or auto fallback.
4. The run uploads `crawl-output-*` as a GitHub Actions artifact.
5. The artifact contains raw HTML, extracted text, response metadata, and `manifest.json`.

This repo is intentionally generic. BHW is only one possible crawl target.

## Job format

```json
{
  "name": "example",
  "mode": "auto",
  "timeout_seconds": 30,
  "wait_after_load_ms": 1500,
  "urls": [
    "https://example.com/"
  ]
}
```

### Modes

- `http`: normal HTTP request only.
- `browser`: Chromium/Playwright rendering.
- `auto`: try HTTP first, then browser when the response looks blocked, empty, or script-dependent.

The crawler is targeted: it fetches the URLs supplied in the job and does not recursively spider a whole site unless a later job explicitly adds that behavior.

The crawler does not attempt CAPTCHA solving, login bypass, or anti-bot circumvention. Block/challenge pages are recorded as such in the manifest.

## Output

Each URL gets a folder containing:

- `page.html` — raw fetched page HTML
- `page.txt` — extracted readable text
- `meta.json` — URL-level metadata

The artifact root also contains `manifest.json`.

Artifacts are retained for 14 days by the workflow and are not committed back into the source tree.
