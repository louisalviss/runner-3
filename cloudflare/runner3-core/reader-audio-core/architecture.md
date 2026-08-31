# Architecture

`AudioController` owns media state and the 75 ms playback clock.

`PositionMapper` maps current audio time to a deterministic EPUB target. Playback rate changes scheduling cadence only; mapping itself is rate-independent.

`ReaderFollower` owns visual follow. It highlights every mapped target, moves only when required, disables decorative animation for automatic moves, and serializes navigation with latest-target-wins semantics.

`PlaybackQueue` resolves/prefetches the next readable section and advances on `ended` when continuous reading is enabled by the integration layer.

The integration layer should persist exactly one playback state object and must be the only owner of resume/restore.
