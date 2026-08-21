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
