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

## Selected-analysis fast lane

Full article text is **lazy/on-demand**, not prefetched for every RSS item.

When the user selects numbered RSS items for deep analysis, ChatGPT should:

1. resolve the exact numbered items from the render manifest;
2. check `data/rss-reader/analysis-cache-index.json` for a valid TTL/hash-matching cache pointer;
3. try normal canonical web access in parallel for selected items that are not cache hits;
4. group only the blocked/partial items into **one** Runner3 request at `data/rss-reader/analysis-request.json`;
5. let the `selected-analysis` job inside `.github/workflows/rss-reader.yml` fetch those canonical URLs in one parallel batch;
6. read the resulting GitHub artifact and verify URL/hash before analysis.

Runtime components:

- `scripts/rss_selected_fetch.py` — generic parallel extractor for selected canonical URLs;
- `.github/workflows/rss-reader.yml` → `selected-analysis` job — on-demand batch job that runs in parallel with normal RSS ingestion for push events;
- `analysis-cache-index.json` — pointer/hash/TTL metadata only;
- GitHub Actions artifact — raw extracted text, retention 7 days.

Important properties:

- raw copyrighted article text is never committed to the repository;
- cache is keyed by canonical URL and optionally content hash;
- one selection such as `1 4 5` creates at most one Runner batch for items that actually need Runner fallback;
- cache hits avoid a new Runner queue entirely;
- batch fetches run in parallel;
- per-item failures are explicit and do not silently substitute another article;
- analysis fetching never advances RSS reader state;
- request-triggered runs use a unique concurrency group so a scheduled RSS run does not cancel an active selected-analysis request.

Legacy VHH-specific prefetch code/index/artifacts are non-canonical and are not auto-refreshed. New analysis acquisition uses the generic lazy selected-analysis path for every source.

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
