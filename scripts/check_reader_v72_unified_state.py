from pathlib import Path
s=Path('cloudflare/runner3-core/artifact-library-simple-entry.js').read_text(encoding='utf-8')
r=Path('cloudflare/runner3-core/artifact-library-reader-v2-entry.js').read_text(encoding='utf-8')
for m in ["R3_UNIFIED_STATE_V72='v72'","ebook_reader_state_v72","scope TEXT PRIMARY KEY","canonical:'d1-scope'","R3_LIBRARY_FAST_INDEX_SCHEMA_V72 = 2","r3SnapshotCatalogV72","r3-library-fast-list-v72","spine-first-image-v72","await r3InvalidateLibraryFastIndexV65(env,'enrich')","r3SyncVisibleV72"]: assert m in s,m
for m in ["R3_READER_UNIFIED_STATE_V72='v72'","window.__R3_BASE_READER_BOOT_DONE!==true","r3ProgrammaticSyncV72","r3SyncReaderVisibleV72","source_client:R3_READER_CLIENT_KIND_V72"]: assert m in r,m
# Anti-regression: boot merge must no longer Date.now()-stamp and repost an existing remote state.
assert "const remote=await r3FetchRemoteProgressV65(key);if(remote){r3ApplyRemoteProgressV65(key,remote,true)" in r
assert "const now=Date.now(),updatedAt=Math.max(now" not in r

e=Path('scripts/enrich_reader_r2_catalog.py').read_text(encoding='utf-8')
w=Path('.github/workflows/reader-r2-catalog-enrich.yml').read_text(encoding='utf-8')
for m in ['read_existing_catalog','merge_entry','first_image_from_spine','object_exists','metadata-preserve-v72','cover_missing_reason','core/ebook/_system/catalog-v72/latest.json']: assert m in e,m
assert "cron: '23 3 * * *'" in w


assert s.count('async function publicEnrichUpload(') == 1, 'enrich handler count'
assert s.count('p === "/artifact-library/api/enrich-upload"') == 1, 'enrich route count'
v65=Path('scripts/patch_reader_v65_fast_library_index.py').read_text(encoding='utf-8')
assert 'V65_PRESERVE_INTERMEDIATE_HANDLERS = True' in v65
assert "if 'publicEnrichUpload' not in intermediate" in v65

print('READER_V72_UNIFIED_STATE_CHECK=PASS')
