# media-runner

Dedicated GitHub Actions compute repo for video/media generation. This repo is intentionally separated from `runner-3` so trading, WordPress, radar, MMO and probe workloads do not share the same workflow namespace with media experiments.

## Architecture

1. `source-ingest.yml` — read a JSON job config, acquire only declared direct/public source URLs, normalize media, and upload a short-lived source artifact.
2. `render-video.yml` — download a source artifact from a selected ingest run, resolve the configured music preview, render the edit from JSON, and upload a short-lived render artifact.
3. `qa-video.yml` — download a render artifact, validate codec/duration/dimensions, generate a master contact sheet and an iPhone 19.5:9 center-cover simulation.

Versions and shot plans belong in `configs/*.json`. Do not create one GitHub workflow for every V1/V2/V3 experiment.

## Repository rules

- Do not commit source video, music, cookies, tokens, or other runtime media.
- Use `workflow_dispatch` for media jobs; no automatic push trigger for expensive renders.
- Keep artifacts short-lived (1 day for source, 3 days for render/QA).
- One config = one job identity. Use concurrency groups to avoid accidental duplicate renders.
- Prefer tools already present on the hosted runner. `scripts/common.py` finds `ffmpeg`/`ffprobe`; install fallback tooling only when required.
- Final output target for short-form video: H.264 High, yuv420p, AAC 48 kHz stereo, 1080×1920 unless the config overrides it.
- QA must simulate a tall iPhone center-cover viewport before a render is treated as final.

## First migrated job

`configs/chainsaw-reze-v18d.json` is the config-driven replacement for the Chainsaw/Reze experimental workflows currently in `runner-3`.

## Cutover

Do not delete media workflows from `runner-3` until the new repo exists and one end-to-end ingest → render → QA run succeeds. See `MIGRATION.md`.
