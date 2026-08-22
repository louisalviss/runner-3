# AI RSS Reader runtime

Canonical behavior lives in Dropbox `AI/AI-MEMORY/FLOWS/AI RSS Reader.md`.
Runtime implementation lives only in `louisalviss/runner-3`.

## Entry point

Run:

```bash
python scripts/rss_reader_run.py
```

The entrypoint runs and validates:

- 12 RSS-only Runner3 logical sources: the original 10 plus Scientific American and Quanta Magazine;
- Võ Hoàng Hạc as one hybrid Runner3 logical source: Articles RSS + verified original Substack Notes;
- the 15-source reader-state shape.

Hồ Quốc Tuấn and vnhacker remain ChatGPT-direct freshness sources at render time.

Full active logical-source model:

- Runner3: 12 RSS-only + 1 Võ Hoàng Hạc hybrid = 13;
- ChatGPT direct: Hồ Quốc Tuấn + vnhacker = 2;
- total = **15 logical sources**.

## Health files

- `runtime-health.json` — primary Runner3 ingestion gate. Read this first.
- `health.json` — detailed health for the 12 RSS-only sources.
- `substack-health.json` — detailed Võ Hoàng Hạc Articles + Notes health.

Runner3 ingestion is healthy only when `runtime-health.json.ingestionOk == true`.
This validates `core12`, Võ Hoàng Hạc hybrid, and the 15-source state shape.
It is not the full 15/15 render gate: ChatGPT must still verify Hồ Quốc Tuấn and vnhacker directly.

## State

`reader-state.json` is the atomic reader cursor for all 15 logical sources.
Collectors MUST NOT modify it. State advances only after ChatGPT completes and renders a successful 15/15 incremental scan.

Scientific American and Quanta were onboarded with a current-high-water baseline so enabling them does not dump historical backlog. Use full-day/history or explicit replay to inspect earlier items.

## Selected-analysis fast lane — Cloudflare primary

Full article text is **lazy/on-demand**, not prefetched for every RSS item.

The production primary path is now Cloudflare Worker + R2. GitHub Actions is deployment/bootstrap and fallback only; it is not the normal request-response path for selected deep analysis.

Production Worker:

- service: `runner3-rss-fastlane`;
- URL: `https://runner3-rss-fastlane.ducduy2411.workers.dev`;
- source: `cloudflare/rss-fastlane/`;
- deploy workflow: `.github/workflows/rss-fastlane-bootstrap.yml`;
- deploy runner: `ubuntu-24.04-arm`;
- R2 bucket: `runner3-rss-fastlane-artifacts`;
- R2 object prefix: `rss-analysis/`;
- retention/lifecycle: 7 days.

Worker endpoints:

- `GET /health` — health + R2 binding check;
- `GET /v1/rss/fetch?sourceKey=...&url=...&title=...&displayIndex=...` — direct one-item adapter suitable for ChatGPT/web GET access;
- `POST /v1/rss/selected-analysis` — batch extraction, max 20 items;
- `GET /v1/rss/artifact?key=rss-analysis/...json` — read a stored R2 analysis artifact.

The Worker allowlists RSS source hosts instead of acting as an open arbitrary-URL proxy. Extraction order is canonical direct HTML first, then Jina live/no-cache fallback when direct fetch fails or produces thin text. Batch items run in parallel. Raw bodies are stored in R2, not committed to GitHub.

When the user selects numbered RSS items for deep analysis, ChatGPT should:

1. resolve exact numbered items from the render manifest;
2. use a still-valid cache/R2 artifact when exact canonical identity/hash is known;
3. otherwise try normal canonical web access in parallel when convenient;
4. for items needing acquisition, call the Cloudflare fast lane directly rather than queueing `ubuntu-latest` GitHub Actions;
5. prefer `GET /v1/rss/fetch` for direct ChatGPT one-item access; use batch POST when the caller supports POST and several items need acquisition together;
6. verify returned canonical URL/source identity, fetch route, character count, errors, storage result and expiry;
7. read the stored R2 artifact when full extracted payload is needed for analysis;
8. only fall back to the legacy GitHub selected-analysis job if the Cloudflare fast lane is unavailable/degraded.

