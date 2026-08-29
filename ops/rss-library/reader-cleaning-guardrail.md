# RSS Reader semantic cleaning guardrail

Status: active

Reader presentation and Nam Minh TTS must consume the same cleaned article body. Raw source artifacts remain unchanged.

Before `renderBlocks` and before RSS audio synthesis, remove page chrome and extraction noise conservatively:

- early breadcrumb/navigation labels such as `TRANG CHỦ`, `BÀI VIẾT`, `HOME`, `ARTICLE`, including when they are prefixed to a duplicated article title;
- duplicated article title near the top, including title text split across a few consecutive source lines;
- standalone font-size controls such as `A+`, `A-`, or `A+ A-`;
- duplicated bylines/authors in prose when they match author metadata, plus clear early multi-author rows such as `Name | Name | Name`;
- image caption/alt duplicates already represented by selected image metadata;
- orphan image captions or photo-credit rows such as `(Ảnh: …)`, `Photo: …`, `Photo by …` when they are extraction chrome rather than prose;
- existing ad/sponsor/newsletter/share/related/tracking boilerplate and known tail attribution rules.

Preserve:

- real headline/subheadline meaning in article metadata;
- actual lead/body paragraphs;
- selected essential images and their proper `figcaption`;
- author/source metadata even when duplicated body byline is removed.

Cleaning is a Reader/TTS presentation transform only. It must not destructively rewrite the canonical raw R2 source artifact.

Implementation:

- `cloudflare/runner3-core/src/rss-reader-clean.mjs`
- `cloudflare/runner3-core/reader-media-entry.js`
- regression workflow: `.github/workflows/rss-reader-clean-test.yml`

Current marker: `rss-reader-clean-v3`.
