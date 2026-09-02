from pathlib import Path

v2 = Path('cloudflare/runner3-core/artifact-library-reader-v2-entry.js').read_text(encoding='utf-8')
v5 = Path('cloudflare/runner3-core/artifact-library-reader-v5-entry.js').read_text(encoding='utf-8')
simple = Path('cloudflare/runner3-core/artifact-library-simple-entry.js').read_text(encoding='utf-8')

for marker in [
    "owner:'atomic-v58'",
    'r3WaitStableBootCfiV58',
    '__R3_READER_BOOT_QUIET_UNTIL_V58',
    "'r3-reader-last-open:'+key",
    'data-r3-sort="recent"',
    "r3LiveLibrarySortV58='recent'",
    'r3SortLiveRowsV58',
]:
    if marker not in v2:
        raise SystemExit('V58_V2_MISSING:' + marker)
for marker in [
    'Date.now()>=Number(window.__R3_READER_BOOT_QUIET_UNTIL_V58||0)',
    'Date.now()<Number(window.__R3_READER_BOOT_QUIET_UNTIL_V58||0)',
]:
    if marker not in v5:
        raise SystemExit('V58_V5_MISSING:' + marker)
for marker in [
    'data-sort="recent"', 'data-sort="new"', 'data-sort="az"',
    "sort:'recent'", 'lastOpenAtV58', 'uploadedAtV58',
    "state.sort==='new'", "state.sort==='az'",
]:
    if marker not in simple:
        raise SystemExit('V58_SIMPLE_MISSING:' + marker)
if "rendition.on('rendered',()=>{bindEpubContents();$('loading').classList.add('hidden');});" in v2:
    raise SystemExit('V58_INTERMEDIATE_RENDER_REVEAL_REMAINS')
if 'if(window.__R3_BASE_READER_BOOT_DONE&&anchor)r3ScheduleReflow(anchor);' in v5:
    raise SystemExit('V58_UNGATED_REFLOW_REMAINS')
print('READER_V58_ATOMIC_BOOT_LIBRARY_SORT_CHECK=PASS')
