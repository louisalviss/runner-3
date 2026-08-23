# Video Flow Router — CANONICAL

Use this router before any video-reference task.

## Default intent

If the user sends a video/link and asks to make something `similar`, `like this`, `theo kiểu này`, `lấy ý tưởng`, or `làm quảng cáo tương tự`:

=> use `FLOWS/video-reference-inspired-ad-v1.md`.

Meaning:
- analyze full reference
- extract idea/structure/grammar
- write new script
- create new assets
- new voice
- new text
- new brand/UI/composition details
- do not reuse source frames

This is the DEFAULT behavior.

## Copy/remake intent

Only use `FLOWS/video-recreate-reference-v1.md` when the user explicitly says one of:
- copy
- remake
- recreate closely
- recreate sát
- 1:1
- pixel-close / frame-close
- tái tạo gần như bản gốc

If the user did not explicitly request copying, do not infer it.

## Approved production defaults

For inspired ads, inherit all locked defaults from `video-reference-inspired-ad-v1.md`, especially:
- asset/layer-based motion
- no global zoom/crop
- safe composition
- vector/SVG icons; no unverified emoji/Unicode icons
- NamMinh Neural Vietnamese voice baseline
- DSH light background music + ducking
- audio-only remux when visual is already approved
- visual + audio + technical QA before success
