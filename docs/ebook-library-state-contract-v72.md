# Ebook Library State Contract v72

Status: canonical as of 2026-09-10.

## Goal

Safari browser, iPhone Home Screen web app, and future clients must converge on one server state even though WebKit isolates localStorage/IndexedDB between browser and installed Home Screen web apps.

## Canonical ownership

- EPUB binary: R2 `core/ebook/<scope>/final/*.epub`.
- Book metadata: R2 `core/ebook/_index/library-books.json` keyed by stable `<scope>`.
- Cover: R2 `core/ebook/<scope>/meta/cover.*` referenced by catalog.
- Sidecar: derived/rebuildable `core/ebook/<scope>/meta/book.json`; never the only source of metadata.
- Reading state: D1 `ebook_reader_state_v72`, primary key = stable `<scope>`.
- Reading-state backup: R2 `core/ebook/_system/progress-v72/latest.json` + daily snapshots.
- Catalog backup: R2 `core/ebook/_system/catalog-v72/latest.json` + daily/pre-enrich snapshots.
- Browser localStorage / IndexedDB / fast index: cache or recovery seed only; never canonical.

## Cross-client sync contract

Startup/Library foreground:

1. Authenticate Library session.
2. Fetch canonical book list from R2 catalog/index.
3. Fetch all D1 v72 reading states.
4. If D1 has a row for a scope, D1 wins and overwrites that client's local cache.
5. Local legacy state may seed D1 only when D1 has no row for that scope.
6. Never assign a new `Date.now()` to stale local state merely because a client opened/refreshed.
7. Re-render after hydration.

Reader startup:

1. Pull D1 state before initial `rendition.display()`.
2. If server state exists, server CFI/percent wins.
3. epub.js `relocated` events during boot/programmatic sync MUST NOT POST progress.
4. Only a real post-boot reading relocation writes a fresh event timestamp and pushes D1.
5. Returning to foreground/focus pulls D1; if another client has newer state, display that CFI without echo-writing it as a new event.

This guarantees Safari -> Home Screen and Home Screen -> Safari convergence without sharing localStorage.

## Metadata / thumbnail contract

Upload is not complete until:

`EPUB R2 put -> metadata extraction -> cover extraction -> catalog update -> sidecar update -> fast-index invalidation -> catalog snapshot -> readback`

Rules:

- Fast-index schema is versioned. A prior schema must be rejected and rebuilt, never silently down-cast fields.
- Fast-index must retain `title`, `creator`, and `cover_key`.
- Client list cache uses a generation-specific namespace; incompatible old cache is ignored.
- Enrich/rebuild is merge-preserve: existing non-empty canonical title/creator wins over weaker EPUB metadata.
- Existing valid cover is preserved. If missing, extractor tries EPUB cover markers, then first image in first spine document, then image fallback.
- `meta/book.json` is recreated on catalog self-heal.
- EPUB with genuinely no image records `cover_missing_reason=epub-no-image`; absence is explicit, not treated as silent data loss.

## Self-heal

`.github/workflows/reader-r2-catalog-enrich.yml` runs daily at 03:23 UTC and on relevant source/trigger changes.

The job is incremental:

- complete scopes are preserved without reparsing EPUB;
- incomplete/missing metadata is repaired from EPUB;
- missing sidecars are recreated;
- missing cover references are repaired when possible;
- catalog is backed up before rewrite.

## Deploy gates

A Reader production deploy must fail if any of these regress:

- rendered inline Library JS syntax;
- v72 stable scope progress contract;
- server-first boot behavior;
- boot/programmatic relocated write suppression;
- Safari/Home Screen foreground resync hook;
- fast-index schema + metadata field retention;
- cache-generation bump;
- catalog snapshot and enrich invalidation;
- preserve-mode catalog repair markers.

## Incident lessons: v70-v71

Do not repeat these patterns:

- do not infer that R2 books being present means Library UI JavaScript is healthy;
- do not serialize a rich row into a reduced cache row and assume metadata survives;
- do not use localStorage as cross-client persistence on iOS;
- do not rebuild catalog destructively from EPUB metadata;
- do not make upload success independent from metadata/cover publication;
- do not re-stamp stale state on page boot.

## Evidence order

1. Physical iPhone Safari + Home Screen switch test.
2. Live production API readback (normal fast-index and forced rebuild must agree).
3. D1/R2 state readback.
4. Browser/runtime smoke.
5. Source markers only.
