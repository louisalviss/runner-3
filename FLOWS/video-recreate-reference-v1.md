# Video Recreate Reference Flow v1

Purpose: recreate a reference video closely in structure, timing, composition and motion without reusing source visual frames as the final visual output.

## Architecture

1. INGEST
- Resolve/download reference video.
- ffprobe media metadata.
- Extract dense reference frames at 2-4 fps, not only one sparse contact sheet.
- Detect hard cuts and meaningful visual-state changes.
- Extract audio waveform and transcript/word timings when speech exists.

2. AI REFERENCE ANALYSIS — REQUIRED BEFORE RENDER
- Divide video into shots and sub-shots.
- For each shot record: exact start/end, composition, object boxes, perspective/camera, background, UI state, text, cursor/gesture, transitions, lighting, palette, effects and motion curves.
- Identify what is real footage, screen capture, UI reconstruction, logo animation, generated visual or compositing.
- Produce `reference-analysis.json` and `storyboard.json`.
- No renderer may invent a scene family from a contact sheet alone.

3. ASSET / SCENE BUILD
- Rebuild each scene using the best medium per shot: HTML/SVG/Canvas/Remotion for UI and motion graphics; generated/rebuilt imagery for photographic scenes; FFmpeg only for compositing/encoding where appropriate.
- Match geometry and information density before styling details.
- Preserve perspective, camera movement, cursor path, text placement and state transitions.

4. MOTION + AUDIO SYNC
- Animate on the reference timeline, not approximate phase durations.
- Match cuts to within 2 frames when practical.
- Match cursor/click/CTA/ripple events to the audio/reference timing.
- Use exact transcript text and word/phrase timing when text is speech-driven.

5. TECHNICAL QA
- Codec/container valid.
- Dimensions, FPS, duration and audio valid.
- No black frames, missing assets, broken fonts or clipped text.
- This gate alone MUST NOT mark the recreation as success.

6. CREATIVE / REFERENCE QA — REQUIRED
- AI compares reference vs render side-by-side at every shot and at dense sampled timestamps.
- Check: shot boundaries; layout/object geometry; perspective/camera; UI density/state; typography/text; color/lighting; cursor paths; transition/effect timing; motion character.
- Record per-shot PASS/FAIL and remediation in `creative-qa.json`.
- Overall status can be `success` only after creative QA passes.

## Status contract

Allowed overall states:
- `running`
- `analysis_required`
- `ready_to_render`
- `technical_pass_creative_pending`
- `creative_fail`
- `success`
- `error`

Never map technical QA directly to `success`.

## Current reference video requirements: clck.ru/3VNYSd

Observed top-level boundaries: ~0s, ~10s, ~20s, ~30.1s.

- 0-10s: filmed physical monitor / desktop scene. Must preserve monitor perspective, environmental lighting/reflection and handheld/camera drift; a flat synthetic dashboard is not equivalent.
- 10-20s: dense SocksNode desktop dashboard. Must reconstruct full dashboard hierarchy, sidebar/cards/data density, cursor interactions and changing UI states; a centered mobile-like product card is not equivalent.
- 20-30.1s: neon branded outro. Must match logo scale/position, green-blue background, CTA, cursor/click and ripple/transition timing.

## Anti-shortcut rules

- A 12-frame contact sheet is discovery material, not a production specification.
- Do not hardcode guessed captions/UI values without extracting/validating against reference.
- Do not use still-image zoompan as a substitute for reference motion when the source contains stateful UI/cursor/camera animation.
- Do not claim quality from file size, FPS, resolution or duration.
