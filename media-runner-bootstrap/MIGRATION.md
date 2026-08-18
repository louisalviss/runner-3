# Migration from runner-3 to media-runner

## Current state

`runner-3` contains unrelated trading, WordPress, radar, MMO, probe and media/video workflows in the same `.github/workflows` namespace. The media work will move to a dedicated `media-runner` repository.

The bootstrap source lives temporarily on branch `bootstrap/media-runner` under `media-runner-bootstrap/`. Files in that subtree are inert because GitHub only loads Actions workflows from root `.github/workflows`.

## Cutover sequence

1. Create repository `louisalviss/media-runner` (public is fine for standard hosted Actions; do not add runtime media to Git history).
2. Copy the contents of `media-runner-bootstrap/` to the root of the new repository.
3. Run `Source Ingest` with `configs/chainsaw-reze-v18d.json`.
4. Run `Render Video` using the successful ingest run ID.
5. Run `QA Video` using the successful render run ID.
6. Treat cutover as successful only if `qa_report.json` says `pass: true` and the master + iPhone contact sheets are visually acceptable.
7. Only after step 6, remove/disable obsolete anime experiment workflows from `runner-3`.

## Phase-1 cleanup candidates in runner-3

These are dedicated anime/edit experiments and should move out after cutover:

- `anime-phonk-demo.yml`
- `iphone-anime-fit-v2.yml`
- `iphone-anime-youtube-demo.yml`
- `jjk-*`
- `solo-beru-*`
- `chainsaw-*`
- `naruto-wikimedia-cc-edit.yml`
- `naruto-youtube-cc-demo.yml`
- `montagem-bandcamp-audio-test.yml`
- `pixabay-montagem-audio-test.yml`

Do not automatically remove broader media infrastructure until reviewed separately, including narrator benchmarks, Remotion smoke tests, R2/media bootstrap tools, WordPress media workflows, or X/video utilities; some may support non-anime projects.

## What stays in runner-3

Trading/backtest/probes, WordPress/site operations, AutoContent, radar/news, MMO, Cloudflare utilities and other non-media automations stay in `runner-3`.

## Design rules after cutover

- New edit iteration = new or updated JSON config, not a new workflow.
- Source, render and QA artifacts are ephemeral and never committed.
- No workflow commits status/manifest files back to `main`.
- All heavy workflows are manual `workflow_dispatch` by default.
- Ingest, render and QA have independent concurrency groups.
- QA includes iPhone 19.5:9 center-cover simulation before delivery.
