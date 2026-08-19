# AI RSS Reader runtime

Canonical behavior lives in Dropbox `AI/AI-MEMORY/FLOWS/AI RSS Reader.md`.
Runtime implementation lives only in `louisalviss/runner-3`.

## Entry point

Run:

```bash
python scripts/rss_reader_run.py
```

The entrypoint runs and validates:

- 10 RSS-only Runner3 logical sources;
- Võ Hoàng Hạc as one hybrid logical source: Articles RSS + verified original Substack Notes;
- the 13-source reader-state shape.

Hồ Quốc Tuấn and vnhacker remain ChatGPT-direct freshness sources at render time.

## Health files

- `runtime-health.json` — primary Runner3 ingestion gate. Read this first.
- `health.json` — detailed health for the 10 RSS-only sources.
- `substack-health.json` — detailed Võ Hoàng Hạc Articles + Notes health.

Runner3 ingestion is healthy only when `runtime-health.json.ingestionOk == true`.
This is not the full 13/13 render gate: ChatGPT must still verify Hồ Quốc Tuấn and vnhacker directly.

## State

`reader-state.json` is the atomic reader cursor for all 13 logical sources.
Collectors MUST NOT modify it. State advances only after ChatGPT completes and renders a successful 13/13 incremental scan.

## Võ Hoàng Hạc

`source/vohoanghac.json` must use `transport = hybrid-rss+substack-profile` and contain both `itemType=article` and `itemType=note`.

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
