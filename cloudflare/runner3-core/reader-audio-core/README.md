# Reader Audio Core

Clean orchestration path for EPUB/TTS playback. This directory is intentionally isolated from the legacy v30/v31 patch chain until acceptance tests pass.

Modules to land here:
- AudioController
- PositionMapper
- ReaderFollower
- PlaybackQueue

Do not wire this directory into the production Reader entry until browser E2E passes.
