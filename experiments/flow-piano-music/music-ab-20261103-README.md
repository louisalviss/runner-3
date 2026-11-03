# Music learning: blind listening gate (2026-11-03)

**Status: code smoke-tested; original music generation and human listening acceptance NOT completed.**
This is a research-only addition to the existing `Flow Piano Music v1.2`. It does **not** replace, deploy, or modify the accepted Concert A+ production renderer.

## Point-in-time evidence

| Example | User feedback | Correct interpretation |
| --- | --- | --- |
| Electric Memory Hook C, original 8-second audition (2026-10-29) | "ổn" | Positive example **only for the 8-second hook** |
| AFTERGLOW original 30 seconds | "Dở" | Negative example |
| SECOND LIGHT original 30 seconds | "Dở" | Negative example |
| Electric Memory C 30-second continuation, PR #513 | No final user feedback | Unknown, not a positive sample |
| Source-reconstructed Concert A+ piano-roll | Accepted for audio/performance | Production reference; not proof of autonomous composing skill |

Evidence authority: Dropbox `/Apps/remotely-save/AI/01_Canonical/Creative/Lousias Music/Chord Composition Research and QA.md` and `/Apps/remotely-save/AI/AI-MEMORY/FLOWS/Flow Piano Music.md`. R2 project `chord-progression` retains original binaries; signed access links expire. These examples are too few and too confounded by unequal durations to train a meaningful preference model.

## Findings from ACE-Step 1.5 public trial

- Official ACE-Step 1.5 model is MIT-licensed; supports text-to-music and reference audio. It generates **audio, not reliable editable MIDI**.
- `runner-vps1` currently reports 8 CPUs, about 16 GB physical RAM, no NVIDIA GPU. Do not install full inference into production without a resource plan.
- The public ZeroGPU Gradio demo accepted one bounded 15-second solo-piano generation request (HTTP 200), but returned only heartbeat events during a 100-second listen. A subsequent request for the event returned 404. **No audio was obtained or quality-judged.**
- Do not repeat remote generation jobs indefinitely or send private reference recordings to public demos. Test with original text prompts first. Prefer isolated GPU if later authorized/available.

## Standalone blind listening script

Requires Python 3.11+ and installed FFmpeg/FFprobe. The script only reads local candidate audio and emits 8-second comparison MP3s, plus the sealed identity map. No network or model call.

Example input manifest:

```json
{
  "candidates": [
    {"id": "candidate_01", "path": "/private/path/new-original-1.wav", "rights": "original", "origin": "original_gen"},
    {"id": "candidate_02", "path": "/private/path/new-original-2.wav", "rights": "original", "origin": "original_gen"}
  ]
}
```

Run:

```sh
python3 experiments/flow-piano-music/music-blind-listening-gate-20261103.py prepare --manifest /private/manifest.json --output /private/music-ab-20261103 --seed 20261103 --max-pairs 8
```

Listen to `pair-01-A.mp3` / `pair-01-B.mp3` without opening `sealed-map.json`. Populate `choice` in `blind-ratings.json` for each pair: `A`, `B` or `tie`. After receiving actual feedback, reveal scores:

```sh
python3 experiments/flow-piano-music/music-blind-listening-gate-20261103.py reveal --sealed /private/music-ab-20261103/sealed-map.json --ratings /private/ratings.json
```

A/B files are approximately LUFS-normalized using a single-pass filter; playback loudness should still be manually matched. When comparing new compositions, keep the same length, style, and timbre wherever possible. Scoring counts a user choice; it cannot prove commercial music quality.

## Verification and next gate

Verified on `runner-vps1` with two *synthetic sine-wave* audio clips: pair preparation PASS; two MP3s distinct; sealed labels hidden from ratings template; a recorded choice correctly counted one win and one loss. Synthetic QA is **not** an artistic listening test.

**Next gate:** obtain actual generated piano audio from an accessible, approved music model without impacting VPS production; archive binary only through private R2 with hash/byte readback and D1 checkpoint; then make 8-second A/B clips, ask user to rate; stop if nothing is compelling. Do not call any study "learned" until it predicts new unseen user choices more accurately than chance.

## Automated regression evidence (2026-11-03)

Three executable tests on runner-vps1 PASS (2.186 seconds): rejects one candidate; rejects unknown rights; prepares a real A/B pair from synthetic test WAVs, hides candidate labels, counts the winner, rejects duplicate ratings, and forbids reusing a nonempty output directory. This validates test mechanics only, not composition quality.

<!-- TEXT2MIDI_CPU_CANARY_20261104 -->
## 2026-11-04 — First real Text2MIDI CPU trial: STRUCTURAL FAIL

