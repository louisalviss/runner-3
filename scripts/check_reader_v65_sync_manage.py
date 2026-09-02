from pathlib import Path

ROOT=Path('cloudflare/runner3-core')
simple=(ROOT/'artifact-library-simple-entry.js').read_text(encoding='utf-8')
router=(ROOT/'opportunity-router-entry.js').read_text(encoding='utf-8')
v2=(ROOT/'artifact-library-reader-v2-entry.js').read_text(encoding='utf-8')
v34=(ROOT/'artifact-library-reader-v34-continuous-range-sync-entry.js').read_text(encoding='utf-8')
v35=(ROOT/'artifact-library-reader-v35-continuity-single-owner-entry.js').read_text(encoding='utf-8')

for marker in [
    "reader_client_version:'v65'",
    "'x-r3-reader-client-version':'v65'",
    'ebook_reader_progress_v65',
    'async function publicProgressV65',
    'async function publicManageBookV65',
    'EPUB_RENAME_COLLISION',
    'readCatalogDocumentV56',
    'r3WriteCatalogV65',
    'r3InstallMainManageV65',
    'await r3HydrateServerProgressV65()',
    'p === "/artifact-library/api/progress"',
    'p === "/artifact-library/api/manage"',
]:
    if marker not in simple: raise SystemExit('READER_V65_SIMPLE_MISSING:'+marker)

for marker in [
    '"/artifact-library/api/progress"',
    '"/artifact-library/api/manage"',
    'r3IsLibraryFastPathV57',
    'r3LoadLibraryFastAppV57',
]:
    if marker not in router: raise SystemExit('READER_V65_ROUTER_MISSING:'+marker)

for marker in [
    "R3_READER_CLIENT_VERSION_V63='v65'",
    'r3FetchRemoteProgressV65',
    'r3MergeRemoteProgressV65',
    'r3ScheduleProgressSyncV65',
    'await r3MergeRemoteProgressV65();',
    'await r3HydrateLiveProgressV65();',
    'r3InstallLiveManageV65',
    'r3ReaderManageBookV65',
    'function r3StructuralPercentV64',
    '__r3SafariBootGeometryV61',
    '__r3PaginatedVerticalClampV62',
    "owner:'atomic-v58'",
]:
    if marker not in v2: raise SystemExit('READER_V65_V2_MISSING:'+marker)

for marker in ['reader-audio-v60-prefetch','reader-audio-v60-warm-current']:
    if marker not in v34: raise SystemExit('READER_V65_AUDIO_V60_MISSING:'+marker)
for marker in ['singleAudioListenerOwner:true','v34+v35:ahead-prefetch+range-follow+single-audio-owner']:
    if marker not in v35: raise SystemExit('READER_V65_AUDIO_OWNER_MISSING:'+marker)
for marker in ['function r3StructuralPercentV64','repairCurrentProgressV64','R3_PROGRESS_REPAIR_V64']:
    if marker not in v2: raise SystemExit('READER_V65_V64_PROGRESS_REGRESSION:'+marker)

print('READER_V65_SYNC_MANAGE_CHECK=PASS')
