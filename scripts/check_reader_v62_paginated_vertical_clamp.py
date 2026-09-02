from pathlib import Path

v2 = Path('cloudflare/runner3-core/artifact-library-reader-v2-entry.js').read_text(encoding='utf-8')
v5 = Path('cloudflare/runner3-core/artifact-library-reader-v5-entry.js').read_text(encoding='utf-8')
v34 = Path('cloudflare/runner3-core/artifact-library-reader-v34-continuous-range-sync-entry.js').read_text(encoding='utf-8')

required_v2 = [
    '__r3PaginatedVerticalClampV62',
    "owner:'paginated-vertical-clamp-v62'",
    'window.__r3ClampPaginatedVerticalV62=r3ClampPaginatedVerticalV62;',
    "r3ClampPaginatedVerticalV62('post-geometry')",
    "r3ClampPaginatedVerticalV62('post-geometry-raf')",
    "r3ClampPaginatedVerticalV62('pre-reveal')",
    "r3ClampPaginatedVerticalV62('visual-viewport')",
    'win.scrollTo(Number(win.scrollX||0),0)',
]
for marker in required_v2:
    if marker not in v2:
        raise SystemExit('READER_V62_V2_MISSING:' + marker)

if "$('loading').classList.add('hidden')" not in v2:
    raise SystemExit('READER_V62_ATOMIC_REVEAL_MISSING')
if "owner:'atomic-v58'" not in v2 or '__r3SafariBootGeometryV61' not in v2:
    raise SystemExit('READER_V62_BOOT_CHAIN_REGRESSION')
if "__r3ClampPaginatedVerticalV62('v5-reflow')" not in v5:
    raise SystemExit('READER_V62_V5_REFLOW_CLAMP_MISSING')

# Layout-only patch must preserve v60 audio behavior.
for marker in ['reader-audio-v60-prefetch', 'reader-audio-v60-warm-current']:
    if marker not in v34:
        raise SystemExit('READER_V62_AUDIO_V60_MISSING:' + marker)

print('READER_V62_PAGINATED_VERTICAL_CLAMP_CHECK=PASS')
