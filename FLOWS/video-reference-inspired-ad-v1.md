# Reference-Inspired Ad Video Flow v1 — CANONICAL

Purpose: when the user sends a reference video and asks to make a similar advertisement, extract the idea, pacing, persuasion structure, visual grammar and production techniques, then create a NEW video. Do not reuse source visual frames unless the user explicitly asks for a copy/remake.

This is the default flow for requests such as: `làm video giống kiểu này`, `lấy ý tưởng video này`, `làm quảng cáo tương tự`, `dùng flow video làm cái này`.

Use `FLOWS/video-recreate-reference-v1.md` only when the user explicitly says `copy`, `remake`, `recreate sát`, `1:1`, or equivalent.

## 0. Locked intent rule

Default = INSPIRED, NOT COPIED.

- Learn: hook, scene sequence, sales structure, rhythm, transition grammar, UI density, CTA pattern, color/mood, motion style.
- Replace: script, voice, copy, brand, UI, assets, icons, imagery, composition details.
- Never use original source frames as final visual assets unless explicit copy/remake permission is requested by the user.
- Do not imitate accidental defects of the reference.

## 1. Reference analysis

AI analyzes the full reference before producing assets.

Extract:
- total duration / aspect ratio / fps
- shot and sub-shot boundaries
- hook structure
- problem -> mechanism -> solution -> demo -> benefits/proof -> CTA structure
- pacing and cut density
- hierarchy of text vs UI vs imagery
- motion grammar: slide, reveal, parallax, cursor, ripple, glow, particles, state changes
- audio grammar: voice cadence, music energy, pauses, accent moments

Output a compact `reference-idea-analysis.json` and `storyboard.json`.

The reference defines GRAMMAR, not pixels.

## 2. Rewrite for the target service

Write a new script specifically for the advertised service.

Rules:
- speech must fit scene timing naturally; never force a long paragraph into a short scene
- prefer 1 idea per scene
- use Vietnamese that sounds spoken, not written
- avoid unnecessary English terms if Vietnamese is clearer
- brand/domain pronunciation must be intentionally scripted
- scene text does not need to repeat every word of the voiceover
- keep claims supportable; do not invent numerical proof or guarantees

Default 30-second structure:
1. 0-4s: hook / pain
2. 4-8s: mechanism / why it happens
3. 8-14s: introduce solution
4. 14-20s: product/demo interaction
5. 20-25s: benefits / proof-like presentation without fabricated claims
6. 25-30s: CTA / brand close

Adjust durations to reference when useful.

## 3. Asset-first visual production

Do NOT animate a single finished poster as the main technique.

Build every scene from separable assets/layers where practical:
- background
- environment / texture
- main UI panel
- cards
- charts
- labels / text
- icons
- logo
- cursor
- CTA
- particles / glow / scan lines / overlays

Preferred media:
- SVG / vector / HTML / Canvas / Remotion for UI, icons and motion graphics
- generated imagery for photographic/illustrative background assets
- FFmpeg for final compositing, audio mix and encoding

### Locked motion rules

- NO global zoom as a default scene animation.
- NO zoom/crop that removes image corners or important UI.
- Preserve full composition inside a safe frame.
- Animate individual layers instead: slide, fade, mask reveal, slight object scale, parallax, glow pulse, cursor motion, click ripple, chart drawing, dropdown/state transitions.
- If camera movement is used, it must be subtle and intentional, not a substitute for real layer animation.
- UI scenes should show state changes, not only static screenshots.

## 4. Safe composition

Default vertical output: 720x1280, 30fps unless reference/user requires otherwise.

- Keep key text/UI inside safe margins.
- Avoid placing important text in edge crop zones.
- Backgrounds may fill the canvas; information-bearing assets should not rely on crop.
- Validate every scene at first, middle and last frame.

## 5. Icon / glyph rule — ANTI-TOFU

Never rely on emoji or arbitrary Unicode symbols for production icons.

Forbidden as unverified UI icons:
- emoji
- dingbats
- symbols such as lightning/check/globe/arrows rendered only by text font unless preflight proves glyph support

Preferred:
- inline SVG paths
- generated vector icons
- geometric primitives drawn directly
- a known icon library converted to SVG

Required preflight:
1. inventory all icon glyphs and special characters
2. confirm the selected font contains every text glyph
3. render representative frames before final encode
4. visually detect missing-glyph boxes/tofu
5. replace any missing glyph with SVG/vector before success

No final video may pass QA with square-box icons.

## 6. Voice — canonical Vietnamese baseline

Preferred default male Vietnamese voice for this flow:
- `vi-VN-NamMinhNeural`

Generate voice scene-by-scene, not one forced monologue.

Baseline:
- rate around `-3%` to `0%` depending script density
- pitch around `-1Hz` to neutral
- leave ~0.2-0.45s breathing room inside each scene
- fit each scene individually with `atempo` only if required
- high-pass ~75Hz
- low-pass ~12.5kHz
- light compression
- normalize voice around -16 LUFS before final mix

Do not accept a technically valid TTS if cadence sounds rushed, robotic or incorrectly pronounces the brand. Rewrite the sentence or regenerate the scene.

## 7. Music — DSH acquisition

For ad videos with modern UI/tech visuals, default to a light ambient-tech / corporate-electronic instrumental unless the reference suggests another genre.

Use DSH audio flow to resolve/download a clean audio-only track.

Selection priorities:
- instrumental
- low speech/vocal content
- clean 1.5-6 minute source
- mood supports, never dominates, the voice

If the first source blocks the worker, DSH selects another technically available source. Do not let music acquisition block voice production.

Mix baseline:
- background music around 8-10% perceived level before ducking
- high-pass ~90Hz / low-pass ~10kHz if needed to reduce masking
- fade in ~1-1.5s
- fade out last ~2-3s
- sidechain-duck music under voice
- final mix target around -14 LUFS, true peak around -1.2dB

## 8. Audio/visual lock behavior

When visuals are already approved and the user asks only to improve voice/music:
- DO NOT rerender visuals
- replace/remix audio only
- remux with video stream copy (`-c:v copy`) when possible
- verify video stream hash/MD5 before vs after; hashes should match if visuals are locked

## 9. QA gates

### Visual QA
- no source-frame reuse in inspired mode
- no global zoom crop
- corners/key UI preserved
- each scene has layer/state motion where appropriate
- no broken font
- no square-box/tofu icons
- no clipped text
- readable hierarchy on mobile

### Audio QA
- natural Vietnamese cadence
- no rushed lines
- correct brand/domain pronunciation
- voice clearly louder than music
- music ducks during speech
- no clipping
- no abrupt music start/end

### Technical QA
- MP4/H.264 + AAC preferred
- correct duration/aspect/fps
- audio present
- no black frames or missing assets

Overall `success` requires all three QA groups to pass.

## 10. Known-good baseline from 2026-08-24 ProxyGrid build

The approved direction used:
- original generated/rebuilt visual assets, not source frames
- layered motion
- no full-frame zoom after correction
- independent UI/cards/cursor/CTA animation
- `vi-VN-NamMinhNeural` scene-timed narration
- rewritten 6-scene script
- DSH-downloaded light ambient-tech music
- subtle music + sidechain ducking
- final audio replacement while preserving approved video stream

Known defect to never repeat: Unicode/emoji-style icon rendered as a square box. All future builds must use vector/SVG icons or verified glyphs.

## 11. Delivery rule

When the user says they only need the result:
- do the full pipeline
- return the final MP4 first
- keep explanation minimal unless a QA issue remains

Do not claim completion until the final MP4 has passed visual, audio and technical QA.