Verified production checkpoint (2026-08-22):

- `/health`: `ok=true`, `r2Bound=true`;
- Fulcrum test: direct route, ~23.2k chars;
- Noema test: direct route, ~16.3k chars;
- batch result: `fetchedCount=2`, `errorCount=0`;
- R2 artifact stored successfully;
- Worker processing about 1.7–2.1 s, E2E about 2.1–2.6 s;
- this replaces the observed failure mode where the actual fetch took seconds but GitHub-hosted runner allocation could queue for ~28 minutes.

Deployment/verification lessons that are now part of the flow:

- `.github/workflows/rss-fastlane-bootstrap.yml` must trigger on both itself and `cloudflare/rss-fastlane/**`;
- deployed entrypoint is `cloudflare/rss-fastlane/src/index-get.js` via `wrangler.jsonc`;
- `/health` is handled directly at the deployed entrypoint and reports `r2Bound`;
- verifier POST requests must send an explicit non-default `User-Agent` (`runner3-fastlane-verifier/1.0`) because the default Python urllib request path can receive HTTP 403 before Worker execution;
- bootstrap persists proof to `ops/rss-fastlane/latest.json`;
- code change is not considered production-ready until health + real extraction + R2 persistence pass.

Legacy/fallback GitHub selected-analysis components remain available:

- `scripts/rss_selected_fetch.py` — generic parallel extractor for selected canonical URLs;
- `.github/workflows/rss-reader.yml` → `selected-analysis` — fallback on-demand batch job;
- `analysis-request.json` — fallback request metadata;
- `analysis-cache-index.json` — legacy/fallback pointer/hash/TTL metadata;
- GitHub Actions artifact — fallback raw extracted text, retention 7 days.

Important properties:

- raw copyrighted article text is never committed to the repository;
- selected-analysis acquisition never advances RSS reader state;
- per-item failures are explicit and do not silently substitute another article;
- Cloudflare/R2 acquisition cache is not freshness authority and must not be used as publication timestamp/cursor evidence;
- stale/expired/mismatched artifacts are cache misses;
- if Cloudflare direct + fallback acquisition still cannot recover enough content, analysis must stay within verified material and state the limitation.

Legacy VHH-specific prefetch code/index/artifacts are non-canonical and are not auto-refreshed.

## Scientific American

Runner3 source key: `scientificamerican`.

Configured feed attempts:

- `https://rss.sciam.com/ScientificAmerican-Global`
- fallback `http://rss.sciam.com/ScientificAmerican-Global`

The fallback exists because GitHub-hosted egress can hit TLS EOF on the HTTPS RSS endpoint. The source is healthy only when a configured feed returns parseable RSS items in the current run.

## Quanta Magazine

Runner3 source key: `quanta`.

Configured feed attempts:

- `https://api.quantamagazine.org/feed/`
- fallback `https://www.quantamagazine.org/feed/`

The source is healthy only when a configured feed returns parseable current items.

## Võ Hoàng Hạc

`sources/vohoanghac.json` must use `transport = hybrid-rss+substack-profile` and contain both `itemType=article` and `itemType=note` when those item classes exist in the retained archive.

Notes identity rules remain fail-closed:

- top-level `item.type=comment`;
- `comment.type=feed`;
- `post_id` empty;
- `ancestor_path` empty;
- author `user_id` equals the profile id verified from the author's publication;
- stable identity is `c-<comment.id>`;
- publish time is `comment.date` only.

Direct Substack profile-feed access is attempted first. When GitHub-hosted egress is blocked, the collector may use the configured no-cache live relay only as transport; returned JSON is still required to pass the same identity/date validator.

## Never use

Do not use `louisalviss/rss-proxy` for runtime freshness, mirrors, cursor, state, or health. It is historical only.
