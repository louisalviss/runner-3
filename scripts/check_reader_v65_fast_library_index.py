from pathlib import Path

# Derived Library index is only a cache; canonical R2 EPUBs remain source of truth.
text=Path('cloudflare/runner3-core/artifact-library-simple-entry.js').read_text(encoding='utf-8')
required=[
  'R3_LIBRARY_FAST_INDEX_KEY_V65',
  'R3_LIBRARY_FAST_INDEX_MAX_AGE_MS_V65',
  'async function r3ReadLibraryFastIndexV65',
  'async function r3WriteLibraryFastIndexV65',
  'async function r3InvalidateLibraryFastIndexV65',
  'async function r3LibraryObjectsFastV65',
  "url.searchParams.get('refresh')==='1'",
  "source:result.source",
  "r3InvalidateLibraryFastIndexV65(env,'upload')",
  "r3InvalidateLibraryFastIndexV65(env,'rename')",
  "r3InvalidateLibraryFastIndexV65(env,'delete')",
  'R3_LIBRARY_FAST_CLIENT_CACHE_V65',
  'r3ReadLibraryClientCacheV65()',
  'r3WriteLibraryClientCacheV65(state.books)',
  "r3HydrateServerProgressV65().then(changed=>{if(changed)render()})",
  "$('refresh').addEventListener('click',()=>load(true));",
]
for marker in required:
    if marker not in text: raise SystemExit('READER_V65_FAST_LIBRARY_INDEX_MISSING:'+marker)
if "await r3HydrateServerProgressV65();status('');render()" in text:
    raise SystemExit('READER_V65_FAST_LIBRARY_PROGRESS_STILL_BLOCKING_FIRST_RENDER')
if 'canonicalFinalBooks(env)' not in text:
    raise SystemExit('READER_V65_FAST_LIBRARY_R2_FALLBACK_MISSING')
print('READER_V65_FAST_LIBRARY_INDEX_CHECK=PASS')
