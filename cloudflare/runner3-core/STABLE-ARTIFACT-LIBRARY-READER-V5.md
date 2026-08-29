# Stable checkpoint — Artifact Library EPUB Reader v5

Status: **KNOWN GOOD / LIVE VERIFIED**

Checkpoint date: 2026-08-29

Canonical code commit: `733f0faca14397b43f1ea5d4892a3209f9ef8989`

Live proof:
- Workflow: `Runner3 Artifact Library Deploy`
- Run ID: `33264346089`
- Result: `SUCCESS`
- Worker: `https://runner3-core.ducduy2411.workers.dev`

## Canonical entrypoint

`cloudflare/runner3-core/artifact-library-reader-v5-entry.js`

Dependency chain:

`artifact-library-reader-v5-entry.js`
→ `artifact-library-reader-v4-entry.js`
→ `artifact-library-reader-v2-entry.js`
→ `artifact-library-simple-entry.js`
→ lower Runner3 Core wrappers

`wrangler.jsonc` points `main` to `artifact-library-reader-v5-entry.js`.

## File integrity at checkpoint

- `artifact-library-reader-v5-entry.js` blob SHA: `2c8c17c33693eaef4dc80d395ed7d4f37e3adc51`
- `artifact-library-reader-v4-entry.js` blob SHA: `5b6f9806adf81a240f2f5fcb6c67958a8dba7fe3`
- `artifact-library-reader-v2-entry.js` blob SHA: `de547ffaa4d8ef55e98fcd33c5063f3fd3184edc`
- `artifact-library-simple-entry.js` blob SHA: `baacaa2582408c8559eaca4e3bb437faab818c38`
- `wrangler.jsonc` blob SHA: `abacce3e939c82d61ad2fcef3174047e95cde718`
- `.github/workflows/runner3-artifact-library-deploy.yml` blob SHA at proof commit: `08a5f447df2ef715ea8aefa1cca446e7d33f00aa`

## Stable behavior to preserve

Library:
- no PIN/login prompt
- final EPUB only, canonical/latest per scope
- book title opens reader
- Download remains available
- search + compact refresh
- noindex/noarchive

Reader:
- full-screen reader viewport
- 3 real HTML hit zones for iPhone Safari reliability
- swipe mode and tap-left/right mode
- center tap toggles controls
- settings backdrop prevents tap-through
- controls/settings idle timeout: 6 seconds
- Light / Dark / Brown themes
- font-size control
- margin control
- line-height control
- settings persist in localStorage
- reading position persists per book
- live font/margin/line-height changes reflow pagination
- CFI is captured before reflow and restored after resize
- reader margin is implemented on the outer viewport, not EPUB XHTML padding

## Rollback rule

If a future reader change breaks layout, gesture handling, settings, or resume behavior, restore the tree at commit:

`733f0faca14397b43f1ea5d4892a3209f9ef8989`

Then redeploy `artifact-library-reader-v5-entry.js` using the canonical Wrangler config and rerun the artifact-library deploy verifier.

Do not overwrite or reinterpret this checkpoint as a newer version. Create a new stable checkpoint for future known-good releases.
