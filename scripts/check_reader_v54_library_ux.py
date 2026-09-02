from pathlib import Path

simple = Path('cloudflare/runner3-core/artifact-library-simple-entry.js').read_text(encoding='utf-8')
reader = Path('cloudflare/runner3-core/artifact-library-reader-v2-entry.js').read_text(encoding='utf-8')

simple_markers = [
    'data-filter="reading"',
    'data-filter="unread"',
    'data-filter="done"',
    "cover.className='cover'",
    "progressLine.className='progress-line'",
    'r3-reader-progress-v1:',
    'r3-library-book-meta-v54',
    "Carl's Doomsday Scenario",
    "The Dungeon Anarchist's Cookbook",
    'The Gate of the Feral Gods',
    "The Butcher's Masquerade",
    'The Eye of the Bedlam Bride',
    'This Inevitable Ruin',
    'A Parade of Horribles',
    'id="uploadEpub"',
    'async function publicUpload(request, env)',
    'p === "/artifact-library/api/upload"',
]
reader_markers = [
    'R3_READER_PROGRESS_PREFIX_V54',
    'r3-reader-progress-v1:',
    'r3-library-book-meta-v54',
    'r3PersistBookMetaV54(book,key)',
    "cover.className='r3-live-cover'",
    "progressLine.className='r3-live-progress-line'",
    'r3TitleForBookV54',
    'data-r3-audio-continuity-v35',
]
for marker in simple_markers:
    if marker not in simple:
        raise SystemExit('V54_SIMPLE_MISSING:' + marker)
for marker in reader_markers:
    if marker not in reader:
        raise SystemExit('V54_READER_MISSING:' + marker)

stale_titles = [
    'Cánh cổng của các Dã thần',
    'Cẩm nang Kẻ Vô chính phủ Hầm ngục',
    'Con mắt của Cô dâu Loạn trí',
    'Cuộc Diễu hành Kinh hoàng',
]
for title in stale_titles:
    if title in simple:
        raise SystemExit('V54_STALE_TITLE:' + title)

if "r3TitleFor=b=>r3Humanize" in reader:
    raise SystemExit('V54_LIVE_SCOPE_TITLE_FALLBACK_REMAINS')
if 'async function publicUpload(request, env)' not in simple:
    raise SystemExit('V54_UPLOAD_ROUTE_REGRESSED')
if "localStorage.setItem(R3_READER_PROGRESS_PREFIX_V54+key" not in reader:
    raise SystemExit('V54_PROGRESS_WRITE_MISSING')

print('READER_V54_LIBRARY_UX_CHECK=PASS')
