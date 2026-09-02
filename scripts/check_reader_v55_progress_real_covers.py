from pathlib import Path

simple = Path('cloudflare/runner3-core/artifact-library-simple-entry.js').read_text(encoding='utf-8')
reader = Path('cloudflare/runner3-core/artifact-library-reader-v2-entry.js').read_text(encoding='utf-8')

for marker in [
    'LIBRARY_CATALOG_INDEX_KEY',
    'async function libraryCatalogIndex(env)',
    'async function publicCover(request, env)',
    'p === "/artifact-library/api/cover"',
    "img.src='/artifact-library/api/cover?key='",
    "raw===null||raw===undefined||raw===''",
    'id="uploadEpub"',
    'async function publicUpload(request, env)',
]:
    if marker not in simple:
        raise SystemExit('V55_SIMPLE_MISSING:' + marker)

for marker in [
    'async function r3EnsureLocationsV55()',
    'book.locations.generate(1600)',
    'book.locations.percentageFromCfi(cfi)',
    'function r3WriteProgressV55(percent,cfi)',
    'setTimeout(()=>r3EnsureLocationsV55(),900)',
    "raw===null||raw===undefined||raw===''",
    "row&&row.cover_key",
]:
    if marker not in reader:
        raise SystemExit('V55_READER_MISSING:' + marker)

# The old v54 conversion of null -> Number(null) -> 0 must be gone in both UIs.
if "const n=Number(row&&row.percent);" in simple:
    raise SystemExit('V55_SIMPLE_NULL_TO_ZERO_REMAINS')
if "const n=Number(row&&row.percent);" in reader:
    raise SystemExit('V55_READER_NULL_TO_ZERO_REMAINS')

# Existing accepted Reader owners remain in the composed source tree.
v35 = Path('cloudflare/runner3-core/artifact-library-reader-v35-continuity-single-owner-entry.js').read_text(encoding='utf-8')
for marker in ['data-r3-audio-continuity-v35', 'singleAudioListenerOwner:true']:
    if marker not in v35:
        raise SystemExit('V55_V35_REGRESSION:' + marker)

print('READER_V55_PROGRESS_REAL_COVERS_CHECK=PASS')
