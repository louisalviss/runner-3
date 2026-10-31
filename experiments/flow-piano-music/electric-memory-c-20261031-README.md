# Electric Memory C — Flow Piano Music isolated 30-second study

Status: **REVIEW PENDING**. User previously approved the original 8-second Hook C, **not** the full 30-second arrangement. Do not promote this experiment to the canonical v1.2 master or production.

## Composition provenance
- Input: user's existing `Electric_Memory_C_30s_Arrangement_Draft.json` (file in ChatGPT Library, not a fresh generated replacement).
- Original 0–7.5 s motif retained in note-level input; sections are **HOOK** (0–7.5), **ANSWER** (7.5–15), **HOOK RETURN** (15–22.5), **ENDING** (22.5–30).
- 128 BPM, 16 bars, 171 note events; no TikTok soundtrack, melody or video was copied.
- Chord sequence: C#m9 / Aadd9 / Eadd9-G# / Bsus4-B; F#m9 / Amaj9 / Eadd9-G# / Bsus4-B; repeat hook; F#m11 / Aadd9 / G#7sus4 / G#7.
- Render uses isolated copy of Flow Piano Music renderer; melody range 42–81 fits the extended pitch viewport.

## Reproduction
1. Retrieve **Electric_Memory_C_30s_render_manifest.json** from durable R2 (below).
2. Use the canonical v1.2 renderer script in this directory for a fresh 30s render with `--manifest ... --soundfont <licensed-salamander-SF2> --output-dir <scratch> --basename Electric_Memory_C_30s`.
3. Run `electric-memory-c-20261031-master.py --input-wav <scratch>/Electric_Memory_C_30s.wav --input-video <scratch>/Electric_Memory_C_30s.mp4 --output-dir <final scratch>`.
4. Do not overwrite any 2026-10-29 approved Flow Piano Music assets. Test source identity and playback before delivery.

## R2 retained artifacts (scope: `chord-progression/flow-piano-music-electric-memory-c-20261031`)
- `Electric_Memory_C_30s.mp4`: 1,655,237 bytes; SHA256 `08249af6511bd44172eb69f8786022a333c8e10393518a770842d169729147ae`.
- `Electric_Memory_C_30s.mp3`: 841,918 bytes; SHA256 `862de5d40166afd3bb01accece3970ee0cbab0b74ff43ec6e0b1662556d09789`.
- `Electric_Memory_C_30s.mid`: 1,637 bytes; SHA256 `f34818027a07382d582c4c44f5c03bccf100b72e06599c1a529cacaf1d969404`.
- `Electric_Memory_C_30s_render_manifest.json`: 32,048 bytes; SHA256 `79699f5d5fa20d51e4aff4fa74f18e3d4a4f774b50ebee78ef01fbc2e17ff563`.
- R2 also holds preview PNG and sample-library attribution.

QA on runner-vps1 (2026-10-31): 720x1280, 30fps, 900 frames, H.264/AAC, 30.000s; 44.1kHz stereo, no clipping; 4 timestamped frames inspected; post-master peak 0.77. Re-master script rerun reproduced final MP3 and MP4 **byte-identical**. R2 file GET/SHA/bytes and D1 checkpoint PASS. Signed links must be minted fresh at delivery.

Salamander Grand Piano instrument samples by Alexander Holm, licensed under CC BY 3.0; provide attribution when publishing. Do not commit/share the instrument sample file.

Acceptance: **technical QA PASS; musical quality/resemblance to @ultravioletchorus NOT YET APPROVED**. The new draft uses a different chord arrangement, not an exact TikTok recreation.
