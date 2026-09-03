from pathlib import Path
import re

ROOT = Path('cloudflare/runner3-core')
SIMPLE = ROOT / 'artifact-library-simple-entry.js'
text = SIMPLE.read_text(encoding='utf-8')

MARKER = '<meta name="r3-ios-home-screen-startup-policy" content="opaque-v39">'
CAPABLE = '<meta name="apple-mobile-web-app-capable" content="yes">'
MOBILE_CAPABLE = '<meta name="mobile-web-app-capable" content="yes">'
STATUS = '<meta name="apple-mobile-web-app-status-bar-style" content="black">'
VIEWPORT = '<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">'
HEADER = '"X-R3-Reader-IOS-Startup-Viewport": "opaque-v39"'

if MARKER not in text:
    if text.count(VIEWPORT) != 1:
        raise SystemExit(f'READER_V39_LIBRARY_VIEWPORT_COUNT_INVALID:{text.count(VIEWPORT)}')
    metas = '\n'.join([VIEWPORT, CAPABLE, MOBILE_CAPABLE, STATUS, MARKER])
    text = text.replace(VIEWPORT, metas, 1)

if HEADER not in text:
    block_re = re.compile(
        r'(if \(p === "/artifact-library"\) \{\s*'
        r'if \(request\.method !== "GET"\) return redirectHome\(\);\s*'
        r'return new Response\(libraryPage\(\), \{ status: 200, headers: headers\(\{)(.*?)(\}\) \}\);\s*\})',
        re.S,
    )
    match = block_re.search(text)
    if not match:
        raise SystemExit('READER_V39_LIBRARY_ROUTE_BLOCK_MISSING')
    middle = match.group(2)
    if '"Content-Type"' not in middle:
        raise SystemExit('READER_V39_LIBRARY_CONTENT_TYPE_MISSING')
    middle = f' {HEADER},' + middle
    text = text[:match.start()] + match.group(1) + middle + match.group(3) + text[match.end():]

for required in [VIEWPORT, CAPABLE, MOBILE_CAPABLE, STATUS, MARKER, HEADER]:
    if required not in text:
        raise SystemExit('READER_V39_LIBRARY_STARTUP_PATCH_MISSING:' + required)

# The real-device v38 fallback produced a double top inset and must never return.
for forbidden in ['r3-ios-standalone-forced-inset-v38', '--r3-ios-forced-top-v38']:
    if forbidden in text:
        raise SystemExit('READER_V39_LIBRARY_OLD_FORCED_INSET_PRESENT:' + forbidden)

SIMPLE.write_text(text, encoding='utf-8')
print('READER_V39_LIBRARY_STARTUP_PATCH=PASS')
