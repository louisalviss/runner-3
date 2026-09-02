from pathlib import Path

simple = Path('cloudflare/runner3-core/artifact-library-simple-entry.js').read_text(encoding='utf-8')
v35 = Path('cloudflare/runner3-core/artifact-library-reader-v35-continuity-single-owner-entry.js').read_text(encoding='utf-8')

markers = [
    'data-r3-library-v56="1"',
    '/artifact-library/vendor/jszip.min.js',
    '/artifact-library/vendor/epub.min.js',
    "const EPUB_CACHE_DB_V56='r3-reader-epub-cache-v49'",
    'async function migrateLegacyProgressV56()',
    'async function migrateLegacyBookV56(bookRow)',
    'epub.locations.generate(1600)',
    'epub.locations.percentageFromCfi(cfi)',
    "migratedBy:'library-v56'",
    'async function extractUploadMetadataV56(file)',
    'window.JSZip.loadAsync(file)',
    "form.append('cover',meta.cover,coverFilenameV56(meta.cover))",
    'async function publicEnrichUpload(request, env)',
    "ROOT+scope+'/meta/book.json'",
    'LIBRARY_CATALOG_INDEX_KEY',
    'p === "/artifact-library/api/enrich-upload"',
    'setTimeout(()=>migrateLegacyProgressV56(),700)',
]
for marker in markers:
    if marker not in simple:
        raise SystemExit('V56_SIMPLE_MISSING:' + marker)

# Upload stays streamed to R2; only the small extracted cover/metadata enrichment is buffered by formData.
if "env.ARTIFACTS.put(key, request.body" not in simple:
    raise SystemExit('V56_UPLOAD_STREAM_REGRESSION')
if "await request.arrayBuffer()" in simple:
    raise SystemExit('V56_FULL_EPUB_BUFFERED_IN_WORKER')

# Existing accepted Reader audio ownership must stay intact.
for marker in ['data-r3-audio-continuity-v35', 'singleAudioListenerOwner:true']:
    if marker not in v35:
        raise SystemExit('V56_V35_REGRESSION:' + marker)

print('READER_V56_AUTO_ENRICH_PROGRESS_MIGRATION_CHECK=PASS')
