# Reader Audio Core checkpoint

Status: acceptance PASS, production cutover intentionally not performed yet.

## Production deploy ownership

- Production Worker: `runner3-core`.
- Sole GitHub Actions production owner: `.github/workflows/runner3-core-public-hosted-reader-deploy.yml`.
- Canonical concurrency group: `runner3-core-production` with `cancel-in-progress: false`.
- Legacy Reader smoke / artifact-library / old core deploy-trigger workflows are validation/no-deploy only.
- Single-writer guard workflow is green.

## Live production baseline

- Live Reader remains `v31-high-speed-serialized-follow`.
- Production baseline restore/deploy passed via canonical owner.
- Reader Audio Core changes are not imported by the production Reader entry.

## Isolated Reader Audio Core

Core modules:
- `state-contract.js`
- `position-mapper.js`
- `reader-follower.js`
- `audio-controller.js`
- `playback-queue.js`
- `reader-audio-adapter.js`
- `dom-segment-builder.js`

The core now exposes canonical play/pause/rate/seek ownership, one 75 ms clock, deterministic audio-time mapping, serialized latest-target-wins following, queue orchestration, canonical persistence, and deterministic DOM timing-to-CFI segment construction.

## Acceptance evidence

GitHub Actions run `33448929343`, job `99674190108`: PASS.

Main live-injection E2E against production v31, without production mutation:
- media single owner: PASS
- single 75 ms playback clock: PASS
- deterministic seek/follow: PASS
- single-flight latest-target-wins: PASS
- auto-follow animation disabled: PASS
- continuous queue advance: PASS
- persisted resume: PASS
- race stress: PASS
- `productionMutation: false`

DOM timing -> CFI integration E2E:
- alignment coverage: `1`
- segment count: `11`
- timing words: `129`
- deterministic mapping: PASS
- mapped CFI follow/highlight: PASS
- display calls: `1`
- max concurrent navigation: `1`
- animation disabled: PASS
- `productionMutation: false`

## Cutover boundary

Do not layer the new core directly on top of production v11/v31 browser audio lifecycle. The legacy v11 script still registers anonymous click/timeupdate/seeked/play/pause/ended persistence/follow handlers. Injecting the new adapter without first removing or redirecting those handlers would recreate dual ownership in the browser.

Next safe phase:
1. Create a clean v33/canary integration wrapper that rewrites legacy ownership before browser execution.
2. Run the same acceptance matrix against the canary.
3. Only after canary PASS, promote the v33 entry through the sole production deploy workflow.
4. Verify live runtime marker, Reader behavior, audio surface, mailbox surface, and single-writer guard after promotion.
