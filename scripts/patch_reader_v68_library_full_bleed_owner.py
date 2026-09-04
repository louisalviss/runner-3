from pathlib import Path

SIMPLE = Path('cloudflare/runner3-core/artifact-library-simple-entry.js')
text = SIMPLE.read_text(encoding='utf-8')

OLD_STATUS = '<meta name="apple-mobile-web-app-status-bar-style" content="black">'
NEW_STATUS = '<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">'
OLD_MARKER = '<meta name="r3-ios-home-screen-startup-policy" content="opaque-v39">'
NEW_MARKER = '<meta name="r3-ios-home-screen-startup-policy" content="full-bleed-v68">'
OLD_HEADER = '"X-R3-Reader-IOS-Startup-Viewport": "opaque-v39"'
NEW_HEADER = '"X-R3-Reader-IOS-Startup-Viewport": "full-bleed-v68"'
SAFE_STYLE = '<style data-r3-library-full-bleed-v68="1">body{padding-top:env(safe-area-inset-top)!important;padding-bottom:env(safe-area-inset-bottom)!important}</style>'

if NEW_MARKER in text and NEW_HEADER in text and SAFE_STYLE in text:
    print('READER_V68_LIBRARY_FULL_BLEED_OWNER=ALREADY_APPLIED')
    raise SystemExit(0)

for old, new, label in [
    (OLD_STATUS, NEW_STATUS, 'STATUS'),
    (OLD_MARKER, NEW_MARKER, 'MARKER'),
    (OLD_HEADER, NEW_HEADER, 'HEADER'),
]:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f'READER_V68_LIBRARY_{label}_COUNT_INVALID:{count}')
    text = text.replace(old, new, 1)

if SAFE_STYLE not in text:
    if text.count(NEW_MARKER) != 1:
        raise SystemExit('READER_V68_LIBRARY_NEW_MARKER_COUNT_INVALID')
    text = text.replace(NEW_MARKER, NEW_MARKER + '\n' + SAFE_STYLE, 1)

for required in [NEW_STATUS, NEW_MARKER, NEW_HEADER, SAFE_STYLE]:
    if required not in text:
        raise SystemExit('READER_V68_LIBRARY_OWNER_MISSING:' + required)
for forbidden in [OLD_STATUS, OLD_MARKER, OLD_HEADER, 'r3-ios-standalone-forced-inset-v38', '--r3-ios-forced-top-v38']:
    if forbidden in text:
        raise SystemExit('READER_V68_LIBRARY_OWNER_FORBIDDEN:' + forbidden)

SIMPLE.write_text(text, encoding='utf-8')
print('READER_V68_LIBRARY_FULL_BLEED_OWNER=PASS')
