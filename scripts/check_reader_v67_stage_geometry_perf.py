from pathlib import Path

ROOT=Path('cloudflare/runner3-core')
V2=(ROOT/'artifact-library-reader-v2-entry.js').read_text(encoding='utf-8')
V36=(ROOT/'artifact-library-reader-v36-home-screen-safe-area-entry.js').read_text(encoding='utf-8')
AUDIO=(ROOT/'audio-entry.js').read_text(encoding='utf-8')
OUTER=(ROOT/'opportunity-router-entry.js').read_text(encoding='utf-8')

required=[
    '__r3StageGeometryV67',
    "owner:'stage-geometry-v67'",
    'postResizeDisplay:false',
    'postRenderGeometryWait:false',
    'dvhOwner:false',
    "html.r3-stage-boot-v67 #viewer iframe{opacity:0!important}",
    "document.documentElement.classList.add('r3-stage-boot-v67')",
    "document.documentElement.classList.remove('r3-stage-boot-v67')",
    "const r3StagePromiseV67=r3WaitPreRenderStageV67();",
    "const r3PreRenderStageV67=await r3StagePromiseV67;",
    "const r3BootGeometryV61=r3PreRenderStageV67||null;",
    "const R3_EPUB_CACHE_LIMIT=12;",
    'rel="preload" href="/artifact-library/vendor/jszip.min.js" as="script"',
    'rel="preload" href="/artifact-library/vendor/epub.min.js" as="script"',
    "'body > :first-child,body > :first-child > :first-child,body > :first-child > :first-child > :first-child':{'margin-top':'8px !important','padding-top':'0 !important'}",
]
for marker in required:
    if marker not in V2:
        raise SystemExit('READER_V67_MISSING:'+marker)

for forbidden in [
    'body{position:fixed;inset:0;width:100%;height:100dvh;background:var(--bg)}',
    'const r3BootGeometryV61=await r3NormalizeBootGeometryV61(r3BootAnchorV61);',
    'const r3BootGeometryV61=await r3WaitStableBootGeometryV61();',
    'const R3_EPUB_CACHE_LIMIT=4;',
]:
    if forbidden in V2:
        raise SystemExit('READER_V67_FORBIDDEN:'+forbidden)

for marker in [
    '/artifact-library/vendor/jszip.min.js',
    '/artifact-library/vendor/epub.min.js',
    'Cache-Control", "public, max-age=86400, stale-while-revalidate=604800"',
]:
    if marker not in V36:
        raise SystemExit('READER_V67_INNER_VENDOR_CACHE_MISSING:'+marker)

for marker in [
    'const READER_VENDOR_CACHE_V67 = new Set([',
    '"/artifact-library/vendor/jszip.min.js"',
    '"/artifact-library/vendor/epub.min.js"',
    'function maybeCacheReaderVendorV67(request, url, response)',
    'headers.set("Cache-Control", "public, max-age=86400, stale-while-revalidate=604800")',
    'headers.set("X-R3-Reader-Vendor-Cache", "v67")',
    'return maybeCacheReaderVendorV67(request, url, startupPatched);',
]:
    if marker not in AUDIO:
        raise SystemExit('READER_V67_OUTER_VENDOR_CACHE_MISSING:'+marker)

for marker in [
    'const READER_VENDOR_CACHE_V67_OUTERMOST = new Set([',
    'function applyReaderVendorCacheV67Outermost(request, url, response)',
    'headers.set("Cache-Control", "public, max-age=86400, stale-while-revalidate=604800")',
    'headers.set("X-R3-Reader-Vendor-Cache", "v67-outermost")',
    'return applyReaderVendorCacheV67Outermost(request, url, response);',
]:
    if marker not in OUTER:
        raise SystemExit('READER_V67_WRANGLER_VENDOR_CACHE_MISSING:'+marker)

print('READER_V67_STAGE_GEOMETRY_PERF_CHECK=PASS')