- Upstream GitHub commit pinned: `AMAAI-Lab/Text2midi@f3245ee402b29ba00b86c6eb9813032f3f05954f`. HF model revision `9bc91479c4a9b08a9a28a7dcfb3f1a56ee2ded36`.
- Pinned official weight SHA256 `d94e8d7dda9207ed734268933629d4a4b7a1a6ce84c77299f610d3470448bfc1` (901867614 bytes); REMI vocabulary SHA256 `877d4511d6b9d5eea1c706199fe13a0de3d984c8f5d09c75d727ffe7f6f54ee6` (27256 bytes). Both source-verified.
- Isolated Python CPU environment staged only under `/tmp/music-midi-direct-20261104` on `runner-vps1` (NOT production Python). 2 inference threads, 180 output tokens, seed `20261104`, temperature `0.9`. Inference 66.36 seconds; no resource guard triggered.
- Generated standard MIDI `text2midi-original-candidate.mid`: **430 bytes**, SHA256 `5f88f5eed3219dd8f099fd6ff8b928489b96b453eced94e45878efc5edec83aa`. It is **NOT a successful 8-second solo-piano composition**.
- Independent `symusic` inspection: duration **1.773 seconds** at 121.29 BPM; 4 piano notes, 35 drum notes and 2 unrelated instrument notes (pan flute and steel guitar), across 4 populated tracks. Output fails all four explicit structural checks. Do not render/publish or ask for a subjective audition of this sample.
- Fixed the *research-only* source script to require and record an explicit structural MIDI gate (duration, >=12 piano notes, no drums/non-piano). Added 5 automated synthetic MIDI tests; **5/5 PASS** on `runner-vps1`. Structural PASS alone never establishes musical quality.
- Existing multi-account GitHub-hosted pool registry lists **no music/MIDI inference flow**, so do NOT mislabel a job under a different allowlisted flow. The single CPU canary ran on VPS with bounded threads/time/memory guard. Afterward VPS swap was ~7.7/8 GiB used; no further heavy inference was launched.
- **No R2 artifact/D1 success checkpoint:** rejected experimental MIDI was not promoted, delivered, or published. Existing Concert A+ masters and Flow Piano Music v1.2 remain unchanged. PR #517 remains DRAFT/NOT MERGED.
- Next research gate: use permitted isolated compute if available, prove 8-second solo-piano MIDI with structural QA, then render/verify R2 + D1 and obtain user listening feedback. One truncated 180-token trial does not establish that every Text2MIDI output fails.


<!-- MIDI_V5_SEED_INFILL_STUDY_20261104_BEGIN -->
## 2026-11-04 — Seeded MIDI Gen AI v5 continuation: NEAR_COPY_REJECT

- New model candidate: `nicholasbien/midigenai`, source commit `17c7fb775789089dc848eb13b5fd477657f024ab`, MIT code/model. HF model revision `bc6386444b0f8038763b4b79e3c6d46da0c98f8b`, v5 checkpoint SHA256 `05026cd7a721a5ef50059d48e687bd77b1c5fb25429d7fed09d1bc628e6aaa74` (454939391 bytes), tokenizer SHA256 `2cb58beac8be709a12967383503d6de9078730e179ba3edccdf82b46a106df18`.
- Input: original user-accepted Electric Memory C 8-second hook reconstructed from the user's own `three-original-hooks-20261029.py` source, Git blob `35c5aef21cddecdf1abd442fcf8c2d1ed18a1749`. Generated a verified 47-note solo-piano MIDI seed at 128 BPM, SHA256 `32fccd81dcb6a0b576f153cfdf46e409cec1856178881bf8e7df5bfda50ec6ee` (377 bytes). This is a reproducible derivative of the confirmed original note event source, not an arbitrary substitute.
- Source-only safety change in isolated scratch: changed upstream's `torch.load(weights_only=False)` to `weights_only=True`; checkpoint state loaded successfully. No production source modified.
- First v5 `generate_to_midi` trial (2 CPU threads, float32, max 760 tokens, seed 20261104) completed in ~10.51 seconds model generation, 183 new tokens, full 714-byte MIDI with 94 notes across 14.77 seconds; 45 solo-piano notes start at/after 7.5 seconds.
- Real comparison to original C via note pitch/onset/duration tolerance found **43/45 matches = 95.56%**. Verdict: **NEAR_COPY_REJECT**. It repeats the hook, not a substantively new musical idea. No audio publication or user A/B.
- Tried v5 **infill** to replace original bars 2–3 while preserving first/last bar, using upstream `infill_span.run`. Watchdog stopped the child after 3 seconds when swap free fell below 230 MB (host reported 8190/8191 MB swap in use). No generated infill candidate. Did NOT relax memory/swap limits or touch production services.
- Strengthened isolated PR #517 MIDI QA: approved 8-second C MIDI note release ends at ~7.293 seconds, so duration gate now accepts 7.0–8.3 seconds of note material (8s audio includes release tail). Added near-copy rejection calibrated on corresponding windows (default 85% threshold). **8/8 synthetic regression tests PASS**; live v5 output independently returns `NEAR_COPY_REJECT` with 0.9556 ratio.
- No final R2 deliverable or D1 success checkpoint for either rejected or unfinished sample. Preserve Concert A+ / Flow Piano Music v1.2 untouched. NEXT: safe isolated compute capacity for v5 middle-bar infill; only publish a genuinely novel piano-only 8-second MIDI/audio after structural QA, private R2 SHA/size readback, D1 checkpoint and human listening approval.
<!-- MIDI_V5_SEED_INFILL_STUDY_20261104_END -->
