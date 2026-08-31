# Reader Audio Core refactor plan

This file marks the architectural pivot recorded in the Dropbox checkpoint dated 2026-08-31.

Principles:
- v30/v31 remain fallback implementations.
- Do not extend the layered Reader patch chain as the primary development path.
- Reader production has one deploy owner.
- Smoke/browser workflows must not independently overwrite the production Worker.
- New Reader Audio Core is introduced behind an isolated entry before promotion.

Target modules:
1. AudioController
2. PositionMapper
3. ReaderFollower
4. PlaybackQueue

Acceptance order:
1. playback + resume reuse
2. mapping + highlight
3. serialized follow at 1x/2x
4. continuous next readable chapter
