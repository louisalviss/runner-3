from pathlib import Path

ROOT=Path('cloudflare/runner3-core')
simple=(ROOT/'artifact-library-simple-entry.js').read_text(encoding='utf-8')
v2=(ROOT/'artifact-library-reader-v2-entry.js').read_text(encoding='utf-8')

checks={
  'main funnel button':'id="viewMenuButton"' in simple,
  'main persisted key':"VIEW_PREF_KEY_V59='r3-library-view-pref-v59'" in simple,
  'main status choices':'data-filter-choice="reading"' in simple and 'data-filter-choice="done"' in simple,
  'main sort choices':'data-sort-choice="recent"' in simple and 'data-sort-choice="new"' in simple and 'data-sort-choice="az"' in simple,
  'main save preference':'saveViewPrefV59()' in simple,
  'main old sort row removed':'class="sort-row"' not in simple,
  'main old filter chips removed':'class="filter active" data-filter=' not in simple,
  'live funnel button':'id="r3LiveViewButton"' in v2,
  'live same persisted key':"r3LiveViewPrefKeyV59='r3-library-view-pref-v59'" in v2,
  'live status choices':'data-r3-filter-choice="reading"' in v2 and 'data-r3-filter-choice="done"' in v2,
  'live sort choices':'data-r3-sort-choice="recent"' in v2 and 'data-r3-sort-choice="new"' in v2 and 'data-r3-sort-choice="az"' in v2,
  'live state filter':"r3LiveLibraryFilterV59==='reading'" in v2 and "r3LiveLibraryFilterV59==='unread'" in v2,
  'live old sort row removed':'class="r3-live-sort-row"' not in v2,
}
failed=[name for name,ok in checks.items() if not ok]
if failed:
    raise SystemExit('READER_V59_CHECK_FAILED: '+', '.join(failed))
print('READER_V59_COMPACT_LIBRARY_FILTER_CHECK=PASS')
