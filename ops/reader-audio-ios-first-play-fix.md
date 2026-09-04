# Reader audio iOS first-play / latency fix

Date: 2026-09-04
Baseline: Reader v69 PASS snapshot already exists in ebook-lib.

Observed iPhone behavior
- First audio preparation may take long while synthesis completes.
- After the async prepare path completes, Safari may reject delayed `audio.play()` because the original tap user-activation has expired, surfacing `The request is not allowed...` / NotAllowedError.
- Audio itself can still become ready later, proving the synth pipeline is alive.

Required fix
1. Preserve Reader v69 geometry and Home Screen behavior.
2. Never attempt delayed autoplay after a synth/queue wait that can outlive the originating user gesture.
3. If media is not already ready on the first tap: immediately start prepare/prefetch, keep button usable as a prepare state, and transition to READY without surfacing NotAllowedError.
4. If media is already ready at tap time: play directly within the user-gesture path.
5. Translate/suppress browser NotAllowedError from the status line; do not show raw English browser errors.
6. Improve perceived latency by prewarming current chapter once Reader location/DOM is stable and preserving existing warm-ahead for the next chapter.
7. Do not wait for next-chapter warm-ahead before beginning current-chapter playback.
8. Acceptance: cold chapter first tap starts prepare with no browser error; second tap (or first tap when already warm) starts immediately; warm chapter first tap starts immediately; v69 layout unchanged.

This file is an ops specification; production code must be patched and smoke-tested before PASS is claimed.
